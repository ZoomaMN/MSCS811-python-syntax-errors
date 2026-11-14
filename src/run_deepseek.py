# -*- coding: utf-8 -*-
"""
run_deepseek.py — call the DeepSeek chat-completions API for the rendered prompts.

Frozen configuration:

    provider            DeepSeek official API
    requested model     deepseek-flash
    thinking            disabled
    temperature         0
    tools / web         none
    output format       the frozen TEXT template, not JSON
    runs per snippet    1

Retry policy, frozen before the first real call:

    network error / timeout / 429 / 5xx      -> retry allowed
    HTTP 200 with EMPTY content              -> terminal model-output FAILURE, no retry
    HTTP 200 with malformed template         -> terminal failure, no retry
    HTTP 200 with usable content             -> recorded as ok

A call whose status is terminal is never re-issued, including on resume. Only transport
failures are retried, in-run and across runs.

Every record stores: raw prompt, raw response, requested model, returned model,
system_fingerprint when present, timestamps, token usage, finish_reason, latency, and the
parsing status from output_parser.

Usage
-----
    python src/run_deepseek.py --set eval --out data --limit 2   # smoke test
    python src/run_deepseek.py --set eval --out data             # 600 calls
"""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from output_parser import parse_output  # noqa: E402

DEFAULT_BASE = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-flash"

# statuses that are final for a call; such a call_id is never re-issued
TERMINAL = ("ok", "empty_content", "malformed")


def now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def build_payload(prompt, model, temperature, thinking_mode, max_tokens):
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
        "stream": False,
    }
    if thinking_mode == "thinking-object":
        payload["thinking"] = {"type": "disabled"}
    elif thinking_mode == "reasoning-effort":
        payload["reasoning_effort"] = "none"
    if max_tokens:
        payload["max_tokens"] = max_tokens
    return payload


def call_api(url, key, payload, timeout):
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=body, method="POST",
        headers={"Content-Type": "application/json",
                 "Authorization": "Bearer %s" % key})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8", "replace")
    return raw, time.time() - t0


def invoke(url, key, payload, timeout, retries, verbose=True):
    """
    One call with transport retries only. Returns a dict; `transport_error` is set when
    every attempt failed, which is the ONLY case that may be retried later.
    """
    last = None
    for attempt in range(1, retries + 1):
        try:
            raw, latency = call_api(url, key, payload, timeout)
            data = json.loads(raw)
            choice = (data.get("choices") or [{}])[0]
            message = choice.get("message") or {}
            content = message.get("content") or ""
            usage = data.get("usage") or {}
            return {
                "transport_error": None,
                "raw_response": raw,
                "content": content,
                "returned_model": data.get("model"),
                "system_fingerprint": data.get("system_fingerprint"),
                "finish_reason": choice.get("finish_reason"),
                "prompt_tokens": usage.get("prompt_tokens"),
                "completion_tokens": usage.get("completion_tokens"),
                "total_tokens": usage.get("total_tokens"),
                "latency_s": round(latency, 3),
                "attempts": attempt,
            }
        except urllib.error.HTTPError as e:
            detail = ""
            try:
                detail = e.read().decode("utf-8", "replace")[:600]
            except Exception:
                pass
            last = "HTTP %s %s" % (e.code, detail)
            if e.code in (400, 401, 403, 404, 422):
                break                      # not a transport problem; do not hammer it
        except Exception as e:
            last = "%s: %s" % (type(e).__name__, e)
        if attempt < retries:
            time.sleep(min(30.0, 2.0 ** attempt))
        if verbose:
            print("   attempt %d failed: %s" % (attempt, last))
    return {"transport_error": last}


def finalise(record, result):
    """Attach the API result and set the terminal status per the frozen policy."""
    if result.get("transport_error"):
        record.update(result)
        record["status"] = "error"
        record["terminal"] = False
        record["terminal_reason"] = "transport failure; retry allowed"
        return record
    record.update(result)
    record.update(parse_output(result.get("content")))
    if not (result.get("content") or "").strip():
        record["status"] = "empty_content"
        record["terminal"] = True
        record["terminal_reason"] = ("HTTP 200 with empty content; counted as a model-output "
                                     "failure per the frozen policy and NOT retried")
    elif not record.get("repair_available"):
        record["status"] = "malformed"
        record["terminal"] = True
        record["terminal_reason"] = ("HTTP 200 but the frozen template produced no usable "
                                     "REPAIRED_CODE; terminal failure, NOT retried")
    else:
        record["status"] = "ok"
        record["terminal"] = True
        record["terminal_reason"] = None
    return record


# ------------------------------------------------------------------------- smoke test

def run_smoke(args, key, url):
    """
    Two real calls, using the FROZEN rendered prompts -- never a hand-written stand-in,
    so the smoke test exercises exactly the bytes the evaluation will send.
    """
    out_dir = args.out
    path = os.path.join(out_dir, "smoke_results.jsonl")

    calls = []
    for arm in ("natural", "synthetic"):
        p = os.path.join(out_dir, "dev_prompts_%s.jsonl" % arm)
        if not os.path.exists(p):
            print("missing prompt file:", p, file=sys.stderr)
            return 2
        first = json.loads(open(p, encoding="utf-8").readline())
        calls.append((arm, first))

    print("smoke test: %d calls, first dev pair %s" % (len(calls), calls[0][1]["pair_id"]))
    print("base url    :", args.base_url)
    print("model       :", args.model)
    print("thinking    :", args.thinking_mode)
    print("")

    records = []
    for arm, item in calls:
        rec = {"call_id": "%s_smoke" % item["call_id"], "pair_id": item["pair_id"],
               "arm": arm, "requested_model": args.model,
               "temperature": args.temperature, "thinking_mode": args.thinking_mode,
               "requested_at_utc": now(), "raw_prompt": item["prompt"]}
        payload = build_payload(item["prompt"], args.model, args.temperature,
                                args.thinking_mode, args.max_tokens)
        res = invoke(url, key, payload, args.timeout, args.retries)
        rec = finalise(rec, res)
        records.append(rec)

        print("---- %s ----" % arm)
        if rec["status"] == "error":
            print("  TRANSPORT ERROR:", rec.get("transport_error"))
            print("  -> the model name or the thinking parameter may be rejected; "
                  "retry with --thinking-mode reasoning-effort")
        else:
            print("  returned model     :", rec.get("returned_model"))
            print("  system_fingerprint :", rec.get("system_fingerprint"))
            print("  finish_reason      :", rec.get("finish_reason"))
            print("  latency_s          :", rec.get("latency_s"))
            print("  tokens             : prompt=%s completion=%s" %
                  (rec.get("prompt_tokens"), rec.get("completion_tokens")))
            print("  content length     :", len(rec.get("content") or ""))
            print("  status             :", rec["status"])
            print("  parse_status       :", rec.get("parse_status"))
            print("  family/line parsed :", rec.get("family_value"),
                  "/", rec.get("line_value"))
            print("  raw content (first 600 chars):")
            print("  " + (rec.get("content") or "")[:600].replace("\n", "\n  "))
        print("")

    with open(path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    n_ok = sum(1 for r in records if r["status"] == "ok")
    n_empty = sum(1 for r in records if r["status"] == "empty_content")
    n_mal = sum(1 for r in records if r["status"] == "malformed")
    n_err = sum(1 for r in records if r["status"] == "error")
    print("smoke verdict: ok=%d malformed=%d empty=%d transport_error=%d -> %s"
          % (n_ok, n_mal, n_empty, n_err, path))
    if n_err:
        print("STOP: transport error. Try --thinking-mode reasoning-effort, then none.")
    elif n_ok == len(records):
        print("GO: model accepted, template followed. Next: --set dev")
    elif n_mal:
        print("STOP: the frozen template was not followed. Format instructions may be "
              "revised (substantive task instructions may not), then re-run the smoke test.")
    else:
        print("STOP: empty content on a successful response. Report before the dev run.")
    return 0


# -------------------------------------------------------------------------- main run

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", dest="which", default="dev", choices=["dev", "eval"])
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--out", default=os.path.join(HERE, "out"))
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--base-url", default=os.environ.get("DEEPSEEK_BASE_URL", DEFAULT_BASE))
    ap.add_argument("--temperature", type=float, default=0.0)
    ap.add_argument("--thinking-mode", default="thinking-object",
                    choices=["thinking-object", "reasoning-effort", "none"])
    ap.add_argument("--max-tokens", type=int, default=4096)
    ap.add_argument("--limit", type=int, default=0, help="0 = all")
    ap.add_argument("--retries", type=int, default=5)
    ap.add_argument("--timeout", type=int, default=180)
    ap.add_argument("--sleep", type=float, default=0.0)
    ap.add_argument("--key-file", default=os.environ.get("DEEPSEEK_KEY_FILE"),
                    help="read the credential from this file instead of the environment; "
                         "the value is never written to any project file")
    args = ap.parse_args()

    key = None
    if args.key_file:
        try:
            key = open(os.path.expanduser(args.key_file), encoding="utf-8").read().strip()
            print("credential read from file: %s (%d chars)" %
                  (args.key_file, len(key)))
        except Exception as e:
            print("cannot read --key-file: %s" % e, file=sys.stderr)
            return 2
    if not key:
        key = os.environ.get("DEEPSEEK_API_KEY")
        if key:
            print("credential read from DEEPSEEK_API_KEY (%d chars)" % len(key))
    if not key:
        print("No credential. Pass --key-file <path> or set DEEPSEEK_API_KEY.",
              file=sys.stderr)
        return 2
    if len(key) < 20:
        print("warning: the credential looks unusually short (%d chars)" % len(key),
              file=sys.stderr)
    url = args.base_url.rstrip("/") + "/chat/completions"

    if args.smoke:
        return run_smoke(args, key, url)

    prefix = args.which
    prompts = []
    for arm in ("natural", "synthetic"):
        path = os.path.join(args.out, "%s_prompts_%s.jsonl" % (prefix, arm))
        if not os.path.exists(path):
            print("missing prompt file:", path, file=sys.stderr)
            return 2
        for line in open(path, encoding="utf-8"):
            prompts.append(json.loads(line))
    if args.limit:
        prompts = prompts[:args.limit]

    results_path = os.path.join(args.out, "%s_results.jsonl" % prefix)
    done = set()
    if os.path.exists(results_path):
        for line in open(results_path, encoding="utf-8"):
            try:
                r = json.loads(line)
            except Exception:
                continue
            if r.get("status") in TERMINAL:      # terminal outcomes are never re-issued
                done.add(r["call_id"])

    todo = [p for p in prompts if p["call_id"] not in done]
    print("prompt calls: %d | terminal already: %d | to run: %d" %
          (len(prompts), len(done), len(todo)))

    ok = empty = err = 0
    with open(results_path, "a", encoding="utf-8") as fh:
        for i, item in enumerate(todo, 1):
            payload = build_payload(item["prompt"], args.model, args.temperature,
                                    args.thinking_mode, args.max_tokens)
            rec = {"call_id": item["call_id"], "pair_id": item["pair_id"],
                   "arm": item["arm"], "family": item["family"],
                   "natural_line_count": item.get("natural_line_count"),
                   "raw_prompt": item["prompt"], "requested_model": args.model,
                   "thinking_mode": args.thinking_mode,
                   "temperature": args.temperature, "requested_at_utc": now()}
            res = invoke(url, key, payload, args.timeout, args.retries, verbose=False)
            rec = finalise(rec, res)
            if rec["status"] == "ok":
                ok += 1
            elif rec["status"] == "empty_content":
                empty += 1
            else:
                err += 1
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            fh.flush()
            if i % 10 == 0 or i == len(todo):
                print("  %d/%d  ok=%d empty=%d transport_error=%d" %
                      (i, len(todo), ok, empty, err))
            if args.sleep:
                time.sleep(args.sleep)

    manifest = {
        "set": prefix, "requested_model": args.model, "base_url": args.base_url,
        "temperature": args.temperature, "thinking_mode": args.thinking_mode,
        "max_tokens": args.max_tokens, "output_format": "frozen text template (not JSON)",
        "retry_policy": "transport errors only; empty content and malformed template are terminal",
        "finished_utc": now(), "calls_ok": ok, "calls_empty_content": empty,
        "calls_transport_error": err,
    }
    with open(os.path.join(args.out, "%s_run_manifest.json" % prefix), "w",
              encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    print("results: %s | ok=%d empty=%d error=%d" % (results_path, ok, empty, err))
    if err:
        print("transport errors remain; re-run the same command to retry only those.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

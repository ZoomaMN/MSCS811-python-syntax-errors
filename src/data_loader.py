# -*- coding: utf-8 -*-
"""
data_loader.py — Wong et al. (2019) Python3.6 Natural Syntax Errors and Corrections.

Stage 1 of the MSCS811 syntax-study pipeline.

Responsibilities
----------------
1. Load parse_errors.json and parse_fixes.json and join them into pairs.
   Join key: fixes[fix_id].pred_post_block_version_id == error_id
2. Re-validate every pair under a PINNED Python version with ast.parse:
       natural (erroneous) snippet  -> MUST fail
       human fix                    -> MUST parse
   A pair that violates either condition is FLAGGED, never silently dropped.
3. Record, for every pair, both the corpus's recorded parser diagnostic and the
   diagnostic regenerated locally, so the two can be compared.
4. Emit pairs.jsonl plus a human-readable loader report.

Usage
-----
    python data_loader.py --data data --out out
"""

import argparse
import ast
import collections
import json
import os
import platform
import sys


def parse_diag(code):
    """Return (ok, error_type, error_message, lineno, offset) for a snippet."""
    try:
        ast.parse(code)
        return True, None, None, None, None
    except SyntaxError as e:
        return False, type(e).__name__, (e.msg or ""), e.lineno, e.offset
    except ValueError as e:
        # ast.parse can raise ValueError on source containing null bytes
        return False, type(e).__name__, str(e), None, None
    except MemoryError:
        return False, "MemoryError", "", None, None


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def build_pairs(data_dir):
    errors = load_json(os.path.join(data_dir, "parse_errors.json"))
    fixes = load_json(os.path.join(data_dir, "parse_fixes.json"))

    runtime_path = os.path.join(data_dir, "parse_fixes_runtime.json")
    fix_runtime = load_json(runtime_path) if os.path.exists(runtime_path) else {}

    # Index fixes by the error id they repair.
    fix_by_error = {}
    for fix_id, rec in fixes.items():
        pred = rec.get("pred_post_block_version_id")
        if pred is None:
            continue
        fix_by_error.setdefault(str(pred), []).append((fix_id, rec))

    pairs = []
    stats = collections.Counter()

    for err_id, erec in errors.items():
        err_id = str(err_id)
        candidates = fix_by_error.get(err_id)
        if not candidates:
            stats["no_fix"] += 1
            continue
        if len(candidates) > 1:
            stats["multi_fix"] += 1
        fix_id, frec = candidates[0]

        natural = erec.get("content") or ""
        fixed = frec.get("content") or ""

        nat_ok, nat_type, nat_msg, nat_line, nat_off = parse_diag(natural)
        fix_ok, fix_type, fix_msg, fix_line, fix_off = parse_diag(fixed)

        # The corpus records a fix that executes cleanly as runtime_error = None.
        rt = fix_runtime.get(str(fix_id))
        if rt is None:
            runtime_error = None
            fix_clean = None          # no runtime record shipped for this fix
        else:
            runtime_error = rt.get("runtime_error")
            fix_clean = (runtime_error is None)   # None == executed with no error

        p = {
            "pair_id": "wong-%s" % err_id,
            "error_id": err_id,
            "fix_id": str(fix_id),
            # code
            "natural_code": natural,
            "human_fix_code": fixed,
            # recorded diagnostics (as shipped by the corpus, Python 3.6 era)
            "recorded_error_type": erec.get("error_type"),
            "recorded_error_message": erec.get("error_message"),
            "recorded_error_line": erec.get("syntax_err_line_no"),
            "recorded_error_offset": erec.get("syntax_err_offset"),
            # regenerated diagnostics (pinned local interpreter)
            "natural_parse_ok": nat_ok,
            "natural_error_type": nat_type,
            "natural_error_message": nat_msg,
            "natural_error_line": nat_line,
            "natural_error_offset": nat_off,
            "human_fix_parse_ok": fix_ok,
            "human_fix_error_type": fix_type,
            "human_fix_error_message": fix_msg,
            # geometry
            "natural_line_count": natural.count("\n") + 1,
            "natural_length": len(natural),
            "fix_line_count": fixed.count("\n") + 1,
            "fix_length": len(fixed),
            # provenance / secondary signals
            "tags": erec.get("tags") or [],
            "fix_runtime_error": runtime_error,
            "fix_runs_clean": fix_clean,
            # validity flags
            "valid_natural_fails": (nat_ok is False),
            "valid_fix_parses": (fix_ok is True),
        }
        p["pair_valid"] = bool(p["valid_natural_fails"] and p["valid_fix_parses"])
        if not p["pair_valid"]:
            stats["invalid_pair"] += 1
        pairs.append(p)

    return pairs, stats, len(errors), len(fixes)


def report(pairs, stats, n_errors, n_fixes, out_dir, pyver):
    lines = []
    add = lines.append

    add("# Wong corpus — loader report")
    add("")
    add("Interpreter: Python %s" % pyver)
    add("")
    add("| Quantity | Value |")
    add("|---|---:|")
    add("| Error records | %d |" % n_errors)
    add("| Fix records | %d |" % n_fixes)
    add("| Joined pairs | %d |" % len(pairs))
    add("| Pairs with no fix (join miss) | %d |" % stats["no_fix"])
    add("| Errors with >1 fix candidate | %d |" % stats["multi_fix"])
    add("| Pairs failing revalidation | %d |" % stats["invalid_pair"])
    add("")

    valid = [p for p in pairs if p["pair_valid"]]
    add("Valid pairs under pinned interpreter: **%d** (%.1f%%)" %
        (len(valid), 100.0 * len(valid) / max(1, len(pairs))))
    add("")

    add("## Recorded error type (as shipped, Python 3.6 era)")
    add("")
    add("| error_type | count |")
    add("|---|---:|")
    for k, v in collections.Counter(p["recorded_error_type"] for p in pairs).most_common():
        add("| %s | %d |" % (k, v))
    add("")

    add("## Regenerated error type (pinned local interpreter)")
    add("")
    add("| error_type | count |")
    add("|---|---:|")
    for k, v in collections.Counter(
            p["natural_error_type"] for p in valid).most_common():
        add("| %s | %d |" % (k, v))
    add("")

    add("## Top 25 recorded messages")
    add("")
    add("| message | count |")
    add("|---|---:|")
    for k, v in collections.Counter(
            p["recorded_error_message"] for p in pairs).most_common(25):
        add("| `%s` | %d |" % (k, v))
    add("")

    add("## Top 25 regenerated messages (valid pairs)")
    add("")
    add("| message | count |")
    add("|---|---:|")
    for k, v in collections.Counter(
            p["natural_error_message"] for p in valid).most_common(25):
        add("| `%s` | %d |" % (k, v))
    add("")

    add("## Did the recorded message survive regeneration?")
    add("")
    same = sum(1 for p in valid
               if p["recorded_error_message"] == p["natural_error_message"])
    add("- Identical message: %d (%.1f%% of valid)" %
        (same, 100.0 * same / max(1, len(valid))))
    add("- Different message: %d" % (len(valid) - same))
    add("- Recorded type preserved (SyntaxError/IndentationError/TabError): %d" %
        sum(1 for p in valid if p["recorded_error_type"] == p["natural_error_type"]))
    add("")

    add("## Snippet geometry (valid pairs)")
    add("")
    lc = sorted(p["natural_line_count"] for p in valid)
    ch = sorted(p["natural_length"] for p in valid)
    if lc:
        add("- natural lines: median %d, p90 %d, max %d" %
            (lc[len(lc) // 2], lc[int(0.9 * len(lc))], lc[-1]))
        add("- natural chars: median %d, p90 %d, max %d" %
            (ch[len(ch) // 2], ch[int(0.9 * len(ch))], ch[-1]))
    add("")

    add("## Reproducibility signal (fix_runs_clean, from the shipped runtime file)")
    add("")
    clean = sum(1 for p in valid if p["fix_runs_clean"] is True)
    dirty = sum(1 for p in valid if p["fix_runs_clean"] is False)
    unknown = sum(1 for p in valid if p["fix_runs_clean"] is None)
    add("| status | count |")
    add("|---|---:|")
    add("| fix executes with no error | %d |" % clean)
    add("| fix raises at runtime | %d |" % dirty)
    add("| unknown | %d |" % unknown)
    add("")

    path = os.path.join(out_dir, "loader_report.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data")
    ap.add_argument("--out", default="out")
    ap.add_argument("--limit", type=int, default=0,
                    help="only process the first N pairs (0 = all)")
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)

    pairs, stats, n_errors, n_fixes = build_pairs(args.data)
    if args.limit:
        pairs = pairs[:args.limit]

    jsonl = os.path.join(args.out, "pairs.jsonl")
    with open(jsonl, "w", encoding="utf-8") as f:
        for p in pairs:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")

    pyver = platform.python_version()
    rp = report(pairs, stats, n_errors, n_fixes, args.out, pyver)

    print("pairs written :", jsonl, "(%d)" % len(pairs))
    print("loader report :", rp)
    valid = sum(1 for p in pairs if p["pair_valid"])
    print("valid pairs   : %d (%.1f%%)" % (valid, 100.0 * valid / max(1, len(pairs))))


if __name__ == "__main__":
    main()

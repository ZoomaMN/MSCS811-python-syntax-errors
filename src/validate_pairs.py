# -*- coding: utf-8 -*-
"""
validate_pairs.py — build and validate the matched natural / synthetic pair pool.

This is the gate the project must pass BEFORE any model is called. It answers one
question: can we construct, for a meaningful number of natural errors, a synthetic
counterpart that breaks the SAME code in the SAME error family at a comparable position
with a comparable edit size?

Pipeline
--------
    pairs.jsonl
      -> family classification (message-first, edit-diff fallback)
      -> minimal-repair filter (the human fix must be a small, single edit)
      -> synthetic injection into the human fix, targeting the natural error position
      -> position-delta acceptance test
      -> matched_pairs.jsonl + validation_report.md

Every exclusion is counted by reason; nothing is dropped silently.

Usage
-----
    python validate_pairs.py --pairs out/pairs.jsonl --out out \
        --max-changed-lines 2 --max-edit-size 8 --max-position-delta 0.10
"""

import argparse
import collections
import json
import os
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from error_families import assign_family, FAMILY_NOTE  # noqa: E402
from injectors import inject  # noqa: E402

# INDENTATION is reported separately: it is by far the largest natural class, and the
# corpus's own construction removes "extraneous white space", so a large share of these
# entries are plausibly extraction artefacts rather than developer mistakes.
PRIMARY_FAMILIES = [
    "MISSING_COLON", "MISSING_COMMA", "MISSING_CLOSER",
    "BRACKET_MISMATCH", "QUOTATION", "PRINT_STATEMENT",
    "KEYWORD_AS_IDENTIFIER",
]
SECONDARY_FAMILIES = ["INDENTATION"]


def classify(p):
    return assign_family(p["natural_code"], p["human_fix_code"],
                         p["natural_error_message"], p["natural_error_type"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pairs", default="out/pairs.jsonl")
    ap.add_argument("--out", default="out")
    ap.add_argument("--max-changed-lines", type=int, default=2)
    ap.add_argument("--max-edit-size", type=int, default=8)
    ap.add_argument("--max-position-delta", type=float, default=0.10)
    ap.add_argument("--include-indentation", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    families = list(PRIMARY_FAMILIES)
    if args.include_indentation:
        families += SECONDARY_FAMILIES

    os.makedirs(args.out, exist_ok=True)

    funnel = collections.Counter()
    per_family = collections.defaultdict(collections.Counter)
    accepted = []
    examples = collections.defaultdict(list)
    natural_sizes = []
    minimality_hist = collections.Counter()

    n = 0
    for line in open(args.pairs, encoding="utf-8"):
        p = json.loads(line)
        n += 1
        if args.limit and n > args.limit:
            break
        if not p["pair_valid"]:
            funnel["invalid_pair"] += 1
            continue

        info = classify(p)
        fam = info["family"]
        natural_sizes.append((p["natural_line_count"], info["edit_size"]))
        minimality_hist[(info["changed_lines"], info["edit_size"])] += 1

        if fam not in families:
            funnel["family_not_eligible"] += 1
            per_family[fam]["not_eligible"] += 1
            continue
        per_family[fam]["eligible_family"] += 1

        if info["changed_lines"] > args.max_changed_lines or \
           info["edit_size"] > args.max_edit_size:
            funnel["not_minimal_repair"] += 1
            per_family[fam]["not_minimal"] += 1
            continue
        per_family[fam]["minimal"] += 1

        nat_line = p["natural_error_line"]
        if not nat_line:
            funnel["no_natural_line"] += 1
            continue
        total = max(1, p["natural_line_count"] - 1)
        target_rel = (nat_line - 1) / total

        inj = inject(p["human_fix_code"], fam, target_rel,
                     avoid_code=p["natural_code"])
        if inj is None:
            funnel["not_injectable"] += 1
            per_family[fam]["not_injectable"] += 1
            continue
        # belt and braces: the injector already refuses to reproduce the natural snippet
        if inj["synthetic_code"] == p["natural_code"]:
            funnel["injection_reproduced_natural"] += 1
            per_family[fam]["reproduced_natural"] += 1
            continue
        per_family[fam]["injected"] += 1

        delta = abs(target_rel - inj["relative_position"])
        if delta > args.max_position_delta:
            funnel["position_delta_too_large"] += 1
            per_family[fam]["position_rejected"] += 1
            continue

        rec = dict(p)
        rec.update({
            "family": fam,
            "family_source": info["family_source"],
            "message_family": info["message_family"],
            "edit_family": info["edit_family"],
            "natural_edit_size": info["edit_size"],
            "natural_changed_lines": info["changed_lines"],
            "natural_relative_position": target_rel,
            "synthetic_code": inj["synthetic_code"],
            "synthetic_error_type": inj["synthetic_error_type"],
            "synthetic_error_message": inj["synthetic_error_message"],
            "synthetic_family": inj["synthetic_family"],
            "synthetic_relative_position": inj["relative_position"],
            "injection_rule": inj["injection_rule"],
            "synthetic_edit_size": inj["edit_size"],
            "position_delta": delta,
        })
        accepted.append(rec)
        per_family[fam]["accepted"] += 1

        if len(examples[fam]) < 2:
            examples[fam].append(rec)
    # end for

    jsonl = os.path.join(args.out, "matched_pairs.jsonl")
    with open(jsonl, "w", encoding="utf-8") as f:
        for r in accepted:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    # ------------------------------------------------------------------ report
    L = []
    add = L.append
    add("# Matched-pair validation report")
    add("")
    add("Frozen thresholds: max changed lines = %d, max edit size = %d, "
        "max position delta = %.2f" %
        (args.max_changed_lines, args.max_edit_size, args.max_position_delta))
    add("")
    add("Families in scope: %s%s" %
        (", ".join(families),
         "" if args.include_indentation else "  (INDENTATION excluded)"))
    add("")
    add("## Funnel")
    add("")
    add("| Stage | Count |")
    add("|---|---:|")
    add("| pairs read | %d |" % n)
    for k in ("invalid_pair", "family_not_eligible", "not_minimal_repair",
              "no_natural_line", "not_injectable", "injection_reproduced_natural",
              "position_delta_too_large"):
        add("| excluded: %s | %d |" % (k, funnel[k]))
    add("| **accepted matched pairs** | **%d** |" % len(accepted))
    add("")

    add("## Per-family funnel")
    add("")
    add("| family | eligible | minimal repair | injected | position ok | **accepted** |")
    add("|---|---:|---:|---:|---:|---:|")
    for fam in families:
        c = per_family[fam]
        add("| %s | %d | %d | %d | %d | **%d** |" %
            (fam, c["eligible_family"], c["minimal"], c["injected"],
             c["injected"] - c["position_rejected"], c["accepted"]))
    add("")

    if accepted:
        ds = [r["position_delta"] for r in accepted]
        ne = [r["natural_edit_size"] for r in accepted]
        se = [r["synthetic_edit_size"] for r in accepted]
        add("## Match quality (accepted pairs)")
        add("")
        add("| Quantity | Value |")
        add("|---|---:|")
        add("| pairs | %d |" % len(accepted))
        add("| family agreement (by construction) | 100% |")
        add("| position delta: median | %.3f |" % statistics.median(ds))
        add("| position delta: p90 | %.3f |" % sorted(ds)[int(0.9 * len(ds))])
        add("| position delta: max | %.3f |" % max(ds))
        add("| natural edit size: median | %s |" % statistics.median(ne))
        add("| synthetic edit size: median | %s |" % statistics.median(se))
        add("| median |natural - synthetic| edit size | %s |" %
            statistics.median([abs(a - b) for a, b in zip(ne, se)]))
        add("")

        fam_counts = collections.Counter(r["family"] for r in accepted)
        add("## Accepted pairs per family")
        add("")
        add("| family | accepted | share |")
        add("|---|---:|---:|")
        for k, v in fam_counts.most_common():
            add("| %s | %d | %.1f%% |" % (k, v, 100.0 * v / len(accepted)))
        add("")

    add("## Minimal-repair distribution over all valid pairs")
    add("")
    add("Top 12 (changed lines, edit size) combinations:")
    add("")
    add("| changed lines | edit size | pairs |")
    add("|---|---:|---:|")
    for (cl, es), v in minimality_hist.most_common(12):
        add("| %d | %d | %d |" % (cl, es, v))
    add("")

    add("## Worked examples")
    add("")
    for fam in families:
        for r in examples.get(fam, [])[:1]:
            add("### %s — %s" % (fam, FAMILY_NOTE.get(fam, "")))
            add("")
            add("- pair: `%s`" % r["pair_id"])
            add("- injection rule: %s" % r["injection_rule"])
            add("- natural message: `%s`" % r["natural_error_message"])
            add("- synthetic message: `%s`" % r["synthetic_error_message"])
            add("- natural family source: %s" % r["family_source"])
            add("- position delta: %.3f" % r["position_delta"])
            add("")
            add("```python")
            add("# natural (erroneous), error reported at line %s" %
                r["natural_error_line"])
            add("\n".join(r["natural_code"].splitlines()[:14]))
            add("```")
            add("")
            add("```python")
            add("# synthetic (injected into the human fix)")
            add("\n".join(r["synthetic_code"].splitlines()[:14]))
            add("```")
            add("")

    rp = os.path.join(args.out, "validation_report.md")
    with open(rp, "w", encoding="utf-8") as f:
        f.write("\n".join(L))

    print("matched pairs :", jsonl, "(%d)" % len(accepted))
    print("report        :", rp)
    print("funnel        :", dict(funnel))


if __name__ == "__main__":
    main()

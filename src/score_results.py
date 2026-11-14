# -*- coding: utf-8 -*-
"""
score_results.py — turn raw model responses into the reported outcomes.

Primary outcome
    reference AST agreement (ast.dump without attributes); paired difference,
    natural minus synthetic, with a bootstrap 95% interval and an exact McNemar test.

Detection
    ERROR_FAMILY is the measure of record; ERROR_LINE is secondary. A missing or
    out-of-vocabulary family fails detection but never suppresses the repair outcome,
    because the detection-to-repair gap is the object of study.

Length
    1. overall paired contrast
    2. pre-specified strata: within-family length tertiles
    3. continuous length, reported as a trend
    The order is fixed and is not revisited after seeing results.

No scipy: the normal CDF uses math.erf and McNemar's exact p uses math.comb.

Usage
-----
    python src/score_results.py --out results/deepseek --sample data/sample.jsonl \
        --matched data/eligible_pairs.jsonl
"""

import argparse
import ast
import collections
import csv
import difflib
import json
import math
import os
import random
import sys

VALID_FAMILIES = [
    "MISSING_COLON", "MISSING_COMMA", "MISSING_CLOSER", "QUOTATION",
    "BRACKET_MISMATCH", "KEYWORD_AS_IDENTIFIER", "PRINT_STATEMENT",
]


# ------------------------------------------------------------------ small statistics

def norm_cdf(x):
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def mcnemar_exact(b, c):
    """
    Two-sided exact binomial test on the discordant pairs.

    This is the confirmatory instrument. It stays valid when the discordant count is zero
    (it returns p = 1) and in small samples, which is exactly where a Wald interval
    collapses to a single point.
    """
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    tail = sum(math.comb(n, i) for i in range(0, k + 1)) / float(2 ** n)
    return min(1.0, 2.0 * tail)


def bootstrap_ci(diffs, reps=10000, seed=20261005):
    """Descriptive percentile interval on the paired difference."""
    rng = random.Random(seed)
    n = len(diffs)
    if n == 0:
        return (float("nan"), float("nan"))
    means = []
    for _ in range(reps):
        s = 0
        for _ in range(n):
            s += diffs[rng.randrange(n)]
        means.append(s / n)
    means.sort()
    return (means[int(0.025 * reps)], means[int(0.975 * reps)])


# ----------------------------------------------------------------------- helpers

def parses(code):
    if code is None:
        return False
    try:
        ast.parse(code)
        return True
    except (SyntaxError, ValueError):
        return False


def error_line(code):
    try:
        ast.parse(code)
        return None
    except SyntaxError as e:
        return e.lineno
    except ValueError:
        return None


def structural_match(candidate, reference):
    """
    PRIMARY OUTCOME — structural match with the reference fix.

    Fixed definition: both snippets parse, and their abstract syntax trees are identical
    under `ast.dump` with `include_attributes=False`, so line numbers, column offsets and
    all formatting are ignored. Comments are not represented in the AST and are therefore
    ignored as well; literal values and program structure are compared exactly.

    Returns True / False, or None when either snippet fails to parse. This measures
    agreement with the reference repair, NOT semantic correctness: an alternative but
    equally valid repair (for example `x += 1` against `x = x + 1`) is counted as a
    non-match.
    """
    try:
        ta = ast.parse(candidate)
        tb = ast.parse(reference)
    except (SyntaxError, ValueError, TypeError):
        return None
    return ast.dump(ta, include_attributes=False) == ast.dump(tb, include_attributes=False)


def normalize(code):
    return "\n".join(ln.rstrip() for ln in (code or "").splitlines()).strip()


def tokens(code):
    return (code or "").split()


def edit_distance(a, b):
    sm = difflib.SequenceMatcher(a=a, b=b, autojunk=True)
    return sum(max(i2 - i1, j2 - j1)
               for tag, i1, i2, j1, j2 in sm.get_opcodes() if tag != "equal")


def tertile_cuts(matched_path):
    by_fam = collections.defaultdict(list)
    for line in open(matched_path, encoding="utf-8"):
        r = json.loads(line)
        by_fam[r["family"]].append(r["natural_line_count"])
    cuts = {}
    for fam, vals in by_fam.items():
        vals.sort()
        n = len(vals)
        cuts[fam] = (vals[n // 3], vals[2 * n // 3])
    return cuts


def tertile_of(line_count, cuts):
    lo, hi = cuts
    if line_count <= lo:
        return "short"
    if line_count <= hi:
        return "medium"
    return "long"


def load_results(path):
    by_call = {}
    for line in open(path, encoding="utf-8"):
        r = json.loads(line)
        by_call[r["call_id"]] = r
    return by_call


# ------------------------------------------------------------------------- scoring

SAMPLE = None


def score(out_dir, which, matched_path, csv_path):
    sample_path = SAMPLE or os.path.join(out_dir, "sample.jsonl" if which == "eval"
                                         else "dev_sample.jsonl")
    results_path = os.path.join(out_dir, "%s_results.jsonl" %
                                ("eval" if which == "eval" else "dev"))
    if not os.path.exists(results_path):
        print("no results file at", results_path, file=sys.stderr)
        return None

    pairs = {}
    for line in open(sample_path, encoding="utf-8"):
        p = json.loads(line)
        pairs[p["pair_id"]] = p
    cuts = tertile_cuts(matched_path) if os.path.exists(matched_path) else {}
    results = load_results(results_path)

    rows = []
    identical = 0
    for pid, p in pairs.items():
        row = {"pair_id": pid, "family": p["family"],
               "lines": p["natural_line_count"],
               "chars": p["natural_length"],
               "identical_pair": (p["natural_code"] == p["synthetic_code"]),
               "tertile": tertile_of(p["natural_line_count"],
                                     cuts.get(p["family"], (0, 0)))
               if p["family"] in cuts else "na"}
        if row["identical_pair"]:
            identical += 1
        for arm, code_key in (("natural", "natural_code"),
                              ("synthetic", "synthetic_code")):
            rec = results.get("%s__%s" % (pid, arm))
            if rec is None:
                row["%s_present" % arm] = False
                row["%s_repair" % arm] = False
                row["%s_astmatch" % arm] = False
                row["%s_det_family" % arm] = False
                row["%s_det_line" % arm] = False
                row["%s_status" % arm] = "missing_call"
                continue
            gt_line = error_line(p[code_key])
            code = rec.get("repaired_code")
            repair = parses(code)
            sm = structural_match(code, p["human_fix_code"])
            det_fam = bool(rec.get("family_valid")
                           and rec.get("family_value") == p["family"])
            det_line = bool(rec.get("line_valid")
                            and gt_line is not None
                            and rec.get("line_value") == gt_line)
            same = (normalize(code) == normalize(p["human_fix_code"]))
            ed = edit_distance(tokens(code), tokens(p["human_fix_code"]))
            row.update({
                "%s_present" % arm: True,
                "%s_status" % arm: rec.get("parse_status"),
                "%s_repair" % arm: repair,
                "%s_astmatch" % arm: bool(sm),
                "%s_astmatch_defined" % arm: sm is not None,
                "%s_det_family" % arm: det_fam,
                "%s_det_line" % arm: det_line,
                "%s_exact" % arm: same,
                "%s_editdist" % arm: ed,
            })
        rows.append(row)

    # ---- per-arm summaries
    summary = {}
    for arm in ("natural", "synthetic"):
        n = sum(1 for r in rows if r.get("%s_present" % arm))
        summary[arm] = {
            "n": n,
            "astmatch": sum(1 for r in rows if r.get("%s_astmatch" % arm)),
            "repair": sum(1 for r in rows if r.get("%s_repair" % arm)),
            "family": sum(1 for r in rows if r.get("%s_det_family" % arm)),
            "line": sum(1 for r in rows if r.get("%s_det_line" % arm)),
            "both": sum(1 for r in rows if r.get("%s_det_family" % arm)
                        and r.get("%s_det_line" % arm)),
            "exact": sum(1 for r in rows if r.get("%s_exact" % arm)),
        }

    # ---- primary paired contrast: structural match with the reference fix
    complete = [r for r in rows
                if r.get("natural_present") and r.get("synthetic_present")
                and not r["identical_pair"]]
    diffs = [int(r["natural_astmatch"]) - int(r["synthetic_astmatch"])
             for r in complete]
    n = len(diffs)
    p_nat = (sum(1 for r in complete if r["natural_astmatch"]) / n) if n else float("nan")
    p_syn = (sum(1 for r in complete if r["synthetic_astmatch"]) / n) if n else float("nan")
    rd = (p_nat - p_syn) if n else float("nan")
    b = sum(1 for r in complete if r["natural_astmatch"] and not r["synthetic_astmatch"])
    c = sum(1 for r in complete if r["synthetic_astmatch"] and not r["natural_astmatch"])
    ci_b = bootstrap_ci(diffs) if n else (float("nan"), float("nan"))
    p_mcn = mcnemar_exact(b, c)

    # ---- strata
    def strata(keyfun):
        groups = collections.defaultdict(list)
        for r in complete:
            groups[keyfun(r)].append(r)
        res = {}
        for k, rs in sorted(groups.items(), key=lambda kv: str(kv[0])):
            m = len(rs)
            dd = [int(r["natural_astmatch"]) - int(r["synthetic_astmatch"])
                  for r in rs]
            res[k] = (m, (sum(dd) / float(m)) if m else float("nan"),
                      bootstrap_ci(dd) if m else (float("nan"),) * 2)
        return res

    by_family = strata(lambda r: r["family"])
    by_tertile = strata(lambda r: r["tertile"])
    short_excl = [int(r["natural_astmatch"]) - int(r["synthetic_astmatch"])
                  for r in complete if r["lines"] > 2]

    # ---- report
    L = []
    add = L.append
    add("# Results — %s set" % which)
    add("")
    add("Calls scored: %d pairs. Prompt template frozen. Malformed output is counted as a "
        "failure (intention-to-treat)." % len(rows))
    add("")
    add("**Primary outcome.** Structural match with "
        "the reference fix: both snippets parse and their syntax trees are identical, "
        "ignoring line numbers, column offsets, formatting and comments. This measures "
        "agreement with the reference repair, not semantic correctness — an alternative "
        "but equally valid repair counts as a non-match.")
    add("")
    if identical:
        add("Literal-identical pairs excluded from the primary comparison: **%d** "
            "(both arms present the same string, so their difference is zero by "
            "construction)." % identical)
        add("")
    add("## Per-arm outcomes")
    add("")
    add("| measure | natural | synthetic |")
    add("|---|---:|---:|")
    for label, key in (("calls present", "n"),
                       ("**structural match with reference fix (primary)**", "astmatch"),
                       ("parses (syntactic validity)", "repair"),
                       ("detection: family correct", "family"),
                       ("detection: line correct", "line"),
                       ("detection: family and line", "both"),
                       ("text match to reference fix", "exact")):
        add("| %s | %d | %d |" % (label, summary["natural"][key],
                                  summary["synthetic"][key]))
    add("")
    add("Rates (denominator = calls present):")
    add("")
    add("| measure | natural | synthetic |")
    add("|---|---:|---:|")
    for label, key in (("structural match with reference fix (primary)", "astmatch"),
                       ("parses (syntactic validity)", "repair"),
                       ("detection: family correct", "family"),
                       ("detection: line correct", "line"),
                       ("text match to reference fix", "exact")):
        a = summary["natural"][key] / max(1, summary["natural"]["n"])
        d = summary["synthetic"][key] / max(1, summary["synthetic"]["n"])
        add("| %s | %.1f%% | %.1f%% |" % (label, 100 * a, 100 * d))
    add("")

    add("## Detection-to-repair gap (per arm)")
    add("")
    add("| arm | family detection | parses | structural match | gap vs match (pp) |")
    add("|---|---:|---:|---:|---:|")
    for arm in ("natural", "synthetic"):
        s = summary[arm]
        dn = s["family"] / max(1, s["n"])
        rn = s["repair"] / max(1, s["n"])
        mn = s["astmatch"] / max(1, s["n"])
        add("| %s | %.1f%% | %.1f%% | %.1f%% | %+.1f |"
            % (arm, 100 * dn, 100 * rn, 100 * mn, 100 * (dn - mn)))
    add("")

    add("## Primary contrast — paired difference in structural match with the reference fix")
    add("")
    add("| Quantity | Value |")
    add("|---|---:|")
    add("| complete non-identical pairs | %d |" % n)
    add("| natural match rate | %.3f |" % p_nat)
    add("| synthetic match rate | %.3f |" % p_syn)
    add("| **paired difference (natural − synthetic)** | **%+.3f** |" % rd)
    add("| 95%% CI (bootstrap percentile, 10k) | [%+.3f, %+.3f] |" % ci_b)
    add("| discordant: natural-only | %d |" % b)
    add("| discordant: synthetic-only | %d |" % c)
    add("| **McNemar exact p (confirmatory)** | **%.4g** |" % p_mcn)
    add("")
    add("No Wald interval is reported. It collapses to a single point when discordance is "
        "zero, and it diverges from the exact test at the boundary; reporting it would "
        "invite selecting whichever interval looks favourable.")
    add("")

    add("## Pre-specified strata (paired risk difference)")
    add("")
    add("### By within-family length tertile")
    add("")
    add("| tertile | pairs | paired difference | 95% CI (bootstrap) |")
    add("|---|---:|---:|---|")
    for k, (m, d, ci) in by_tertile.items():
        add("| %s | %d | %+.3f | [%+.3f, %+.3f] |" % (k, m, d, ci[0], ci[1]))
    add("")
    add("### By error family (descriptive, not confirmatory)")
    add("")
    add("| family | pairs | paired difference | 95% CI (bootstrap) |")
    add("|---|---:|---:|---|")
    for k, (m, d, ci) in by_family.items():
        add("| %s | %d | %+.3f | [%+.3f, %+.3f] |" % (k, m, d, ci[0], ci[1]))
    add("")

    add("## Sensitivity: exclude snippets of 2 lines or fewer")
    add("")
    if short_excl:
        m = len(short_excl)
        d = sum(short_excl) / m
        ci = bootstrap_ci(short_excl)
        bb = sum(1 for r in complete if r["lines"] > 2
                 and r["natural_astmatch"] and not r["synthetic_astmatch"])
        cc = sum(1 for r in complete if r["lines"] > 2
                 and r["synthetic_astmatch"] and not r["natural_astmatch"])
        add("| pairs | paired difference | 95% CI (bootstrap) | McNemar exact p |")
        add("|---:|---:|---|---:|")
        add("| %d | %+.3f | [%+.3f, %+.3f] | %.4g |"
            % (m, d, ci[0], ci[1], mcnemar_exact(bb, cc)))
    else:
        add("No pairs outside the short stratum.")
    add("")

    add("## Note on interpretation")
    add("")
    add("The evaluation sample is a **balanced analytical sample**, not a "
        "prevalence-weighted estimate of the 62,882-pair corpus: every family holds a "
        "floor of pairs, so the pooled rates describe this design rather than the "
        "corpus's natural mix.")
    add("")

    rp = os.path.join(out_dir, "%s_results_report.md" %
                      ("eval" if which == "eval" else "dev"))
    with open(rp, "w", encoding="utf-8") as f:
        f.write("\n".join(L))

    if csv_path:
        keys = ["pair_id", "family", "lines", "chars", "tertile",
                "identical_pair"]
        for arm in ("natural", "synthetic"):
            keys += ["%s_astmatch" % arm, "%s_repair" % arm,
                     "%s_det_family" % arm, "%s_det_line" % arm,
                     "%s_exact" % arm, "%s_editdist" % arm, "%s_status" % arm]
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
            w.writeheader()
            for r in rows:
                w.writerow(r)

    print("report :", rp)
    if csv_path:
        print("csv    :", csv_path)
    print("PRIMARY paired difference in structural match (natural - synthetic): "
          "%+.4f  95%% CI [%+.4f, %+.4f]  McNemar p=%.4g"
          % (rd, ci_b[0], ci_b[1], p_mcn))
    return {"rows": rows, "summary": summary, "rd": rd, "ci": ci_b, "p": p_mcn}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "out"))
    ap.add_argument("--set", dest="which", default="eval", choices=["dev", "eval"])
    ap.add_argument("--matched", default=None)
    ap.add_argument("--sample", default=None)
    args = ap.parse_args()
    global SAMPLE
    SAMPLE = args.sample

    matched = args.matched or os.path.join(args.out, "matched_pairs.jsonl")
    suffix = "eval" if args.which == "eval" else "dev"
    csv_path = os.path.join(args.out, "%s_pair_outcomes.csv" % suffix)
    res = score(args.out, args.which, matched, csv_path)
    return 0 if res else 1


if __name__ == "__main__":
    sys.exit(main())

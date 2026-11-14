"""Compute the paired statistics reported in the paper from the scored pair outcomes.

Usage: python src/compute_stats.py
Reads results/<service>/eval_pair_outcomes.csv and writes results/stats.json.
"""
import csv, json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from score_results import mcnemar_exact, bootstrap_ci

ROOT = os.path.dirname(HERE)
SERVICES = {"DeepSeek": "deepseek", "Claude": "claude"}
OUTCOMES = {"ast": "astmatch", "parse": "repair", "family": "det_family",
            "line": "det_line", "exact": "exact"}


def flag(v):
    return v == "True"


def contrast(rows, get):
    nat = [get(r, "natural") for r in rows]
    syn = [get(r, "synthetic") for r in rows]
    n = len(rows)
    b = sum(1 for x, y in zip(nat, syn) if x and not y)
    c = sum(1 for x, y in zip(nat, syn) if y and not x)
    lo, hi = bootstrap_ci([int(x) - int(y) for x, y in zip(nat, syn)])
    return {"n": n, "nat": sum(nat), "syn": sum(syn),
            "natp": round(100 * sum(nat) / n, 2), "synp": round(100 * sum(syn) / n, 2),
            "diff": round(100 * (sum(nat) - sum(syn)) / n, 2),
            "ci": [round(100 * lo, 2), round(100 * hi, 2)],
            "nat_only": b, "syn_only": c, "p": mcnemar_exact(b, c)}


def main():
    stats = {}
    for name, folder in SERVICES.items():
        with open(os.path.join(ROOT, "results", folder, "eval_pair_outcomes.csv"), encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        s = {}
        for key, col in OUTCOMES.items():
            s[key] = contrast(rows, lambda r, arm, col=col: flag(r["%s_%s" % (arm, col)]))
        s["joint"] = contrast(rows, lambda r, arm: flag(r[arm + "_det_family"]) and flag(r[arm + "_det_line"]))
        s["fam"] = {}
        for fam in sorted({r["family"] for r in rows}):
            sub = [r for r in rows if r["family"] == fam]
            s["fam"][fam] = contrast(sub, lambda r, arm: flag(r[arm + "_astmatch"]))
        stats[name] = s
    out = os.path.join(ROOT, "results", "stats.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(stats, fh, indent=1)
    print("wrote", out)


if __name__ == "__main__":
    main()

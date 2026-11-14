# -*- coding: utf-8 -*-
"""
sample_pairs.py — draw the evaluation sample from the eligible pool.

  * Evaluation sample: 300 pairs.
      - a floor of 40 pairs per error family
      - the remainder allocated in proportion to each family's share of the pool,
        by largest remainder
      - within a family, pairs are spread as evenly as possible across that family's own
        length tertiles
  * A single seed (20261114) fixes the draw.

Usage
-----
    python src/sample_pairs.py --matched data/eligible_pairs.jsonl --out data
"""

import argparse
import collections
import json
import os
import random
import statistics


def tertile_cut(pairs):
    """Cut points for three equal-count length bins inside one family."""
    vals = sorted(p["natural_line_count"] for p in pairs)
    if not vals:
        return (0, 0)
    n = len(vals)
    return (vals[n // 3], vals[2 * n // 3])


def tertile_of(line_count, cuts):
    lo, hi = cuts
    if line_count <= lo:
        return "short"
    if line_count <= hi:
        return "medium"
    return "long"


def spread(total, bins):
    """Distribute `total` items over `bins` labels as evenly as possible."""
    base = total // len(bins)
    rem = total - base * len(bins)
    out = {}
    for i, b in enumerate(bins):
        out[b] = base + (1 if i < rem else 0)
    return out


def largest_remainder(weights, total):
    """Proportional integer allocation that sums exactly to `total`."""
    s = float(sum(weights.values())) or 1.0
    raw = {k: v / s * total for k, v in weights.items()}
    alloc = {k: int(v) for k, v in raw.items()}
    short = total - sum(alloc.values())
    order = sorted(raw, key=lambda k: (-(raw[k] - int(raw[k])), k))
    for i in range(short):
        alloc[order[i % len(order)]] += 1
    return alloc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--matched", default="out/matched_pairs.jsonl")
    ap.add_argument("--out", default="out")
    ap.add_argument("--n-eval", type=int, default=300)
    ap.add_argument("--n-dev", type=int, default=0)
    ap.add_argument("--floor", type=int, default=40)
    ap.add_argument("--seed", type=int, default=20261114)
    ap.add_argument("--exclude-ids", default=None,
                    help="file of pair_ids that must never enter the evaluation sample: "
                         "previously used pairs (default: <out>/excluded_ids.txt)")
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    rng = random.Random(args.seed)

    exclude_path = args.exclude_ids or os.path.join(args.out, "excluded_ids.txt")
    exclude = set()
    if os.path.exists(exclude_path):
        exclude = {l.strip() for l in open(exclude_path, encoding="utf-8") if l.strip()}
        print("excluding %d previously used pair_ids from %s" %
              (len(exclude), exclude_path))

    by_family = collections.defaultdict(list)
    identical = 0
    seen_excluded = 0
    for line in open(args.matched, encoding="utf-8"):
        r = json.loads(line)
        # A pair already sent to a model has had its output inspected, so it can no longer
        # act as confirmatory evidence.
        if r["pair_id"] in exclude:
            seen_excluded += 1
            continue
        # A pair whose two arms are the same string has a paired difference of zero by
        # construction. The injector refuses to build such a pair; this is the sampler's
        # independent guard in case an older pool is ever passed in.
        if r["natural_code"] == r["synthetic_code"]:
            identical += 1
            continue
        by_family[r["family"]].append(r)

    families = sorted(by_family, key=lambda f: -len(by_family[f]))
    pool_sizes = {f: len(by_family[f]) for f in families}

    # ---- allocation ------------------------------------------------------------
    need = args.n_eval - args.floor * len(families)
    alloc = {f: min(args.floor, pool_sizes[f]) for f in families}
    if need > 0:
        extra = largest_remainder({f: pool_sizes[f] for f in families}, need)
        for f in families:
            alloc[f] = min(pool_sizes[f], alloc[f] + extra[f])
    # if the floor could not be met anywhere, push the shortfall to the largest pools
    shortfall = args.n_eval - sum(alloc.values())
    guard = 0
    while shortfall > 0 and guard < 1000:
        guard += 1
        for f in families:
            if shortfall <= 0:
                break
            if alloc[f] < pool_sizes[f]:
                alloc[f] += 1
                shortfall -= 1

    # ---- draw per family, spread across that family's own length tertiles -------
    eval_pairs, dev_pairs = [], []
    cells = {}

    for f in families:
        fam_pairs = sorted(by_family[f], key=lambda r: r["pair_id"])
        cuts = tertile_cut(fam_pairs)
        strata = collections.defaultdict(list)
        for r in fam_pairs:
            strata[tertile_of(r["natural_line_count"], cuts)].append(r)

        order = ["short", "medium", "long"]
        # dev first, so it can never overlap the evaluation sample
        dev_alloc = spread(min(args.n_dev // len(families), len(fam_pairs)), order)
        for s in order:
            cand = strata[s][:]
            rng.shuffle(cand)
            take = min(dev_alloc[s], len(cand))
            dev_pairs.extend(cand[:take])
            strata[s] = cand[take:]

        ev_alloc = spread(alloc[f], order)
        for s in order:
            cand = strata[s][:]
            rng.shuffle(cand)
            take = min(ev_alloc[s], len(cand))
            eval_pairs.extend(cand[:take])
            strata[s] = cand[take:]  # drawn pairs leave the stratum
            cells[(f, s)] = take

        # top up this family if a tertile ran dry
        got = sum(cells[(f, s)] for s in order)
        if got < alloc[f]:
            leftover = [r for s in order for r in strata[s]]
            rng.shuffle(leftover)
            need_more = alloc[f] - got
            for r in leftover[:need_more]:
                eval_pairs.append(r)
                cells[(f, tertile_of(r["natural_line_count"], cuts))] += 1

    ids = [r["pair_id"] for r in eval_pairs]
    assert len(ids) == len(set(ids)), "duplicate pair in evaluation sample"

    # dev top-up to the requested size, from families with remaining stock
    used = {r["pair_id"] for r in eval_pairs} | {r["pair_id"] for r in dev_pairs}
    if len(dev_pairs) < args.n_dev:
        leftovers = [r for f in families for r in by_family[f]
                     if r["pair_id"] not in used]
        rng.shuffle(leftovers)
        dev_pairs.extend(leftovers[:args.n_dev - len(dev_pairs)])

    # ---- write -----------------------------------------------------------------
    manifest = {
        "seed": args.seed,
        "n_eval_requested": args.n_eval,
        "n_dev_requested": args.n_dev,
        "per_family_floor": args.floor,
        "pool_sizes": pool_sizes,
        "allocation": alloc,
        "identical_pairs_excluded": identical,
        "previously_used_pairs_excluded": seen_excluded,
        "exclusion_file": exclude_path,
        "n_eval_drawn": len(eval_pairs),
        "n_dev_drawn": len(dev_pairs),
        "evaluation_pair_ids": sorted(r["pair_id"] for r in eval_pairs),
        "development_pair_ids": sorted(r["pair_id"] for r in dev_pairs),
    }
    with open(os.path.join(args.out, "sample_manifest.json"), "w",
              encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    for name, rows in (("sample.jsonl", eval_pairs), ("dev_sample.jsonl", dev_pairs)):
        with open(os.path.join(args.out, name), "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

    # ---- report ----------------------------------------------------------------
    L = []
    add = L.append
    add("# Sample report")
    add("")
    add("Frozen seed: `%d`  |  evaluation pairs: %d  |  development pairs: %d" %
        (args.seed, len(eval_pairs), len(dev_pairs)))
    add("")
    add("The sample is not re-drawn for any reason. Pair IDs are fixed in "
        "`sample_manifest.json`.")
    add("")
    add("Contamination guards: **%d** previously used pair_ids excluded (listed in "
        "`excluded_ids.txt`), and **%d** literal-identical pairs excluded."
        % (seen_excluded, identical))
    add("")
    add("## Allocation")
    add("")
    add("| family | pool | floor | allocated | drawn | pool share | sample share |")
    add("|---|---:|---:|---:|---:|---:|---:|")
    tot_pool = sum(pool_sizes.values())
    for f in families:
        n = sum(1 for r in eval_pairs if r["family"] == f)
        add("| %s | %d | %d | %d | %d | %.1f%% | %.1f%% |" %
            (f, pool_sizes[f], args.floor, alloc[f], n,
             100.0 * pool_sizes[f] / tot_pool,
             100.0 * n / max(1, len(eval_pairs))))
    add("")

    add("## family x length tertile (evaluation sample)")
    add("")
    add("| family | short | medium | long | total |")
    add("|---|---:|---:|---:|---:|")
    for f in families:
        row = [sum(1 for r in eval_pairs
                   if r["family"] == f and
                   tertile_of(r["natural_line_count"],
                              tertile_cut(by_family[f])) == s)
               for s in ("short", "medium", "long")]
        add("| %s | %d | %d | %d | %d |" % (f, row[0], row[1], row[2], sum(row)))
    add("")

    add("## Length tertile boundaries (computed inside each family, on the pool)")
    add("")
    add("| family | short <= | medium <= | long > |")
    add("|---|---:|---:|---:|")
    for f in families:
        lo, hi = tertile_cut(by_family[f])
        add("| %s | %d | %d | %d |" % (f, lo, hi, hi))
    add("")

    add("## Continuous length in the evaluation sample")
    add("")
    lines = [r["natural_line_count"] for r in eval_pairs]
    chars = [r["natural_length"] for r in eval_pairs]
    add("| Quantity | lines | characters |")
    add("|---|---:|---:|")
    add("| median | %s | %s |" % (statistics.median(lines), statistics.median(chars)))
    add("| p10 | %d | %d |" % (sorted(lines)[int(0.1 * len(lines))],
                               sorted(chars)[int(0.1 * len(chars))]))
    add("| p90 | %d | %d |" % (sorted(lines)[int(0.9 * len(lines))],
                               sorted(chars)[int(0.9 * len(chars))]))
    add("| max | %d | %d |" % (max(lines), max(chars)))
    add("")

    add("## Why this sample is not prevalence-representative")
    add("")
    add("The floor gives every family at least %d pairs, so large families are "
        "under-weighted relative to the pool. Any overall success rate is therefore a "
        "**balanced-sample** estimate, not a corpus-level estimate. Family-level rates "
        "are descriptive; the confirmatory test is the paired contrast." % args.floor)
    add("")

    rp = os.path.join(args.out, "sample_report.md")
    with open(rp, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L))

    print("manifest        :", os.path.join(args.out, "sample_manifest.json"))
    print("evaluation pairs:", len(eval_pairs), "-> sample.jsonl")
    print("development     :", len(dev_pairs), "-> dev_sample.jsonl")
    print("report          :", rp)


if __name__ == "__main__":
    main()

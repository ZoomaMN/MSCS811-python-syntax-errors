# -*- coding: utf-8 -*-
"""
build_prompts.py — render the frozen prompt for every arm of every sampled pair.

Each matched pair yields TWO calls under the identical prompt:

    <pair_id>__natural     the naturally occurring erroneous snippet
    <pair_id>__synthetic   the injected counterpart, same code, same family, same position

The rendered file is model-agnostic: a runner only has to read `prompt` and write back
`raw_output`. No model call is made here.

Usage
-----
    python build_prompts.py --out out
"""

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def render(template, code):
    return template.replace("{code}", code)


def build(sample_path, template, arm, out_path):
    rows = []
    for line in open(sample_path, encoding="utf-8"):
        r = json.loads(line)
        if arm == "natural":
            code = r["natural_code"]
        else:
            code = r["synthetic_code"]
        rows.append({
            "call_id": "%s__%s" % (r["pair_id"], arm),
            "pair_id": r["pair_id"],
            "arm": arm,
            "family": r["family"],
            "natural_line_count": r["natural_line_count"],
            "natural_length": r["natural_length"],
            "prompt": render(template, code),
        })
    with open(out_path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return len(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="out")
    ap.add_argument("--template", default=os.path.join(HERE, "prompt.txt"))
    args = ap.parse_args()

    template = open(args.template, encoding="utf-8").read()
    if "{code}" not in template:
        print("template has no {code} placeholder", file=sys.stderr)
        return 1

    total = 0
    for sample, prefix in (("sample.jsonl", "eval"), ("dev_sample.jsonl", "dev")):
        path = os.path.join(args.out, sample)
        if not os.path.exists(path):
            continue
        for arm in ("natural", "synthetic"):
            n = build(path, template, arm,
                      os.path.join(args.out, "%s_prompts_%s.jsonl" % (prefix, arm)))
            total += n
            print("%s_prompts_%s.jsonl  %d" % (prefix, arm, n))
    print("total rendered calls:", total)
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Build the eligible pool from the validated natural/synthetic pairs.

Removes previously used pair_ids and the keyword-as-identifier family, then keeps only
pairs whose natural and synthetic snippets are both verified as one isolated repair of
the assigned family (verifier.verify). No model output is read.

Usage: python src/build_pool.py data/validated_pairs.jsonl data
"""
import collections
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from verifier import verify  # noqa: E402

POOL = Path(sys.argv[1])
OUT = Path(sys.argv[2]) if len(sys.argv) > 2 else Path('data')
excluded = {l.strip() for l in open(OUT / 'excluded_ids.txt', encoding='utf-8') if l.strip()}

kept, log = [], collections.Counter()
for line in open(POOL, encoding='utf-8'):
    p = json.loads(line)
    fam = p['family']
    if p['pair_id'] in excluded:
        log['excluded_previously_used'] += 1; continue
    if p['natural_code'] == p['synthetic_code']:
        log['excluded_identical'] += 1; continue
    if fam == 'KEYWORD_AS_IDENTIFIER':
        log['excluded_keyword_family'] += 1; continue
    nf, _ = verify(p['natural_code'], p['human_fix_code'])
    sf, _ = verify(p['synthetic_code'], p['human_fix_code'])
    if not (nf == sf == fam):
        log['not_verified'] += 1; continue
    kept.append(p)
    log['eligible_' + fam] += 1

with open(OUT / 'eligible_pairs.jsonl', 'w', encoding='utf-8') as fh:
    for p in kept:
        fh.write(json.dumps(p, ensure_ascii=False) + '\n')
report = {'eligible_total': len(kept), **dict(sorted(log.items()))}
(OUT / 'pool_report.json').write_text(json.dumps(report, indent=2))
print(json.dumps(report, indent=2))

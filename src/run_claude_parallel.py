"""Parallel driver for run_claude.py: same request(), same record fields, same finalise(); 4 workers.

Usage: python src/run_claude_parallel.py <folder with eval_prompts_*.jsonl>
"""
import json, os, sys, time, threading, hashlib, platform
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import run_claude as rc
if len(sys.argv) < 2:
    sys.exit('usage: python src/run_claude_parallel.py <folder with eval_prompts_*.jsonl>')
OUT = Path(sys.argv[1])
key = os.environ['ANTHROPIC_API_KEY'].strip()
prompts = []
for arm in ('natural', 'synthetic'):
    prompts.extend(json.loads(s) for s in (OUT / ('eval_prompts_%s.jsonl' % arm)).read_text(encoding='utf-8').splitlines() if s.strip())
full_hash = hashlib.sha256(json.dumps(prompts, sort_keys=True).encode()).hexdigest()
path = OUT / 'eval_results.jsonl'
prev = {}
if path.exists():
    for line in path.read_text(encoding='utf-8').splitlines():
        if line.strip():
            r = json.loads(line); prev[r['call_id']] = r
todo = [p for p in prompts if prev.get(p['call_id'], {}).get('status') not in rc.TERMINAL]
manifest = {'provider': 'Anthropic', 'requested_model': rc.MODEL, 'temperature': 'provider_default',
            'thinking': {'type': 'between_tools'}, 'effort': 'high', 'max_tokens': 4096,
            'python': platform.python_version(), 'set': 'eval', 'prompt_sha256': full_hash,
            'driver': 'par_claude.py (4 concurrent workers, same request and finalise)',
            'started_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}
(OUT / 'eval_run_manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
print('Expected: %d | Remaining: %d' % (len(prompts), len(todo)), flush=True)
lock = threading.Lock(); n = [0]
def work(p):
    rec = {k: p[k] for k in ('call_id', 'pair_id', 'arm', 'family')}
    rec.update(raw_prompt=p['prompt'], requested_model=rc.MODEL, temperature=None,
               thinking_mode='between_tools', effort='high', max_tokens=4096,
               requested_at_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()))
    result = rc.request(p['prompt'], key)
    rec = rc.finalise(rec, result)
    with lock:
        with path.open('a', encoding='utf-8') as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + '\n')
        n[0] += 1
        if result.get('transport_error'):
            print('ERROR', p['call_id'], result['transport_error'], flush=True)
        if n[0] % 20 == 0 or n[0] == len(todo):
            print('Completed %d/%d' % (n[0], len(todo)), flush=True)
with ThreadPoolExecutor(max_workers=4) as ex:
    list(ex.map(work, todo))
print('Done', flush=True)

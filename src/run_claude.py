"""Run the Claude evaluation on the rendered prompts (sequential driver)."""
import argparse
import hashlib
import json
import os
import platform
from pathlib import Path
import time
import urllib.error
import urllib.request

from run_deepseek import finalise

MODEL = 'claude-sonnet-5-5'
URL = 'https://api.anthropic.com/v1/messages'
TERMINAL = {'ok', 'empty_content', 'malformed'}


def request(prompt, key):
    payload = {'model': MODEL, 'max_tokens': 4096,
               'thinking': {'type': 'between_tools'},
               'output_config': {'effort': 'high'},
               'messages': [{'role': 'user', 'content': prompt}]}
    started = time.monotonic()
    for attempt in range(1, 6):
        req = urllib.request.Request(URL, data=json.dumps(payload).encode(), method='POST',
              headers={'x-api-key': key, 'anthropic-version': '2023-06-01',
                       'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(req, timeout=180) as response:
                raw = response.read().decode('utf-8')
                request_id = response.headers.get('request-id')
            data = json.loads(raw)
            content = ''.join(b['text'] for b in data['content'] if b['type'] == 'text')
            usage = data.get('usage', {})
            return {'transport_error': None, 'raw_response': raw, 'content': content,
                    'returned_model': data.get('model'), 'request_id': request_id,
                    'system_fingerprint': None, 'finish_reason': data.get('stop_reason'),
                    'prompt_tokens': usage.get('input_tokens'),
                    'completion_tokens': usage.get('output_tokens'),
                    'total_tokens': usage.get('input_tokens', 0) + usage.get('output_tokens', 0),
                    'latency_s': round(time.monotonic() - started, 3), 'attempts': attempt}
        except urllib.error.HTTPError as exc:
            code = exc.code
            if code not in (408, 429, 500, 502, 503, 504, 529):
                return {'transport_error': f'HTTP {code}', 'fatal': True, 'attempts': attempt}
            error = f'HTTP {code}'
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            error = 'Connection failure'
        except (ValueError, KeyError, TypeError):
            return {'transport_error': 'Unexpected API response', 'fatal': True, 'attempts': attempt}
        if attempt < 5:
            time.sleep(min(60, 2 ** attempt))
    return {'transport_error': error, 'fatal': False, 'attempts': 5}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--set', choices=['dev', 'eval'], default='eval')
    ap.add_argument('--limit', type=int, default=0)
    args = ap.parse_args()
    key = os.environ.get('ANTHROPIC_API_KEY', '').strip()
    if not key:
        print('ANTHROPIC_API_KEY is missing.')
        return 2
    prompts = []
    for arm in ('natural', 'synthetic'):
        prompts.extend(json.loads(s) for s in (args.out / f'{args.set}_prompts_{arm}.jsonl').read_text(encoding='utf-8').splitlines() if s.strip())
    full_prompt_hash = hashlib.sha256(json.dumps(prompts, sort_keys=True).encode()).hexdigest()
    if args.limit < 0:
        raise ValueError('Limit must be nonnegative.')
    if args.limit:
        prompts = prompts[:args.limit]
    result_path = args.out / f'{args.set}_results.jsonl'
    previous = {}
    if result_path.exists():
        for line in result_path.read_text(encoding='utf-8').splitlines():
            if line.strip():
                r = json.loads(line)
                previous[r['call_id']] = r
    for p in prompts:
        old = previous.get(p['call_id'])
        if old and (old.get('raw_prompt') != p['prompt'] or old.get('requested_model') != MODEL
                    or old.get('thinking_mode') != 'between_tools'
                    or old.get('effort') != 'high' or old.get('max_tokens') != 4096):
            raise ValueError('Existing results have a different prompt or model.')
    todo = [p for p in prompts if previous.get(p['call_id'], {}).get('status') not in TERMINAL]
    manifest = {'provider': 'Anthropic', 'requested_model': MODEL, 'temperature': 'provider_default',
                'thinking': {'type': 'between_tools'}, 'effort': 'high', 'max_tokens': 4096,
                'python': platform.python_version(), 'set': args.set,
                'prompt_sha256': full_prompt_hash,
                'started_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}
    (args.out / f'{args.set}_run_manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print(f'Expected: {len(prompts)} | Remaining: {len(todo)}', flush=True)
    with result_path.open('a', encoding='utf-8') as fh:
        for i, p in enumerate(todo, 1):
            rec = {k: p[k] for k in ('call_id', 'pair_id', 'arm', 'family')}
            rec.update(raw_prompt=p['prompt'], requested_model=MODEL, temperature=None,
                       thinking_mode='between_tools', effort='high', max_tokens=4096,
                       requested_at_utc=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()))
            result = request(p['prompt'], key)
            rec = finalise(rec, result)
            fh.write(json.dumps(rec, ensure_ascii=False) + '\n')
            fh.flush()
            if result.get('transport_error'):
                print('Stopped:', result['transport_error'], flush=True)
                return 2
            if result.get('returned_model') != MODEL:
                print('Stopped: unexpected returned model.', flush=True)
                return 2
            if i % 10 == 0 or i == len(todo):
                print(f'Completed {i}/{len(todo)}', flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

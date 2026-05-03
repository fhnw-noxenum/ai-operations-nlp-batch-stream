import argparse, time
import httpx

p = argparse.ArgumentParser()
p.add_argument('--url', default='http://localhost:8000')
p.add_argument('--prompt', default='Erkläre Batch und Stream Inference kurz.')
args = p.parse_args()

t0 = time.perf_counter()
first = None
with httpx.stream('GET', f'{args.url}/v1/stream', params={'prompt': args.prompt, 'max_tokens': 50}, timeout=60) as r:
    r.raise_for_status()
    for line in r.iter_lines():
        if not line.startswith('data: '):
            continue
        data = line[6:]
        if first is None:
            first = time.perf_counter() - t0
            print(f'\nTTFT={first:.3f}s\n')
        if data == '[DONE]':
            break
        print(data, end='', flush=True)
print(f'\nE2E={time.perf_counter() - t0:.3f}s')

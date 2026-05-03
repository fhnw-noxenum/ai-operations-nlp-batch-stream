import argparse, base64, time
import httpx

p = argparse.ArgumentParser()
p.add_argument('--url', default='http://localhost:8000')
p.add_argument('--prompt', default='Erzeuge drei kurze Sätze. Jeder Satz soll Audio simulieren.')
args = p.parse_args()

t0 = time.perf_counter()
first = None
bytes_total = 0
with httpx.stream('GET', f'{args.url}/v1/audio', params={'prompt': args.prompt, 'max_tokens': 60}, timeout=60) as r:
    r.raise_for_status()
    for line in r.iter_lines():
        if not line.startswith('data: '):
            continue
        data = line[6:]
        if data == '[DONE]':
            break
        if first is None:
            first = time.perf_counter() - t0
            print(f'TTFA={first:.3f}s')
        chunk = base64.b64decode(data)
        bytes_total += len(chunk)
        print('.', end='', flush=True)
print(f'\nbytes={bytes_total} E2E={time.perf_counter() - t0:.3f}s')

import argparse, statistics, time
import httpx

p = argparse.ArgumentParser()
p.add_argument('--n', type=int, default=10)
p.add_argument('--url', default='http://localhost:8000')
args = p.parse_args()

latencies = []
for i in range(args.n):
    t0 = time.perf_counter()
    r = httpx.post(f'{args.url}/v1/generate', json={'prompt': f'Test {i}', 'max_tokens': 40}, timeout=60)
    r.raise_for_status()
    latencies.append(time.perf_counter() - t0)
print(f'n={args.n} p50={statistics.median(latencies):.3f}s p95={statistics.quantiles(latencies, n=20)[18]:.3f}s')

import http from 'k6/http';
import { check, sleep } from 'k6';

const BASE_URL = __ENV.BASE_URL || 'http://localhost:8000';
export const options = {
  scenarios: { sync: { executor: 'ramping-vus', stages: [
    { duration: '20s', target: 5 }, { duration: '40s', target: 15 }, { duration: '20s', target: 0 }
  ]}},
  thresholds: { http_req_duration: ['p(95)<8000'], http_req_failed: ['rate<0.02'] },
};

export default function () {
  const payload = JSON.stringify({ prompt: `sync prompt ${__VU}-${__ITER}`, max_tokens: 40 });
  const res = http.post(`${BASE_URL}/v1/generate`, payload, { headers: { 'Content-Type': 'application/json' } });
  check(res, { '200': r => r.status === 200, 'has text': r => r.json('text') !== '' });
  sleep(0.2);
}

import { check, sleep } from 'k6';
import http from 'k6/http';

const BASE_URL = __ENV.BASE_URL || 'http://localhost:8000';
export const options = {
  scenarios: {
    batch: {
      executor: 'ramping-vus', stages: [
        { duration: '20s', target: 5 }, { duration: '40s', target: 20 }, { duration: '20s', target: 0 }
      ]
    }
  },
  thresholds: { http_req_duration: ['p(95)<6000'], http_req_failed: ['rate<0.02'] },
};

export default function () {
  const prompts = Array.from({ length: 4 }, (_, i) => `batch prompt ${__VU}-${__ITER}-${i}`);
  const payload = JSON.stringify({ prompts, max_tokens: 40 });
  const res = http.post(`${BASE_URL}/v1/batch`, payload, { headers: { 'Content-Type': 'application/json' } });
  check(res, { '200': r => r.status === 200, '4 results': r => (r.json('results') || []).length === 4 });
  sleep(0.2);
}

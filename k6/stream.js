import { check, sleep } from 'k6';
import http from 'k6/http';
import { Trend } from 'k6/metrics';

const BASE_URL = __ENV.BASE_URL || 'http://localhost:8000';
const ttftProxy = new Trend('ttft_proxy_ms');

export const options = {
  scenarios: {
    stream: {
      executor: 'ramping-vus', stages: [
        { duration: '20s', target: 5 }, { duration: '40s', target: 20 }, { duration: '20s', target: 0 }
      ]
    }
  },
  thresholds: { ttft_proxy_ms: ['p(95)<1200'], http_req_failed: ['rate<0.02'] },
};

export default function () {
  const url = `${BASE_URL}/v1/stream?prompt=${encodeURIComponent('stream prompt ' + __VU + '-' + __ITER)}&max_tokens=40`;
  const res = http.get(url, { responseType: 'text' });
  ttftProxy.add(res.timings.waiting);
  check(res, { '200': r => r.status === 200, 'done': r => r.body.includes('[DONE]') });
  sleep(0.2);
}

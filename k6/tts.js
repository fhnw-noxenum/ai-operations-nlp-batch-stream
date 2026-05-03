import { check, sleep } from 'k6';
import http from 'k6/http';
import { Trend } from 'k6/metrics';

const BASE_URL = __ENV.BASE_URL || 'http://localhost:8000';
const ttfaProxy = new Trend('ttfa_proxy_ms');

export const options = {
  scenarios: {
    tts: {
      executor: 'ramping-vus', stages: [
        { duration: '20s', target: 3 }, { duration: '40s', target: 10 }, { duration: '20s', target: 0 }
      ]
    }
  },
  thresholds: { ttfa_proxy_ms: ['p(95)<1800'], http_req_failed: ['rate<0.02'] },
};

export default function () {
  const prompt = 'Erzeuge kurze Sätze für Audio Streaming. Satz eins. Satz zwei.';
  const res = http.get(`${BASE_URL}/v1/audio?prompt=${encodeURIComponent(prompt)}&max_tokens=50`, { responseType: 'text' });
  ttfaProxy.add(res.timings.waiting);
  check(res, { '200': r => r.status === 200, 'done': r => r.body.includes('[DONE]') });
  sleep(0.2);
}

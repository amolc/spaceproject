// performance_test.js - simple k6 script for Space Internet Service Provider
import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  stages: [
    { duration: '30s', target: 50 }, // ramp-up to 50 users
    { duration: '1m', target: 200 }, // sustain 200 users
    { duration: '30s', target: 0 }, // ramp-down
  ],
  thresholds: {
    http_req_duration: ['p(95)<200'], // 95% of requests should be < 200ms
  },
};

function randomCoord() {
  const lat = Math.random() * 180 - 90; // -90 to 90
  const lon = Math.random() * 360 - 180; // -180 to 180
  return { lat, lon };
}

export default function () {
  const { lat, lon } = randomCoord();
  const res = http.get(`http://127.0.0.1:8000/api/orbit/nearest/?lat=${lat}&lon=${lon}`);
  check(res, {
    'status is 200': (r) => r.status === 200,
    'response contains satellites': (r) => r.body && r.body.length > 0,
  });
  sleep(0.2);
}

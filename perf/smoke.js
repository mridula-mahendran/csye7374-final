import http from "k6/http";
import { check, sleep } from "k6";

// Base URL and load shape are configurable from the environment so the same
// script runs locally and in CI.
const BASE = __ENV.BASE_URL || "http://localhost:8000";

export const options = {
  vus: Number(__ENV.VUS || 10),
  duration: __ENV.DURATION || "20s",
  // These thresholds are the performance gate. If p95 latency or the error rate
  // exceed budget, k6 exits non-zero and the CI job fails. This is what catches
  // the latency-regression demo (Bug 4).
  thresholds: {
    http_req_failed: ["rate<0.01"],
    http_req_duration: ["p(95)<500"],
    "http_req_duration{endpoint:list}": ["p(95)<600"],
  },
};

export function setup() {
  const email = `k6_${Date.now()}@example.com`;
  const password = "Str0ngPassw0rd!";
  http.post(`${BASE}/auth/register`, JSON.stringify({ email, password }), {
    headers: { "Content-Type": "application/json" },
  });
  // OAuth2 password flow expects form-encoded data; passing an object makes k6
  // send application/x-www-form-urlencoded.
  const res = http.post(`${BASE}/auth/token`, { username: email, password });
  return { token: res.json("access_token") };
}

export default function (data) {
  const authHeaders = { headers: { Authorization: `Bearer ${data.token}` } };

  const health = http.get(`${BASE}/health`);
  check(health, { "health is 200": (r) => r.status === 200 });

  const list = http.get(
    `${BASE}/tasks?limit=20`,
    Object.assign({ tags: { endpoint: "list" } }, authHeaders),
  );
  check(list, { "list is 200": (r) => r.status === 200 });

  sleep(0.5);
}

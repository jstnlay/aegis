/**
 * TC-SYS-03 load-test harness (PH11 Cycle 4).
 *
 * This is the missing harness the QA log asked for: it logs in once, then
 * hammers two read endpoints (health + one authenticated list) and fails if
 * error rate or p(95) latency crosses the bars below.
 *
 * Run against a DEPLOYED environment (local throttling differs):
 *
 *   k6 run -e BASE_URL=https://<deployed-host> \
 *     -e AEGIS_EMAIL=<admin email> -e AEGIS_PASSWORD=<password> \
 *     backend/scripts/loadtest.js
 *
 * Tune VUS / DURATION with -e too. Thresholds are starting bars, not spec —
 * adjust after the first run and record the run in the test log.
 */
import http from "k6/http";
import { check, sleep } from "k6";

const BASE_URL = __ENV.BASE_URL || "http://localhost:8000";
const EMAIL = __ENV.AEGIS_EMAIL || "";
const PASSWORD = __ENV.AEGIS_PASSWORD || "";

export const options = {
  vus: Number(__ENV.VUS || 20),
  duration: __ENV.DURATION || "5m",
  thresholds: {
    http_req_failed: ["rate<0.01"],
    http_req_duration: ["p(95)<2000"],
  },
};

// Login once (VU 0) and share the token with every VU.
export function setup() {
  if (!EMAIL || !PASSWORD) {
    throw new Error("Set AEGIS_EMAIL and AEGIS_PASSWORD (deployed QA account).");
  }
  const res = http.post(
    `${BASE_URL}/api/v1/auth/login/`,
    JSON.stringify({ email: EMAIL, password: PASSWORD }),
    { headers: { "Content-Type": "application/json" } }
  );
  check(res, { "login returns 200": (r) => r.status === 200 });
  const body = res.json();
  // Accept either SimpleJWT shape: {access} or {access_token}.
  const token = body.access || body.access_token;
  if (!token) throw new Error(`Login did not return a token: ${res.body}`);
  return { token };
}

export default function (data) {
  const headers = { Authorization: `Bearer ${data.token}` };

  check(http.get(`${BASE_URL}/api/v1/health/`), {
    "health 200": (r) => r.status === 200,
  });

  check(http.get(`${BASE_URL}/api/v1/academics/sections/`, { headers }), {
    "sections 200": (r) => r.status === 200,
  });

  sleep(1);
}

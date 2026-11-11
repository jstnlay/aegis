/**
 * TC-SYS-03 load-test harness (PH11 Cycle 4).
 *
 * This is the missing harness the QA log asked for: it logs in, then hammers
 * one authenticated list endpoint and fails if the error rate or p(95)
 * latency crosses the bars below.
 *
 * Run against a DEPLOYED environment (local throttling differs):
 *
 *   k6 run -e BASE_URL=https://<deployed-host> \
 *     -e AEGIS_EMAILS=<email1>,<email2>,<email3> -e AEGIS_PASSWORD=<password> \
 *     --summary-export=docs/qa/TC-SYS-03-summary.json \
 *     backend/scripts/loadtest.js
 *
 * Why several accounts
 * --------------------
 * The rate limits are real and they are per client: 600 requests a minute
 * for an authenticated user, 120 for an anonymous probe. One account and one
 * address therefore have a ceiling, and a load test that ignores the ceiling
 * measures the limiter instead of the system - every request past it answers
 * 429, which k6 counts as a failure, and the run fails its own error-rate
 * threshold. So the harness spreads its virtual users over several accounts
 * (each account has its own bucket) and probes /health/ once per user rather
 * than once per iteration.
 *
 * Tune VUS / DURATION with -e too. Thresholds are starting bars, not spec -
 * adjust after the first run and record the run in the test log.
 */
import http from "k6/http";
import { check, sleep } from "k6";

const BASE_URL = __ENV.BASE_URL || "http://localhost:8000";
const EMAILS = (__ENV.AEGIS_EMAILS || __ENV.AEGIS_EMAIL || "")
  .split(",")
  .map((value) => value.trim())
  .filter((value) => value.length > 0);
const PASSWORD = __ENV.AEGIS_PASSWORD || "";

export const options = {
  vus: Number(__ENV.VUS || 20),
  duration: __ENV.DURATION || "5m",
  thresholds: {
    http_req_failed: ["rate<0.01"],
    http_req_duration: ["p(95)<2000"],
  },
};

function login(email) {
  const res = http.post(
    `${BASE_URL}/api/v1/auth/login/`,
    JSON.stringify({ email: email, password: PASSWORD }),
    { headers: { "Content-Type": "application/json" } }
  );
  check(res, { "login returns 200": (r) => r.status === 200 });
  const body = res.json();
  // Accept either SimpleJWT shape: {access} or {access_token}.
  const token = body.access || body.access_token;
  if (!token) throw new Error(`Login did not return a token for ${email}: ${res.body}`);
  return token;
}

// Log in once per account and share the tokens with every virtual user.
export function setup() {
  if (!EMAILS.length || !PASSWORD) {
    throw new Error(
      "Set AEGIS_EMAILS (comma separated) and AEGIS_PASSWORD (deployed QA accounts)."
    );
  }
  const tokens = EMAILS.map(login);

  // The liveness probe once, not per iteration: it is throttled per address
  // at 120 a minute, which a virtual user loop crosses immediately.
  const health = http.get(`${BASE_URL}/api/v1/health/`);
  check(health, { "health 200": (r) => r.status === 200 });

  return { tokens };
}

export default function (data) {
  // Spread the virtual users over the accounts so no single bucket is
  // exhausted and the numbers measure the service, not the limiter.
  const token = data.tokens[__VU % data.tokens.length];
  const headers = { Authorization: `Bearer ${token}` };

  check(http.get(`${BASE_URL}/api/v1/academics/sections/`, { headers }), {
    "sections 200": (r) => r.status === 200,
  });

  sleep(1);
}

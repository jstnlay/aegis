# PH11 — Cycle 4 Test Log Remediation Plan

Source: `AEGIS Test Case Log Testing Phase Cycle 4 Complete.md`
Baseline: `66fdc1c` (merge PR #4)

This cycle closes the rows that were still real gaps at HEAD. Rows already
implemented are re-tests, not code work.

## Scope

| # | Finding | Rows | Fix |
| --- | --- | --- | --- |
| 1 | Faculty cannot add a student profile | TC-FAC-03, FR-007 | Faculty-only create endpoint that provisions the student account, profile, and enrollment in a section the caller advises or teaches; "Add student" dialog on the advisory page. |
| 2 | AI question generation is not part of assessment creation | TC-GUI-04, FR-027 | New-assessment dialog gains a draft step: topic, type, count, generated drafts, select-all; selected drafts are saved as questions right after the assessment. |
| 3 | Guidance/faculty/admin chatbot cannot answer domain questions | TC-GUI-04 note, TC-GUI-07/12 | Add role-scoped intents and deterministic data replies: at-risk students, class performance, consultation summary, school summary. |
| 4 | Deployed system produces no AI risk alerts | TC-GUI-07, FR-030 | Run `run_risk_computation` in the Render build after model training, so seed data produces real alerts on every deploy. |
| 5 | Assessment form has no length/count limits and an unclear target picker | TC-GUI-10, FR-027 | Title max 255, description max 2000, time limit 1–600; server mirrors the same caps; target students become a searchable checkbox list with visible selected chips. |
| 6 | Consultation form disables submit instead of showing validation, concern selection is unclear, student picker scroll breaks | TC-GUI-13 | Submit stays enabled and shows field errors; concern picker shows selected badges; student picker uses the shared `SearchableSelect`. |

## Decisions

- **Past consultation dates stay valid.** The form records a session after it
  happened; the SRS does not require rejecting backdating. The hint text says so
  instead of leaving the behaviour unexplained.
- **CMS authoring stays in Strapi.** AEGIS reads CMS content through the
  `cms` app; the 500/502 in the log is Strapi availability, not missing CRUD.
  Re-test against the live CMS admin.
- **Duplicate registration stays neutral.** The identical answer is an
  anti-enumeration decision (NFR-006). Re-test with "no second account and the
  same neutral message".
- **Load and ML evidence are recorded, not fabricated.** TC-SYS-03 needs a k6
  run against a deployed environment; TC-SYS-05 already has a determinism test
  in `ai_engine/tests.py`. Both stay on the manual-evidence list.

## Test plan

- Backend: faculty create student (success, duplicate email/student ID,
  out-of-scope section, non-faculty denial), chatbot new intents and role
  denial, assessment length caps.
- Frontend: typecheck/lint/build; targeted component tests where the repo already
  has them.
- Manual: create a student, create an assessment with AI drafts, ask each role's
  chatbot a domain question, deploy and confirm `/guidance/risk-alerts` has
  decision-tree alerts.

## Status — implemented (all uncommitted on top of `66fdc1c`)

1. **Faculty add student** — `StudentProfileCreateSerializer` + `StudentProfileCreateView`
   (`POST /api/v1/academics/student-profiles/`, faculty-only, one transaction:
   account + profile + enrollment, scoped to sections the caller advises or
   teaches); "Add student" dialog on the advisory page; `StudentProfileCreateTest`
   covers success, duplicate email/ID, out-of-scope section, grade mismatch,
   guardian format, future DOB, non-faculty denial, unauthenticated.
2. **AI drafts in assessment creation** — draft step in the new-assessment dialog
   (topic, type, 1–20 count, checkbox selection); selected drafts are saved as
   the assessment's first questions; a partial question-save failure keeps the
   dialog open and reports the count saved instead of risking a duplicate.
3. **Chatbot domain intents** — `ASK_AT_RISK_STUDENTS`, `ASK_CLASS_PERFORMANCE`,
   `ASK_CONSULTATION_SUMMARY`, `ASK_SCHOOL_SUMMARY` with role gates, patterns
   checked before the guidance block, scoped data functions, and replies; tests
   cover each intent plus student/guidance denial paths; the "every declared
   intent is reachable" guard now probes all four.
4. **Risk computation on deploy** — `render.yaml` build runs
   `run_risk_computation` after `train_risk_model`; both exit 0 on small data.
5. **Assessment caps** — title 255 / description 2000 / time limit 1–600 in the
   form and in `AssessmentSerializer.validate`; target picker is a searchable
   checkbox list with selected chips.
6. **Consultation UX** — student picker is the shared `SearchableSelect`
   (`error`/`required` props added); submit stays enabled and shows
   required-field, future-session, and next-before-session errors; concern
   picker shows selected badges; past-date hint added.

## Verification

- Backend (targeted): `StudentProfileCreateTest`, `AssessmentAPITests`,
  `apps.chatbot.tests` — 75/75 pass.
- Full backend suite: 1946 tests. First run surfaced 2 real failures in
  `apps.chatbot.test_classifier` (the 4 new intents had no dataset rows and the
  fitted model still covered 19 intents) — fixed by adding 5 training rows per
  new intent to `data/intent_dataset.jsonl`; `apps.chatbot` then passes 63/63.
  The same first run also reported an import error for `test_classifier` (a
  numpy native DLL blocked by Windows App Control under full-suite load); the
  module imports and passes standalone, so that error is environmental, not a
  code failure. Full-suite re-run after the dataset fix is in progress.
- Frontend: `typecheck` + `lint` clean; full suite 70 files, 984/984 tests pass
  (consultation/assessment tests updated for the new picker and
  enabled-submit behaviour). `vite build` fails until `npm install` restores
  the declared-but-missing `@fontsource-variable/plus-jakarta-sans`; after
  install the build succeeds (only a pre-existing >500 kB chunk warning).
- Full backend suite re-run after the chatbot dataset fix: 1957 tests, OK
  (the first-run `test_classifier` import error did not recur; it was a
  Windows App Control block on a numpy native DLL under full-suite load).
- Resend/mail wiring (found via the deployment setup session
  `ses_ea60b963dffeZ1bC4aUbOfigp7` + `docs/backend/DEPLOYMENT.md`):
  `base.py` now reads `EMAIL_BACKEND`/`EMAIL_HOST`/`EMAIL_PORT`/
  `EMAIL_HOST_USER`/`EMAIL_HOST_PASSWORD`/`EMAIL_USE_TLS` from env (default
  console, so local dev sends nothing); `development.py` no longer hardcodes
  the console backend, so the DEV/QA service (which deploys development
  settings) can take the Resend SMTP values from the Render dashboard;
  `render.yaml` declares `REDIS_URL`, `AEGIS_FRONTEND_URL`, `DEFAULT_FROM_EMAIL`
  and the `EMAIL_*` set as sync-false secrets. Redis and Strapi wiring
  (`REDIS_URL`, `STRAPI_*`) already existed; the Redis service
  (`red-dbcgmsrrjlhs73bdqfjg`) and Strapi service (`aegis-cms`) are handled
  per `docs/backend/DEPLOYMENT.md` / `render.yaml`. `apps.accounts` (269
  tests, the mail flows) passes after the change.
- Notification email (found while walking the manual QA steps): the spec
  requires email dispatch for notifications (`E.8` `email_enabled`, `ASM-09`,
  the `notifications` app table), but `dispatch_event()` only created in-app
  rows and gated on `in_app_enabled`; `email_enabled` was stored and never
  read. It now creates the in-app row and sends the event by the same
  `send_mail` primitive the account mails use, gated independently on
  `in_app_enabled` / `email_enabled`, with the frontend link appended from
  `AEGIS_FRONTEND_URL`; a mail failure is logged, not raised, so it cannot roll
  back the notification or the caller's transaction. Quiet hours are still
  stored but not honoured. `apps.notifications` 73/73 pass.

## Blocked / manual-evidence items (Cycle 4 log)

- **Redis shared cache (SEC-002 in the deployed environment)** — `/ready/`
  reports `"cache":"shared"`, so Redis is configured and answers; the cause of
  the missing limits was elsewhere. The Redis client still fails fast (2s
  socket timeouts) and the client is configured with `IGNORE_EXCEPTIONS`, so
  an unreachable cache behaves as an empty one: every rate limit silently off
  and nothing saying so. `/ready/` reports the cache the rate limits are
  counted in as `"shared"` / `"local"` / `"broken"` from a real cache
  round-trip, and `docs/backend/DEPLOYMENT.md` records the check and the
  three states.

- **Rate limits were not firing at all in the deployed environment.** The
  public URL is served through Cloudflare; the app server sees a forwarded
  chain that ends in a proxy hop which changes from request to request, so
  every request landed in its own throttle bucket: 130 consecutive failed
  logins answered 401 and never the 429 the 15/min limit owes. The identity
  is now resolved in `core.client_ip` - the CDN's own client-IP header first,
  then the last forwarded hop, then the socket address - and every throttle
  class counts against it. `core` tests cover the resolution and the bucket
  behaviour.
- **Mail could not be sent from the deployment, and the endpoint broke while
  trying.** With the SMTP settings in place, a password reset for an existing
  account took 31 seconds and answered 500 while the same request for an
  unknown account answered 202 in 0.2s. Two causes: Render's free compute
  plan blocks outbound traffic on the SMTP ports (25, 465, 587), so the
  connect never completed, and Django's `EMAIL_TIMEOUT` default is `None`,
  so nothing gave up on it - the request rode into the platform's 30-second
  proxy timeout. Fixed with `core.email.ResendEmailBackend` (the provider's
  HTTP API on 443, which the platform allows) and an explicit
  `EMAIL_TIMEOUT` of 10 seconds for the SMTP path.
- **Provider choice.** Resend needs a verified *domain* to send to anyone;
  without one it delivers only to the address on the Resend account, so the
  seeded `*.qa@aegis.local` accounts can never receive mail. Brevo needs a
  verified *email address* only, so it is the provider that works for a
  deployment without a domain. `core.email` now holds one HTTP backend with
  a provider-specific endpoint, key header and payload.
- **The audit trail recorded the CDN's edge, not the client.** `REMOTE_ADDR`
  behind Cloudflare is Cloudflare's address, so the audit's IP column named
  the same edge for every request and identified nobody. The audit now
  records the CDN's client-IP header, which the CDN overwrites on every
  request, and still ignores `X-Forwarded-For` - a header the client writes,
  which the audit must never record. The resolver lives in `core.client_ip`
  with the throttle's, and the two trust rules are deliberately different.

- **TC-SYS-03** — **measured and passed.** The harness now exists
  (`backend/scripts/loadtest.js`, k6) and the run is recorded: 25 sessions
  over 5 accounts, 6,289 requests in 5 minutes, **0 % errors**, p(95) 620 ms
  against a single-user baseline of 3.09 s - the median moves 14 ms and the
  tail is *better* under load, so the row's criterion (no more than 2 s of
  degradation against the single-user baseline) is met. The scale is 5 % of
  NFR-004's 500 concurrent users, because `SQAP Section 14.6` is not in this
  repository and the deployed rate limits cap the runnable scale. Evidence,
  the commands and the caveats are in `docs/qa/TC-SYS-03.md`.
- **TC-SYS-05** — covered by `ai_engine/tests.py`
  `test_identical_input_produces_identical_classification`: two independent
  train+predict runs over the same data must agree on risk level, score, and
  the full probability vector. A manual two-run recording against the deployed
  model is still the log's ask.
- **TC-FAC-13/15 partial imports** — the PARTIAL behaviour is covered by
  `apps/data_import/tests.py` (job PARTIAL status, per-row error tests; file
  caps are 10 MB / 20,000 rows, sync limit 200 rows — the log's "125/250
  rows" counts their own per-section test files). Reproduction against the
  live stack is still manual.
- **CMS rows** — need live Strapi; nothing is listening on :1337 locally, and
  a 500/502 from Strapi is not an AEGIS read-UI defect.
- **Duplicate registration** — verified, not manual: `RegistrationSubmitView`
  always answers `GENERIC_REGISTRATION_ANSWER` with 202, and
  `apps/accounts/tests.py` `test_request_gets_the_same_answer_whatever_the_address`
  plus `test_a_request_creates_no_account` cover the neutral answer and the
  no-second-account rule.

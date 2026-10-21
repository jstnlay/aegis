# Backend review, hardening and scalability

Date: 2026-10-21. Scope: `backend/aegis_backend` (Django 5.2, DRF, PostgreSQL).

## What was already strong

The review found a backend that had already been through a security pass, so
most of the work below is closing specific gaps rather than rewriting
anything. Verified by reading the code:

- Role-based permissions (`core/permissions.py`) with object-level checks
  for student, parent and faculty ownership.
- Per-endpoint throttles for login, token refresh, the Strapi webhook, data
  import, controlled export and the password change.
- Onboarding gate: a provisioned account with `must_change_password` can
  only reach the password-change and logout routes.
- Audit trail on writes, append-only, with a request-scoped actor cell.
- CSV export cells sanitized against formula injection; the Strapi webhook
  compares its shared secret with `hmac.compare_digest`; uploaded import
  files are validated by content, not by extension, before parsing.
- `select_related`/`prefetch_related` on the list querysets, so the list
  endpoints are not N+1.

## Security changes

1. **Password change is now rate-limited** (`core/throttling.py`,
   `apps/accounts/views.py`). The endpoint verifies the current password, so
   it is unreachable without a token — but a stolen access token could
   otherwise guess the current password as fast as the network allows. The
   limit is 10/min, keyed on the account rather than the client IP: the
   threat model is one compromised token, and a shared office IP must not
   lock out every account behind it.
2. **Production refuses to start without a host allow-list**
   (`config/settings/production.py`). An empty list takes the API down and
   `"*"` accepts any Host header, which is how a Host-header injection
   reaches the application. Neither is a deployable default.
3. **Production refuses to start with a weak secret key.** Django's deploy
   check reports a short or auto-generated key as a warning, and a pipeline
   that only reads warnings still ships it. Here it is a start-up failure:
   at least 50 characters, more than four distinct characters, and not
   `django-insecure-`.
4. **Production security headers completed** — `SECURE_PROXY_SSL_HEADER` (the
   deployment sits behind a TLS terminator, so the scheme has to come from
   the proxy), `SECURE_REFERRER_POLICY`, `SECURE_CROSS_ORIGIN_OPENER_POLICY`,
   `SameSite` on the session and CSRF cookies.
5. **The Django admin site is not published in production** by default. It
   authenticates on `is_staff` and knows nothing about the five-role model,
   so it is a second authority that AEGIS accounts (`is_staff=False`) cannot
   use. A deployment that wants it sets `DJANGO_ENABLE_ADMIN_SITE=true`.
6. **Health and readiness probes** (`core/health.py`, `core/api_v1.py`):
   `GET /api/v1/health/` is liveness and touches nothing outside the
   process; `GET /api/v1/ready/` checks the database and answers 503 when it
   cannot be reached. Both are anonymous, both report a boolean, and neither
   echoes the database error, host or credentials. The readiness probe opens
   a connection, so it carries its own rate cap.
7. **The local secret key was rotated** (`backend/.env`, not committed).
   `manage.py check --deploy` had flagged it (security.W009) — it was short
   and low-entropy. Rotating it invalidates issued access tokens, so anyone
   signed in on the dev instance signs in again.

## Scalability changes

1. **Persistent database connections** (`config/settings/base.py`):
   `CONN_MAX_AGE=60` and `CONN_HEALTH_CHECKS=True`. Without them Django
   opens and closes a PostgreSQL connection per request, and the first thing
   to run out under load is database connections.
2. **Nine database indexes** on the columns the hot queries filter and group
   by, with migrations (`accounts.0005`, `academics.0004`, `attendance.0002`,
   `guidance.0005`):
   - `grade_status_idx`, `grade_student_period_idx` — the dashboard reads a
     student's grades for one period, analytics reads every finalized grade.
   - `enroll_section_active_idx` — the section roster and the active
     enrollment count per section.
   - `attend_student_status_idx`, `attend_date_idx` — the attendance summary
     counts by status, the school-wide trend groups by date.
   - `risk_score_status_idx`, `risk_score_student_time_idx` — the risk
     aggregates read the latest computable scores.
   - `risk_alert_status_idx`, `risk_alert_status_time_idx` — open alerts are
     counted per student and per day for the 30-day trend.
   - `user_role_idx` — every role-scoped queryset filters on `role`.
3. **The cache is named explicitly.** DRF throttling runs through the
   default cache, so the rate limits that protect login, refresh, import,
   export and password change are enforced through it. The local-memory
   cache is per-process: with more than one worker the effective limit
   multiplies by the number of processes. That is documented at the setting
   rather than left to the framework default.

## Correctness under concurrency

`POST /academics/grades/{id}/finalize/` now runs in one transaction with the
row locked (`select_for_update`):

- The old read-then-write was a race. Two administrators finalizing the same
  grade at the same time both read "submitted", both wrote "finalized", and
  both dispatched a notification set. The second caller now sees the
  finalized row and is told the grade is no longer finalizable.
- A failure in the notification dispatch used to leave the grade published
  and the family never told. Inside the transaction the rollback takes the
  status change with it, so the grade stays submitted and the admin can
  retry.

## Tests

- `config/tests.py` (new): the production module refuses to load without a
  host allow-list, with a weak secret key, or with an auto-generated one.
- `core/tests.py`: the health and readiness probes, including that a
  database failure is reported as 503 without leaking the error.
- `apps/accounts/tests.py`: the password-change rate limit, that it is keyed
  per account, and that a legitimate change below the limit still works.
- `apps/academics/tests.py`: the finalize rollback.

## Known gaps, left open on purpose

1. **The guidance student directory is now server-side.** It used to be
   composed in the browser from five complete lists (alerts, consultations,
   interventions, assessment results, behavioural notes), so the payload grew
   with the caseload. It is now one endpoint, `GET /api/v1/guidance/students/`,
   computed with grouped queries: one row per student, about a dozen queries
   whatever the caseload size. The visibility rules are the ones the
   individual endpoints already enforce, so a counselor sees exactly what
   those endpoints would show them.
2. **Throttle state is per-process** — *fixed by configuration, one variable
   away*. The DRF throttles (login, refresh, import, export, password change,
   registration) run through the default cache. The local-memory cache is
   per-process, so with more than one worker every limit is multiplied by the
   number of workers. Set `REDIS_URL` and install `django-redis` (listed in
   `requirements/production.txt`) and the limits hold across the whole
   deployment. Without it they hold per process, and the settings say so in a
   warning at start-up.
   - A Redis outage does not take the API down: the client treats an
     unreachable cache as an empty cache, so requests are served and that
     window's limit is not enforced.
   - Locally, `python scripts/fake_redis.py` serves the Redis protocol from
     `fakeredis` (a development-only dependency), so the shared path can be
     exercised without a Redis service.
   - `python scripts/verify_shared_throttle.py` proves it: two processes make
     the same failed sign-in, and with a shared cache the second one is
     throttled (429) where a per-process cache lets it through (401).
3. **`RiskModelArtifact.payload` is a pickle.** Loading it is arbitrary code
   execution if an attacker can write that row. Only the
   `train_risk_model` management command writes it and no API exposes it, so
   the risk is database access rather than the API. A reviewable format
   (JSON tree dump) would remove it entirely.
4. **Audit rows grow forever.** The trail is append-only by design and there
   is no retention policy or partitioning.

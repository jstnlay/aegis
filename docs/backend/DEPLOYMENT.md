# Deployment notes (Render + Vercel)

Backend: `https://aegis-0pav.onrender.com`
Frontend: `https://aegis-frontend-neon.vercel.app`

## Production cutover (Phase 1)

The service must run `config.settings.production`. `render.yaml` describes the
target configuration, but the live service was created in the Render Dashboard,
so the Dashboard is what actually changes it. Set every row below in
**Environment**, then **Save and Redeploy**.

Production settings fail the build on a missing value instead of serving an
insecure deployment: `DJANGO_ALLOWED_HOSTS` must be non-empty,
`DJANGO_SECRET_KEY` must be at least 50 characters, and
`FIELD_ENCRYPTION_KEYS` must be set.

| Variable | Value |
| --- | --- |
| `DJANGO_SETTINGS_MODULE` | `config.settings.production` |
| `DJANGO_DEBUG` | `False` |
| `DJANGO_ALLOWED_HOSTS` | `aegis-0pav.onrender.com` |
| `DJANGO_ENABLE_ADMIN_SITE` | `False` |
| `DJANGO_SECRET_KEY` | 50+ random characters; keep the existing value if already set |
| `FIELD_ENCRYPTION_KEYS` | `python manage.py generate_encryption_key` output |
| `REDIS_URL` | the Redis service's **Internal Redis URL** (see below) |
| `IMPORT_QUEUE_ENABLED` | `false` on this deployment. `true` would hand a large import to the `aegis-worker` queue service, which is not deployed (Render's free plan has no background workers); with `false` the import runs in a worker thread in the web process (see *Background work*) |
| `SENTRY_DSN` | optional; the Sentry project's DSN. Unset means no error reporting (see *Error reporting*) |
| `SENTRY_ENVIRONMENT` | optional; defaults to `production` |
| `AEGIS_FRONTEND_URL` | `https://aegis-frontend-neon.vercel.app` |
| `CORS_ALLOWED_ORIGINS` | `https://aegis-frontend-neon.vercel.app` |
| `EMAIL_BACKEND` | `core.email.BrevoEmailBackend`, `core.email.Smtp2GoEmailBackend` or `core.email.ResendEmailBackend` on the free plan (see *Outgoing mail*) |
| `DEFAULT_FROM_EMAIL` | the verified sender address |
| `SUPABASE_S3_ENDPOINT` | `https://<project-ref>.supabase.co/storage/v1/s3` |
| `SUPABASE_S3_BUCKET` | the public bucket name, e.g. `cms-upload` |
| `SUPABASE_S3_REGION` | the bucket's region, e.g. `ap-southeast-1` |
| `SUPABASE_S3_ACCESS_KEY` | the Supabase S3 access key id |
| `SUPABASE_S3_SECRET_KEY` | the Supabase S3 secret access key |
| `VAPID_PUBLIC_KEY` | Web Push pair, public half (see *Web Push* below) |
| `VAPID_PRIVATE_KEY` | Web Push pair, private half. Never leaves the server |
| `VAPID_ADMIN_EMAIL` | contact address for the push claim; defaults to `DEFAULT_FROM_EMAIL` |
| `GEMINI_API_KEY` | the assistant's model key (see *The assistant's answers* below) |
| `GEMINI_API_KEYS` | optional comma-separated fallback keys |

The build command is `pip install`, `migrate`,
`provision_qa_accounts --reset-password`, then `run_risk_computation`. The five
shared DEV/QA logins are provisioned on every deploy: the free plan has no shell,
so a manual run is not available, and the QA accounts must exist for a demo.
`--reset-password` makes each account accept `QA_SHARED_PASSWORD`, so the
documented password always works; without the flag the command never overwrites
a tester-chosen password. Only the five allowlisted addresses are ever written.
The variable must be set on the service or the build fails.

`seed_qa_dataset` and `train_risk_model` stay out of the build: they write a
synthetic school into the database, so they must only run by hand on a DEV/QA
environment. `run_risk_computation` runs in the build because this deployment
has no cron service to run it nightly (Phase 5 of `docs/WEB_APP_PLAN.md`; see
*Background work* for what that tradeoff costs and how to undo it). It exits 0
with a message when there is no trained model or no completed grading period, so
a quiet run is not a failed deploy.

Because the Blueprint is not linked to the live service, the build command and
health check are Dashboard settings too. In **Settings → Build & Deploy** set:

| Setting | Value |
| --- | --- |
| Build Command | `pip install -r ../requirements/production.txt && python manage.py migrate && python manage.py provision_qa_accounts --reset-password && python manage.py run_risk_computation` |
| Health Check Path | `/api/v1/health/` |

Without this step the old build command keeps seeding the database even after
the environment variables above are set.

The `SUPABASE_S3_*` set moves uploaded files (profile photos) out of the
service's own disk. The free Render plan has no persistent disk, so a photo
uploaded there is gone after the next redeploy; with these set, uploads go to
the Supabase bucket and the URL points at it. Without them the app keeps
using the local disk, so a deployment that has not configured storage is
unaffected.

`CORS_ALLOWED_ORIGINS` accepts regular expressions, so
`https://.*\.vercel\.app` can be added to let preview deployments talk to the
API as well.

`EMAIL_USE_TLS=True` with port 587 is STARTTLS, which is what Resend's SMTP
relay expects. Resend's port 465 needs implicit SSL, which Django's SMTP
backend does not do; use 587. Note that the free compute plan blocks those
ports entirely — see *Outgoing mail*.

## The assistant's answers

`GEMINI_API_KEY` is what lets the assistant answer anything that is not on the
student's record: small talk, definitions, general questions. Without it the
deployment still starts and every grade, attendance and resource question is
still answered from the database, but free conversation falls back to the
school-only tail ("I can look up your grades, attendance and approved learning
resources…") and Layer 2 sensitivity classification is off, leaving the keyword
screen alone.

That degradation is silent on purpose — the application, not the model, is
authoritative — which is why an unset key is easy to miss: the chat looks
healthy until a student asks something unrelated to their record. Set the key
and redeploy; `GEMINI_API_KEYS` adds comma-separated fallback keys and
`GEMINI_MODEL` / `GEMINI_MODEL_FALLBACKS` override the model names (the code
defaults are the approved ones, so leave them unset unless a model is retired).

Check it from the admin console: `/api/v1/chatbot/admin/model-status/` reports
`configured`, `available` and the last failure reason, never a key.

## Render: the Redis service

Region Singapore, environment Production, eviction `allkeys-lru`, free plan
(25 MB, 50 connections) — all correct. The host is
`red-dbcgmsrrjlhs73bdqfjg`.

Open the Redis service → **Connection** and copy the **Internal Redis URL**
in full. The string pasted so far, `redis://red-dbcgmsrrjlhs73bdqfjg:6379`,
has no password in it. If the panel shows the password separately, the URL is:

```
redis://:<PASSWORD>@red-dbcgmsrrjlhs73bdqfjg:6379
```

The internal URL only resolves for services in the same Render project,
environment and region. If the API service is in another region, use the
**External Redis URL** instead (`rediss://…`, over TLS) — that one also works
from a local shell.

Paste the finished URL into the API service's `REDIS_URL`. It is a secret:
set it in the Render dashboard, not in the repository.

## Vercel: the frontend

Project → Settings → Environment Variables → **Production**:

| Variable | Value |
| --- | --- |
| `VITE_API_BASE_URL` | `https://aegis-0pav.onrender.com/api/v1` |
| `VITE_VAPID_PUBLIC_KEY` | the same public key as Render's `VAPID_PUBLIC_KEY` |
| `VITE_SENTRY_DSN` | optional; the same Sentry project's DSN (see *Error reporting*) |

Add it for **Preview** too if preview deployments should reach the API, then
**Redeploy**. A Vite build bakes the value in, so saving the variable is not
enough.

## Error reporting

Phase 7 of `WEB_APP_PLAN.md`. Both tiers report to one Sentry project, and both
are off until a DSN is set.

| Tier | Variable | Where |
| --- | --- | --- |
| Django (the web service) | `SENTRY_DSN` | Render → Environment |
| Browser | `VITE_SENTRY_DSN` | Vercel → Environment Variables |

Both values are publishable, but set them in the dashboards, not in the
repository. Left unset, nothing is reported, no Sentry code is downloaded and
no build changes: the frontend imports `@sentry/react` dynamically, so a build
with no DSN ships no Sentry code at all.

The release is the deploy's commit — `RENDER_GIT_COMMIT` on Render,
`VERCEL_GIT_COMMIT_SHA` on Vercel (compiled into the bundle by the `define` in
`vite.config.ts`, because Vite only reads `VITE_`-prefixed variables). Sentry
groups issues by release, so "did this deploy cause it" is answered without
guessing.

What is deliberately **not** sent:

- Django: no PII (`send_default_pii=False`) and no request body
  (`max_request_body_size="never"`). A body can be a grade entry, an
  assessment draft, a password change or an import row.
- Browser: no user identity, no cookies, no request bodies and no URL query
  strings. The `dataCollection` block in `src/lib/error-reporting.ts` states
  that, because the SDK's default is to collect generously.
- Neither tier sends performance spans (`traces_sample_rate` is 0), so an error
  report costs one event and not a sampled transaction.

A render error caught by the frontend `ErrorBoundary` never reaches
`window.onerror`, so the boundary reports it itself (`captureError`); uncaught
errors and unhandled rejections go through the SDK's default handlers.

### Uptime check

`.github/workflows/uptime.yml` runs every 15 minutes and fails when
`GET https://aegis-0pav.onrender.com/api/v1/ready/` does not answer
`{"status":"ok","database":true,…}`. It is a scheduled workflow rather than a
CI step on purpose: it reports on what is deployed, not on what is in a push,
so a platform outage cannot look like a bad commit. The `cache` field is
printed and not asserted — the Redis instance is on the free tier, and an
expired one degrades the rate limits without failing a request
(`WEB_APP_PLAN.md` §5.1).

It is a "watch this if it goes red" check, not an alerting system: nothing has
notification routing, so a failure is a red run in the Actions tab. Route it to
a Sentry cron monitor or a mail step if it ever needs to wake someone.

## Web Push

Phase 4 of `WEB_APP_PLAN.md`. Push works only after both halves are set.

1. Generate the pair once. In the backend virtualenv:

   ```
   pip install pywebpush
   python -c "import base64; from py_vapid import Vapid; from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat; b=lambda x: base64.urlsafe_b64encode(x).rstrip(b'=').decode(); v=Vapid(); v.generate_keys(); print('PUBLIC =', b(v.public_key.public_bytes(encoding=Encoding.X962, format=PublicFormat.UncompressedPoint))); print('PRIVATE=', b(v.private_key.private_numbers().private_value.to_bytes(32, 'big')))"
   ```

   `PUBLIC` is base64url of the raw uncompressed point (65 bytes); that same
   string is what a browser needs in `applicationServerKey`. `PRIVATE` is the
   raw 32-byte scalar, base64url encoded; it never leaves the server.

   Do not print `v.public_key` / `v.private_key` directly: on py_vapid 1.9.6
   they are cryptography key objects, and printing them gives a repr, not a
   key. pywebpush accepts this raw-32 form via `Vapid.from_string`.

2. Render → **Environment**: set `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY` and
   `VAPID_ADMIN_EMAIL` (a `mailto:` contact, for example the verified sender)
   on the `aegis` web service. It is the only service that sends push: a
   notification is pushed from the request path, and the risk alerts go out
   from the build command, which runs on this same service. Save and redeploy.
3. Vercel → **Environment Variables**: set `VITE_VAPID_PUBLIC_KEY` to the
   same public key. Vite bakes it into the build, so redeploy the frontend.
4. The sender shown by every provider is `AEGIS — HIS CARE CHRISTIAN INSTITUTE`
   (decision D3). For email that means `DEFAULT_FROM_EMAIL` is set to
   `AEGIS — HIS CARE CHRISTIAN INSTITUTE <no-reply@<verified-address>>`. The
   display name is provider-supplied, not a separate variable.

With `VAPID_*` empty the backend sends in-app and email as before and skips
push silently; nothing else changes.

## Outgoing mail

### Mail goes over HTTPS, not SMTP

The free compute plan **blocks outbound traffic on the SMTP ports** (25, 465
and 587), so an SMTP connection from this deployment never completes: the
request hangs until the platform's proxy gives up and answers 500, and the
password reset never arrives. Two ways out:

- **Free plan (current):** use a provider's HTTP API.

  | Variable | Value |
  | --- | --- |
  | `EMAIL_BACKEND` | `core.email.BrevoEmailBackend`, `core.email.Smtp2GoEmailBackend` or `core.email.ResendEmailBackend` |
  | `BREVO_API_KEY` | the Brevo key, for the Brevo backend |
  | `SMTP2GO_API_KEY` | the SMTP2GO key, for the SMTP2GO backend |
  | `RESEND_API_KEY` | the Resend key, for the Resend backend |
  | `DEFAULT_FROM_EMAIL` | a verified sender address |

  `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD` and
  `EMAIL_USE_TLS` are then unused.

  The two providers differ in one way that matters here. **Resend** needs a
  verified *domain* to send to anyone; until one is verified it delivers only
  to the address on the Resend account. **Brevo** and **SMTP2GO** need a
  verified *email address*, which is enough to send to anyone - so a
  deployment without a domain of its own can still deliver.
- **Paid plan:** Django's own SMTP backend works. Set `EMAIL_BACKEND` to
  `django.core.mail.backends.smtp.EmailBackend` with `EMAIL_HOST=smtp.resend.com`,
  `EMAIL_PORT=587`, `EMAIL_HOST_USER=resend`, `EMAIL_HOST_PASSWORD` the key
  and `EMAIL_USE_TLS=True`.

`EMAIL_TIMEOUT` (default 10 seconds) bounds the attempt either way. Django's
own default is no timeout at all, which is what let a blocked connect hold the
request open until the platform killed it.

### Resend, step by step

1. Resend dashboard → **API Keys** → **Create API Key**, name it `AEGIS`.
   Copy the key (it starts with `re_`). It is shown once.
2. Resend → **Domains** → **Add Domain**, e.g. `mail.<your-domain>`. Resend
   gives a set of DNS records (SPF, DKIM, and a CNAME for the sending
   subdomain) that have to be added at the domain registrar. Until the
   domain is verified, Resend only allows sending to your own address.
3. `DEFAULT_FROM_EMAIL` must be on the verified domain, for example
   `no-reply@mail.<your-domain>`. An unverified from-address is silently
   dropped by Resend, and the parent never receives the invitation.

### Brevo, step by step (no domain needed)

1. Sign up at **brevo.com** and confirm the account email.
2. **Senders & Domains** → **Verify a new email address** → add the address
   the school wants to send from (for example `aegisofficialsupport@gmail.com`).
   Brevo emails a confirmation link; the address is unusable until that link
   is clicked. A *domain* can be authenticated instead, which is better for
   a school's mail but needs DNS access.
3. **SMTP & API** → **API Keys** → **Generate a new API key** → name it
   `AEGIS`. The key starts with `xkeysib-` and is shown once.
4. Set `EMAIL_BACKEND=core.email.BrevoEmailBackend`, `BREVO_API_KEY` to that
   key, and `DEFAULT_FROM_EMAIL` to the verified address.
5. Free tier: 300 mails a day, which is far beyond what a school needs in a
   day of testing.

### SMTP2GO, step by step (also no domain)

1. Sign up at **smtp2go.com**. The free plan is 1,000 mails a month, no card
   needed. Note that the signup form asks for a *work* address and rejects
   public domains such as Gmail or Yahoo.
2. **Sending → Verified Senders** → **Add single sender email** → the address
   the school sends from → a confirmation by email. A domain can be
   authenticated instead, which is better but needs DNS access.
3. **Sending → API Keys** → create a key. It is 32 characters with an `api-`
   prefix, and it goes into the `X-Smtp2go-Api-Key` header.
4. Set `EMAIL_BACKEND=core.email.Smtp2GoEmailBackend`, `SMTP2GO_API_KEY` to
   that key, and `DEFAULT_FROM_EMAIL` to the verified address.
5. The provider answers 200 even when it delivered to nobody, so the backend
   reads the body and treats "succeeded: 0" as a failure - the caller then
   logs it instead of believing the mail went out.

## Why the Redis instance exists

The rate limits (login, refresh, import, export, password change,
registration) are enforced through the Django cache. The local-memory cache
is per-process, so with more than one gunicorn worker every limit is
multiplied by the number of workers: a 15/minute login limit becomes 30 with
two workers. A shared Redis makes it one limit for the whole service.

If a Redis outage occurs, the cache client is configured to treat the
unreachable cache as empty rather than to fail the request: the API stays up
and that window's limit is not enforced. An outage should not take the
system down.

## Background work

Phase 5 of `WEB_APP_PLAN.md` designed two extra Render services, neither of
which answers HTTP:

| Service | Command | Schedule |
| --- | --- | --- |
| `aegis-worker` (worker) | `python manage.py rqworker imports` | always on |
| `aegis-risk-recompute` (cron) | `python manage.py run_risk_computation` | `0 18 * * *` UTC (02:00 Asia/Manila) |

**Neither is deployed**, and that is the decision, not an oversight. Render
grants free instances only to web services, static sites, Postgres and Key Value
— *"Other service types don't support Free instances"* — and a background worker
starts at about $7/month while a cron job carries a $1/month minimum. This
deployment is free, so it runs without them. The commands and the queue code
they exercise are left in place and still covered by the test suite, so
reinstating them means adding two services, not changing the application.

What stands in for them:

| Was | Is |
| --- | --- |
| A large import handed to the `imports` queue | `IMPORT_QUEUE_ENABLED=false`: the import runs in a worker thread in the web process |
| Risk scores recomputed nightly by the cron | `run_risk_computation` in the web service's build command, so scores refresh on each deploy |

**Large imports.** A file above `IMPORT_SYNC_ROW_LIMIT` (200 rows,
`apps/data_import/constants.py`) runs in a thread inside the web process, not in
the request: the POST still answers immediately and the client polls
`GET /api/v1/data-import/jobs/{id}/` exactly as before. What the queue bought
was durability — with a thread, a redeploy, a crash or a Render restart ends an
import that was already accepted, and the job row stays `processing`. That is
the cost of running without the worker.

**A job that stops.** The job endpoint fails any job that has sat in `pending`
or `processing` for 30 minutes (`STALE_JOB_AFTER` in
`apps/data_import/runner.py`), with error code `JOB_QUEUE_LOST` telling the
uploader to re-upload, so a stuck job is never a client polling forever. With
the queue off, that also covers a thread killed by a restart between polls. The
cutoff is far beyond the worst measured runtime, so an import that is genuinely
still running is never marked failed underneath the worker doing it. If you
raise `MAX_IMPORT_ROWS`, raise that cutoff with it.

**Risk scores.** `run_risk_computation` runs in the build command (see
*Production cutover*). A score therefore refreshes on each deploy rather than
every night, and a deploy rewrites every score: with one web service and no cron
that is the tradeoff, and the command is safe to run because it exits 0 with a
message when there is no trained model or no completed grading period. Risk
alerts dispatched from that run use the same mail and `VAPID_*` variables as the
service it runs on; without them the scores are still recomputed and only the
in-app notification lands.

**Reinstating Phase 5.** Add the two services back and switch the queue on:
create **New + → Worker** named `aegis-worker` (repository `jstnlay/aegis`,
branch `master`, root directory `backend/aegis_backend`, build
`pip install -r ../requirements/production.txt`, start
`python manage.py rqworker imports`) and **New + → Cron Job** named
`aegis-risk-recompute` (same repository, branch, root and build, start
`python manage.py run_risk_computation`, schedule `0 18 * * *`); give each the
environment from the matching `render.yaml` block (the earlier revisions of this
file and of `render.yaml` in git history list them in full); then set
`IMPORT_QUEUE_ENABLED=true` on the web service and drop `run_risk_computation`
from its build command. Neither service may migrate: the web service owns
migrations.


### Running the worker locally

```
cd backend/aegis_backend
REDIS_URL=redis://127.0.0.1:6379/0 IMPORT_QUEUE_ENABLED=true python manage.py rqworker imports
```

Windows has no `fork`, so use `--worker-class rq.SimpleWorker` there. On Render
the default worker is correct. This needs a real Redis: `scripts/fake_redis.py`
serves the throttle cache happily, but its `CLIENT INFO` reply is not parseable
by redis-py, so an RQ worker started against it dies before it dequeues
anything.

## Which address the rate limits count

The public URL is served through Cloudflare, and the app server behind it sees
a forwarded chain that ends in a proxy hop - and that hop is not the same on
every request. A limit keyed on the socket address or on the whole forwarded
chain therefore gives every request its own bucket, and the limit never
fires. That is not a hypothetical: it is what this deployment did until the
identity was fixed, and the symptom is a login endpoint that answers 401
forever.

`core.client_ip` resolves the client address in two ways, because the two
consumers need different things:

- **Rate limits** (`throttle_identity`) — the CDN's client-IP header first
  (Cloudflare overwrites it, so a client cannot choose it), then the last hop
  of `X-Forwarded-For`, then the socket address. A limit needs one bucket per
  client, and behind a proxy the socket address is the proxy's.
- **The audit trail** (`client_address`) — the CDN's client-IP header, then
  the socket address. `X-Forwarded-For` is never used there: it is a header
  the client writes, and the audit must not record a value the actor chose.
  Without the CDN header the recorded address would be Cloudflare's edge,
  which is the same for every request and identifies nobody.

Note that the origin is also reachable directly, without Cloudflare, and a
direct request can set the CDN header itself. Both are therefore best-effort
against an actor who bypasses the CDN; the socket address remains the value
that cannot be chosen.

## Verifying it

1. `GET https://aegis-0pav.onrender.com/api/v1/health/` → 200 with JSON
   `{"status":"ok"}`, not the DRF browsable-API HTML page.
2. `GET https://aegis-0pav.onrender.com/api/v1/ready/` → 200 with
   `"database":true` and `"cache":"shared"`. The cache field says which cache
   the rate limits are counted in:
   - `"shared"` — Redis is configured and answers. One limit for the whole
     deployment.
   - `"local"` — the per-process cache is in use. Every limit is multiplied by
     the number of workers.
   - `"broken"` — Redis is configured but does not answer. The client treats
     it as empty, so no limit is enforced at all. Check `REDIS_URL` and that
     the Redis instance and the API service share a region.
3. `GET https://aegis-0pav.onrender.com/admin/` → **404**. A 200 means
   `DJANGO_ENABLE_ADMIN_SITE` is still on or the service is still running
   development settings.
4. From one machine, make 16 failed sign-in requests to
   `POST https://aegis-0pav.onrender.com/api/v1/auth/login/`. The 16th must
   answer **429** with a `Retry-After` header. If it answers 401, the limit is
   still per worker.
5. Sign in on `https://aegis-frontend-neon.vercel.app/`, use **Forgot
   password?**, and check that the link points at the Vercel URL and the
   mail arrives.
6. Raise an error on purpose and watch it arrive: a page that throws in the
   deployed frontend (with `VITE_SENTRY_DSN` set) and any 500 from the API
   (with `SENTRY_DSN` set). The event carries the commit as its release, and
   no request body, cookie or query string.
7. Run the five role journeys locally, which builds the frontend, starts Django
   on its own SQLite file and drives Chromium:

   ```
   cd frontend
   PHASE7_E2E_PASSWORD=<the seed password> npm run e2e
   ```

   The first run needs `npx playwright install chromium`.

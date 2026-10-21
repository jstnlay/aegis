# Deployment notes (Render + Vercel)

Backend: `https://aegis-0pav.onrender.com`
Frontend: `https://aegis-frontend-neon.vercel.app`

## What is deployed right now

The running Render build is older than the current code: it serves the API
(the frozen error envelope, JSON only, no browsable API) but it does not have
the health probes, the sign-in features, the server-side guidance directory,
or the shared-cache support. **Redeploy the API service from the current
branch** before setting the environment below, otherwise the new variables
have nothing to configure.

After the redeploy:

- `GET https://aegis-0pav.onrender.com/health/` → `{"status":"ok"}`
- `GET https://aegis-0pav.onrender.com/ready/` → `{"status":"ok","database":true}`
- `GET https://aegis-0pav.onrender.com/admin/` → 404 (the admin site is off
  in production; it was published before this change)

## Render: the API service

Environment tab, then **Save and Redeploy**.

| Variable | Value |
| --- | --- |
| `REDIS_URL` | the Redis service's **Internal Redis URL** (see below) |
| `AEGIS_FRONTEND_URL` | `https://aegis-frontend-neon.vercel.app` |
| `CORS_ALLOWED_ORIGINS` | `https://aegis-frontend-neon.vercel.app` |
| `ALLOWED_HOSTS` | `aegis-0pav.onrender.com` |
| `DEFAULT_FROM_EMAIL` | `no-reply@<your sending domain>` |
| `EMAIL_HOST` | `smtp.resend.com` |
| `EMAIL_PORT` | `587` |
| `EMAIL_HOST_USER` | `resend` |
| `EMAIL_HOST_PASSWORD` | the Resend API key |
| `EMAIL_USE_TLS` | `True` |

`CORS_ALLOWED_ORIGINS` accepts regular expressions, so
`https://.*\.vercel\.app` can be added to let preview deployments talk to the
API as well.

`EMAIL_USE_TLS=True` with port 587 is STARTTLS, which is what Resend's SMTP
relay expects. Resend's port 465 needs implicit SSL, which Django's SMTP
backend does not do; use 587.

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

Add it for **Preview** too if preview deployments should reach the API, then
**Redeploy**. A Vite build bakes the value in, so saving the variable is not
enough.

## Resend, step by step

1. Resend dashboard → **API Keys** → **Create API Key**, name it `AEGIS`.
   Copy the key (it starts with `re_`). It is shown once.
2. Resend → **Domains** → **Add Domain**, e.g. `mail.<your-domain>`. Resend
   gives a set of DNS records (SPF, DKIM, and a CNAME for the sending
   subdomain) that have to be added at the domain registrar. Until the
   domain is verified, Resend only allows sending to your own address.
3. `DEFAULT_FROM_EMAIL` must be on the verified domain, for example
   `no-reply@mail.<your-domain>`. An unverified from-address is silently
   dropped by Resend, and the parent never receives the invitation.

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

## Verifying it

1. `GET https://aegis-0pav.onrender.com/health/` → 200
2. `GET https://aegis-0pav.onrender.com/ready/` → 200 with `"database":true`
3. From one machine, make 16 failed sign-in requests to
   `POST https://aegis-0pav.onrender.com/api/v1/auth/login/`. The 16th must
   answer **429** with a `Retry-After` header. If it answers 401, the limit is
   still per worker.
4. Sign in on `https://aegis-frontend-neon.vercel.app/`, use **Forgot
   password?**, and check that the link points at the Vercel URL and the
   mail arrives.

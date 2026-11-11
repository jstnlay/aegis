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
- `GET https://aegis-0pav.onrender.com/ready/` → `{"status":"ok","database":true,"cache":"shared"}`
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

1. `GET https://aegis-0pav.onrender.com/health/` → 200
2. `GET https://aegis-0pav.onrender.com/ready/` → 200 with `"database":true`
   and `"cache":"shared"`. The cache field says which cache the rate limits
   are counted in:
   - `"shared"` — Redis is configured and answers. One limit for the whole
     deployment.
   - `"local"` — the per-process cache is in use. Every limit is multiplied by
     the number of workers.
   - `"broken"` — Redis is configured but does not answer. The client treats
     it as empty, so no limit is enforced at all. Check `REDIS_URL` and that
     the Redis instance and the API service share a region.
3. From one machine, make 16 failed sign-in requests to
   `POST https://aegis-0pav.onrender.com/api/v1/auth/login/`. The 16th must
   answer **429** with a `Retry-After` header. If it answers 401, the limit is
   still per worker.
4. Sign in on `https://aegis-frontend-neon.vercel.app/`, use **Forgot
   password?**, and check that the link points at the Vercel URL and the
   mail arrives.

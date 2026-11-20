# AEGIS: from website to web application

**Status: Phase 1 (production posture), Phase 2 (installable app shell), Phase 3
(live data), Phase 4 (push, backend and frontend) and Phase 6 (mobile payload)
are built and deployed. Phase 5 (background work) is blocked by D6; Phase 7
(proof and observability) is not built.** The install prompt, offline page and
recovery were verified in Chrome. The two-browser notification check and the
push delivery check on a real device are still outstanding.

**Scope.** How the deployed AEGIS stops being "a website that happens to have
pages behind a login" and becomes an application a parent or a student opens
like an app: installable, live, and running on production posture.

**Companion.** `docs/BACKEND_SPECIFICATION.md` is the approved baseline
(CR-001, the NFR list, and §L open questions). This plan does not replace it.
Where a phase needs a decision that only the panel or the school can make,
it is listed under *Open decisions* and the phase is written to be safe
without it.

---

## 1. What "web app" means here

The capstone calls AEGIS a web-based platform (CR-001: browser-only, no native
app). That phrase is currently satisfied in the weakest possible way: a
website is a set of documents you request; a web application is a program you
run. The difference is not visual. It is behavioural:

| Web application | AEGIS today |
|---|---|
| Installs to a home screen and launches in its own window | No manifest, no icons, no standalone mode |
| Opens offline and says the data needs a connection | Nothing is cached; every screen fails closed on a dead connection |
| Tells you about a new grade while the app is closed | In-app row + email only; nothing reaches a closed app |
| Updates the screen you are looking at when the data changes | The notification list is a one-shot fetch |
| Does slow work outside the request that asked for it | Imports run in a thread pool inside the web process |
| Runs on production settings | The deployed service runs `config.settings.development` |

Five of those six are missing. That is the gap this plan closes.

**Non-goals.** No native app, no app store, no new role model, no rewrite of
the frozen API contract (`docs/BACKEND_SPECIFICATION.md` §PH10), no offline
*write* path, and no feature that serves only one of the five roles unless it
is the whole slice.

**Offline is out, and stays out.** §A.9 of the approved baseline already
scopes it: "No offline access" and "Internet connection required at all
times". That limitation is the panel's, and it was signed off before this
plan existed, so it is not reopened here. The consequence for this plan is
concrete and it is a simplification: **the service worker caches the app
shell and static assets only. No API response is ever written to a cache.**
An installed app therefore opens offline and says the screen needs a
connection; it never shows a student's grades from last week. That also
removes the whole class of "which account does this cached row belong to"
questions, and it means the worker never needs a token.

---

## 2. Audit: what is actually deployed

Verified on 2026-11-13 against the live services
(`https://aegis-frontend-neon.vercel.app`, `https://aegis-0pav.onrender.com`)
and the repository.

| # | Symptom | Evidence |
|---|---|---|
| A1 | **Not installable.** `GET /manifest.webmanifest` returns the SPA HTML, not a manifest. `GET /sw.js` returns the SPA HTML, not a worker. There is no service worker and no `vite-plugin-pwa` in `frontend/package.json`. | `frontend/vercel.json` rewrites `/(.*)` to `/index.html`, so every unknown path answers 200 with HTML. `frontend/index.html` has no manifest link, no `theme-color`, no `apple-touch-icon`, no `apple-mobile-web-app-capable`. |
| A2 | **No live updates.** `frontend/src/lib/queryClient.ts` sets `refetchOnWindowFocus: false` and `staleTime: 60_000`; `useUnreadNotifications` in `frontend/src/features/notifications/api.ts` sets no `refetchInterval`. A notification created while the app is open is invisible until something invalidates the query. | `frontend/src/lib/queryClient.ts:20-31`, `frontend/src/features/notifications/api.ts` |
| A3 | **No push.** `NotificationPreference` carries `email_enabled`, `in_app_enabled` and quiet hours; there is no push channel, no subscription model, no VAPID key anywhere. The spec still carries this as open: §L OQ-7, panel correction #16. | `backend/aegis_backend/apps/notifications/models.py`, `docs/BACKEND_SPECIFICATION.md` §L |
| A4 | **Slow work inside the request.** A large import is queued into a `ThreadPoolExecutor(max_workers=2)` living in the web process. A redeploy mid-import kills the job; the module docstring says so and tells the user to upload again. | `backend/aegis_backend/apps/data_import/runner.py` |
| A5 | **Scheduled work is scheduled by deploy.** `render.yaml` runs `train_risk_model` and `run_risk_computation` in the build command, so risk scores are recomputed when the code is deployed and then age. `run_risk_computation` is described as a "scheduled batch" and nothing schedules it. | `render.yaml` buildCommand, `backend/aegis_backend/ai_engine/management/commands/run_risk_computation.py` |
| A6 | **Production runs development settings.** The live service sets `DJANGO_SETTINGS_MODULE=config.settings.development`, `DJANGO_DEBUG=True`, `DJANGO_ALLOWED_HOSTS=*`. Consequences, all confirmed live: the browsable API is served (`GET https://aegis-0pav.onrender.com/api/v1/health/` returns the DRF HTML page), and the Django admin site is published (`GET /admin/` returns 200). `config/settings/production.py` exists and is not used. | `render.yaml` envVars, `backend/aegis_backend/config/settings/production.py`, live requests |
| A7 | **Every deploy re-seeds fake school data and QA accounts** into the same database, because the build command calls `provision_qa_accounts` and `seed_qa_dataset`. | `render.yaml` buildCommand |
| A8 | **The health probe is missing.** `render.yaml` still carries the comment "this Django project exposes no health endpoint" and sets no `healthCheckPath`. The endpoint exists now: `GET /api/v1/health/` → `{"status":"ok"}`, `GET /api/v1/ready/` → `{"status":"ok","database":true,"cache":"shared"}`. | `backend/aegis_backend/core/health.py`, `backend/aegis_backend/config/api_v1.py`, `render.yaml` |
| A9 | **Cold starts.** Render's free web services sleep when idle; the repo already documents a ~50 s first response after a Strapi instance sleeps. For a parent opening the app from a phone, a 50 s cold start is the app's first impression. | `docs/MANUAL_TASKS.md` |
| A10 | **Heavy mobile payloads.** The landing page ships `front bg.png` at 1.84 MB and `cover-photo.png` at 650 KB; the entry JS is 637 KB and the entry CSS 485 KB (pre-compression, `br` on the wire). Hashed assets are served `Cache-Control: public, max-age=0, must-revalidate`, so they are revalidated on every load. | `frontend/public/`, `frontend/src/routes/pages/LandingPage.tsx:141`, live `HEAD` requests |
| A11 | **Tokens in `localStorage`.** The bearer pair lives in `localStorage`, readable by any script in the origin. A service worker cannot read it, so a worker cannot authenticate a request on its own. Not a blocker for this plan: with no API response cached (see §1), the worker never needs one. It stays on the list because it is a standing risk if cached reads are ever added. | `frontend/src/lib/auth-storage.ts` |
| A12 | **No observability.** No Sentry, no OpenTelemetry, no Prometheus anywhere in the repo. A production error is only visible in a Render log. | repo-wide search |
| A13 | **No end-to-end proof.** CI runs Django tests and Vitest. Nothing exercises the five role portals in a browser, so "the app works" is a manual claim. | `.github/workflows/ci.yml` |
| A14 | **Assets on ephemeral disk.** CMS uploads are lost on redeploy unless the Supabase S3 keys are set on the `aegis-cms` service; the Django service's profile photos have the same dependency. | `docs/MANUAL_TASKS.md` §2 |

---

## 3. Target architecture

```
Browser / installed PWA
        │  HTTPS, Bearer JWT
        ▼
Vercel (static SPA)  ── service worker ── precached shell + static assets only
        │  /api/* rewrite (same-origin)
        ▼
Render web service (gunicorn, production settings)
        │        │
        │        ├── PostgreSQL (Supabase)          durable data
        │        ├── Redis                          shared throttle cache + job queue
        │        └── Strapi (Render)                content, media in Supabase Storage
        │
        └── background worker (separate service, same image)
                 · import jobs      · risk recompute      · push delivery
```

Two invariants:

1. **The service worker caches no API response.** It precaches the shell and
   the static assets and nothing else; every `/api/*` request goes to the
   network and fails honestly when there is none. Offline data is out of
   scope (§1), so there is no cache key to get wrong and no token for the
   worker to hold.
2. **Nothing slow runs in a request.** Imports, risk recomputation and push
   delivery move to a worker. The request that uploaded a file returns a job
   id, exactly as it does now — only the job actually survives a restart.

---

## 4. Phases

Each phase is independently shippable and leaves the deployment working.
Verification commands are the ones CI already runs.

### Phase 0 — Decisions

Two of the six decisions are answered (D1–D4). The record lives in this
document's decision table rather than in `DECISIONS.md`: that file's scope
header names the safety/Gemini/recommendation workstream, so appending a
second workstream to it would blur what it is authoritative for.

Only D5, the domain, is still open. It does not block any phase; it only names
the installed app and the sender address.

**Acceptance:** the decision table in §5 carries an answer and a named owner
for every row.

**Verification:** review with the project owner.

---

### Phase 1 — Production posture

The cheapest and the most urgent phase. The app is already a target; it is
currently being served by a development configuration.

**Tasks**

1. Switch the deployed service to `config.settings.production`: `DEBUG=False`,
   `DJANGO_ALLOWED_HOSTS` set to the real host list, `DJANGO_SECRET_KEY` a real
   50+ character secret, `DJANGO_ENABLE_ADMIN_SITE=false`.
   *File:* `render.yaml` (envVars block), `docs/backend/DEPLOYMENT.md` (env table).
2. Remove `provision_qa_accounts`, `seed_qa_dataset`, `train_risk_model` and
   `run_risk_computation` from the build command. Those are DEV/QA steps; in
   production they overwrite real data with a synthetic school.
   *File:* `render.yaml`.
3. Set `healthCheckPath: /api/v1/health/` and delete the stale comment that
   says the project has no health endpoint.
   *File:* `render.yaml`.
4. Point `CORS_ALLOWED_ORIGINS` and `AEGIS_FRONTEND_URL` at the deployed
   frontend origin, and set `EMAIL_BACKEND` + the provider key so
   invitations and reset mail actually leave the instance.
   *Files:* `render.yaml`, `docs/backend/DEPLOYMENT.md`.
5. Verify the live service no longer serves the browsable API and no longer
   answers `/admin/` with 200.

**Acceptance criteria**

- `GET /api/v1/health/` returns JSON, not the DRF HTML page.
- `GET /admin/` returns 404.
- `GET /api/v1/ready/` still reports `{"database": true, "cache": "shared"}`.
- A build no longer writes synthetic students into the production database.

**Verification:** `python aegis_backend/manage.py check` locally; live `curl`
of the three endpoints above.

**Files:** `render.yaml`, `docs/backend/DEPLOYMENT.md`,
`backend/aegis_backend/config/settings/production.py` (no longer forces the
SMTP mail backend, so the free-plan HTTP provider is honoured).
**Scope:** Small.

---

### Phase 2 — Installable app shell

The first visible difference between a website and an app.

**Tasks**

1. Add `vite-plugin-pwa` (v2 supports Vite 8) and generate the service
   worker: precache the app shell and the static assets, and route every
   `/api/*` request straight to the network with no cache write. `navigateFallback`
   points at `index.html` so a deep link still opens offline.
   *Files:* `frontend/package.json`, `frontend/vite.config.ts`.
2. Write `frontend/public/manifest.webmanifest`: `display: standalone`,
   `start_url: /app/dashboard`, `scope: /`, theme and background colours from
   the design tokens in `frontend/src/index.css`, and 192/512/maskable icons
   derived from `frontend/public/hcci-logo.png`.
3. Link the manifest, `theme-color`, `apple-touch-icon` and
   `apple-mobile-web-app-capable` from `frontend/index.html`.
4. Add an install affordance: a small prompt in the account menu offering
   "Add AEGIS to home screen", shown only when `beforeinstallprompt` fires.
   *File:* `frontend/src/features/settings/` (the surface that already holds
   account preferences).
5. Add an offline page served from the precache, and make a failed API call
   render that page instead of a generic error.

**Acceptance criteria**

- Chrome's install prompt appears for the site; the app launches in a
  standalone window with no browser chrome.
- The five role portals deep-link correctly (`/app/guidance/risk-alerts`
  opens directly), because the Vercel rewrite already answers deep routes
  with `index.html`.
- With the network off, the app opens and shows the offline page rather than
  a blank screen, and the page says the screen needs a connection.
- Nothing from `/api/*` is in the cache afterwards: the service worker
  storage panel shows only the precached shell and static assets.

**Built (2026-11-15).** `vite-plugin-pwa` precaches the shell; `/api/*` is
NetworkOnly. `OfflineGate` swaps the tree for the offline page when the browser
reports no connection, so a dead network never mounts pages that cannot load
data. A failed API call while the browser still reports a connection keeps the
normal error state instead: it is an outage, not an offline device. The install
action lives in the account menu and appears only while the browser holds a
`beforeinstallprompt` event.

**Verification:** `npm run build` and `npm run typecheck`; manual install
check on Chrome (Android and desktop) and on iOS 16.4+ via Share → Add to
Home Screen.

**Files:** `frontend/package.json`, `frontend/vite.config.ts`,
`frontend/index.html`, `frontend/public/manifest.webmanifest`,
`frontend/src/features/settings/*`.
**Scope:** Medium (3–5 files).

---

### Phase 3 — Live data

The second difference: an application tells you what changed while you are
looking at it.

**Tasks**

1. Replace the fixed `staleTime` for the notification and dashboard queries
   with an adaptive poll: refetch every 20 s while the tab is visible, stop
   when it is hidden, refetch immediately on focus. Keep `retry: 1` and the
   existing error normalisation.
   *Files:* `frontend/src/features/notifications/api.ts`,
   `frontend/src/lib/queryClient.ts`.
2. Surface "updated <time>" on the screens that poll, so the user can tell
   fresh data from stale data.
3. Keep the notification list and the unread badge on the same query key so a
   new notification updates the badge without a second request.

**Acceptance criteria**

- A notification created in one browser appears in an already-open AEGIS tab
  within 30 s without a manual reload.
- No polling happens on a hidden tab (verifiable in the network panel).

**Built (2026-11-15).** `liveQueryOptions` in `lib/queryClient.ts` owns the
rule: 20 s interval, `staleTime: 0`, refetch on focus even when data is fresh,
and React Query's default pause while the tab is hidden. Every notification
list uses it, so the bell, the previews and the inbox behave the same. The
student dashboard polls its metrics, attendance and grades queries; the other
role dashboards are unchanged. The bell badge now counts the unread rows of the
list query it already renders instead of issuing a second unread request, and
the dashboard and inbox show the time of the last successful update.

**Verification:** `npm test`; manual two-browser check.

**Files:** `frontend/src/features/notifications/api.ts`,
`frontend/src/lib/queryClient.ts`, one dashboard component.
**Scope:** Small.

---

### Phase 4 — Push notifications

This is the panel's own open question (§L OQ-7, panel correction #16), so
this phase closes a documented gap rather than opening a new one.

**Prerequisite:** Phase 2 (a push-capable install) and a decision on the
sending identity (see §5).

**Tasks**

**Backend built (2026-11-15), not yet deployed.** `PushSubscription` plus
`NotificationPreference.push_enabled` (default on) and migration `0003`;
`POST/DELETE /api/v1/notifications/push-subscriptions/` upsert on `endpoint`
and are scoped to the caller; `dispatch_event()` delivers Web Push to every
subscription of every opted-in, non-quiet-hours recipient, deletes 404/410
endpoints and logs the rest; `pywebpush` sends with `settings.VAPID_*`. The
preference is independent of in-app and email. Push is synchronous in the
request, the same place the email send already runs; Phase 5 moves both. The
SPA path used for the click target is the one in `Notification.link` when it
starts with `/app/`, otherwise `/app/notifications`.

1. Add `PushSubscription` to the notifications app: `user`, `endpoint`,
   `p256dh`, `auth`, `created_at`, with one row per browser.
2. Add two endpoints: `POST /api/v1/notifications/push-subscriptions/` and
   `DELETE /api/v1/notifications/push-subscriptions/{id}/`, scoped to the
   caller's own subscriptions.
3. Generate a VAPID key pair, store it in the environment
   (`VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY`), and send with `pywebpush`.
4. Extend `NotificationPreference` with `push_enabled`, honouring the quiet
   hours that already exist in the model.
5. Deliver from `dispatch_event()` in
   `backend/aegis_backend/apps/notifications/events.py` — the single place
   every notification already passes through — rather than from each caller.
6. Frontend: a permission prompt that appears after a real event, not on
   first load; a service worker `push` handler that shows the notification
   and focuses the existing window on click.

**Acceptance criteria**

- A grade posted for a student produces an OS-level notification on that
  student's registered device within 5 s.
- A user who turned push off in preferences receives none.
- A device that never opted in has no subscription row and no endpoint call.

**Verification:** backend tests for the preference gate and the
subscription ownership; manual device check on Chrome Android and iOS 16.4+
(iOS only delivers to an installed Home Screen app).

**Files:** `backend/aegis_backend/apps/notifications/{models,views,serializers,urls}.py`,
`backend/aegis_backend/apps/notifications/events.py`,
`backend/aegis_backend/config/settings/base.py`,
`backend/requirements/base.txt`, `frontend/src/lib/pwa/*`.
**Scope:** Large (8+ files) — split into 4a (backend) and 4b (frontend).

---

### Phase 5 — Background work

Imports and risk recomputation stop being side effects of a deploy.

**Tasks**

1. Move the import executor out of the web process into a queue. Redis is
   already deployed and already the shared throttle cache; `django-rq` on that
   Redis is the smallest change that keeps the job durable and restart-safe.
   *File:* `backend/aegis_backend/apps/data_import/runner.py`.
2. Run the worker as its own service from the same image:
   `python manage.py rqworker`. Vercel and Render stay the hosts; a worker is
   a separate Render service type, and another provider is acceptable if
   Render's price or sleep behaviour does not work (see D4).
3. Schedule the risk recomputation: `run_risk_computation` already exists and
   already exits 0 when there is not enough history. Point a scheduler at it
   (a Render cron job, or an external cron pinger hitting a signed admin
   endpoint).
4. Keep the job's HTTP contract unchanged: `GET /api/v1/data-import/jobs/{id}/`
   keeps polling the same way. Only the executor changes.

**Acceptance criteria**

- A large import survives a redeploy mid-job and completes.
- Risk scores are recomputed on a schedule, not only on deploy; a student
  whose grades changed yesterday has a fresh score today.
- The import job endpoint and the frontend polling code need no change.

**Verification:** backend tests for the queue path; manual redeploy during a
large import.

**Files:** `backend/aegis_backend/apps/data_import/runner.py`,
`backend/aegis_backend/apps/data_import/apps.py`,
`backend/requirements/production.txt`, `render.yaml`.
**Scope:** Medium.

---

### Phase 6 — Mobile payload

**Built (2026-11-20).** The seven landing and sign-in rasters are WebP after
Pillow conversion (`front bg.png` 1.84 MB → `front bg.webp` 100 KB, and the
same treatment for `background`, `announcement pic`, `completer login`, `MandV
bg`, `footer bg`; `cover-photo` was unreferenced and is gone). Every reference
in `LandingPage.tsx`, `FeaturedAnnouncement.tsx`, `AppShell.tsx` and the three
landing CSS files points at the WebP; the coarse originals are deleted so they
are not deployed. Public pages became lazy routes with their own `Suspense`
boundary, which moves 94 KB of landing and login CSS out of the entry
stylesheet (474 KB → 380 KB; gzip 72 KB → 58 KB). `vercel.json` serves
`/assets/*` with `max-age=31536000, immutable` and keeps `sw.js`/`push-sw.js`
revalidated so a new worker is still picked up.

Measured after build: landing first load is **327 KB gzip** (entry JS 150 KB,
entry CSS 58 KB, landing chunk 8 KB JS + 11 KB CSS, hero 100 KB), before fonts.
The same page previously shipped 3.9 MB of raster art.

No decision gates this phase. It is the difference between an app that opens
on a phone in two seconds and one that opens in twenty.

**Tasks**

1. Replace the raster landing assets: `front bg.png` (1.84 MB),
   `cover-photo.png` (650 KB) and `background.png` (349 KB) become WebP or
   AVIF at the sizes actually displayed, with `srcset` and `loading="lazy"`
   below the fold. Lazy-load the landing hero.
2. Split the CSS: 485 KB in one file is mostly the design-system surface.
   Split the app shell from the public pages so a signed-in user does not
   download the landing styles.
3. Give hashed assets a long-lived immutable `Cache-Control` instead of
   `must-revalidate`, so a returning user downloads the shell once.

**Acceptance criteria**

- The landing page transfers under 400 KB on a cold mobile connection.
- A signed-in user on a phone gets the app shell in under 3 s on a warm
  connection, with the API call still the long pole.

**Verification:** `npm run build` plus a size report; Lighthouse against the
deployed URL.

**Files:** `frontend/public/*`, `frontend/src/routes/pages/LandingPage.tsx`,
`frontend/src/components/layout/AppShell.tsx`,
`frontend/vite.config.ts`.
**Scope:** Medium.

---

### Phase 7 — Proof and observability

**Tasks**

1. Add Playwright end-to-end coverage over one path per role: sign in, land
   on the role dashboard, open the role's core screen, sign out. Five specs.
   *Files:* `frontend/e2e/*`, `.github/workflows/ci.yml`.
2. Add error reporting for both tiers: `sentry-sdk` on the frontend and
   `sentry-sdk` in Django, wired to one project with the release tagged by
   deploy SHA.
3. Add an uptime check against `/api/v1/ready/` and a CI step that fails on
   a broken install manifest or a missing icon.

**Acceptance criteria**

- CI runs the five role paths on every push and fails on a regression.
- A frontend exception in production appears in the error tracker with the
  user's role and route, and nothing identifying beyond that.

**Verification:** `npm test`, `npm run build`, CI green on a branch.

**Files:** `frontend/e2e/*`, `frontend/package.json`,
`backend/requirements/production.txt`, `.github/workflows/ci.yml`.
**Scope:** Medium.

---

## 5. Decision record

| ID | Decision | Answer | Status |
|---|---|---|---|
| D1 | **Offline student data.** §A.9 of the approved spec says "No offline access" and "Internet connection required at all times". | **Not in scope, and it stays that way.** The limitation was signed off before this plan existed, so it is not reopened. The service worker caches the shell and static assets only; no API response is ever cached. | Closed |
| D2 | **Push notification scope.** Panel correction #16 asks what is needed and is applicable; §L OQ-7 asks whether in-app plus email is enough for v1. | **All notification types.** Grade posted, attendance threshold, behaviour, assessments, risk alerts, interventions, announcements, consultations, maintenance — same fan-out as in-app and email, one extra channel. | Closed |
| D3 | **Sending identity for push and mail.** Web push shows the app's own name; email needs a verified sender. | **`AEGIS — HIS CARE CHRISTIAN INSTITUTE`.** Email still needs a provider-verified address (e.g. `no-reply@<school-domain>`) passed as `DEFAULT_FROM_EMAIL` with this display name; push labels itself with the installed app name. | Closed — the sender address is an ops value, not a code value |
| D4 | **Hosting tier.** Phase 5 needs a worker service and a scheduler. | **Vercel and Render stay.** A worker is a separate Render service from the same image; another provider is acceptable if Render's sleep behaviour or price does not work. | Closed, with the escape hatch named |
| D5 | **Domain and certificate.** The app is installed from `*.vercel.app` today. A school domain makes the install feel real. | Unanswered. | Open — does not block any phase |
| D6 | **Redis durability.** The shared throttle cache is a Render Redis instance. If it sits on the free tier it can expire after a period of inactivity, which silently turns the rate limits back to per-process without failing anything. | **To be tested.** The procedure is in §5.1 below. | Open — gates Phase 5 only |

**What the closed answers change in this plan**

- D1 removes the cached-reads work from Phase 2 and the offline-reads work
  from Phase 6. It also removes the account-scoped cache-key problem and the
  service-worker token question entirely: the worker never stores a token and
  never stores an API response.
- D4 turns Phase 5's worker from "a hypothetical paid service" into "a second
  service on the host we already use".

### 5.1 Testing Redis durability (D6)

The question is not "is the cache shared" — that is already answered and
verified — it is "will this instance still exist in six months". Three
checks, in order:

1. **Read the instance's tier.** Render dashboard → the Redis service → the
   plan row and the banner above it. A free instance shows an expiry notice
   ("this instance will be deleted on <date>" or similar). That banner is the
   answer to the question; no test is needed for it.
2. **Prove the cache is the shared one, not a silent local fallback.**
   `GET https://aegis-0pav.onrender.com/api/v1/ready/` must report
   `"cache": "shared"`. If it reports `"cache": "local"`, the `REDIS_URL`
   variable is not set on the service and every rate limit is per-process
   right now — that is a Phase 1 fix, not a Phase 5 one.
3. **Prove the limits really are shared** with the harness the repo already
   has: `backend/scripts/verify_shared_throttle.py` runs the same failed
   sign-in twice in two separate processes and reports whether the second was
   throttled. Run it against the deployed configuration.

**Decision rule.** If the instance is free and shows an expiry date, Phase 5
puts the queue on a Redis that is not going to disappear: either the paid
instance, or a Redis inside the Supabase project the database already lives
in. If it is already paid, D6 closes with nothing to do.

---

## 6. Sequencing

```
Phase 0 decisions
   ├── Phase 1 production posture        (do first, independent of every decision)
   ├── Phase 2 installable shell         (do second; needs no decision)
   ├── Phase 3 live data                 (do third; needs no decision)
   ├── Phase 6 mobile payload            (no decision needed any more)
   ├── Phase 5 background work           (needs D6 tested)
   ├── Phase 4 push                      (needs D2, D3)
   └── Phase 7 proof + observability     (do last; covers everything above)
```

Phase 1 changes what is served, so it lands alone. Phases 2, 3 and 6 are
independent of each other and of every decision, so they can run in
parallel. Phase 4a (backend) and Phase 6 (frontend) touch different trees and
can also run in parallel.

**Checkpoints**

- After Phase 1: the live service is on production settings; the browsable
  API and the admin site are gone.
- After Phase 3: a user watching an open tab sees new data arrive.
- After Phase 5: a redeploy during an import no longer loses the job.
- After Phase 7: the five role paths are covered by CI, and production
  errors are visible without reading Render logs.

---

## 7. Risks

| Risk | Impact | Mitigation |
|---|---|---|
| Phase 1 removes the QA seed from the build, so a fresh environment has no school in it | The deployed DEV/QA service loses its demo data | Apply Phase 1 to the production service only; keep the QA seeding in a separate QA blueprint or a manual command |
| A service worker caches an API response by accident | A student row is written to disk on a shared device | The worker is configured to write nothing from `/api/*`; the Phase 2 acceptance test opens the worker storage panel and checks it |
| Push lands on the school-branded channel without approval | Reputational problem with the panel or the school | D3 is answered before Phase 4 starts; a neutral title is the fallback |
| The Redis instance is on the free tier and expires | The rate limits silently fall back to per-process, and the Phase 5 queue loses its broker | §5.1 decides this before Phase 5 starts; the queue goes on a Redis that is not going to disappear |
| Adding endpoints breaks the "frozen API contract" rule | Contract violation | Phase 4 adds endpoints only; no existing route, field or payload changes. The addition is recorded in `docs/BACKEND_SPECIFICATION.md` |
| iOS does not deliver push to a browser tab | Phase 4 looks broken on iPhone | iOS 16.4+ delivers push only to a Home Screen install, which Phase 2 provides; the acceptance test uses an installed app |

---

## 8. Explicitly not doing

- **No native app.** CR-001 says browser-only. An installable PWA is the
  sanctioned way to reach a home screen.
- **No offline data, in either direction.** §A.9 of the approved baseline
  says "No offline access" and "Internet connection required at all times".
  No grades, attendance or risk rows are cached for offline reading, and
  nothing is queued for a later write. The app opens offline and says the
  screen needs a connection.
- **No cached API responses at all.** The service worker stores the shell
  and the static assets and nothing else.
- **No rewrite of the API contract.** New endpoints only.
- **No new role.** The five-role model is the approved baseline.
- **No service-worker token storage.** The token stays in `localStorage` for
  now; moving it is its own security change with its own review.

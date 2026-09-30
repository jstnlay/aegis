# AEGIS frontend

React 19 + TypeScript + Vite 8 single-page application for the Academic
Governance and Intervention System. UI follows the PH11.2 design language
(`docs/PH11.2_DESIGN_LANGUAGE.md`) and talks to the frozen Django API contract
(`docs/BACKEND_SPECIFICATION.md`).

## Prerequisites

- Node.js 20+ (engine pinned in `package.json`)
- The AEGIS backend running on `http://localhost:8000` — needed to load data for
  the auth flow and the five role dashboards, which all fetch from the API.
- One route is still a static placeholder and renders without any backend:
  `/app/academics` (`AcademicsLandingPage`). Its own copy says full functionality
  lands in PH11.6, but it was not implemented there. It is reachable by faculty
  and admin.

## Setup

```bash
npm install
cp .env.example .env.local   # adjust VITE_API_BASE_URL if needed
npm run dev                  # http://localhost:5173
```

## Commands

| Command                | Purpose                                               |
| ---------------------- | ----------------------------------------------------- |
| `npm run dev`          | Vite dev server with HMR                              |
| `npm run build`        | Type-check then production build to `dist/`           |
| `npm run preview`      | Serve the production build locally                    |
| `npm run typecheck`    | `tsc -b --force` (strict, project refs)               |
| `npm run lint`         | ESLint (flat config, `eslint.config.mjs`)             |
| `npm run test`         | Vitest (jsdom) unit + component tests                 |
| `npm run format`       | Prettier write                                        |
| `npm run format:check` | Prettier check                                        |
| `npm run smoke`        | Node-side render check of the shell/route/guard layer |

### What `npm run smoke` does and does not cover

`scripts/smoke.tsx` bundles the app with esbuild and renders it in Node (no
browser, no network) to assert the **structural** layer:

- `/login` and `/change-password` mount without error
- the not-found route renders
- `ProtectedRoute` renders its loading skeleton
- `AppShell` landmarks — skip link, `<main>`, brand, auth actions
- navigation config per role (Dashboard entry, page-title resolution) and
  role-scoped route visibility
- `auth/api` and guard module exports

It is **not** a dashboard test: it does not render the five role dashboards, does
not exercise any data fetching, and gives **no browser or visual coverage**. Use
`npm test` for dashboard behaviour and a real browser session for layout and
rendered-contrast checks.

**A passing `npm run smoke` is not evidence that a dashboard was rendered.** It
asserts that modules import, routes mount, and shell/guard wiring is present — it
never paints a dashboard or issues a data request. The PH11.6 dashboards were
browser-rendered in that phase's own verification; later colour changes
(semantic risk/score text, PH11.15) were validated by static resolution of the
built CSS, **not** by a fresh browser run, because the later contrast harness
was blocked by the browser tool's URL policy. Do not read a green smoke run as
browser verification of the current UI.

## Structure

```
src/
  components/ui/         shadcn/ui components (PH11.2-tokenized)
  components/layout/     AppShell, Sidebar, Header, SkipLink, LoadingScreen
  features/
    auth/                AuthProvider/useAuth, api wrappers, route guards
    student/             StudentDashboard + api (hooks, query keys)
    parent/              ParentDashboard + api
    faculty/             FacultyDashboard + api
    guidance/            GuidanceDashboard + api
    admin/               AdminDashboard + api
  lib/
    api.ts               fetch client, silent refresh + token rotation
    auth-storage.ts      localStorage token storage
    error.ts             error normalization (normalizeApiError, getFieldErrors)
    queryClient.ts       shared TanStack Query client
    utils.ts             cn() class merge helper
    roles.ts             ROLES, ROLE_LABELS, userDisplayName
    navigation.ts        role-aware navigation model (single source of truth)
    pagination.ts        fetchAllPages helper
    metric-format.ts     formatCount / formatPercent / N/A handling
    grade-badge.ts       letter-grade class map
    status-badge.ts      risk-level and consultation-status class maps
  routes/
    routes.tsx           route table (see below)
    router.tsx           router instance
    pages/               Login, ChangePassword, RoleLandingPage,
                         AcademicsLandingPage, NotFoundPage
  types/                 frozen backend contract mirrors
  test/setup.ts          Vitest setup (jsdom, matchMedia, ResizeObserver stubs)
```

Tests are colocated as `*.test.ts` / `*.test.tsx` next to the module they cover
(19 files).

### Routes

```
/login                                     LoginPage
/change-password                           ChangePasswordPage
/ (ProtectedRoute)
  /app (AppShell)
    index                            -> /app/dashboard
    /app/dashboard (RoleLandingPage + <Outlet/>)
      index                          -> RoleDashboardRedirect (role -> own route)
      /app/dashboard/student         RequireRole[student]  -> StudentDashboard
      /app/dashboard/parent          RequireRole[parent]   -> ParentDashboard
      /app/dashboard/faculty         RequireRole[faculty]  -> FacultyDashboard
      /app/dashboard/guidance        RequireRole[guidance] -> GuidanceDashboard
      /app/dashboard/admin           RequireRole[admin]    -> AdminDashboard
    /app/academics                    RequireRole[faculty, admin] -> AcademicsLandingPage (static stub)
*                                      NotFoundPage
```

A role accessing a route it is not allowed for is redirected to `/app`, which
resolves to that role's own dashboard.

## Conventions

- Path alias `@/` → `src/` (see `tsconfig.json`, `tsconfig.app.json`).
- API errors are normalized to a single shape (`lib/error.ts`);
  silent refresh + token rotation live in `lib/api.ts`.
- Tailwind only emits utilities it can find as complete literals in the source.
  Never build class names at runtime (`` `bg-${x}-100` `` produces no CSS) —
  use a static typed map instead, as in `lib/grade-badge.ts` and
  `lib/status-badge.ts`.
- Status and grade colours use the PH11.2 semantic tokens. Note the recorded
  accessibility trade-off: risk badges use a text/outline treatment rather than
  the solid fill PH11.2 §6.2 documents, because the pinned token values cannot
  back a small `text-xs` label at 4.5:1. See
  `PH11.6_IMPLEMENTATION_SUMMARY.md` §11 before changing those classes.
- New UI primitives should be added via `npx shadcn@latest add <name>`,
  then re-tokenized if needed (see the PH11.3 note).

## Phase notes

Implementation notes live in `docs/`. Each is a record of the frontend **at the
time that phase closed**, so their test counts, formatting results, and route
tables are historical rather than current — re-run the commands before trusting
any number in them.

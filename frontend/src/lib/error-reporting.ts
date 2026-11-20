/**
 * Frontend error reporting (Phase 7).
 *
 * Off unless `VITE_SENTRY_DSN` is set. Even then the SDK is fetched as a
 * separate chunk: `@sentry/react` is a lot of code, and a deployment with no
 * Sentry project must not ship it to every parent's phone for nothing — the
 * same budget Phase 6 spent the rest of the plan defending.
 *
 * `captureError` is safe to call whether or not reporting is running. It is a
 * no-op until the chunk has loaded, so `ErrorBoundary` can report a render
 * error without waiting on a network fetch and without depending on Sentry.
 */

const DSN = import.meta.env.VITE_SENTRY_DSN

type Sdk = typeof import("@sentry/react")

let sdk: Sdk | null = null

/** Start reporting. Called once from `main.tsx`; never awaited. */
export function initErrorReporting(): void {
  if (!DSN) return

  void import("@sentry/react")
    .then((module) => {
      module.init({
        dsn: DSN,
        // The commit Vercel built, compiled in by vite.config.ts.
        release: __AEGIS_RELEASE__,
        environment: import.meta.env.MODE,
        // Errors only. Request latency is measured where the request happens.
        tracesSampleRate: 0,
        /*
         * What may leave the browser. This app handles a student's name,
         * grades and guidance notes, so the default (collect generously) is
         * the wrong posture: no user identity, no cookies, no request bodies
         * and no URL query strings. A stack trace is what this is for.
         */
        dataCollection: {
          userInfo: false,
          cookies: false,
          httpBodies: [],
          urlQueryParams: false,
        },
      })
      sdk = module
    })
    .catch(() => {
      // A blocked or failed chunk must not break the app it was meant to
      // report on. Nothing else to do: console already carries the error.
    })
}

/** Report a caught error, if reporting is running. */
export function captureError(error: unknown): void {
  sdk?.captureException(error)
}

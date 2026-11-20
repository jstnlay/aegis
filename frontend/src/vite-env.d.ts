/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string
  readonly VITE_SENTRY_DSN?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}

/**
 * Deploy commit SHA, compiled in by `define` in vite.config.ts. Vercel sets
 * `VERCEL_GIT_COMMIT_SHA` without the `VITE_` prefix Vite requires for
 * `import.meta.env`, so it cannot be read from the environment at runtime.
 * Locally it is the literal `"dev"`.
 */
declare const __AEGIS_RELEASE__: string

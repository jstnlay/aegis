import { existsSync, mkdirSync } from "node:fs"
import { fileURLToPath } from "node:url"

import { defineConfig, devices } from "@playwright/test"

/**
 * Phase 7 end-to-end harness.
 *
 * `npm run e2e` is the whole command: it builds the frontend against a local
 * API, starts Django on a throwaway SQLite file with the five `e2e.*` accounts
 * seeded, and runs the journeys in Chromium. No service is needed beyond the
 * browser (`npx playwright install chromium`).
 *
 * Ports are deliberately not the development ones (5173 / 8000): a developer
 * running their own `manage.py runserver` against PostgreSQL must not be the
 * backend these tests talk to, and `strictPort` makes a clash a loud failure
 * rather than a test run against the wrong server.
 */

const BACKEND_PORT = 8001
const PREVIEW_PORT = 4174

const BACKEND_DIR = fileURLToPath(
  new URL("../backend/aegis_backend/", import.meta.url)
)
const VENV_PYTHON = fileURLToPath(
  new URL("../backend/.venv/Scripts/python.exe", import.meta.url)
)

/** The interpreter that runs Django. Override with E2E_PYTHON. */
const PYTHON =
  process.env.E2E_PYTHON ??
  (existsSync(VENV_PYTHON) ? `"${VENV_PYTHON}"` : "python")

/*
 * The database and the seed password come from the environment so the same
 * values reach the server this config starts and the spec that signs in.
 */
const DB_FILE = fileURLToPath(new URL("./.e2e/e2e.sqlite3", import.meta.url))
mkdirSync(fileURLToPath(new URL("./.e2e/", import.meta.url)), {
  recursive: true,
})

const PASSWORD = process.env.PHASE7_E2E_PASSWORD

if (!PASSWORD) {
  throw new Error(
    "PHASE7_E2E_PASSWORD is not set. It is the password " +
      "backend/scripts/seed_phase7_e2e.py gives the e2e.* accounts. There is " +
      "no default: a journey that cannot sign in proves nothing."
  )
}

const API_BASE_URL = `http://127.0.0.1:${BACKEND_PORT}/api/v1`
const PREVIEW_ORIGIN = `http://127.0.0.1:${PREVIEW_PORT}`

/**
 * Django's own environment.
 *
 * `config.settings.test` for the same reasons `scripts/run_tests.py` pins it:
 * SQLite instead of PostgreSQL, and password hashing at 10,000 iterations
 * instead of 1,500,000 — five logins at the production cost would dominate the
 * run. It also keeps the import queue off, so no job is pushed at a Redis.
 */
const BACKEND_ENV = {
  ...process.env,
  DJANGO_SETTINGS_MODULE: "config.settings.test",
  DJANGO_SECRET_KEY: "e2e-only-not-a-real-secret-key",
  DJANGO_DEBUG: "False",
  // base.py defaults this to an empty list, which refuses every Host header.
  DJANGO_ALLOWED_HOSTS: `127.0.0.1,localhost`,
  DJANGO_TEST_DATABASE_NAME: DB_FILE,
  // The preview origin is a different port, so every API call is cross-origin.
  CORS_ALLOWED_ORIGINS: PREVIEW_ORIGIN,
  PHASE7_E2E_PASSWORD: PASSWORD,
}

export default defineConfig({
  testDir: "./e2e",
  /*
   * One worker, no parallelism. The five journeys share one Django process and
   * one SQLite file, and they all sign in and out: parallel workers would
   * interleave sessions and the login throttle for no wall-clock gain at this
   * size.
   */
  fullyParallel: false,
  workers: 1,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["github"], ["list"]] : "list",

  use: {
    baseURL: PREVIEW_ORIGIN,
    trace: "on-first-retry",
    screenshot: "only-on-failure",
  },

  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],

  webServer: [
    {
      /*
       * Start from an empty database, then migrate, seed and serve. Chained
       * rather than split across CI steps so the database, the seed and the
       * server cannot disagree about which file they are using, and so a local
       * run needs no setup beyond the browser.
       *
       * The delete is here and not at module scope: Playwright loads this
       * config in the worker as well, after the servers are already running,
       * so a module-scope delete wipes the database the server is serving.
       *
       * A fresh file every run matters because the seeder only sets a password
       * on the users it creates: a file left over from an earlier run keeps
       * that run's password and then cannot sign in.
       */
      command:
        `node -e "require('fs').rmSync(process.env.DJANGO_TEST_DATABASE_NAME,{force:true})" && ` +
        `${PYTHON} manage.py migrate --noinput && ` +
        `${PYTHON} ../scripts/seed_phase7_e2e.py && ` +
        `${PYTHON} manage.py runserver 127.0.0.1:${BACKEND_PORT} --noreload`,
      cwd: BACKEND_DIR,
      env: BACKEND_ENV,
      url: `${API_BASE_URL}/ready/`,
      reuseExistingServer: false,
      timeout: 180_000,
    },
    {
      /*
       * Build with the local API URL and serve it. The URL is baked in at build
       * time, so the production build cannot be reused here — and building
       * inside this command is what makes a local run one command.
       *
       * VITE_SENTRY_DSN is cleared so the run never reports a test failure as
       * a production error, whatever the developer has exported.
       */
      command: `npm run build && npm run preview -- --port ${PREVIEW_PORT} --strictPort`,
      env: {
        ...process.env,
        VITE_API_BASE_URL: API_BASE_URL,
        VITE_SENTRY_DSN: "",
      },
      url: PREVIEW_ORIGIN,
      reuseExistingServer: false,
      timeout: 180_000,
    },
  ],
})

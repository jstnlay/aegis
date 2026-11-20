import { expect, test, type Page } from "@playwright/test"

/**
 * Phase 7: one journey per role, in a real browser, against a real backend.
 *
 * Every journey walks the same three steps — sign in, open the role's core
 * screen, sign out — because that is the path all five roles walk, and it is
 * the one a wrong route guard, a stale token or a missing role branch breaks
 * first. The five roles are a table rather than five near-identical files: five
 * copies would be five places to forget, and a failure still names the role.
 *
 * What this proves that the unit suites cannot: that the built bundle, the
 * router, the API and the database agree end to end, for each role, in the
 * browser the app is actually used from.
 */

const PASSWORD = process.env.PHASE7_E2E_PASSWORD

if (!PASSWORD) {
  throw new Error(
    "PHASE7_E2E_PASSWORD is not set. It is the password " +
      "backend/scripts/seed_phase7_e2e.py gives the e2e.* accounts. There is " +
      "no skip: a journey that cannot sign in proves nothing."
  )
}

interface Journey {
  role: string
  email: string
  /** Where the role's own dashboard lives. */
  dashboard: string
  /** Sidebar entry for the role's core screen. */
  coreLabel: string
  /** The path that entry opens. */
  corePath: string
}

const JOURNEYS: readonly Journey[] = [
  {
    role: "admin",
    email: "e2e.admin@aegis.dev",
    dashboard: "/app/dashboard/admin",
    coreLabel: "Users",
    corePath: "/app/admin/users",
  },
  {
    role: "faculty",
    email: "e2e.faculty@aegis.dev",
    dashboard: "/app/dashboard/faculty",
    coreLabel: "Academics",
    corePath: "/app/academics",
  },
  {
    role: "guidance",
    email: "e2e.guidance@aegis.dev",
    dashboard: "/app/dashboard/guidance",
    coreLabel: "Risk Alerts",
    corePath: "/app/risk-alerts",
  },
  {
    role: "student",
    email: "e2e.student@aegis.dev",
    dashboard: "/app/dashboard/student",
    coreLabel: "Schedule",
    corePath: "/app/schedule",
  },
  {
    role: "parent",
    email: "e2e.parent@aegis.dev",
    dashboard: "/app/dashboard/parent",
    coreLabel: "Academic Record",
    corePath: "/app/parent/academics",
  },
]

/**
 * Clear the first-visit policy gate.
 *
 * A fresh browser context has no acknowledgment in localStorage, so the dialog
 * is always there and signing in without it does nothing — `onSubmit` returns
 * early. Asserting it is visible is therefore deterministic, not a wait.
 */
async function acknowledgePolicies(page: Page) {
  const gate = page.getByRole("dialog", { name: "Before you begin" })
  await expect(gate).toBeVisible()
  await gate.getByRole("checkbox").check()
  await gate.getByRole("button", { name: "Agree and continue" }).click()
  await expect(gate).toBeHidden()
}

async function signIn(page: Page, journey: Journey) {
  await page.goto("/login")
  await acknowledgePolicies(page)
  // exact: the password field carries a "Show password" toggle whose
  // accessible name still contains the word.
  await page.getByLabel("Email", { exact: true }).fill(journey.email)
  await page.getByLabel("Password", { exact: true }).fill(PASSWORD)
  await page.getByRole("button", { name: "Sign in", exact: true }).click()

  // The role's own dashboard, not the generic one: the redirect through
  // /app/dashboard is part of what is under test.
  await expect(page).toHaveURL(new RegExp(`${journey.dashboard}/?$`))
}

async function signOut(page: Page) {
  await page.getByRole("button", { name: "Account menu" }).click()
  await page.getByRole("menuitem", { name: "Sign out" }).click()

  const confirm = page.getByRole("alertdialog", { name: "Sign out of AEGIS?" })
  await expect(confirm).toBeVisible()
  await confirm.getByRole("button", { name: "Sign out" }).click()

  await expect(page).toHaveURL(/\/login\/?$/)
  // The guard, not just the URL: the tokens are gone, so a reload cannot get
  // back in either. The policy gate deliberately does not reappear — it is a
  // browser-local acknowledgment and outlives the session.
  expect(
    await page.evaluate(() => localStorage.getItem("aegis.access_token"))
  ).toBeNull()
  await expect(
    page.getByRole("heading", { name: "Sign in to AEGIS" })
  ).toBeVisible()
}

for (const journey of JOURNEYS) {
  test(`${journey.role}: signs in, opens ${journey.coreLabel}, signs out`, async ({
    page,
  }) => {
    await signIn(page, journey)

    await page
      .getByRole("link", { name: journey.coreLabel, exact: true })
      .first()
      .click()
    await expect(page).toHaveURL(new RegExp(`${journey.corePath}/?$`))
    await expect(
      page
        .getByRole("heading", { name: journey.coreLabel, exact: true })
        .first()
    ).toBeVisible()
    // A route that renders the error boundary has not "opened".
    await expect(page.getByText("could not be displayed")).toHaveCount(0)

    await signOut(page)
  })
}

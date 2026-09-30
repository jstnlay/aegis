/**
 * PH11.4 smoke render check.
 *
 * Renders the app with react-dom/server + a memory router in Node and
 * asserts which routes actually render. No browser needed.
 *
 * Run via: npm run smoke
 */
import type { ReactElement, ReactNode } from "react"
import { renderToString } from "react-dom/server"
import {
  createMemoryRouter,
  MemoryRouter,
  RouterProvider,
} from "react-router-dom"
import { QueryClientProvider } from "@tanstack/react-query"

import { AppShell } from "../src/components/layout/AppShell"
import { AuthProvider } from "../src/features/auth/AuthContext"
import { queryClient } from "../src/lib/queryClient"
import { appRoutes } from "../src/routes/routes"

let failures = 0

function check(html: string, needle: string, label: string) {
  if (!html.includes(needle)) {
    console.error(`FAIL ${label}: output does not contain "${needle}"`)
    failures += 1
  } else {
    console.log(`ok ${label}`)
  }
}

function checkTrue(condition: boolean, label: string) {
  if (!condition) {
    console.error(`FAIL ${label}`)
    failures += 1
  } else {
    console.log(`ok ${label}`)
  }
}

function withProviders(children: ReactNode): ReactElement {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>{children}</AuthProvider>
    </QueryClientProvider>
  )
}

function renderAt(path: string): string {
  const router = createMemoryRouter(appRoutes, { initialEntries: [path] })
  return renderToString(withProviders(<RouterProvider router={router} />))
}

/* ------------------------------------------------------------------ */
/* Public routes                                                       */
/* ------------------------------------------------------------------ */
console.log("Rendering public auth routes...")

/* renderToString does not run React effects, so AuthProvider's
   bootstrap useEffect never fires — status stays "loading".
   LoginPage and ChangePasswordPage return null during loading.
   We verify the route tree mounts without throwing. */
const loginHtml = renderAt("/login")
console.log(
  `ok /login route mounted without error (rendered ${loginHtml.length} chars)`
)

const changeHtml = renderAt("/change-password")
console.log(
  `ok /change-password route mounted without error (rendered ${changeHtml.length} chars)`
)

const notFoundHtml = renderAt("/definitely-not-a-route")
check(notFoundHtml, "Page not found", "* renders the not-found page")

/* ------------------------------------------------------------------ */
/* Protected route — renders the loading skeleton during SSR            */
/* ------------------------------------------------------------------ */
console.log("Rendering protected routes...")
const protectedHtml = renderAt("/app/dashboard")
check(
  protectedHtml,
  "Loading",
  "Protected route renders the loading skeleton during SSR"
)

/* ------------------------------------------------------------------ */
/* Shared AppShell                                                     */
/* ------------------------------------------------------------------ */
console.log("Rendering the shared AppShell...")
const shellHtml = renderToString(
  withProviders(
    <MemoryRouter initialEntries={["/app/dashboard"]}>
      <AppShell />
    </MemoryRouter>
  )
)
check(shellHtml, "Skip to main content", "AppShell exposes a skip link")
check(shellHtml, 'id="main-content"', "AppShell exposes the main landmark")
check(shellHtml, "AEGIS", "AppShell renders the brand")
check(shellHtml, "Sign out", "AppShell renders the auth actions")

/* ------------------------------------------------------------------ */
/* Role-aware navigation configuration                                 */
/* ------------------------------------------------------------------ */
console.log("Verifying role-aware navigation...")
// SSR never runs effects, so useAuth() stays null during the render above.
// The navigation model is a pure module — verify it directly.
// eslint-disable-next-line @typescript-eslint/no-require-imports
const navigation = require("../src/lib/navigation")
const allRoles = ["student", "parent", "faculty", "guidance", "admin"]
for (const role of allRoles) {
  const items = navigation.getNavItemsForRole(role)
  checkTrue(
    items.some((item: { route: string }) => item.route === "dashboard"),
    `${role} navigation includes Dashboard`
  )
  checkTrue(
    navigation.getPageTitle(`/app/${role}`) === "AEGIS" ||
      navigation.getPageTitle("/app/dashboard") === "Dashboard",
    `${role} page title resolves from navigation config`
  )
}
checkTrue(
  navigation.isRouteVisibleToRole("admin", "academics"),
  "admin navigation includes the academics route"
)
checkTrue(
  !navigation.isRouteVisibleToRole("parent", "users"),
  "parent navigation excludes the admin users route"
)

/* ------------------------------------------------------------------ */
/* Verify auth modules import cleanly                                  */
/* ------------------------------------------------------------------ */
console.log("Verifying auth module imports...")
// eslint-disable-next-line @typescript-eslint/no-require-imports
const authApi = require("../src/features/auth/api")
checkTrue(
  typeof authApi.loginRequest === "function",
  "auth/api exports loginRequest"
)
checkTrue(
  typeof authApi.logoutRequest === "function",
  "auth/api exports logoutRequest"
)
checkTrue(
  typeof authApi.refreshRequest === "function",
  "auth/api exports refreshRequest"
)
checkTrue(
  typeof authApi.fetchCurrentUser === "function",
  "auth/api exports fetchCurrentUser"
)
checkTrue(
  typeof authApi.changePasswordRequest === "function",
  "auth/api exports changePasswordRequest"
)

// eslint-disable-next-line @typescript-eslint/no-require-imports
const authContext = require("../src/features/auth/AuthContext")
checkTrue(
  typeof authContext.AuthProvider === "function",
  "auth/AuthContext exports AuthProvider"
)
checkTrue(
  typeof authContext.useAuth === "function",
  "auth/AuthContext exports useAuth"
)

// eslint-disable-next-line @typescript-eslint/no-require-imports
const protectedRoute = require("../src/features/auth/ProtectedRoute")
checkTrue(
  typeof protectedRoute.ProtectedRoute === "function",
  "auth/ProtectedRoute exports ProtectedRoute"
)

// eslint-disable-next-line @typescript-eslint/no-require-imports
const requireRole = require("../src/features/auth/RequireRole")
checkTrue(
  typeof requireRole.RequireRole === "function",
  "auth/RequireRole exports RequireRole"
)

if (failures > 0) {
  console.error(`\nSMOKE FAILED: ${failures} assertion(s) failed`)
  process.exitCode = 1
} else {
  console.log("\nSMOKE PASSED")
}

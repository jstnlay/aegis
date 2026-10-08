import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { fireEvent, render, screen } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { MemoryRouter, Navigate, Route, Routes } from "react-router-dom"

import { AppShell } from "@/components/layout/AppShell"
import { AuthProvider } from "@/features/auth/AuthContext"
import { ProtectedRoute } from "@/features/auth/ProtectedRoute"
import { RequireRole } from "@/features/auth/RequireRole"
import { fetchCurrentUser, restorePersistedTokens } from "@/features/auth/api"
import { tokenStorage } from "@/lib/auth-storage"
import { AcademicsLandingPage } from "@/routes/pages/AcademicsLandingPage"
import { RoleLandingPage } from "@/routes/pages/RoleLandingPage"
import { ROLES, type Role, type User } from "@/types/auth"

const ROLE_LABEL: Record<Role, string> = {
  student: "Student",
  parent: "Parent",
  faculty: "Faculty",
  guidance: "Guidance Counselor",
  admin: "Administrator",
}

/* ---------- auth module mocks (bootstrap + /me flow) ----------------- */

const apiState = vi.hoisted(() => {
  const handlers = new Set<() => void>()
  return {
    onSessionExpired: (handler: () => void) => {
      handlers.add(handler)
      return () => handlers.delete(handler)
    },
  }
})

vi.mock("@/lib/api", () => ({
  onSessionExpired: apiState.onSessionExpired,
}))

vi.mock("@/features/auth/api", () => ({
  loginRequest: vi.fn(),
  logoutRequest: vi.fn(),
  fetchCurrentUser: vi.fn(),
  changePasswordRequest: vi.fn(),
  restorePersistedTokens: vi.fn(),
}))

const mockedMe = vi.mocked(fetchCurrentUser)
const mockedRestore = vi.mocked(restorePersistedTokens)

const tokenPair = { access: "access-token", refresh: "refresh-token" }

function makeUser(role: Role): User {
  return {
    id: `u-${role}`,
    email: `${role}@school.edu`,
    username: role,
    first_name: "Ana",
    last_name: "Cruz",
    role,
    phone_number: null,
    address: null,
    language_preference: null,
    is_active: true,
    created_at: "2025-01-01T00:00:00Z",
    updated_at: "2025-01-01T00:00:00Z",
  }
}

/* ---------- render helpers ------------------------------------------- */

function testRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<div>Login route</div>} />
      <Route
        path="/change-password"
        element={<div>Change password route</div>}
      />
      <Route path="/" element={<ProtectedRoute />}>
        <Route path="app" element={<AppShell />}>
          <Route index element={<Navigate to="dashboard" replace />} />
          <Route path="dashboard" element={<RoleLandingPage />} />
          <Route
            path="academics"
            element={
              <RequireRole allowedRoles={["faculty", "admin"]}>
                <AcademicsLandingPage />
              </RequireRole>
            }
          />
          <Route path="*" element={<Navigate to="dashboard" replace />} />
        </Route>
      </Route>
      <Route path="*" element={<div>Not found</div>} />
    </Routes>
  )
}

function wrapApp(initialPath: string, children: React.ReactNode) {
  return (
    <QueryClientProvider client={new QueryClient()}>
      <AuthProvider>
        <MemoryRouter initialEntries={[initialPath]}>{children}</MemoryRouter>
      </AuthProvider>
    </QueryClientProvider>
  )
}

async function renderAuthenticatedApp(
  role: Role,
  initialPath = "/app/dashboard"
) {
  mockedRestore.mockReturnValue(tokenPair)
  tokenStorage.setTokens(tokenPair.access, tokenPair.refresh)
  mockedMe.mockResolvedValue(makeUser(role))
  return render(wrapApp(initialPath, testRoutes()))
}

beforeEach(() => {
  vi.clearAllMocks()
  localStorage.clear()
  document.body.innerHTML = ""
})

/* =====================================================================
   Authenticated user is shown in the shell
   ===================================================================== */
describe("authenticated user in shell", () => {
  it.each(ROLES)(
    "renders the user's name and role label (%s)",
    async (role) => {
      await renderAuthenticatedApp(role)

      // The header always shows the current user's name and role label.
      expect(await screen.findAllByText(/Ana Cruz/)).not.toHaveLength(0)
      expect(screen.getAllByText(ROLE_LABEL[role]).length).toBeGreaterThan(0)
    }
  )
})

/* =====================================================================
   Role-aware sidebar navigation
   ===================================================================== */
describe("role-aware sidebar", () => {
  /**
   * PH11.7 made Academics and Attendance real routes for students, so both are
   * now links. `Assessments` remains the planned-entry assertion: it must stay
   * informative and non-navigable rather than pointing at a fake route.
   */
  it("shows Dashboard, Academics and Attendance as real links for students", async () => {
    await renderAuthenticatedApp("student")

    expect(
      await screen.findByRole("link", { name: "Dashboard" })
    ).toHaveAttribute("href", "/app/dashboard")
    expect(screen.getByRole("link", { name: "Academics" })).toHaveAttribute(
      "href",
      "/app/academics"
    )
    expect(screen.getByRole("link", { name: "Attendance" })).toHaveAttribute(
      "href",
      "/app/attendance"
    )

    // Assessments is now a real student route (`student/assessments`), for
    // taking and reviewing objective 2.4. The planned `Reports` entry remains
    // informative and non-navigable rather than pointing at a fake route.
    expect(screen.getByRole("link", { name: "Assessments" })).toHaveAttribute(
      "href",
      "/app/student/assessments"
    )
    expect(screen.queryByRole("link", { name: "Reports" })).toBeNull()
    expect(screen.getByText("Reports")).toBeInTheDocument()
    expect(screen.getAllByText("Planned").length).toBeGreaterThan(0)
  })

  it("shows the parent the three real PH11.9 links, and no Attendance placeholder", async () => {
    /*
     * PH11.9 gave parent real routes. The old assertion was that Attendance
     * stayed a non-link placeholder; that placeholder is gone because the
     * attendance data now lives inside `Academic Record`, so a separate
     * Attendance entry would have duplicated it and pointed nowhere.
     */
    await renderAuthenticatedApp("parent")

    expect(
      await screen.findByRole("link", { name: "Dashboard" })
    ).toBeInTheDocument()
    expect(
      screen.getByRole("link", { name: "Academic Record" })
    ).toHaveAttribute("href", "/app/parent/academics")
    expect(screen.getByRole("link", { name: "Assessments" })).toHaveAttribute(
      "href",
      "/app/parent/assessments"
    )
    expect(
      screen.getByRole("link", { name: "Student Support" })
    ).toHaveAttribute("href", "/app/parent/support")
    expect(screen.queryByText("Attendance")).toBeNull()
  })

  it("shows the Academics and Attendance links to faculty", async () => {
    await renderAuthenticatedApp("faculty")

    expect(
      await screen.findByRole("link", { name: "Academics" })
    ).toHaveAttribute("href", "/app/academics")
    expect(screen.getByRole("link", { name: "Attendance" })).toHaveAttribute(
      "href",
      "/app/attendance"
    )
  })

  it("shows role-specific groups in the sidebar", async () => {
    await renderAuthenticatedApp("guidance")
    // PH11.8 turned Risk Alerts from a roadmap entry into a real route, so
    // guidance now gets a link rather than a non-navigable placeholder.
    expect((await screen.findAllByText("Risk Alerts")).length).toBeGreaterThan(
      0
    )
    expect(
      await screen.findByRole("link", { name: "Risk Alerts" })
    ).toBeInTheDocument()
    expect(screen.getByText("Student Support")).toBeInTheDocument()
  })

  it("gives guidance links for the whole PH11.8 surface", async () => {
    await renderAuthenticatedApp("guidance")

    for (const label of [
      "Risk Alerts",
      "Consultations",
      "Interventions",
      "Students",
      "Assessments",
      "Account Settings",
    ]) {
      expect(
        await screen.findByRole("link", { name: label }),
        label
      ).toBeInTheDocument()
    }

    // /app/guidance is not a page and has no nav entry at all, so neither a
    // link nor a placeholder should appear.
    expect(screen.queryByText("Guidance")).toBeNull()
    expect(screen.queryByRole("link", { name: "Guidance" })).toBeNull()
  })

  it("keeps the PH11.8 guidance links out of a student's sidebar", async () => {
    await renderAuthenticatedApp("student")

    for (const label of [
      "Risk Alerts",
      "Consultations",
      "Interventions",
      "Students",
      "Account Settings",
    ]) {
      expect(screen.queryByRole("link", { name: label }), label).toBeNull()
    }
  })

  it("keeps admin-only items out of non-admin navigation", async () => {
    await renderAuthenticatedApp("student")
    // Users and Settings are absent from the student's entire tree.
    expect(screen.queryByText("Users")).toBeNull()
    expect(screen.queryByText("Settings")).toBeNull()
  })

  it("gives admin eight real links and no Settings placeholder", async () => {
    /*
     * PH11.9 replaced this with real routes. The `users` planned entry became
     * the `admin/users` page, and `settings` was removed entirely because no
     * SystemSetting endpoint exists in the backend for it to reach.
     */
    await renderAuthenticatedApp("admin")

    expect(
      await screen.findByRole("link", { name: "Dashboard" })
    ).toBeInTheDocument()

    for (const [label, href] of [
      ["Academic Structure", "/app/admin/academics"],
      ["Grades", "/app/admin/grades"],
      ["Attendance", "/app/admin/attendance"],
      ["Analytics", "/app/admin/analytics"],
      ["Users", "/app/admin/users"],
      ["Imports & Exports", "/app/admin/data"],
      ["Content", "/app/admin/cms"],
      ["Audit Logs", "/app/admin/audit"],
    ] as const) {
      expect(screen.getByRole("link", { name: label }), label).toHaveAttribute(
        "href",
        href
      )
    }

    expect(screen.queryByText("Settings")).toBeNull()
  })

  it("keeps every admin link off the other four roles", async () => {
    for (const role of ["student", "parent", "faculty", "guidance"] as const) {
      const view = await renderAuthenticatedApp(role)

      for (const label of [
        "Academic Structure",
        "Analytics",
        "Imports & Exports",
        "Audit Logs",
      ]) {
        expect(
          screen.queryByRole("link", { name: label }),
          `${role} / ${label}`
        ).toBeNull()
      }

      view.unmount()
    }
  })

  it("shows parent the three real links and no Attendance placeholder", async () => {
    /*
     * PH11.7 kept Attendance as a non-link placeholder for parent. PH11.9 gave
     * parent a real attendance view inside `Academic Record`, so the
     * placeholder is gone: a separate Attendance entry would duplicate that
     * data and point at no route.
     */
    await renderAuthenticatedApp("parent")

    expect(
      await screen.findByRole("link", { name: "Dashboard" })
    ).toBeInTheDocument()
    expect(
      screen.getByRole("link", { name: "Academic Record" })
    ).toHaveAttribute("href", "/app/parent/academics")
    expect(screen.getByRole("link", { name: "Assessments" })).toHaveAttribute(
      "href",
      "/app/parent/assessments"
    )
    expect(
      screen.getByRole("link", { name: "Student Support" })
    ).toHaveAttribute("href", "/app/parent/support")
    expect(screen.queryByText("Attendance")).toBeNull()
  })
})

/* =====================================================================
   Active navigation state
   ===================================================================== */
describe("active navigation state", () => {
  it("marks the current route with aria-current=page", async () => {
    await renderAuthenticatedApp("faculty", "/app/academics")

    const academics = await screen.findByRole("link", { name: "Academics" })
    expect(academics).toHaveAttribute("aria-current", "page")
    const dashboard = screen.getByRole("link", { name: "Dashboard" })
    expect(dashboard).not.toHaveAttribute("aria-current")
  })

  it("marks Dashboard when on the dashboard route", async () => {
    await renderAuthenticatedApp("student", "/app/dashboard")
    const dashboard = await screen.findByRole("link", { name: "Dashboard" })
    expect(dashboard).toHaveAttribute("aria-current", "page")
  })
})

/* =====================================================================
   Role landing content
   ===================================================================== */
describe("role landing content", () => {
  it.each([
    ["student", "Student Portal"],
    ["parent", "Parent Portal"],
    ["faculty", "Faculty Dashboard"],
    ["guidance", "Guidance Center"],
    ["admin", "Administration Panel"],
  ] as const)("renders a role-specific landing for %s", async (role, title) => {
    await renderAuthenticatedApp(role)
    expect(await screen.findByRole("heading", { name: title })).toBeDefined()
  })

  it("does not fabricate statistics or numbers", async () => {
    const { container } = await renderAuthenticatedApp("student")
    await screen.findByRole("heading", { name: "Student Portal" })
    const text = container.textContent ?? ""
    // Landing content must stay honest — no invented KPI values.
    expect(/\b\d{3,}\b/.test(text)).toBe(false)
  })
})

/* =====================================================================
   Unauthorized role route behavior
   ===================================================================== */
describe("unauthorized role route behavior", () => {
  it("redirects a student away from /app/academics", async () => {
    await renderAuthenticatedApp("student", "/app/academics")

    // RequireRole sends the student back to the shared dashboard.
    const heading = await screen.findByRole("heading", {
      name: "Student Portal",
    })
    expect(heading).toBeDefined()
    expect(screen.queryByText(/Getting started/)).toBeNull()
  })

  it("allows a faculty member onto /app/academics", async () => {
    await renderAuthenticatedApp("faculty", "/app/academics")
    const headings = await screen.findAllByRole("heading", {
      name: "Academics",
    })
    expect(headings.length).toBeGreaterThan(0)
  })
})

/* =====================================================================
   No-navigation / fallback behavior
   ===================================================================== */
describe("no-navigation / fallback behavior", () => {
  it("redirects an unauthenticated user to login (no navigation rendered)", async () => {
    mockedRestore.mockReturnValue(null)
    tokenStorage.clear()

    render(wrapApp("/app/dashboard", testRoutes()))

    expect(await screen.findByText("Login route")).toBeDefined()
    expect(screen.queryByRole("navigation")).toBeNull()
  })
})

/* =====================================================================
   Render-error containment (PH11.9 foundation C)
   ===================================================================== */

/** Throws during render, the way a malformed record does. */
function MalformedRecord(): React.ReactElement {
  throw new Error("Objects are not valid as a React child")
}

describe("a page render failure does not unmount the shell", () => {
  it("keeps navigation mounted and offers recovery", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {})
    mockedRestore.mockReturnValue(tokenPair)
    tokenStorage.setTokens(tokenPair.access, tokenPair.refresh)
    mockedMe.mockResolvedValue(makeUser("admin"))

    const routes = (
      <Routes>
        <Route path="/" element={<ProtectedRoute />}>
          <Route path="app" element={<AppShell />}>
            <Route index element={<Navigate to="broken" replace />} />
            <Route path="broken" element={<MalformedRecord />} />
            <Route path="dashboard" element={<div>Dashboard route</div>} />
            <Route path="*" element={<Navigate to="dashboard" replace />} />
          </Route>
        </Route>
      </Routes>
    )

    render(wrapApp("/app/broken", routes))

    // The recovery state replaces only the page body.
    expect(await screen.findByRole("alert")).toBeDefined()

    // The shell itself survives: sidebar navigation and header are still
    // mounted, so the user is not stranded on a blank page.
    expect(screen.getByRole("navigation")).toBeDefined()
    expect(screen.getAllByText(/Ana Cruz/).length).toBeGreaterThan(0)
    expect(screen.getByRole("button", { name: /try again/i })).toBeDefined()

    // And navigating to a healthy route clears the error with no reload.
    fireEvent.click(screen.getByRole("link", { name: /dashboard/i }))
    expect(await screen.findByText("Dashboard route")).toBeDefined()
    expect(screen.queryByRole("alert")).toBeNull()
  })
})

/* =====================================================================
   PH11.11 — mobile drawer keyboard contract and route-change focus
   ===================================================================== */

/**
 * jsdom's `matchMedia` never matches, because it evaluates no media queries
 * against a viewport. `Sidebar` needs to know whether it is at the `lg`
 * breakpoint or below to know whether the drawer is actually off-canvas, so
 * these tests pin the viewport explicitly. Without this the desktop layout
 * could not be told apart from the mobile one.
 */
function stubViewport(options: { wide: boolean }) {
  const original = window.matchMedia
  window.matchMedia = ((query: string) => ({
    matches: query.includes("min-width") ? options.wide : false,
    media: query,
    onchange: null,
    addEventListener: () => {},
    removeEventListener: () => {},
    addListener: () => {},
    removeListener: () => {},
    dispatchEvent: () => false,
  })) as unknown as typeof window.matchMedia

  return () => {
    window.matchMedia = original
  }
}

/**
 * The shell renders only after the auth bootstrap resolves, so every
 * assertion here has to wait for it. Waiting on the hamburger is also the
 * narrowest possible confirmation that the header mounted.
 */
async function shellReady() {
  return screen.findByRole("button", { name: /open navigation/i })
}

function primaryNav(): HTMLElement {
  return screen.getByRole("navigation", { name: "Main" })
}

describe("PH11.11 mobile drawer keyboard contract", () => {
  it("reports its state and the region it controls", async () => {
    const restore = stubViewport({ wide: false })
    try {
      await renderAuthenticatedApp("student")
      const trigger = await shellReady()

      // PH11.2 §16.3: the control has to say whether what it controls is open.
      expect(trigger).toHaveAttribute("aria-expanded", "false")
      expect(trigger).toHaveAttribute("aria-controls", primaryNav().id)
    } finally {
      restore()
    }
  })

  it("updates aria-expanded when the drawer is opened", async () => {
    const restore = stubViewport({ wide: false })
    try {
      await renderAuthenticatedApp("student")
      const trigger = await shellReady()

      fireEvent.click(trigger)

      expect(trigger).toHaveAttribute("aria-expanded", "true")
    } finally {
      restore()
    }
  })

  it("removes the off-canvas navigation from the tab order while it is closed", async () => {
    const restore = stubViewport({ wide: false })
    try {
      await renderAuthenticatedApp("student")
      await shellReady()

      // Closed and narrow: the drawer is translated off screen, so its links must
      // not stay focusable. A keyboard user used to tab invisibly through the
      // whole navigation before reaching anything on the page.
      expect(primaryNav()).toHaveAttribute("inert")
    } finally {
      restore()
    }
  })

  it("keeps the navigation focusable while the drawer is open", async () => {
    const restore = stubViewport({ wide: false })
    try {
      await renderAuthenticatedApp("student")
      const trigger = await shellReady()

      fireEvent.click(trigger)

      expect(primaryNav()).not.toHaveAttribute("inert")
    } finally {
      restore()
    }
  })

  it("never marks the navigation inert at desktop width, where it is always visible", async () => {
    const restore = stubViewport({ wide: true })
    try {
      await renderAuthenticatedApp("student")
      await shellReady()

      // `inert` is a DOM attribute with no responsive variant, so applying it
      // purely on `open` would strip the navigation from the tab order on the
      // one layout where the sidebar is permanently on screen.
      expect(primaryNav()).not.toHaveAttribute("inert")
    } finally {
      restore()
    }
  })

  it("closes the drawer on Escape", async () => {
    const restore = stubViewport({ wide: false })
    try {
      await renderAuthenticatedApp("student")
      const trigger = await shellReady()

      fireEvent.click(trigger)
      expect(primaryNav()).not.toHaveAttribute("inert")

      // PH11.2 §16.3: "Escape key: closes modals, dropdowns, and drawers."
      fireEvent.keyDown(document, { key: "Escape" })

      expect(primaryNav()).toHaveAttribute("inert")
    } finally {
      restore()
    }
  })

  it("returns focus to the trigger when the drawer closes", async () => {
    const restore = stubViewport({ wide: false })
    try {
      await renderAuthenticatedApp("student")
      const trigger = await shellReady()

      trigger.focus()
      fireEvent.click(trigger)
      fireEvent.keyDown(document, { key: "Escape" })

      // Focus was inside the drawer, which has just become inert. Leaving it
      // there drops the reader onto an unreachable element.
      expect(document.activeElement).toBe(trigger)
    } finally {
      restore()
    }
  })

  it("moves focus to the main region on navigation", async () => {
    // Two constraints on this test, both learned the hard way:
    //
    // 1. Desktop width, because the sidebar is `inert` at narrow widths while
    //    closed — which is the other test's point, and correctly hides its links
    //    from the accessibility tree.
    // 2. Faculty, not admin. `testRoutes()` mounts `AcademicsLandingPage` at
    //    `/app/academics` and sends everything else to the dashboard. An admin's
    //    "Academic Structure" link points at `/app/admin/academics`, which that
    //    router does not define, so the click bounced back to the dashboard and
    //    a `findByRole` for the academics page would never resolve.
    const restore = stubViewport({ wide: true })
    try {
      await renderAuthenticatedApp("faculty", "/app/dashboard")
      await shellReady()

      fireEvent.click(screen.getByRole("link", { name: "Academics" }))

      // The outlet swapped underneath a client-side navigation, so focus has to
      // be placed deliberately or it stays on the link that is now gone.
      await screen.findByRole("heading", { name: "Academics", level: 2 })
      expect(document.activeElement).toBe(
        document.getElementById("main-content")
      )
    } finally {
      restore()
    }
  })

  it("does not steal focus on first render", async () => {
    const restore = stubViewport({ wide: false })
    try {
      await renderAuthenticatedApp("student")
      await shellReady()

      // Focusing `main` on mount would yank focus away from whatever opened the
      // shell.
      expect(document.activeElement).not.toBe(
        document.getElementById("main-content")
      )
    } finally {
      restore()
    }
  })
})

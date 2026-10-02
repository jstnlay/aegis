import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, screen } from "@testing-library/react"
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

    // Planned roadmap items are informative but never fake routes.
    expect(screen.queryByRole("link", { name: "Assessments" })).toBeNull()
    expect(screen.getByText("Assessments")).toBeInTheDocument()
    expect(screen.getAllByText("Planned").length).toBeGreaterThan(0)
  })

  it("keeps Attendance planned (not a link) for parent", async () => {
    await renderAuthenticatedApp("parent")

    expect(
      await screen.findByRole("link", { name: "Dashboard" })
    ).toBeInTheDocument()
    expect(screen.queryByRole("link", { name: "Attendance" })).toBeNull()
    expect(screen.getByText("Attendance")).toBeInTheDocument()
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
    // Guidance sees Student Support / Risk Alerts roadmap entry (in the
    // sidebar and echoed by the landing-page roadmap list).
    expect((await screen.findAllByText("Risk Alerts")).length).toBeGreaterThan(
      0
    )
    expect(screen.queryByRole("link", { name: "Risk Alerts" })).toBeNull()
    expect(screen.getByText("Student Support")).toBeInTheDocument()
  })

  it("keeps admin-only items out of non-admin navigation", async () => {
    await renderAuthenticatedApp("student")
    // Users and Settings are absent from the student's entire tree.
    expect(screen.queryByText("Users")).toBeNull()
    expect(screen.queryByText("Settings")).toBeNull()
  })

  it("shows admin-only items as planned entries for admins", async () => {
    await renderAuthenticatedApp("admin")
    expect(await screen.findByText("Users")).toBeInTheDocument()
    expect(screen.getByText("Settings")).toBeInTheDocument()
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

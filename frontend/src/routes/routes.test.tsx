import { render, screen, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import type { ReactNode } from "react"
import { createMemoryRouter, RouterProvider } from "react-router-dom"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { appRoutes } from "@/routes/routes"
import type { Role, User } from "@/types/auth"

const authState = vi.hoisted(() => ({ user: null as User | null }))

vi.mock("@/features/auth/AuthContext", () => ({
  useAuth: () => ({
    status: "authenticated",
    user: authState.user,
    mustChangePassword: false,
    isAuthenticated: true,
    login: vi.fn(),
    logout: vi.fn(),
    changePassword: vi.fn(),
  }),
  AuthProvider: ({ children }: { children: ReactNode }) => children,
}))

// Keep dashboard data hooks inert — this test only exercises routing/guards.
vi.mock("@/lib/pagination", () => ({
  fetchAllPages: vi.fn(async () => ({ results: [], count: 0 })),
}))
vi.mock("@/lib/api", () => ({
  API_BASE_URL: "http://localhost:8000/api/v1",
  onSessionExpired: vi.fn(() => () => {}),
  apiClient: {
    get: vi.fn(async () => ({
      data: { count: 0, next: null, previous: null, results: [] },
    })),
  },
}))

function makeUser(role: Role): User {
  return {
    id: `u-${role}`,
    email: `${role}@school.edu`,
    username: role,
    first_name: "Test",
    last_name: role,
    role,
    phone_number: null,
    address: null,
    language_preference: null,
    is_active: true,
    created_at: "2025-01-01T00:00:00Z",
    updated_at: "2025-01-01T00:00:00Z",
  }
}

function renderAt(path: string) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  const router = createMemoryRouter(appRoutes, { initialEntries: [path] })
  return render(
    <QueryClientProvider client={client}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  )
}

beforeEach(() => {
  authState.user = null
})

const ROLE_CASES: ReadonlyArray<{ role: Role; heading: RegExp }> = [
  { role: "student", heading: /Student Dashboard/i },
  { role: "parent", heading: /Parent Portal/i },
  { role: "faculty", heading: /Faculty Dashboard/i },
  { role: "guidance", heading: /Guidance Center/i },
  { role: "admin", heading: /Administration Panel/i },
]

describe("PH11.7 domain routes", () => {
  /**
   * The AppShell header already renders an `<h1>` with the page title, so a
   * heading assertion alone is ambiguous. Each case asserts a marker that is
   * unique to the role-specific page body.
   */
  const DOMAIN_CASES: ReadonlyArray<{
    role: Role
    path: string
    marker: RegExp
  }> = [
    {
      role: "student",
      path: "/app/academics",
      marker: /Grades appear here once they are finalized/i,
    },
    {
      role: "faculty",
      path: "/app/academics",
      marker: /Encode a grade/i,
    },
    {
      role: "student",
      path: "/app/attendance",
      marker: /Attendance records tied to you/i,
    },
    {
      role: "faculty",
      path: "/app/attendance",
      marker: /Take attendance/i,
    },
  ]

  it.each(DOMAIN_CASES)(
    "renders $role $path without a blank page",
    async ({ role, path, marker }) => {
      authState.user = makeUser(role)
      renderAt(path)

      expect(await screen.findByText(marker)).toBeInTheDocument()
      expect(document.body.textContent?.trim().length ?? 0).toBeGreaterThan(0)
    }
  )

  it("redirects a parent away from the student-only attendance route", async () => {
    authState.user = makeUser("parent")
    renderAt("/app/attendance")

    // RequireRole bounces to /app -> dashboard -> parent dashboard.
    expect(
      await screen.findByRole("heading", { name: /Parent Portal/i })
    ).toBeInTheDocument()
    await waitFor(() =>
      expect(screen.queryByText(/Take attendance/i)).not.toBeInTheDocument()
    )
  })

  it("redirects guidance away from Academics", async () => {
    authState.user = makeUser("guidance")
    renderAt("/app/academics")

    expect(
      await screen.findByRole("heading", { name: /Guidance Center/i })
    ).toBeInTheDocument()
    await waitFor(() =>
      expect(screen.queryByText(/Encode a grade/i)).not.toBeInTheDocument()
    )
  })

  it("shows admin the documented Academics placeholder, not a student view", async () => {
    authState.user = makeUser("admin")
    renderAt("/app/academics")

    expect(
      await screen.findByText(/first domain to be implemented/i)
    ).toBeInTheDocument()
    // Admin must not be shown the student grade-record surface.
    expect(
      screen.queryByText(/Grades appear here once they are finalized/i)
    ).not.toBeInTheDocument()
  })
})

describe("role dashboard routes", () => {
  it.each(ROLE_CASES)(
    "renders the $role dashboard at /app/dashboard/$role without a blank page",
    async ({ role, heading }) => {
      authState.user = makeUser(role)
      renderAt(`/app/dashboard/${role}`)

      expect(
        await screen.findByRole("heading", { name: heading })
      ).toBeInTheDocument()
      expect(document.body.textContent?.trim().length ?? 0).toBeGreaterThan(0)
    }
  )

  it("redirects a role to its own dashboard when it hits another role's route", async () => {
    authState.user = makeUser("student")
    renderAt("/app/dashboard/admin")

    // RequireRole bounces to /app -> dashboard -> student dashboard.
    expect(
      await screen.findByRole("heading", { name: /Student Dashboard/i })
    ).toBeInTheDocument()
    await waitFor(() =>
      expect(
        screen.queryByRole("heading", { name: /Administration Panel/i })
      ).not.toBeInTheDocument()
    )
  })

  it("redirects the bare /app/dashboard index to the role's dashboard", async () => {
    authState.user = makeUser("faculty")
    renderAt("/app/dashboard")

    expect(
      await screen.findByRole("heading", { name: /Faculty Dashboard/i })
    ).toBeInTheDocument()
  })
})

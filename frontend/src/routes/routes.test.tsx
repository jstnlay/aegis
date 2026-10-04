import { render, screen, waitFor, within } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import type { ReactNode } from "react"
import { createMemoryRouter, RouterProvider } from "react-router-dom"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { appRoutes } from "@/routes/routes"
import { ROLES } from "@/types/auth"
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
    // Routing only, so every response is inert. The shape still has to match
    // what the hook destructures: the guidance report and the attendance
    // summary are single objects, not paginated envelopes.
    get: vi.fn(async (url: string) => {
      if (url.startsWith("/guidance/reports/student/")) {
        return {
          data: {
            student: "sp-1",
            student_name: "Test Guidance",
            student_id_code: "S-0001",
            behavioral_note_counts: {},
            consultation_summary: { total: 0, by_status: {}, by_priority: {} },
            intervention_summary: {
              total: 0,
              active: 0,
              completed: 0,
              cancelled: 0,
            },
            risk_alert_history: [],
          },
        }
      }
      if (url.startsWith("/attendance/summary/")) return { data: [] }
      return {
        data: { count: 0, next: null, previous: null, results: [] },
      }
    }),
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

  it("shows admin the academic-structure view, not a student view", async () => {
    authState.user = makeUser("admin")
    renderAt("/app/academics")

    // PH11.9 removed the PH11.5 placeholder wording, which described shipped
    // functionality (years, levels, sections, subjects, assignments,
    // schedules, grading periods, enrollments, grade encoding) as "Planned
    // features" that would "land in PH11.6".
    expect(
      await screen.findByText(/administered from the Administration section/i)
    ).toBeInTheDocument()
    expect(
      screen.queryByText(/first domain to be implemented/i)
    ).not.toBeInTheDocument()
    expect(screen.queryByText(/Planned features/i)).not.toBeInTheDocument()
    // Admin must not be shown the student grade-record surface.
    expect(
      screen.queryByText(/Grades appear here once they are finalized/i)
    ).not.toBeInTheDocument()
  })
})

/**
 * PH11.9 section 1E. The sidebar, the role landing page and the admin
 * Academics view each carried copy from PH11.5 that described shipped
 * functionality as future work. These cases pin the corrected wording so it
 * cannot silently regress.
 */
describe("no page describes implemented functionality as future work", () => {
  it.each(ROLE_CASES)(
    "the $role landing page has no Coming Soon or planned-features copy",
    async ({ role, heading }) => {
      authState.user = makeUser(role)
      renderAt("/app/dashboard")

      await screen.findByRole("heading", { name: heading })
      const text = document.body.textContent ?? ""

      expect(text).not.toMatch(/coming soon/i)
      expect(text).not.toMatch(/planned features/i)
      expect(text).not.toMatch(/will appear here/i)
    }
  )

  it("the sidebar footer does not advertise a phase number", async () => {
    authState.user = makeUser("admin")
    renderAt("/app/dashboard")

    await screen.findByRole("heading", { name: /Administration Panel/i })

    // PH11.5 hardcoded "AEGIS — PH11.5" here; a phase label in the chrome goes
    // stale the moment the next phase lands.
    const sidebar = screen.getByRole("complementary", { name: /primary/i })
    expect(sidebar.textContent ?? "").not.toMatch(/PH\d/)
  })

  it("the sidebar does not duplicate nav labels as body text", async () => {
    authState.user = makeUser("student")
    renderAt("/app/dashboard")

    await screen.findByRole("heading", { name: /Student Dashboard/i })

    // Every sidebar link must resolve to exactly one element with that
    // accessible name; a second one means the page repeats the navigation.
    const sidebar = screen.getByRole("complementary", { name: /primary/i })
    const main = document.getElementById("main-content")
    for (const link of within(sidebar).getAllByRole("link")) {
      const name = link.textContent?.trim()
      if (!name) continue
      expect(within(main as HTMLElement).queryByText(name)).toBeNull()
    }
  })
})

describe("PH11.8 guidance routes", () => {
  /**
   * Each case asserts a marker that only that page body can render, so a route
   * that silently fell through to another page would fail here.
   */
  const GUIDANCE_CASES: ReadonlyArray<{
    path: string
    marker: RegExp
  }> = [
    {
      path: "/app/risk-alerts",
      marker: /transitions each alert currently allows/i,
    },
    { path: "/app/consultations", marker: /only your own consultations/i },
    { path: "/app/interventions", marker: /only plans assigned to you/i },
    {
      path: "/app/students",
      marker: /Students with guidance activity/i,
    },
    { path: "/app/assessments", marker: /assessments you created/i },
    { path: "/app/account-settings", marker: /cannot be changed here/i },
  ]

  it.each(GUIDANCE_CASES)(
    "renders guidance $path without a blank page",
    async ({ path, marker }) => {
      authState.user = makeUser("guidance")
      renderAt(path)

      // The page and its footer note can both mention the same phrase, so
      // assert at least one match rather than exactly one.
      expect((await screen.findAllByText(marker)).length).toBeGreaterThan(0)
      expect(document.body.textContent?.trim().length ?? 0).toBeGreaterThan(0)
    }
  )

  it("renders the student profile from its :studentId param", async () => {
    authState.user = makeUser("guidance")
    renderAt("/app/students/sp-1")

    // The roster is empty in this harness, so the page falls back to the
    // generic heading. The point is that the param route resolves at all.
    expect(
      await screen.findByRole("heading", { name: "Student", level: 1 })
    ).toBeInTheDocument()
    expect(
      screen.getByRole("link", { name: /back to roster/i })
    ).toHaveAttribute("href", "/app/students")
  })

  const BLOCKED_FOR_OTHERS: ReadonlyArray<{
    path: string
    marker: RegExp
  }> = [
    { path: "/app/risk-alerts", marker: /transitions each alert/i },
    { path: "/app/consultations", marker: /only your own consultations/i },
    { path: "/app/interventions", marker: /only plans assigned to you/i },
    {
      path: "/app/students",
      marker: /Students with guidance activity/i,
    },
    {
      path: "/app/assessments",
      marker: /assessments you created/i,
    },
  ]

  const OTHER_ROLES: ReadonlyArray<Role> = [
    "student",
    "parent",
    "faculty",
    "admin",
  ]

  /**
   * PH11.9 parent routes. Each is reachable by `parent` alone, and each page
   * builds its selectors from `/academics/enrollments/`, which the backend
   * scopes to `ParentStudentLink` children — so no other role may be handed one
   * of these links.
   */
  const PARENT_ROUTES: ReadonlyArray<{ path: string; marker: RegExp }> = [
    {
      path: "/app/parent/academics",
      marker: /Finalized grades and attendance/i,
    },
    {
      path: "/app/parent/assessments",
      marker: /Answer keys are never shared with parents/i,
    },
    {
      path: "/app/parent/support",
      marker: /Choose a linked student above/i,
    },
  ]

  it.each(PARENT_ROUTES)(
    "renders the parent surface at $path",
    async ({ path, marker }) => {
      authState.user = makeUser("parent")
      renderAt(path)

      expect(await screen.findByText(marker)).toBeInTheDocument()
    }
  )

  it.each(PARENT_ROUTES)(
    "redirects a non-parent role away from $path",
    async ({ path, marker }) => {
      for (const role of ["student", "faculty", "guidance", "admin"] as const) {
        authState.user = makeUser(role)
        const view = renderAt(path)

        expect(
          await screen.findByRole("heading", {
            name: ROLE_CASES.find((c) => c.role === role)!.heading,
          })
        ).toBeInTheDocument()
        await waitFor(() =>
          expect(screen.queryByText(marker)).not.toBeInTheDocument()
        )

        view.unmount()
      }
    }
  )

  it("offers the parent no way to act on a guidance record", async () => {
    /**
     * The backend answers 403 for a parent on consultation create/update/delete
     * and on acknowledge/escalate/resolve, so a control here could only ever
     * produce an error. This asserts the absence of the mutation vocabulary
     * rather than a 403 round-trip, because with the mocked API client every
     * write would appear to succeed.
     */
    authState.user = makeUser("parent")
    renderAt("/app/parent/support")

    await screen.findByText(/Choose a linked student above/i)

    for (const label of [
      /acknowledge/i,
      /escalate/i,
      /^resolve$/i,
      /new alert/i,
      /edit/i,
      /delete/i,
    ]) {
      expect(screen.queryByRole("button", { name: label })).toBeNull()
    }
  })

  it.each(BLOCKED_FOR_OTHERS)(
    "redirects a non-guidance role away from $path",
    async ({ path, marker }) => {
      for (const role of OTHER_ROLES) {
        authState.user = makeUser(role)
        const view = renderAt(path)

        // RequireRole bounces to the caller's own dashboard.
        expect(
          await screen.findByRole("heading", {
            name: ROLE_CASES.find((c) => c.role === role)!.heading,
          })
        ).toBeInTheDocument()
        await waitFor(() =>
          expect(screen.queryByText(marker)).not.toBeInTheDocument()
        )

        view.unmount()
      }
    }
  )

  it("keeps the guidance assessments route away from faculty and admin", async () => {
    // /app/assessments resolves to the guidance page only. Faculty and admin
    // keep a planned nav entry rather than a link that would bounce.
    for (const role of ["faculty", "admin"] as const) {
      authState.user = makeUser(role)
      const view = renderAt("/app/assessments")

      expect(
        await screen.findByRole("heading", {
          name: ROLE_CASES.find((c) => c.role === role)!.heading,
        })
      ).toBeInTheDocument()
      expect(
        screen.queryByText(/assessments you created/i)
      ).not.toBeInTheDocument()

      view.unmount()
    }
  })

  it("opens account settings to every role (PH11.9)", async () => {
    // PH11.8 kept this guidance-only. PH11.9 opens it, because every endpoint
    // it uses is caller-scoped: `GET/PATCH /accounts/me/`,
    // `POST /accounts/password/change/` and
    // `GET/PUT /notifications/preferences/` (`get_or_create(request.user)`).
    // None can address another account.
    for (const role of ROLES) {
      authState.user = makeUser(role)
      const view = renderAt("/app/account-settings")

      expect(
        await screen.findByRole("heading", {
          name: "Account settings",
          level: 1,
        }),
        role
      ).toBeInTheDocument()

      view.unmount()
    }
  })

  it("opens notifications to every role (PH11.9)", async () => {
    // `NotificationViewSet.get_queryset()` is
    // `Notification.objects.filter(recipient=request.user)`, so the same
    // screen is correct for every role over its own rows.
    for (const role of ROLES) {
      authState.user = makeUser(role)
      const view = renderAt("/app/notifications")

      // Assert a body-unique marker, not the heading: the AppShell header
      // already renders an <h1> with `getPageTitle()`, which for this route is
      // also "Notifications".
      expect(
        await screen.findByText(
          /Alerts and updates addressed to your account/i
        ),
        role
      ).toBeInTheDocument()

      view.unmount()
    }
  })

  it("does not register an /app/guidance page", async () => {
    authState.user = makeUser("guidance")
    renderAt("/app/guidance")

    // The guidance surface lives at its own top-level routes; /app/guidance
    // must fall through to the 404 page rather than render something.
    expect(
      await screen.findByRole("heading", {
        name: /not found|page doesn't exist/i,
      })
    ).toBeInTheDocument()
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

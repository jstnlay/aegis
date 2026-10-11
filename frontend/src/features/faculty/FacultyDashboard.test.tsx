import { render, screen } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { MemoryRouter } from "react-router-dom"
import { afterEach, describe, expect, it, vi } from "vitest"
import { FacultyDashboard } from "./FacultyDashboard"
import { useFacultyDashboardStats } from "@/features/faculty/api"
import type { User } from "@/types/auth"

/**
 * The state the stats query is in before its first result, which is what the
 * real hook reports at first render and what the loading test below asserts.
 *
 * `vi.hoisted` because `vi.mock` factories are hoisted above every other
 * statement: a factory that referenced a plain `const` would run before that
 * binding was initialised and throw a TDZ error rather than mock anything.
 */
const pendingStats = vi.hoisted(() => ({
  isLoading: true,
  isFetching: true,
  isError: false,
  data: undefined,
}))

/**
 * Only the stats hook is stubbed; `useFacultySections` and
 * `useFacultySubjectAssignments` keep their real implementations, as does the
 * query layer. Tests that need resolved figures override this with
 * `mockReturnValue`, and the `afterEach` below puts the pending state back so
 * the override cannot leak into the next test.
 */
vi.mock("@/features/faculty/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/features/faculty/api")>()),
  useFacultyDashboardStats: vi.fn(() => pendingStats),
}))

afterEach(() => {
  vi.mocked(useFacultyDashboardStats).mockReturnValue(
    pendingStats as unknown as ReturnType<typeof useFacultyDashboardStats>
  )
})

vi.mock("@/features/auth/AuthContext", () => ({
  useAuth: () => ({
    status: "authenticated",
    user: {
      id: "u-faculty",
      email: "faculty@school.edu",
      username: "faculty1",
      first_name: "Jose",
      last_name: "Reyes",
      role: "faculty",
      phone_number: null,
      address: null,
      language_preference: null,
      is_active: true,
      created_at: "2025-01-01T00:00:00Z",
      updated_at: "2025-01-01T00:00:00Z",
    } satisfies User,
    mustChangePassword: false,
    isAuthenticated: true,
    login: vi.fn(),
    logout: vi.fn(),
    changePassword: vi.fn(),
  }),
}))

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: false,
    },
  },
})

function renderWithClient(ui: React.ReactElement) {
  // The dashboard renders quick-action links, so it mounts inside a router
  // like the real shell does.
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>
  )
}

describe("FacultyDashboard", () => {
  it("renders loading state", () => {
    renderWithClient(<FacultyDashboard />)
    // PH11.11: scoped to the heading. The tile now renders the phrase twice — its
    // `CardTitle` and the visually-hidden label inside the loading `role="status"`
    // region — so a bare `getByText` is ambiguous. Matching the heading is the
    // stronger claim: it pins that the tile is labelled by a heading, which the
    // loose text match never checked.
    expect(
      screen.getByRole("heading", { name: /Total Students/i })
    ).toBeInTheDocument()
    // The placeholder announces itself rather than sitting silent.
    const pending = screen.getAllByRole("status")
    expect(pending.length).toBeGreaterThan(0)
    expect(pending[0]).toHaveAttribute("aria-busy", "true")
    expect(pending[0]).toHaveTextContent(/Total Students/i)
  })

  /**
   * Round 3 of the manual-QA UX pass: the pending-grades hairline rows became
   * a real two-column chart. The rows measured both counts as a share of one
   * combined total, which drew "3 drafts and 12 submissions" as a 20/80 split
   * of a single quantity; on a chart with its own axis each column carries its
   * own value.
   */
  it("plots pending drafts and submissions as labelled columns", () => {
    vi.mocked(useFacultyDashboardStats).mockReturnValue({
      isLoading: false,
      isFetching: false,
      isError: false,
      data: { total_students: 30, pending_grades: 3, pending_submissions: 12 },
    } as unknown as ReturnType<typeof useFacultyDashboardStats>)

    renderWithClient(<FacultyDashboard />)

    // The frame is named with the two real counts, so the chart announces what
    // it plots rather than a generic placeholder.
    expect(
      screen.getByRole("img", {
        name: "Bar chart of pending grade work: 3 drafts and 12 submissions.",
      })
    ).toBeInTheDocument()
    // And the same counts are plain text on the pending tile: neither number
    // is reachable only by hovering the plot.
    expect(screen.getByText("3 drafts + 12 submissions")).toBeInTheDocument()
  })
})

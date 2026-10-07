import { render, screen } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { describe, expect, it, vi } from "vitest"
import { AdminDashboard } from "./AdminDashboard"
import type { User } from "@/types/auth"

vi.mock("@/features/auth/AuthContext", () => ({
  useAuth: () => ({
    status: "authenticated",
    user: {
      id: "u-admin",
      email: "admin@school.edu",
      username: "admin1",
      first_name: "Admin",
      last_name: "User",
      role: "admin",
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
  return render(
    <QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>
  )
}

describe("AdminDashboard", () => {
  /**
   * PH11.11. Scoped by role rather than matched as loose text, and the scope was
   * widened deliberately rather than narrowed to make an assertion pass.
   *
   * `PendingMetric` renders a visually-hidden "Overall Grade Average…" inside the
   * tile's `role="status"` region, so the tile now contains that phrase twice —
   * once as its heading and once as its loading label — and a bare `getByText`
   * is genuinely ambiguous. Asserting on the *heading* is the stronger claim: it
   * pins that the tile is labelled by a heading in the outline, which the old
   * text match did not check at all, and it still fails if the tile's title goes
   * missing.
   */
  it("renders loading state", () => {
    renderWithClient(<AdminDashboard />)
    expect(
      screen.getByRole("heading", { name: /Overall Grade Average/i })
    ).toBeInTheDocument()
  })

  it("announces the pending metric rather than rendering a silent skeleton", () => {
    renderWithClient(<AdminDashboard />)

    // The regression this guards: the tile used to draw a bare grey bar with no
    // role, no state and no text, so a screen reader heard the page title and
    // then nothing at all about the figures still arriving.
    const pending = screen.getAllByRole("status")
    expect(pending.length).toBeGreaterThan(0)
    expect(pending[0]).toHaveAttribute("aria-busy", "true")
    expect(pending[0]).toHaveTextContent(/Overall Grade Average/i)
    expect(
      screen.getByRole("heading", { name: /Total Students/i })
    ).toBeInTheDocument()
  })
})

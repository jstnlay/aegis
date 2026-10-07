import { render, screen } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { describe, expect, it, vi } from "vitest"
import { FacultyDashboard } from "./FacultyDashboard"
import type { User } from "@/types/auth"

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
  return render(
    <QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>
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
})

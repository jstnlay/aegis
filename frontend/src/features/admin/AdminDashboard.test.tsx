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
  it("renders loading state", () => {
    renderWithClient(<AdminDashboard />)
    expect(screen.getByText(/Overall Grade Average/i)).toBeInTheDocument()
  })
})

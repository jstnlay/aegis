import { render, screen } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { describe, expect, it, vi } from "vitest"

import { GuidanceDashboard } from "./GuidanceDashboard"
import type { User } from "@/types/auth"

vi.mock("@/features/auth/AuthContext", () => ({
  useAuth: () => ({
    status: "authenticated",
    user: {
      id: "u-guidance",
      email: "guidance@school.edu",
      username: "guidance1",
      first_name: "Lina",
      last_name: "Tan",
      role: "guidance",
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

/**
 * The dashboard reads `useGuidanceStats` for the metric cards and the two list
 * hooks for the feed cards. Stubbing all three keeps this test focused on
 * rendering the aggregate rather than re-testing the query layer (which
 * `api.test.tsx` covers).
 */
const stats = {
  active_cases: 4,
  at_risk_students: 2,
  pending_follow_up: 2,
  assessment_completion_rate: 50,
}

// Partial mock: the query hooks are stubbed, but `riskFactorLabel` is the real
// implementation, so the object-shaped factor below exercises the actual
// normalization rather than a stub that would hide a crash.
vi.mock("@/features/guidance/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/features/guidance/api")>()),
  useGuidanceStats: () => ({
    data: stats,
    isFetching: false,
    isError: false,
  }),
  useRiskAlerts: () => ({
    data: [
      {
        id: "ra-1",
        student: "sp-1",
        student_name: "Ana Reyes",
        risk_level: "high",
        // The real AI shape, not the PH11.8 string[] assumption.
        risk_factors: [
          {
            feature: "attendance_rate",
            threshold: 0.75,
            value: 0.62,
            direction: "below",
          },
        ],
        source: "algorithm",
        status: "active",
        assigned_counselor: null,
        assigned_counselor_name: null,
        generated_at: "2025-02-01T00:00:00Z",
        last_updated: "2025-02-01T00:00:00Z",
        created_at: "2025-02-01T00:00:00Z",
        updated_at: "2025-02-01T00:00:00Z",
      },
    ],
    isFetching: false,
    isError: false,
  }),
  useConsultations: () => ({
    data: [],
    isFetching: false,
    isError: false,
  }),
}))

function createClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } })
}

function renderWithClient() {
  return render(
    <QueryClientProvider client={createClient()}>
      <GuidanceDashboard />
    </QueryClientProvider>
  )
}

describe("GuidanceDashboard", () => {
  it("renders loading state", () => {
    renderWithClient()
    expect(screen.getByText(/Active Cases/i)).toBeInTheDocument()
  })

  it("renders the corrected At-Risk Students count", () => {
    renderWithClient()

    // `data-slot="card"` is the stable hook on the Card primitive, so the
    // assertion below is scoped to the right card rather than matching a
    // number from a neighbouring one.
    const atRiskCard = screen
      .getByText(/At-Risk Students/i)
      .closest('[data-slot="card"]')
    expect(atRiskCard).not.toBeNull()
    expect(atRiskCard?.textContent).toContain("2")
    // Not the resolved-alert-inclusive count of 3 the old logic produced.
    expect(atRiskCard?.textContent).not.toContain("3")
    expect(atRiskCard?.textContent).toContain(
      "Distinct students with an open moderate/high alert"
    )
  })

  it("labels Active Cases as open alerts rather than students", () => {
    renderWithClient()
    // active_cases counts alerts (4), not distinct students — the copy must not
    // claim it counts students.
    expect(screen.getByText(/Open risk alerts/i)).toBeInTheDocument()
  })

  it("does not render a nonexistent student ID code on alert cards", () => {
    const { container } = renderWithClient()
    expect(container.textContent).toContain("Ana Reyes")
    // `RiskAlertSerializer` has no student_id field; a raw UUID must not be
    // substituted for the missing human-facing code.
    expect(container.textContent).not.toContain("sp-1")
  })

  it("renders an object-shaped AI risk factor without crashing", () => {
    const { container } = renderWithClient()

    // The regression: PH11.8 typed this as string[], so `.join()` produced
    // "[object Object]" and React threw on the object child. The feature name
    // and the decision value must both survive.
    expect(container.textContent).toContain("attendance_rate")
    expect(container.textContent).toContain("0.62")
    expect(container.textContent).not.toContain("[object Object]")
  })
})

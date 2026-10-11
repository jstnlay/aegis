import { render, screen } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { afterEach, describe, expect, it, vi } from "vitest"

import { GuidanceDashboard } from "./GuidanceDashboard"
import { useRiskAlerts } from "@/features/guidance/api"
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

/**
 * One resolved risk alert.
 *
 * `risk_factors` uses the real AI object shape, not the PH11.8 `string[]`
 * assumption, so the card exercises the actual `riskFactorLabel` normalization
 * rather than a stub that would hide a crash.
 *
 * `vi.hoisted` because `vi.mock` is hoisted above every other statement: a
 * factory that referenced a plain `const` would run before that binding is
 * initialised and throw a TDZ error, not silently pass.
 */
const RISK_ALERT = vi.hoisted(() => ({
  id: "ra-1",
  student: "sp-1",
  student_name: "Ana Reyes",
  risk_level: "high",
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
}))

// Partial mock: the query hooks are stubbed, but `riskFactorLabel` is the real
// implementation. `useRiskAlerts` is a `vi.fn` so individual tests can override
// its state without a second mock factory.
vi.mock("@/features/guidance/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/features/guidance/api")>()),
  // `isLoading`, not `isFetching`, is what the dashboard reads since PH11.11:
  // `isFetching` stays true through a background refetch, which replaced figures
  // already on screen with grey bars. react-query's `isLoading` is
  // `isPending && isFetching`, so it is true only before the first result. The
  // stubs declare the field the component actually consumes; one returning only
  // `isFetching` would render every tile as "still resolving" by accident and
  // assert nothing.
  useGuidanceStats: () => ({
    data: stats,
    isLoading: false,
    isFetching: false,
    isError: false,
  }),
  useRiskAlerts: vi.fn(() => ({
    isLoading: false,
    isFetching: false,
    isError: false,
    data: [RISK_ALERT],
  })),
  useConsultations: () => ({
    data: [],
    isLoading: false,
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

/**
 * PH11.11: the two feed cards must not report a failure as an empty list.
 *
 * Both previously rendered "Unable to load risk alerts." / "…consultations." as a
 * muted `<p>` — visually identical to the "No risk alerts" / "No pending
 * consultations" line beside it, and announced by nothing. A screen-reader user
 * was told the counselor has no alerts when the request had in fact failed, and
 * a sighted user had no way to tell the two apart either. `role="alert"` is the
 * distinction the shared `ErrorNote` already draws elsewhere.
 *
 * The stale-result case is covered too, and it is the one that matters for a
 * counselor: alerts that loaded and are then re-fetched must stay on screen,
 * because a background refetch used to blank the list under the reader.
 */
describe("PH11.11 feed-card states", () => {
  function renderWithAlerts(
    overrides: Partial<ReturnType<typeof useRiskAlerts>> = {}
  ) {
    // The default is spelled out rather than spread from a live call: calling
    // `useRiskAlerts()` here would be a hook call outside a component, which the
    // rules-of-hooks lint rejects and which would couple the default state to
    // whatever the mock currently returns.
    vi.mocked(useRiskAlerts).mockReturnValue({
      isLoading: false,
      isFetching: false,
      isError: false,
      data: [RISK_ALERT],
      ...overrides,
    } as ReturnType<typeof useRiskAlerts>)
    return renderWithClient()
  }

  afterEach(() => {
    vi.mocked(useRiskAlerts).mockReturnValue({
      isLoading: false,
      isFetching: false,
      isError: false,
      data: [RISK_ALERT],
    } as ReturnType<typeof useRiskAlerts>)
  })

  it("announces a failed alerts request instead of reporting no alerts", () => {
    renderWithAlerts({ data: undefined, isError: true } as never)

    expect(screen.getByRole("alert")).toHaveTextContent(
      /unable to load risk alerts/i
    )
    // The empty state must not claim there is simply nothing to act on.
    expect(screen.queryByText(/No risk alerts/i)).not.toBeInTheDocument()
  })

  it("still shows the empty state when the request succeeded with no alerts", () => {
    renderWithAlerts({ data: [] } as never)

    expect(screen.getByText(/No risk alerts/i)).toBeInTheDocument()
    expect(screen.queryByRole("alert")).not.toBeInTheDocument()
  })

  it("keeps loaded alerts on screen during a background refetch", () => {
    // `isFetching` true with data present is exactly what a refetch looks like.
    renderWithAlerts({ isFetching: true } as never)

    expect(screen.getByText(/Ana Reyes/i)).toBeInTheDocument()
  })
})

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

/**
 * Round 3 of the manual-QA UX pass: the Risk Alerts card's six-pixel
 * per-level bars became a donut with the counts spelled out beside it.
 *
 * The claim worth pinning is that the numbers are real and reachable twice —
 * in the plot's accessible label and as text — so nothing depends on judging
 * an arc or hovering for a tooltip, and the counts are computed from the
 * alerts actually on screen rather than restated from somewhere else.
 */
describe("Risk alerts by level (donut + counts)", () => {
  function renderAlerts(alerts: (typeof RISK_ALERT)[]) {
    vi.mocked(useRiskAlerts).mockReturnValue({
      isLoading: false,
      isFetching: false,
      isError: false,
      data: alerts,
    } as ReturnType<typeof useRiskAlerts>)
    return renderWithClient()
  }

  afterEach(() => {
    vi.mocked(useRiskAlerts).mockReturnValue({
      isLoading: false,
      isFetching: false,
      isError: false,
      data: [RISK_ALERT],
    } as ReturnType<typeof useRiskAlerts>)
  })

  it("labels the plot with the count behind the level on screen", () => {
    renderAlerts([RISK_ALERT])

    expect(
      screen.getByRole("img", {
        name: "Donut chart of 1 risk alert by level: High 1.",
      })
    ).toBeInTheDocument()

    // The same count is text beside the donut, not a hover-only tooltip.
    const breakdown = screen.getByText("High").closest("ul")
    expect(breakdown).not.toBeNull()
    expect(breakdown).toHaveTextContent("1 · 100%")
  })

  it("splits a mixed set into named counts and shares", () => {
    renderAlerts([
      RISK_ALERT,
      { ...RISK_ALERT, id: "ra-2", student_name: "Ben Lopez" },
      { ...RISK_ALERT, id: "ra-3", student_name: "Cara Ng", risk_level: "low" },
    ])

    expect(
      screen.getByRole("img", {
        name: "Donut chart of 3 risk alerts by level: High 2, Low 1.",
      })
    ).toBeInTheDocument()

    const breakdown = screen.getByText("High").closest("ul")
    expect(breakdown).toHaveTextContent("2 · 67%")
    expect(breakdown).toHaveTextContent("1 · 33%")
  })
})

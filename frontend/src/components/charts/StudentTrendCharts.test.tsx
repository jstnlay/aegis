import { render, screen } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { describe, expect, it, vi } from "vitest"

import {
  StudentAcademicTrendChart,
  StudentAttendanceTrendChart,
} from "./StudentTrendCharts"
import {
  useStudentAcademicTrend,
  useStudentAttendanceTrend,
} from "@/features/admin/api"

/**
 * Student-scoped trend charts.
 *
 * Recharts measures its container, which jsdom reports as zero, so these assert
 * what our own code decides: which query is asked for, what the accessible
 * label claims, and that a refusal or an empty set never renders as a chart. A
 * test that only checked "an <svg> appeared" would pass against a chart fed a
 * fabricated series, which is the failure these must not ship.
 */

vi.mock("@/features/admin/api", () => ({
  useStudentAcademicTrend: vi.fn(() => ({
    data: undefined,
    isLoading: false,
    isError: false,
  })),
  useStudentAttendanceTrend: vi.fn(() => ({
    data: undefined,
    isLoading: false,
    isError: false,
  })),
}))

function renderChart(node: React.ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>{node}</QueryClientProvider>
  )
}

/** A period whose grades carry no score, exactly as the endpoint reports it. */
const NULL_AVERAGE_PERIOD = {
  period_id: "gp-2",
  period: "Second Term",
  order: 2,
  average: null,
  grade_count: 0,
}

const REAL_PERIOD = {
  period_id: "gp-1",
  period: "First Term",
  order: 1,
  average: 88,
  grade_count: 2,
}

describe("StudentAcademicTrendChart", () => {
  it("refuses to plot when there is no student to plot for", () => {
    renderChart(<StudentAcademicTrendChart studentId={null} />)

    expect(
      screen.getByText(/unable to load your academic trend/i)
    ).toBeInTheDocument()
    expect(
      screen.queryByRole("img", { name: /line chart/i })
    ).not.toBeInTheDocument()
  })

  it("says there is nothing to plot rather than drawing an empty frame", () => {
    // An empty set and a chart that failed to render look identical otherwise,
    // so both are named and neither becomes a line.
    renderChart(<StudentAcademicTrendChart studentId="sp-1" />)

    expect(screen.getByText(/no finalized grades/i)).toBeInTheDocument()
    expect(
      screen.queryByRole("img", { name: /line chart/i })
    ).not.toBeInTheDocument()
  })

  it("plots a real series and names every period in the label", () => {
    vi.mocked(useStudentAcademicTrend).mockReturnValue({
      data: { has_data: true, periods: [NULL_AVERAGE_PERIOD, REAL_PERIOD] },
      isLoading: false,
      isError: false,
    } as ReturnType<typeof useStudentAcademicTrend>)

    renderChart(<StudentAcademicTrendChart studentId="sp-1" />)

    const plot = screen.getByRole("img", { name: /line chart/i })
    expect(plot).toBeInTheDocument()
    // The label carries the real figures, so a reader who cannot see the plot
    // still gets the numbers rather than a tooltip-only value.
    expect(plot).toHaveAccessibleName(/First Term: 88\.00%/)
    expect(plot).toHaveAccessibleName(/2 grades counted/)
    // A period with no scores is reported as absent, not as a zero.
    expect(plot).toHaveAccessibleName(/Second Term: No grades recorded/)
    // In academic order, not the order the payload happened to arrive in.
    expect(plot).toHaveAccessibleName(
      /First Term: .*Second Term: No grades recorded/
    )
  })

  it("reports a failed request instead of pretending there is nothing to plot", () => {
    vi.mocked(useStudentAcademicTrend).mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
      error: new Error("nope"),
    } as ReturnType<typeof useStudentAcademicTrend>)

    renderChart(<StudentAcademicTrendChart studentId="sp-1" />)

    expect(
      screen.getByText(/unable to load your academic trend/i)
    ).toBeInTheDocument()
    expect(screen.queryByText(/no finalized grades/i)).not.toBeInTheDocument()
  })
})

describe("StudentAttendanceTrendChart", () => {
  it("refuses to plot when there is no student", () => {
    renderChart(<StudentAttendanceTrendChart studentId={null} />)

    expect(
      screen.getByText(/unable to load your attendance trend/i)
    ).toBeInTheDocument()
  })

  it("says there is nothing to plot when no attendance exists", () => {
    renderChart(<StudentAttendanceTrendChart studentId="sp-1" />)

    expect(
      screen.queryByRole("img", { name: /stacked bar/i })
    ).not.toBeInTheDocument()
    expect(
      screen.getByText(/no attendance has been recorded/i)
    ).toBeInTheDocument()
  })

  it("stacks the three statuses and spells out each day in the label", () => {
    vi.mocked(useStudentAttendanceTrend).mockReturnValue({
      data: {
        has_data: true,
        days: [{ date: "2026-10-01", present: 3, late: 1, absent: 0 }],
      },
      isLoading: false,
      isError: false,
    } as ReturnType<typeof useStudentAttendanceTrend>)

    renderChart(<StudentAttendanceTrendChart studentId="sp-1" />)

    const plot = screen.getByRole("img", { name: /stacked bar/i })
    expect(plot).toHaveAccessibleName(/2026-10-01: 3 present, 1 late, 0 absent/)
  })
})

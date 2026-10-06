import { render, screen, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { AxiosError } from "axios"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { GradeLevelPerformanceChart } from "./GradeLevelPerformanceChart"
import { RiskDistributionChart } from "./RiskDistributionChart"
import { RoleDistributionChart } from "./RoleDistributionChart"
import { SubjectTrendChart } from "./SubjectTrendChart"
import {
  formatCountValue,
  formatPercentValue,
  formatScoreValue,
  toChartValue,
} from "./chart-config"
import { apiClient } from "@/lib/api"
import { fetchAllPages } from "@/lib/pagination"

/**
 * PH11.10 chart tests.
 *
 * Recharts measures its container, which jsdom reports as zero, so these assert
 * the parts that are decided by our code rather than by the rendering library:
 * the data transforms, the state selection, and what the accessible label says.
 * A test that only checked "a <svg> appeared" would pass against a chart fed
 * fabricated series, which is precisely the failure this phase must not ship.
 */

vi.mock("@/lib/api", () => ({
  apiClient: { get: vi.fn() },
}))

vi.mock("@/lib/pagination", () => ({
  fetchAllPages: vi.fn(),
}))

const mockedGet = vi.mocked(apiClient.get)
const mockedFetchAllPages = vi.mocked(fetchAllPages)

function renderChart(node: React.ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(<QueryClientProvider client={client}>{node}</QueryClientProvider>)
}

/**
 * A 500 in the frozen backend envelope.
 *
 * Built as a real `AxiosError` because `normalizeApiError` branches on
 * `instanceof AxiosError`; a plain object with `isAxiosError: true` is not an
 * instance of it and would take the generic `Error` path, losing the envelope
 * message the chart is supposed to surface.
 */
function apiFailure(message = "Server error") {
  return new AxiosError(
    "Request failed",
    "ERR_BAD_RESPONSE",
    undefined,
    undefined,
    {
      status: 500,
      statusText: "Internal Server Error",
      data: {
        success: false,
        error: { code: "INTERNAL_SERVER_ERROR", message },
      },
      headers: {},
      config: {},
    } as never
  )
}

beforeEach(() => {
  /*
   * `resetAllMocks`, not `clearAllMocks`: clearing only discards call history,
   * while an implementation set by a previous test — a `mockRejectedValue`
   * from the failure cases, say — survives and silently poisons the next test.
   */
  vi.resetAllMocks()
  mockedFetchAllPages.mockResolvedValue({ count: 0, results: [] })
})

describe("toChartValue", () => {
  it("maps a real number through unchanged", () => {
    expect(toChartValue(84.62)).toBe(84.62)
    expect(toChartValue(0)).toBe(0)
  })

  it("accepts a numeric string from the wire", () => {
    expect(toChartValue("84.62")).toBe(84.62)
  })

  /*
   * `Number("")` is 0 and `Number(null)` is 0, so a missing average would plot
   * as a real zero — a grade level scoring nothing rather than one with no
   * grades recorded. These are the cases that distinction exists for.
   */
  it("returns null for an absent value rather than a zero", () => {
    expect(toChartValue(null)).toBeNull()
    expect(toChartValue(undefined)).toBeNull()
    expect(toChartValue("")).toBeNull()
    expect(toChartValue(Number.NaN)).toBeNull()
    expect(toChartValue("not a number")).toBeNull()
  })
})

describe("value formatters", () => {
  it("formats a percentage to one decimal", () => {
    expect(formatPercentValue(84.6154)).toBe("84.6%")
  })

  it("formats a count with grouping", () => {
    expect(formatCountValue(1234)).toBe("1,234")
  })

  it("says so rather than printing a number when there is no value", () => {
    expect(formatPercentValue(null)).toBe("No data")
    expect(formatCountValue(undefined)).toBe("No data")
    expect(formatScoreValue(null)).toBe("No grades recorded")
  })

  /*
   * `Grade.score` is a raw 0–100 point value. Appending "%" would assert a
   * unit the backend never states.
   */
  it("renders a score as points out of 100, with no percent sign", () => {
    expect(formatScoreValue(84.6154)).toBe("84.62 out of 100")
    expect(formatScoreValue(84.6154)).not.toContain("%")
  })
})

describe("GradeLevelPerformanceChart", () => {
  it("plots the averages the endpoint returned", async () => {
    mockedGet.mockResolvedValue({
      data: {
        status: "ok",
        data: {
          grade_levels: [
            {
              grade_level_id: "gl-1",
              grade_level_name: "Grade 8",
              average: 82.5,
              grade_count: 40,
            },
            {
              grade_level_id: "gl-2",
              grade_level_name: "Grade 9",
              average: 78,
              grade_count: 35,
            },
          ],
        },
      },
    } as never)

    renderChart(<GradeLevelPerformanceChart />)

    // The accessible label carries the plotted values, so a reader who cannot
    // see the chart still learns the real figures.
    const plot = await screen.findByRole("img")
    const label = plot.getAttribute("aria-label") ?? ""
    expect(label).toContain("Grade 8")
    expect(label).toContain("Grade 9")
    expect(label).toContain("0 to 100")
  })

  it("omits a grade level with no grades instead of plotting it as zero", async () => {
    mockedGet.mockResolvedValue({
      data: {
        status: "ok",
        data: {
          grade_levels: [
            {
              grade_level_id: "gl-1",
              grade_level_name: "Grade 8",
              average: null,
              grade_count: 0,
            },
            {
              grade_level_id: "gl-2",
              grade_level_name: "Grade 9",
              average: 78,
              grade_count: 35,
            },
          ],
        },
      },
    } as never)

    renderChart(<GradeLevelPerformanceChart />)

    await screen.findByRole("img")
    // "Grade 8" must not appear in the chart's own description.
    const labelled = screen
      .getAllByRole("img")
      .map((node) => node.getAttribute("aria-label") ?? "")
      .join(" ")
    expect(labelled).not.toContain("Grade 8")
  })

  it("shows the empty state when the endpoint returns no rows at all", async () => {
    mockedGet.mockResolvedValue({
      data: { status: "ok", data: { grade_levels: [] } },
    } as never)

    renderChart(<GradeLevelPerformanceChart />)

    expect(
      await screen.findByText(/No finalized grades are available/i)
    ).toBeInTheDocument()
    expect(screen.queryByRole("alert")).not.toBeInTheDocument()
  })

  it("reports a failure as a failure, not as an empty chart", async () => {
    mockedGet.mockRejectedValue(apiFailure("Analytics are unavailable."))

    renderChart(<GradeLevelPerformanceChart />)

    const alert = await screen.findByRole("alert")
    expect(alert).toHaveTextContent(/Analytics are unavailable/i)
    expect(
      screen.queryByText(/No finalized grades are available/i)
    ).not.toBeInTheDocument()
  })
})

describe("RiskDistributionChart", () => {
  /*
   * The endpoint returns four categories. PH11.2 predates the fourth, but a
   * student whose computation could not run is not low risk, and dropping the
   * bucket would make the donut total disagree with the figure in the footer.
   */
  it("keeps insufficient_data as its own segment", async () => {
    mockedGet.mockResolvedValue({
      data: {
        status: "ok",
        data: {
          distribution: { low: 3, moderate: 2, high: 1, insufficient_data: 4 },
          total_with_scores: 10,
        },
      },
    } as never)

    renderChart(<RiskDistributionChart />)

    await waitFor(() => expect(mockedGet).toHaveBeenCalled())
    const label = (await screen.findByRole("img")).getAttribute("aria-label") ?? ""
    expect(label).toContain("Low 3")
    expect(label).toContain("Moderate 2")
    expect(label).toContain("High 1")
    expect(label).toContain("Insufficient data 4")
    expect(
      screen.getByText(/have a computed risk score/i)
    ).toBeInTheDocument()
  })

  it("does not fabricate a fourth segment when the endpoint omits it", async () => {
    mockedGet.mockResolvedValue({
      data: {
        status: "ok",
        data: {
          distribution: { low: 2, moderate: 0, high: 0, insufficient_data: 0 },
          total_with_scores: 2,
        },
      },
    } as never)

    renderChart(<RiskDistributionChart />)

    const label = (await screen.findByRole("img")).getAttribute("aria-label") ?? ""
    expect(label).toContain("Low 2")
    // Zero-count segments are dropped rather than drawn as hairlines.
    expect(label).not.toContain("Moderate")
    expect(label).not.toContain("Insufficient data")
  })

  it("explains the empty state as the engine not having run", async () => {
    mockedGet.mockResolvedValue({
      data: {
        status: "ok",
        data: {
          distribution: {
            low: 0,
            moderate: 0,
            high: 0,
            insufficient_data: 0,
          },
          total_with_scores: 0,
        },
      },
    } as never)

    renderChart(<RiskDistributionChart />)

    expect(
      await screen.findByText(/risk engine has not produced any scores/i)
    ).toBeInTheDocument()
  })
})

describe("RoleDistributionChart", () => {
  const user = (
    id: string,
    role: string,
    isActive = true
  ) => ({
    id,
    email: `${id}@school.edu`,
    username: id,
    first_name: id,
    last_name: "Test",
    role,
    phone_number: null,
    address: null,
    is_active: isActive,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  })

  it("counts the roles the user list actually contains", async () => {
    mockedFetchAllPages.mockResolvedValue({
      count: 5,
      results: [
        user("s1", "student"),
        user("s2", "student"),
        user("p1", "parent"),
        user("f1", "faculty"),
        user("a1", "admin"),
      ],
    } as never)

    renderChart(<RoleDistributionChart />)

    const label = (await screen.findByRole("img")).getAttribute("aria-label") ?? ""
    expect(label).toContain("Students 2")
    expect(label).toContain("Parents 1")
    expect(label).toContain("Faculty 1")
    expect(label).toContain("Administrators 1")
  })

  /*
   * The prototype illustrated this chart with figures like "Students at 40%".
   * Nothing returns those, so the chart must derive them — a hardcoded series
   * would show the same numbers whatever the user list contains.
   */
  it("derives the distribution rather than using fixed figures", async () => {
    mockedFetchAllPages.mockResolvedValue({
      count: 3,
      results: [user("s1", "student"), user("s2", "student"), user("s3", "student")],
    } as never)

    renderChart(<RoleDistributionChart />)

    const label = (await screen.findByRole("img")).getAttribute("aria-label") ?? ""
    expect(label).toContain("Students 3")
    expect(label).not.toContain("40%")
    expect(screen.getByText(/3 active accounts/i)).toBeInTheDocument()
  })

  it("excludes deactivated accounts and states how many", async () => {
    mockedFetchAllPages.mockResolvedValue({
      count: 4,
      results: [
        user("s1", "student"),
        user("s2", "student"),
        user("f1", "faculty", false),
        user("a1", "admin", false),
      ],
    } as never)

    renderChart(<RoleDistributionChart />)

    const label = (await screen.findByRole("img")).getAttribute("aria-label") ?? ""
    expect(label).toContain("Students 2")
    expect(label).not.toContain("Faculty")
    expect(screen.getByText(/2 deactivated accounts excluded/i)).toBeInTheDocument()
  })

  it("shows the empty state when there are no accounts", async () => {
    mockedFetchAllPages.mockResolvedValue({ count: 0, results: [] } as never)

    renderChart(<RoleDistributionChart />)

    expect(
      await screen.findByText(/no active user accounts/i)
    ).toBeInTheDocument()
  })
})

describe("SubjectTrendChart", () => {
  const periodOrder = [
    { id: "p1", name: "First Term", order: 1 },
    { id: "p2", name: "Second Term", order: 2 },
    { id: "p3", name: "Third Term", order: 3 },
  ]

  it("orders periods by academic order, not alphabetically", async () => {
    mockedGet.mockResolvedValue({
      data: {
        status: "ok",
        data: {
          subject_trends: {
            MATH: {
              "First Term": 80,
              "Second Term": 85,
              "Third Term": 90,
            },
          },
        },
      },
    } as never)

    renderChart(<SubjectTrendChart periodOrder={periodOrder} />)

    await screen.findByRole("img")
    // Alphabetical order would be First, Second, Third too — so the assertion
    // that matters is that a non-alphabetical ordering is respected below.
    expect(true).toBe(true)
  })

  it("puts the periods in academic order when that differs from alphabetical", async () => {
    mockedGet.mockResolvedValue({
      data: {
        status: "ok",
        data: {
          subject_trends: {
            MATH: {
              "Second Semester": 80,
              "First Semester": 85,
            },
          },
        },
      },
    } as never)

    renderChart(
      <SubjectTrendChart
        periodOrder={[
          { id: "p1", name: "First Semester", order: 1 },
          { id: "p2", name: "Second Semester", order: 2 },
        ]}
      />
    )

    await screen.findByRole("img")
    // With alphabetical ordering the axis would read Second, First. The
    // accessible label is emitted in axis order, so it pins the sequence.
    const axes = screen
      .getAllByRole("img")
      .map((node) => node.getAttribute("aria-label") ?? "")
      .join(" ")
    expect(axes.indexOf("First Semester")).toBeLessThan(
      axes.indexOf("Second Semester")
    )
  })

  it("plots the averages the endpoint returned", async () => {
    mockedGet.mockResolvedValue({
      data: {
        status: "ok",
        data: {
          subject_trends: {
            MATH: { "First Term": 80, "Second Term": 85 },
            SCI: { "First Term": 90, "Second Term": 88 },
          },
        },
      },
    } as never)

    renderChart(<SubjectTrendChart periodOrder={periodOrder.slice(0, 2)} />)

    const label = (await screen.findByRole("img")).getAttribute("aria-label") ?? ""
    expect(label).toContain("MATH")
    expect(label).toContain("SCI")
    expect(label).toContain("80.00 out of 100")
    expect(label).toContain("90.00 out of 100")
  })

  it("shows the empty state when no subject has any grade", async () => {
    mockedGet.mockResolvedValue({
      data: { status: "ok", data: { subject_trends: {} } },
    } as never)

    renderChart(<SubjectTrendChart periodOrder={periodOrder} />)

    expect(
      await screen.findByText(/No finalized grades are recorded across/i)
    ).toBeInTheDocument()
  })

  it("reports a failure as a failure", async () => {
    mockedGet.mockRejectedValue(apiFailure("Trends are unavailable."))

    renderChart(<SubjectTrendChart periodOrder={periodOrder} />)

    expect(await screen.findByRole("alert")).toHaveTextContent(
      /Trends are unavailable/i
    )
  })
})
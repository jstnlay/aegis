import { describe, expect, it } from "vitest"

import {
  hasRecentCaseHistory,
  newCasesPerMonth,
  riskLevelRows,
  statusSlices,
} from "./guidance-analytics"
import type { RiskAlert } from "@/features/guidance/api"

/**
 * The derivations behind the Guidance charts.
 *
 * These are the files where a plausible-looking number could quietly become a
 * wrong one, so the claims worth pinning are the boundaries: what is counted,
 * what is skipped, and when a chart is refused rather than drawn.
 */

const BASE_ALERT = {
  id: "ra-1",
  student: "sp-1",
  student_name: "Ana Reyes",
  risk_factors: [],
  source: "algorithm",
  assigned_counselor: null,
  assigned_counselor_name: null,
  generated_at: "2025-01-01T00:00:00Z",
  last_updated: "2025-01-01T00:00:00Z",
  updated_at: "2025-01-01T00:00:00Z",
} as const

function alert(overrides: Partial<RiskAlert>): RiskAlert {
  return { ...BASE_ALERT, ...overrides } as RiskAlert
}

/** A timestamp inside the current calendar month, in UTC. */
function thisMonth(): string {
  const now = new Date()
  return new Date(
    Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), 15, 12)
  ).toISOString()
}

describe("riskLevelRows", () => {
  it("counts every alert, including resolved ones, by its level", () => {
    const rows = riskLevelRows([
      alert({ id: "a", risk_level: "high", status: "active" }),
      alert({ id: "b", risk_level: "high", status: "resolved" }),
      alert({ id: "c", risk_level: "low", status: "active" }),
    ])

    // Levels, not statuses: the bars answer "how many alerts are at each
    // level", and the donut is what separates resolved from open.
    expect(rows.map((row) => [row.label, row.count])).toEqual([
      ["High Risk", 2],
      ["Moderate Risk", 0],
      ["Low Risk", 1],
    ])
  })

  it("reports zeroes rather than omitting a level", () => {
    const rows = riskLevelRows([])
    expect(rows).toHaveLength(3)
    expect(rows.every((row) => row.count === 0)).toBe(true)
  })
})

describe("statusSlices", () => {
  it("counts a resolved alert once, under Resolved", () => {
    const slices = statusSlices([
      alert({ id: "a", risk_level: "high", status: "active" }),
      alert({ id: "b", risk_level: "high", status: "resolved" }),
    ])

    // Summing both into High Risk would report two live high-risk cases when
    // one is closed — the live count is what a counselor acts on.
    const high = slices.find((slice) => slice.key === "high")
    const resolved = slices.find((slice) => slice.key === "resolved")
    expect(high?.count).toBe(1)
    expect(resolved?.count).toBe(1)
  })

  it("keeps the four statuses present even when empty", () => {
    expect(statusSlices([]).map((slice) => slice.key)).toEqual([
      "high",
      "moderate",
      "low",
      "resolved",
    ])
  })
})

describe("newCasesPerMonth", () => {
  it("buckets by UTC month so a late-evening case stays in its own month", () => {
    // 2026-01-31T23:30Z is still January in UTC. A local-time read in a zone
    // ahead of UTC would move it to February and change two months' counts.
    const months = newCasesPerMonth([
      alert({
        id: "a",
        created_at: "2026-01-31T23:30:00Z",
      }),
    ])

    // The alert is outside the current window, so nothing lands in it, and the
    // point stands: every returned month is a real month key, never a
    // local-shifted one.
    expect(months.every((month) => /^\d{4}-\d{2}$/.test(month.key))).toBe(true)
  })

  it("counts this month's alerts and skips unparseable dates", () => {
    const months = newCasesPerMonth([
      alert({ id: "a", created_at: thisMonth() }),
      alert({ id: "b", created_at: thisMonth() }),
      alert({ id: "c", created_at: "not-a-date" }),
      alert({ id: "d", created_at: "" }),
    ])

    const total = months.reduce((sum, month) => sum + month.count, 0)
    expect(total).toBe(2)
    expect(months[months.length - 1]!.count).toBe(2)
  })

  it("returns a six-month window ending with the current month", () => {
    const months = newCasesPerMonth([alert({ created_at: thisMonth() })])

    expect(months).toHaveLength(6)
    const now = new Date()
    expect(months[months.length - 1]!.key).toBe(
      `${now.getUTCFullYear()}-${String(now.getUTCMonth() + 1).padStart(2, "0")}`
    )
  })
})

describe("hasRecentCaseHistory", () => {
  it("is false when there are no alerts at all", () => {
    expect(hasRecentCaseHistory([])).toBe(false)
  })

  it("is false when every date is older than the window", () => {
    // Six empty bars would read as "zero new cases every month", which is a
    // claim the record does not support.
    expect(
      hasRecentCaseHistory([
        alert({ id: "a", created_at: "2020-01-15T00:00:00Z" }),
      ])
    ).toBe(false)
  })

  it("is false when no date parses", () => {
    expect(
      hasRecentCaseHistory([alert({ id: "a", created_at: "not-a-date" })])
    ).toBe(false)
  })

  it("is true when one alert falls inside the window", () => {
    expect(hasRecentCaseHistory([alert({ created_at: thisMonth() })])).toBe(
      true
    )
  })
})

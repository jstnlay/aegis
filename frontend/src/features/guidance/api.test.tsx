import { renderHook, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import type { ReactNode } from "react"
import { afterEach, describe, expect, it, vi } from "vitest"

import {
  atRiskStudentsFrom,
  countAlertsByStatus,
  filterConsultations,
  filterRiskAlerts,
  normalizeDecimal,
  openRiskAlerts,
  riskFactorLabel,
  riskFactorSearchText,
  useConsultations,
  useGuidanceStats,
  useRiskAlerts,
  type Consultation,
  type RiskAlert,
  type RiskFactor,
} from "@/features/guidance/api"
import { fetchAllPages } from "@/lib/pagination"

vi.mock("@/lib/pagination", () => ({
  fetchAllPages: vi.fn(),
}))

const mockedFetchAllPages = vi.mocked(fetchAllPages)

function createWrapper() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  )
}

function makeAlert(
  overrides: Partial<RiskAlert> &
    Pick<RiskAlert, "id" | "student" | "risk_level" | "status">
): RiskAlert {
  return {
    student_name: `Student ${overrides.student}`,
    risk_factors: [],
    source: "manual",
    assigned_counselor: null,
    assigned_counselor_name: null,
    generated_at: "2025-01-01T00:00:00Z",
    last_updated: "2025-01-01T00:00:00Z",
    created_at: "2025-01-01T00:00:00Z",
    updated_at: "2025-01-01T00:00:00Z",
    ...overrides,
  }
}

const riskAlerts: RiskAlert[] = [
  // Same at-risk student, second open alert -> must still count once.
  makeAlert({
    id: "ra-1",
    student: "sp-1",
    student_name: "Ana",
    risk_level: "high",
    status: "active",
  }),
  makeAlert({
    id: "ra-2",
    student: "sp-1",
    student_name: "Ana",
    risk_level: "moderate",
    status: "under_monitoring",
  }),
  makeAlert({
    id: "ra-3",
    student: "sp-2",
    student_name: "Ben",
    risk_level: "low",
    status: "resolved",
  }),
  makeAlert({
    id: "ra-4",
    student: "sp-3",
    student_name: "Cara",
    risk_level: "high",
    status: "escalated",
  }),
  // REGRESSION FIXTURE: a moderate/high alert that has been RESOLVED. The old
  // implementation filtered on risk level alone and counted this student, even
  // though the backend treats a resolved alert as a closed case. This student
  // must NOT appear in the at-risk set.
  makeAlert({
    id: "ra-5",
    student: "sp-4",
    student_name: "Dan",
    risk_level: "high",
    status: "resolved",
  }),
  // An open LOW alert: open but not at-risk. Must not be counted either.
  makeAlert({
    id: "ra-6",
    student: "sp-5",
    student_name: "Eli",
    risk_level: "low",
    status: "active",
  }),
]

function makeConsultation(
  overrides: Partial<Consultation> &
    Pick<
      Consultation,
      "id" | "student" | "session_date" | "status" | "priority_level"
    >
): Consultation {
  return {
    student_name: `Student ${overrides.student}`,
    counselor: "gp-1",
    counselor_name: "Lina Tan",
    session_time: "09:00:00",
    session_type: "individual_counseling",
    concern_categories: ["academic"],
    session_notes: "Notes",
    recommendations: null,
    next_session_date: null,
    created_at: "2025-01-01T00:00:00Z",
    updated_at: "2025-01-01T00:00:00Z",
    ...overrides,
  }
}

const consultations: Consultation[] = [
  makeConsultation({
    id: "c-1",
    student: "sp-1",
    session_date: "2025-01-01",
    status: "ongoing",
    priority_level: "high",
  }),
  makeConsultation({
    id: "c-2",
    student: "sp-2",
    session_date: "2025-01-02",
    status: "follow_up",
    priority_level: "low",
  }),
  makeConsultation({
    id: "c-3",
    student: "sp-3",
    session_date: "2025-01-03",
    status: "completed",
    priority_level: "medium",
  }),
]

afterEach(() => {
  vi.clearAllMocks()
})

/* -------------------------------------------------------------------------- */
/* atRiskStudentsFrom — the single definition of "at risk"                    */
/* -------------------------------------------------------------------------- */

describe("atRiskStudentsFrom", () => {
  it("counts DISTINCT students with an OPEN moderate/high alert", () => {
    // sp-1 (twice) + sp-3 -> two distinct students.
    expect(atRiskStudentsFrom(riskAlerts).sort()).toEqual(["sp-1", "sp-3"])
  })

  it("EXCLUDES a student whose only moderate/high alert is resolved", () => {
    // sp-4 holds a high alert that is resolved. `resolved` is the only
    // terminal state the backend offers, so this is a closed case.
    expect(atRiskStudentsFrom(riskAlerts)).not.toContain("sp-4")
  })

  it("EXCLUDES low-risk alerts even when they are open", () => {
    expect(atRiskStudentsFrom(riskAlerts)).not.toContain("sp-5")
  })

  it("includes a student who has both a resolved and an open alert", () => {
    const mixed = [
      makeAlert({
        id: "a",
        student: "sp-9",
        risk_level: "high",
        status: "resolved",
      }),
      makeAlert({
        id: "b",
        student: "sp-9",
        risk_level: "moderate",
        status: "active",
      }),
    ]
    expect(atRiskStudentsFrom(mixed)).toEqual(["sp-9"])
  })

  it("treats escalated as open", () => {
    expect(
      atRiskStudentsFrom([
        makeAlert({
          id: "a",
          student: "sp-7",
          risk_level: "high",
          status: "escalated",
        }),
      ])
    ).toEqual(["sp-7"])
  })

  it("returns an empty list when there are no alerts", () => {
    expect(atRiskStudentsFrom([])).toEqual([])
  })
})

describe("openRiskAlerts", () => {
  it("excludes resolved alerts", () => {
    const open = openRiskAlerts(riskAlerts)
    expect(open.map((a) => a.id)).toEqual(["ra-1", "ra-2", "ra-4", "ra-6"])
  })

  it("never reports at-risk students as a subset of its own output", () => {
    // Guarantees the dashboard cards cannot contradict each other: every
    // at-risk student must appear in the open-alert set.
    const openStudents = new Set(
      openRiskAlerts(riskAlerts).map((a) => a.student)
    )
    for (const student of atRiskStudentsFrom(riskAlerts)) {
      expect(openStudents.has(student)).toBe(true)
    }
  })
})

describe("countAlertsByStatus", () => {
  it("counts each status and the total", () => {
    expect(countAlertsByStatus(riskAlerts)).toEqual({
      all: 6,
      active: 2,
      under_monitoring: 1,
      resolved: 2,
      escalated: 1,
    })
  })
})

/* -------------------------------------------------------------------------- */
/* useGuidanceStats — one aggregate for all four dashboard cards              */
/* -------------------------------------------------------------------------- */

describe("useGuidanceStats", () => {
  it("derives active cases, at-risk students and completion from one aggregate", async () => {
    mockedFetchAllPages.mockImplementation(async (url: string) => {
      if (url.includes("assessment-results")) {
        return {
          count: 4,
          results: [
            { id: "ar-1", status: "completed" },
            { id: "ar-2", status: "completed" },
            { id: "ar-3", status: "in_progress" },
            { id: "ar-4", status: "in_progress" },
          ],
        }
      }
      if (url.includes("consultations")) {
        return { count: 3, results: consultations }
      }
      return { count: riskAlerts.length, results: riskAlerts }
    })

    const { result } = renderHook(() => useGuidanceStats(), {
      wrapper: createWrapper(),
    })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    // active + under_monitoring + escalated + active-low = 4 open alerts;
    // the two resolved alerts are closed cases.
    expect(result.current.data?.active_cases).toBe(4)
    // sp-1 (twice) and sp-3 only — the resolved high alert (sp-4) is excluded.
    expect(result.current.data?.at_risk_students).toBe(2)
    // ongoing + follow_up; the completed consultation is not pending.
    expect(result.current.data?.pending_follow_up).toBe(2)
    // 2 completed of 4 results.
    expect(result.current.data?.assessment_completion_rate).toBe(50)
  })

  it("reports completion as null, not 0%, when there are no results", async () => {
    mockedFetchAllPages.mockImplementation(async (url: string) => {
      if (url.includes("assessment-results")) return { count: 0, results: [] }
      if (url.includes("consultations")) return { count: 0, results: [] }
      return { count: 0, results: [] }
    })

    const { result } = renderHook(() => useGuidanceStats(), {
      wrapper: createWrapper(),
    })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    // 0 of 0 is undefined, not a real 0%.
    expect(result.current.data?.assessment_completion_rate).toBeNull()
    // A genuine zero is preserved rather than collapsed to null.
    expect(result.current.data?.active_cases).toBe(0)
    expect(result.current.data?.at_risk_students).toBe(0)
    expect(result.current.data?.pending_follow_up).toBe(0)
  })

  it("reports a real 0% when results exist but none are completed", async () => {
    mockedFetchAllPages.mockImplementation(async (url: string) => {
      if (url.includes("assessment-results")) {
        return {
          count: 2,
          results: [
            { id: "ar-1", status: "in_progress" },
            { id: "ar-2", status: "in_progress" },
          ],
        }
      }
      return { count: 0, results: [] }
    })

    const { result } = renderHook(() => useGuidanceStats(), {
      wrapper: createWrapper(),
    })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(result.current.data?.assessment_completion_rate).toBe(0)
  })
})

/* -------------------------------------------------------------------------- */
/* List hooks                                                                */
/* -------------------------------------------------------------------------- */

describe("useRiskAlerts", () => {
  it("returns every visible alert without narrowing", async () => {
    mockedFetchAllPages.mockResolvedValue({
      count: riskAlerts.length,
      results: riskAlerts,
    })

    const { result } = renderHook(() => useRiskAlerts(), {
      wrapper: createWrapper(),
    })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(result.current.data).toHaveLength(6)
  })
})

describe("useConsultations", () => {
  it("returns ALL statuses, newest session first", async () => {
    mockedFetchAllPages.mockResolvedValue({
      count: consultations.length,
      results: consultations,
    })

    const { result } = renderHook(() => useConsultations(), {
      wrapper: createWrapper(),
    })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    // The old implementation filtered to ongoing/follow_up here, which made the
    // Consultations page unable to show completed records. Status narrowing is a
    // page-level concern, so the hook returns everything, sorted by date desc.
    expect(result.current.data?.map((c) => c.status)).toEqual([
      "completed",
      "follow_up",
      "ongoing",
    ])
  })

  it("breaks same-day ties by created_at so ordering is deterministic", async () => {
    const sameDay = [
      makeConsultation({
        id: "old",
        student: "sp-1",
        session_date: "2025-01-01",
        status: "ongoing",
        priority_level: "low",
        created_at: "2025-01-01T08:00:00Z",
      }),
      makeConsultation({
        id: "new",
        student: "sp-2",
        session_date: "2025-01-01",
        status: "ongoing",
        priority_level: "low",
        created_at: "2025-01-01T10:00:00Z",
      }),
    ]
    mockedFetchAllPages.mockResolvedValue({ count: 2, results: sameDay })

    const { result } = renderHook(() => useConsultations(), {
      wrapper: createWrapper(),
    })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(result.current.data?.map((c) => c.id)).toEqual(["new", "old"])
  })
})

/* -------------------------------------------------------------------------- */
/* Client-side filters                                                        */
/* -------------------------------------------------------------------------- */

describe("filterRiskAlerts", () => {
  it("returns everything when no filter is set", () => {
    expect(filterRiskAlerts(riskAlerts, {})).toHaveLength(6)
  })

  it("filters by status, including 'all' as a no-op", () => {
    expect(
      filterRiskAlerts(riskAlerts, { status: "resolved" }).map((a) => a.id)
    ).toEqual(["ra-3", "ra-5"])
    expect(filterRiskAlerts(riskAlerts, { status: "all" })).toHaveLength(6)
  })

  it("filters by risk level", () => {
    expect(
      filterRiskAlerts(riskAlerts, { riskLevel: "high" }).map((a) => a.id)
    ).toEqual(["ra-1", "ra-4", "ra-5"])
  })

  it("filters by student UUID", () => {
    expect(
      filterRiskAlerts(riskAlerts, { studentId: "sp-1" }).map((a) => a.id)
    ).toEqual(["ra-1", "ra-2"])
  })

  it("searches student name, counselor and risk factors", () => {
    expect(
      filterRiskAlerts(riskAlerts, { search: "cara" }).map((a) => a.id)
    ).toEqual(["ra-4"])
  })

  it("combines filters with AND semantics", () => {
    expect(
      filterRiskAlerts(riskAlerts, {
        status: "resolved",
        riskLevel: "high",
      }).map((a) => a.id)
    ).toEqual(["ra-5"])
  })
})

describe("filterConsultations", () => {
  it("filters by status and priority", () => {
    expect(
      filterConsultations(consultations, { status: "completed" }).map(
        (c) => c.id
      )
    ).toEqual(["c-3"])
    expect(
      filterConsultations(consultations, { priority: "high" }).map((c) => c.id)
    ).toEqual(["c-1"])
  })

  it("searches student name and session notes", () => {
    expect(
      filterConsultations(consultations, { search: "sp-2" }).map((c) => c.id)
    ).toEqual(["c-2"])
  })
})

/* -------------------------------------------------------------------------- */
/* Decimal normalization                                                      */
/* -------------------------------------------------------------------------- */

describe("normalizeDecimal", () => {
  it("parses DRF decimal strings", () => {
    expect(normalizeDecimal("8.00")).toBe(8)
    expect(normalizeDecimal("0")).toBe(0)
    expect(normalizeDecimal("97.50")).toBe(97.5)
  })

  it("passes numbers through unchanged", () => {
    expect(normalizeDecimal(12.25)).toBe(12.25)
  })

  it("collapses absent and unparseable values to null rather than NaN", () => {
    expect(normalizeDecimal(null)).toBeNull()
    expect(normalizeDecimal(undefined)).toBeNull()
    expect(normalizeDecimal("")).toBeNull()
    expect(normalizeDecimal("not-a-number")).toBeNull()
    expect(normalizeDecimal(Number.NaN)).toBeNull()
  })

  it("distinguishes a real zero from missing data", () => {
    expect(normalizeDecimal("0.00")).toBe(0)
    expect(normalizeDecimal(null)).toBeNull()
  })
})

/**
 * `RiskAlert.risk_factors` is a bare JSONField, and the AI engine writes the
 * object form that `_extract_decision_path` produces:
 *
 *   {"feature": ..., "threshold": ..., "value": ..., "direction": ...}
 *
 * These fixtures use that real shape. PH11.8 typed the field as `string[]`,
 * which made every consumer either print "[object Object]" or hand an object to
 * React as a child and throw.
 */
describe("riskFactorLabel", () => {
  it("renders a string factor as typed", () => {
    expect(riskFactorLabel("Chronic absenteeism")).toBe("Chronic absenteeism")
  })

  it("renders a real AI decision-path factor with its detail", () => {
    const factor: RiskFactor = {
      feature: "attendance_rate",
      threshold: 0.75,
      value: 0.62,
      direction: "below",
    }

    const label = riskFactorLabel(factor)

    expect(label).toContain("attendance_rate")
    expect(label).toContain("below")
    expect(label).toContain("0.62")
    expect(label).toContain("0.75")
    expect(label).not.toContain("[object Object]")
  })

  it("omits threshold and direction the model did not supply", () => {
    expect(
      riskFactorLabel({ feature: "current_term_grade_average", value: 65 })
    ).toBe("current_term_grade_average value 65")
  })

  it("falls back to the feature key alone when only it is present", () => {
    expect(riskFactorLabel({ feature: "behavioral_points" })).toBe(
      "behavioral_points"
    )
  })

  it("returns an empty string for an unusable entry", () => {
    expect(riskFactorLabel({})).toBe("")
    expect(riskFactorLabel({ feature: "   " })).toBe("")
    expect(riskFactorLabel(null as unknown as RiskFactor)).toBe("")
    expect(riskFactorLabel(7 as unknown as RiskFactor)).toBe("")
  })

  it("never drops a factor whose numeric detail is not finite", () => {
    const label = riskFactorLabel({
      feature: "attendance_rate",
      value: Number.NaN,
      threshold: Number.POSITIVE_INFINITY,
    })

    expect(label).toBe("attendance_rate")
    expect(label).not.toContain("NaN")
    expect(label).not.toContain("Infinity")
  })
})

describe("riskFactorSearchText", () => {
  it("matches an object factor on its label and its bare feature key", () => {
    const factor: RiskFactor = {
      feature: "attendance_rate",
      threshold: 0.75,
      value: 0.62,
      direction: "below",
    }

    expect(riskFactorSearchText(factor)).toContain("attendance_rate")
    expect(riskFactorSearchText(factor)).toContain("0.62")
  })

  it("does not put [object Object] into the search haystack", () => {
    const text = riskFactorSearchText({ feature: "attendance_rate" })

    expect(text).not.toContain("[object Object]")
  })

  it("returns empty text for an unusable entry", () => {
    expect(riskFactorSearchText({} as RiskFactor)).toBe("")
  })
})

describe("filterRiskAlerts with object-shaped factors", () => {
  const alerts: RiskAlert[] = [
    makeAlert({
      id: "ra-obj",
      student: "sp-obj",
      student_name: "Object Factored",
      risk_level: "high",
      status: "active",
      risk_factors: [
        { feature: "attendance_rate", threshold: 0.75, value: 0.62 },
        "Family conflict",
      ],
    }),
  ]

  it("searches the object factor by feature name", () => {
    const result = filterRiskAlerts(alerts, { search: "attendance_rate" })

    expect(result.map((alert) => alert.id)).toEqual(["ra-obj"])
  })

  it("still searches the string factor", () => {
    const result = filterRiskAlerts(alerts, { search: "Family conflict" })

    expect(result.map((alert) => alert.id)).toEqual(["ra-obj"])
  })

  it("does not match every alert on an object-shaped haystack", () => {
    const others: RiskAlert[] = [
      makeAlert({
        id: "ra-other",
        student: "sp-other",
        student_name: "Someone Else",
        risk_level: "low",
        status: "active",
        risk_factors: [],
      }),
    ]

    // A needle present in both names must still match both, proving the
    // object-shaped entry did not collapse the haystack to a single value.
    expect(
      filterRiskAlerts([...alerts, ...others], { search: "e" }).map(
        (alert) => alert.id
      )
    ).toEqual(["ra-obj", "ra-other"])
    expect(
      filterRiskAlerts([...alerts, ...others], { search: "attendance_rate" })
    ).toHaveLength(1)
  })
})

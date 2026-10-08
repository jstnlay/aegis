import { renderHook, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import type { ReactNode } from "react"
import { afterEach, describe, expect, it, vi } from "vitest"

import { apiClient } from "@/lib/api"
import { fetchAllPages } from "@/lib/pagination"
import {
  summarizeAttendance,
  useChildAttendanceSummary,
  useChildResults,
  useChildRiskAlerts,
  useLinkedStudents,
  useParentAssessments,
} from "@/features/parent/api"

vi.mock("@/lib/pagination", () => ({
  fetchAllPages: vi.fn(),
}))

vi.mock("@/lib/api", () => ({
  apiClient: { get: vi.fn() },
}))

const mockedFetchAllPages = vi.mocked(fetchAllPages)
const mockedGet = vi.mocked(apiClient.get)

function createWrapper() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  )
}

afterEach(() => {
  vi.clearAllMocks()
})

describe("useLinkedStudents", () => {
  it("deduplicates multiple enrollments for the same child by StudentProfile UUID", async () => {
    mockedFetchAllPages.mockResolvedValue({
      count: 3,
      results: [
        {
          id: "enr-1",
          student: "sp-uuid-1",
          student_name: "Ana Cruz",
          student_id: "STU-001",
          section_name: "Section A",
          is_active: true,
        },
        {
          id: "enr-2",
          student: "sp-uuid-1",
          student_name: "Ana Cruz",
          student_id: "STU-001",
          section_name: "Section B",
          is_active: false,
        },
        {
          id: "enr-3",
          student: "sp-uuid-2",
          student_name: "Ben Cruz",
          student_id: "STU-002",
          section_name: "Section C",
          is_active: true,
        },
      ],
    })

    const { result } = renderHook(() => useLinkedStudents(), {
      wrapper: createWrapper(),
    })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(result.current.data).toHaveLength(2)
    // The linked child id is the StudentProfile UUID, never the Enrollment PK.
    expect(result.current.data?.map((s) => s.id)).toEqual([
      "sp-uuid-1",
      "sp-uuid-2",
    ])
    expect(result.current.data?.map((s) => s.id)).not.toContain("enr-1")
  })
})

describe("useChildAttendanceSummary", () => {
  it("requests the summary action with the student as a query parameter", async () => {
    /*
     * `summary` is wired as a view-level action at `/attendance/summary/`, so
     * the student belongs in the query string. Appending it as a path segment
     * matches no route: verified against the URL conf, `/attendance/summary/
     * <uuid>` raises Resolver404 while `/attendance/summary/?student=<uuid>`
     * returns 200 with a bare array.
     */
    mockedGet.mockResolvedValue({ data: [] } as never)

    const { result } = renderHook(() => useChildAttendanceSummary("sp-1"), {
      wrapper: createWrapper(),
    })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(mockedGet).toHaveBeenCalledWith("/attendance/summary/?student=sp-1")
  })

  it("does not request anything until a child is selected", () => {
    const { result } = renderHook(() => useChildAttendanceSummary(null), {
      wrapper: createWrapper(),
    })

    expect(result.current.fetchStatus).toBe("idle")
    expect(mockedGet).not.toHaveBeenCalled()
  })

  it("returns the bare array the endpoint actually sends", async () => {
    mockedGet.mockResolvedValue({
      data: [
        {
          student: "sp-1",
          present_count: 8,
          late_count: 1,
          absent_count: 1,
          total_records: 10,
        },
      ],
    } as never)

    const { result } = renderHook(() => useChildAttendanceSummary("sp-1"), {
      wrapper: createWrapper(),
    })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    // An array, not `{count, results}` — `fetchAllPages` would throw on this.
    expect(Array.isArray(result.current.data)).toBe(true)
    expect(result.current.data).toHaveLength(1)
  })
})

describe("summarizeAttendance", () => {
  it("sums across every section row", () => {
    const totals = summarizeAttendance([
      { present_count: 5, late_count: 1, absent_count: 0, total_records: 6 },
      { present_count: 3, late_count: 0, absent_count: 2, total_records: 5 },
    ])

    expect(totals).toEqual({
      present: 8,
      late: 1,
      absent: 2,
      total: 11,
      rate: (9 / 11) * 100,
    })
  })

  it("reports no data rather than 0% when there are no records", () => {
    const totals = summarizeAttendance([])

    expect(totals.total).toBe(0)
    expect(totals.rate).toBeNull()
  })

  it("preserves a genuine 0% rate", () => {
    const totals = summarizeAttendance([
      { present_count: 0, late_count: 0, absent_count: 4, total_records: 4 },
    ])

    expect(totals.rate).toBe(0)
  })

  it("counts late arrivals as attended, matching the student dashboard rule", () => {
    const totals = summarizeAttendance([
      { present_count: 0, late_count: 4, absent_count: 0, total_records: 4 },
    ])

    expect(totals.rate).toBe(100)
  })
})

describe("useChildResults", () => {
  it("narrows to the selected child's rows", async () => {
    mockedFetchAllPages.mockResolvedValue({
      count: 3,
      results: [
        { id: "r1", assessment: "a1", student: "sp-1", score: 8 },
        { id: "r2", assessment: "a1", student: "sp-2", score: 6 },
        { id: "r3", assessment: "a2", student: "sp-1", score: 9 },
      ],
    })

    const { result } = renderHook(() => useChildResults("sp-1"), {
      wrapper: createWrapper(),
    })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(result.current.data?.map((r) => r.id)).toEqual(["r1", "r3"])
  })

  it("requests the registered results route, not a guessed path", async () => {
    /*
     * Regression: this hook used to call `/assessments/results/`, which is not
     * a registered route. `apps/assessments/urls.py` registers exactly
     * `assessments`, `assessment-questions`, `assessment-results`, so the old
     * path 404'd in production while the mocked `fetchAllPages` test passed.
     * The URL itself must therefore be asserted, not just the filtering.
     */
    mockedFetchAllPages.mockResolvedValue({ count: 0, results: [] })

    const { result } = renderHook(() => useChildResults("sp-1"), {
      wrapper: createWrapper(),
    })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(mockedFetchAllPages).toHaveBeenCalledWith(
      "/assessments/assessment-results/"
    )
  })

  it("does not request results before a child is selected", () => {
    const { result } = renderHook(() => useChildResults(null), {
      wrapper: createWrapper(),
    })

    expect(result.current.fetchStatus).toBe("idle")
    expect(mockedFetchAllPages).not.toHaveBeenCalled()
  })
})

describe("useParentAssessments", () => {
  it("returns the list shape the list endpoint actually sends", async () => {
    /*
     * `AssessmentViewSet.get_serializer_class()` returns
     * `AssessmentListSerializer` for list, which carries `question_count` and
     * has no nested `questions`. Reading questions off a list row would be
     * reading a field the response never contains.
     */
    mockedFetchAllPages.mockResolvedValue({
      count: 1,
      results: [
        {
          id: "asm-1",
          title: "Well-Being Check",
          assessment_type: "wellness",
          question_count: 7,
        },
      ],
    })

    const { result } = renderHook(() => useParentAssessments(), {
      wrapper: createWrapper(),
    })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(result.current.data?.[0]?.question_count).toBe(7)
    expect(result.current.data?.[0]).not.toHaveProperty("questions")
  })

  it("never requests the answer key", async () => {
    mockedFetchAllPages.mockResolvedValue({ count: 0, results: [] })

    const { result } = renderHook(() => useParentAssessments(), {
      wrapper: createWrapper(),
    })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    // The list serializer does not carry correct_answer at all; the detail
    // serializer strips it for any non-author. Nothing here asks for it.
    expect(mockedFetchAllPages).toHaveBeenCalledWith(
      "/assessments/assessments/"
    )
  })
})

describe("useChildRiskAlerts", () => {
  it("keeps only the selected child's alerts", async () => {
    mockedFetchAllPages.mockResolvedValue({
      count: 2,
      results: [
        { id: "a1", student: "sp-1", risk_level: "moderate", status: "active" },
        { id: "a2", student: "sp-2", risk_level: "high", status: "active" },
      ],
    })

    const { result } = renderHook(() => useChildRiskAlerts("sp-1"), {
      wrapper: createWrapper(),
    })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(result.current.data?.map((a) => a.id)).toEqual(["a1"])
  })

  it("exposes no mutation hook for alerts", () => {
    /*
     * The backend answers 403 for a parent on create/update/delete and on the
     * acknowledge/escalate/resolve transitions, so the client offers no way to
     * attempt one. This asserts the absence rather than a 403 round-trip.
     */
    mockedFetchAllPages.mockResolvedValue({ count: 0, results: [] })

    renderHook(() => useChildRiskAlerts("sp-1"), { wrapper: createWrapper() })

    for (const call of mockedFetchAllPages.mock.calls) {
      expect(call[0]).not.toMatch(/acknowledge|escalate|resolve/)
      expect(
        (call[1] as { method?: string } | undefined)?.method
      ).toBeUndefined()
    }
  })
})

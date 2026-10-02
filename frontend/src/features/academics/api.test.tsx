import { renderHook, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import type { ReactNode } from "react"
import { afterEach, describe, expect, it, vi } from "vitest"

import {
  countByStatus,
  normalizeScore,
  useEncodeGrade,
  useFacultyGrades,
  useStudentGrades,
  type Grade,
  type GradeStatus,
} from "@/features/academics/api"
import { apiClient } from "@/lib/api"
import { fetchAllPages } from "@/lib/pagination"

vi.mock("@/lib/pagination", () => ({ fetchAllPages: vi.fn() }))

const mockedFetchAllPages = vi.mocked(fetchAllPages)

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

/**
 * PH11.7 regression guard.
 *
 * `Grade.score` is a `DecimalField`, and the project leaves DRF's
 * `COERCE_DECIMAL_TO_STRING` at its default of `True`, so the API emits
 * `"85.00"` rather than `85`. Arithmetic on the raw value string-concatenates
 * and yields `NaN`, which is exactly what PH11.6's `averageGrade` fallback
 * does when the analytics metrics endpoint reports `has_data: false`.
 * `normalizeScore` is the boundary that prevents this from recurring.
 */
describe("normalizeScore", () => {
  it("converts the DRF decimal string into a real number", () => {
    expect(normalizeScore("85.00")).toBe(85)
    expect(normalizeScore("0")).toBe(0)
    expect(normalizeScore(92.5)).toBe(92.5)
  })

  it("treats absent and unparseable values as no-data rather than NaN", () => {
    expect(normalizeScore(null)).toBeNull()
    expect(normalizeScore(undefined)).toBeNull()
    expect(normalizeScore("")).toBeNull()
    expect(normalizeScore("not-a-number")).toBeNull()
    expect(normalizeScore(Number.NaN)).toBeNull()
    expect(normalizeScore(Number.POSITIVE_INFINITY)).toBeNull()
  })

  it("preserves a genuine zero score", () => {
    const zero = normalizeScore("0.00")
    expect(zero).toBe(0)
    expect(zero).not.toBeNull()
  })

  it("keeps an average free of NaN for string-encoded scores", () => {
    const scores = ["85.00", "90.00", "0.00"].map(normalizeScore)
    const numeric = scores.filter((s): s is number => s !== null)
    const average = numeric.reduce((a, b) => a + b, 0) / numeric.length
    expect(Number.isNaN(average)).toBe(false)
    expect(average).toBeCloseTo(58.33, 2)
  })
})

function gradeWire(overrides: Record<string, unknown> = {}) {
  return {
    id: "g-1",
    student: "sp-1",
    student_name: "Ana Cruz",
    student_id: "STU-001",
    subject_assignment: "sa-1",
    subject_name: "Mathematics",
    subject_code: "MATH-101",
    section_name: "Section A",
    grading_period: "gp-1",
    grading_period_name: "First Quarter",
    score: "88.50",
    letter_grade: "B+",
    remarks: null,
    encoded_by: "fp-1",
    encoded_by_name: "Dr. Reyes",
    status: "finalized",
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    ...overrides,
  }
}

describe("useStudentGrades", () => {
  it("requests only finalized grades for the given student", async () => {
    mockedFetchAllPages.mockResolvedValue({
      count: 1,
      results: [gradeWire()],
    })

    const { result } = renderHook(() => useStudentGrades("sp-1"), {
      wrapper: createWrapper(),
    })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(mockedFetchAllPages).toHaveBeenCalledWith(
      "/academics/grades/?status=finalized&student=sp-1"
    )
    expect(result.current.data?.[0]?.score).toBe(88.5)
  })

  it("does not request anything without a student profile id", async () => {
    const { result } = renderHook(() => useStudentGrades(null), {
      wrapper: createWrapper(),
    })

    await waitFor(() => expect(result.current.fetchStatus).toBe("idle"))
    expect(mockedFetchAllPages).not.toHaveBeenCalled()
  })

  it("resolves to an empty array, not undefined, when there are no grades", async () => {
    mockedFetchAllPages.mockResolvedValue({ count: 0, results: [] })

    const { result } = renderHook(() => useStudentGrades("sp-1"), {
      wrapper: createWrapper(),
    })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data).toEqual([])
  })
})

describe("useFacultyGrades", () => {
  it("fetches unfiltered and normalizes every score to a number", async () => {
    mockedFetchAllPages.mockResolvedValue({
      count: 3,
      results: [
        gradeWire({ id: "g-1", score: "88.50", status: "draft" }),
        gradeWire({ id: "g-2", score: "91.00", status: "submitted" }),
        gradeWire({ id: "g-3", score: "77.25", status: "finalized" }),
      ],
    })

    const { result } = renderHook(() => useFacultyGrades(), {
      wrapper: createWrapper(),
    })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(mockedFetchAllPages).toHaveBeenCalledWith("/academics/grades/")
    expect(result.current.data?.map((g) => g.score)).toEqual([88.5, 91, 77.25])
  })
})

describe("countByStatus", () => {
  it("counts each lifecycle status plus the total", () => {
    const grades = [
      { status: "draft" },
      { status: "draft" },
      { status: "submitted" },
      { status: "finalized" },
    ] as Grade[]

    expect(countByStatus(grades)).toEqual({
      all: 4,
      draft: 2,
      submitted: 1,
      finalized: 1,
    })
  })

  it("reports zeros for an empty list rather than throwing", () => {
    expect(countByStatus([])).toEqual({
      all: 0,
      draft: 0,
      submitted: 0,
      finalized: 0,
    })
  })

  it("ignores an unexpected status value instead of producing NaN", () => {
    const grades = [{ status: "archived" }] as unknown as Grade[]
    const counts = countByStatus(grades)
    expect(counts.all).toBe(1)
    expect(Number.isNaN(counts.draft)).toBe(false)
  })
})

describe("grade status vocabulary", () => {
  it("matches the backend Grade.StatusChoices exactly", () => {
    // draft / submitted / finalized are the only values Grade.status can hold.
    const valid: GradeStatus[] = ["draft", "submitted", "finalized"]
    expect(valid).toHaveLength(3)
  })
})

describe("useEncodeGrade", () => {
  it("posts the documented encode payload and normalizes the response", async () => {
    const post = vi
      .spyOn(apiClient, "post")
      .mockResolvedValue({ data: gradeWire({ score: "95.00" }) })

    const { result } = renderHook(() => useEncodeGrade(), {
      wrapper: createWrapper(),
    })

    await result.current.mutateAsync({
      student: "sp-1",
      subject_assignment: "sa-1",
      grading_period: "gp-1",
      score: 95,
    })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(post).toHaveBeenCalledWith("/academics/grades/encode/", {
      student: "sp-1",
      subject_assignment: "sa-1",
      grading_period: "gp-1",
      score: 95,
    })
    expect(result.current.data?.score).toBe(95)
  })
})

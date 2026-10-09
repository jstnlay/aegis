import { renderHook, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import type { ReactNode } from "react"
import { afterEach, describe, expect, it, vi } from "vitest"

import { apiClient } from "@/lib/api"
import { fetchAllPages } from "@/lib/pagination"
import {
  useStudentDashboardData,
  useStudentProfileId,
} from "@/features/student/api"

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

afterEach(() => {
  vi.clearAllMocks()
})

describe("useStudentProfileId", () => {
  it("resolves the StudentProfile UUID (not the User UUID) from enrollments", async () => {
    mockedFetchAllPages.mockResolvedValue({
      count: 2,
      results: [
        {
          id: "enr-old",
          student: "old-profile-uuid",
          student_name: "Ana Cruz",
          student_id: "STU-001",
          section_name: "Section A",
          is_active: false,
        },
        {
          id: "enr-current",
          student: "current-profile-uuid",
          student_name: "Ana Cruz",
          student_id: "STU-001",
          section_name: "Section B",
          is_active: true,
        },
      ],
    })

    const { result } = renderHook(() => useStudentProfileId(), {
      wrapper: createWrapper(),
    })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    // Prefers the active enrollment's `student` field (a StudentProfile UUID).
    expect(result.current.data).toBe("current-profile-uuid")
    // It must NOT return the Enrollment PK.
    expect(result.current.data).not.toBe("enr-current")
  })

  it("requests every page of enrollments so later pages are not lost", async () => {
    mockedFetchAllPages.mockResolvedValue({ count: 0, results: [] })

    const { result } = renderHook(() => useStudentProfileId(), {
      wrapper: createWrapper(),
    })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(mockedFetchAllPages).toHaveBeenCalledWith("/academics/enrollments/")
    expect(result.current.data).toBeNull()
  })
})

describe("useStudentDashboardData attendance", () => {
  /**
   * Regression: the attendance query used to return `undefined` when the
   * backend returned an empty list. TanStack Query v5 treats a resolved
   * `undefined` as an error ("Query data cannot be undefined"), which set
   * the shared `error` flag and rendered a false "Unable to load academic
   * progress" / "Unable to load grades" message on the Student and Parent
   * dashboards even though every request had returned 200. It must resolve
   * to `null` — the codebase's established "no data" value — instead.
   */
  it("resolves to null, not undefined, when the student has no attendance records", async () => {
    vi.spyOn(apiClient, "get").mockImplementation((async (url: string) => {
      if (url.startsWith("/attendance/summary")) return { data: [] }
      if (url.includes("/metrics/")) {
        return { data: { status: "ok", data: { has_data: false } } }
      }
      throw new Error(`Unexpected request: ${url}`)
    }) as unknown as typeof apiClient.get)

    mockedFetchAllPages.mockResolvedValue({ count: 0, results: [] })

    const { result } = renderHook(
      () => useStudentDashboardData("profile-uuid"),
      { wrapper: createWrapper() }
    )

    await waitFor(() => expect(result.current.loading).toBe(false))

    // Resolved successfully — NOT an error state.
    expect(result.current.error).toBeFalsy()
    // Explicitly `null` so TanStack Query treats it as valid data.
    expect(result.current.attendance).toBeNull()
    expect(result.current.attendance).not.toBeUndefined()
  })

  it("preserves a genuine 0% rate when every record is an absence", async () => {
    vi.spyOn(apiClient, "get").mockImplementation((async (url: string) => {
      if (url.startsWith("/attendance/summary")) {
        return {
          data: [
            {
              student: "profile-uuid",
              student_name: "Ana Cruz",
              student_id_code: "STU-001",
              section_name: "Section A",
              present_count: 0,
              late_count: 0,
              absent_count: 4,
              total_records: 4,
            },
          ],
        }
      }
      if (url.includes("/metrics/")) {
        return { data: { status: "ok", data: { has_data: false } } }
      }
      throw new Error(`Unexpected request: ${url}`)
    }) as unknown as typeof apiClient.get)

    mockedFetchAllPages.mockResolvedValue({ count: 0, results: [] })

    const { result } = renderHook(
      () => useStudentDashboardData("profile-uuid"),
      { wrapper: createWrapper() }
    )

    await waitFor(() => expect(result.current.loading).toBe(false))

    expect(result.current.error).toBeFalsy()
    // A real 0% is data, not "no data" — it must not collapse to null/N/A.
    expect(result.current.attendance?.attendance_rate).toBe(0)
    expect(result.current.attendance?.total_days).toBe(4)
  })
})

describe("useStudentDashboardData grading periods", () => {
  /**
   * Regression for the "finalized grades on Academics, N/A on Dashboard"
   * report (TC-STU-03).
   *
   * A finalized grade whose grading period name is null was grouped into an
   * "Unassigned" bucket but kept `""` as its own `grading_period`, so the
   * default period filter matched nothing, every row dropped out of
   * `filteredGrades`, and the derived average collapsed to null. The same
   * rows were listed in full on the Academics page.
   */
  it("keeps grades with no grading period in the default period", async () => {
    vi.spyOn(apiClient, "get").mockImplementation((async (url: string) => {
      if (url.startsWith("/attendance/summary")) return { data: [] }
      if (url.includes("/metrics/")) {
        return { data: { status: "ok", data: { has_data: false } } }
      }
      throw new Error(`Unexpected request: ${url}`)
    }) as unknown as typeof apiClient.get)

    mockedFetchAllPages.mockImplementation(async (url: string) => {
      if (url.includes("/academics/grades/")) {
        return {
          count: 1,
          results: [
            {
              subject_name: "Mathematics",
              subject_code: "MATH",
              score: 88,
              letter_grade: "B",
              grading_period_name: null,
            },
          ],
        }
      }
      if (url.includes("/academics/grading-periods/")) {
        return { count: 0, results: [] }
      }
      return { count: 0, results: [] }
    })

    const { result } = renderHook(
      () => useStudentDashboardData("profile-uuid"),
      { wrapper: createWrapper() }
    )

    await waitFor(() => expect(result.current.loading).toBe(false))

    expect(result.current.error).toBeFalsy()
    expect(result.current.grades).toHaveLength(1)
    expect(result.current.periods).toHaveLength(1)
    expect(result.current.periods[0]?.period_name).toBe("Unassigned")
    expect(result.current.averageGrade).toBe(88)
  })
})

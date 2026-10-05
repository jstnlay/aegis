import { renderHook, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import type { ReactNode } from "react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { apiClient } from "@/lib/api"
import { fetchAllPages } from "@/lib/pagination"
import {
  cmsResourceFileUrl,
  filenameFromDisposition,
  useAdminAttendanceSummary,
  useAdminGrades,
  useAdminUsers,
  useAuditLogs,
  useGradeLevelComparison,
  useImportJobs,
  useRiskDistribution,
  useSchoolWideMetrics,
} from "@/features/admin/api"

vi.mock("@/lib/api", () => ({
  apiClient: { get: vi.fn() },
}))

vi.mock("@/lib/pagination", () => ({
  fetchAllPages: vi.fn(async () => ({ results: [], count: 0 })),
}))

const mockedGet = vi.mocked(apiClient.get)
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

describe("admin analytics clients", () => {
  it("unwraps the { status, data } envelope for school-wide metrics", async () => {
    mockedGet.mockResolvedValueOnce({
      data: {
        status: "ok",
        data: {
          total_students: 320,
          overall_grade_average: 84.5,
          grade_levels: 6,
        },
      },
    })

    const { result } = renderHook(() => useSchoolWideMetrics(), {
      wrapper: createWrapper(),
    })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(result.current.data).toEqual({
      total_students: 320,
      overall_grade_average: 84.5,
      grade_levels: 6,
    })
    expect(mockedGet).toHaveBeenCalledWith("/analytics/school-wide/")
  })

  it("returns the whole risk payload, distribution plus the score total", async () => {
    /*
     * `total_with_scores` matters: RiskScore has no API surface, so zero here
     * means the engine has not run. Dropping it would leave the UI unable to
     * distinguish "no student is at risk" from "no risk model output exists".
     */
    mockedGet.mockResolvedValueOnce({
      data: {
        status: "ok",
        data: {
          distribution: { low: 10, moderate: 4, high: 2, insufficient_data: 1 },
          total_with_scores: 16,
        },
      },
    })

    const { result } = renderHook(() => useRiskDistribution(), {
      wrapper: createWrapper(),
    })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(result.current.data).toEqual({
      distribution: { low: 10, moderate: 4, high: 2, insufficient_data: 1 },
      total_with_scores: 16,
    })
  })

  it("unwraps the grade_levels array out of the nested data object", async () => {
    /*
     * `grade_level_comparison()` returns `{"status","data":{"grade_levels":[...]}}`
     * — the array is nested one level deeper than `school-wide`, whose `data` is
     * the object itself. Reading `data.data` as the array would give undefined.
     */
    mockedGet.mockResolvedValueOnce({
      data: {
        status: "ok",
        data: {
          grade_levels: [
            {
              grade_level_id: "gl-1",
              grade_level_name: "Grade 7",
              average: 82.5,
              grade_count: 240,
            },
          ],
        },
      },
    })

    const { result } = renderHook(() => useGradeLevelComparison(), {
      wrapper: createWrapper(),
    })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(result.current.data).toHaveLength(1)
    expect(result.current.data?.[0]?.grade_level_name).toBe("Grade 7")
    expect(mockedGet).toHaveBeenCalledWith(
      "/analytics/grade-levels/comparison/"
    )
  })

  /**
   * NFR-010 requires admin analytics to stay aggregated. No client in this
   * module may request the one endpoint that returns named students, or the
   * admin surface would be able to render exactly what the requirement rules
   * out.
   */
  it("exposes no client for the student-naming low-performance endpoint", () => {
    const requested: string[] = []
    for (const hook of [
      useSchoolWideMetrics,
      useRiskDistribution,
      useGradeLevelComparison,
    ]) {
      void renderHook(() => hook(), { wrapper: createWrapper() })
    }
    for (const call of mockedGet.mock.calls) requested.push(String(call[0]))

    expect(requested).not.toContain("/analytics/low-performance/")
  })
})

describe("admin list clients use the paginated envelope", () => {
  it("requests users, grades and audit logs through the paginated path", () => {
    /*
     * These three endpoints return `{count, results}` and DRF caps
     * `page_size` at 100, so `fetchAllPages` is what makes them complete. A
     * single `apiClient.get` would silently show only the first page.
     */
    renderHook(() => useAdminUsers(), { wrapper: createWrapper() })
    renderHook(() => useAdminGrades(), { wrapper: createWrapper() })
    renderHook(() => useAuditLogs(), { wrapper: createWrapper() })
    renderHook(() => useImportJobs(), { wrapper: createWrapper() })

    const urls = mockedFetchAllPages.mock.calls.map((call) => String(call[0]))
    expect(urls).toContain("/accounts/users/")
    expect(urls).toContain("/academics/grades/")
    expect(urls).toContain("/audit/logs/")
    expect(urls).toContain("/data-import/jobs/")
  })

  it("maps every audit filter onto the bounded query parameter", async () => {
    mockedGet.mockResolvedValueOnce({ data: [] })

    const { result } = renderHook(
      () =>
        useAuditLogs({
          action: "login",
          modelName: "accounts.User",
          objectId: "11111111-1111-1111-1111-111111111111",
          search: "Cruz",
          startTime: "2026-01-01T00:00:00Z",
          endTime: "2026-02-01T00:00:00Z",
        }),
      { wrapper: createWrapper() }
    )

    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    const url = String(mockedFetchAllPages.mock.calls.at(-1)?.[0])

    expect(url).toContain("action=login")
    expect(url).toContain("model_name=accounts.User")
    expect(url).toContain("object_id=")
    expect(url).toContain("search=Cruz")
    expect(url).toContain("start_time=")
    expect(url).toContain("end_time=")
  })
})

describe("admin attendance", () => {
  beforeEach(() => {
    // Each case sets its own resolved value, but the query cache is shared
    // across renderHook calls in this file, so an earlier result would
    // otherwise satisfy the next assertion.
    mockedGet.mockReset()
  })

  it("requests the summary action with section as a query parameter", async () => {
    /*
     * `summary` is wired at `/attendance/summary/`, so `section` belongs in the
     * query string. Confirmed against the URL conf that a path segment there
     * resolves to nothing.
     */
    mockedGet.mockResolvedValueOnce({ data: [] })

    const { result } = renderHook(() => useAdminAttendanceSummary("sec-1"), {
      wrapper: createWrapper(),
    })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(mockedGet).toHaveBeenCalledWith("/attendance/summary/?section=sec-1")
  })

  it("treats the summary as a bare array, not a paginated envelope", async () => {
    mockedGet.mockResolvedValueOnce({
      data: [
        {
          student: "sp-1",
          student_name: "Ana",
          student_id_code: "S-1",
          section_name: "Bonifacio",
          present_count: 10,
          late_count: 1,
          absent_count: 1,
          total_records: 12,
        },
      ],
    })

    const { result } = renderHook(() => useAdminAttendanceSummary(null), {
      wrapper: createWrapper(),
    })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(Array.isArray(result.current.data)).toBe(true)
    expect(result.current.data).toHaveLength(1)
  })
})

describe("export filename parsing", () => {
  it("reads the RFC 5987 extended filename the backend actually sends", () => {
    // `build_content_disposition()` emits `filename*=UTF-8''...`, so a parser
    // that only looks for `filename="..."` would lose the name.
    const header =
      "attachment; filename*=UTF-8''grades_export.csv; filename=\"fallback.csv\""
    expect(filenameFromDisposition(header)).toBe("grades_export.csv")
  })

  it("decodes percent-escapes in the extended filename", () => {
    expect(
      filenameFromDisposition(
        "attachment; filename*=UTF-8''aegis%20grades%20export.csv"
      )
    ).toBe("aegis grades export.csv")
  })

  it("falls back to the plain parameter when there is no extended one", () => {
    expect(
      filenameFromDisposition('attachment; filename="attendance.csv"')
    ).toBe("attendance.csv")
  })

  it("returns null when the header is absent or unparseable", () => {
    expect(filenameFromDisposition(undefined)).toBeNull()
    expect(filenameFromDisposition("attachment")).toBeNull()
  })
})

describe("CMS resource file link", () => {
  /**
   * SEC-007: the file is proxied through AEGIS under the caller's own access
   * rules. Pointing at the Strapi URL instead would bypass that entirely.
   */
  it("builds the authorized proxy path, not a Strapi URL", () => {
    const url = cmsResourceFileUrl("doc-123")

    expect(url).toBe("/api/v1/cms/resources/doc-123/file/")
    expect(url).not.toContain("strapi")
    expect(url).not.toContain("http")
  })

  it("escapes the document id so a crafted value cannot escape the path", () => {
    expect(cmsResourceFileUrl("a/b?x=1")).toBe(
      "/api/v1/cms/resources/a%2Fb%3Fx%3D1/file/"
    )
  })
})

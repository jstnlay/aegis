import { renderHook, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import type { ReactNode } from "react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { apiClient } from "@/lib/api"
import { fetchAllPages } from "@/lib/pagination"
import {
  cmsResourceFilePath,
  downloadCmsResource,
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

/* Poll faster than the 3 s the app uses: the assertion below only needs to see
 * a second request happen at all. */
vi.mock("@/lib/importJobs", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/importJobs")>()
  return { ...actual, IMPORT_JOB_POLL_INTERVAL_MS: 20 }
})

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

  it("keeps refreshing the job list while a job is still processing", async () => {
    /*
     * An upload larger than the request returns `processing` and is finished by
     * a worker, so without the poll the page would show "processing" forever.
     */
    mockedFetchAllPages.mockResolvedValue({
      results: [
        {
          id: "job-1",
          uploaded_by: { id: "u1", name: "Ada Min" },
          file_name: "grades.csv",
          import_type: "grades",
          status: "processing",
          total_rows: 500,
          processed_rows: 0,
          error_rows: 0,
          created_at: "2026-01-01T00:00:00Z",
          completed_at: null,
          record_summary: { success: 0, error: 0, skipped: 0 },
        },
      ],
      count: 1,
    })

    renderHook(() => useImportJobs(), { wrapper: createWrapper() })

    await waitFor(() =>
      expect(mockedFetchAllPages.mock.calls.length).toBeGreaterThan(1)
    )
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

describe("CMS resource download", () => {
  /**
   * SEC-007: the file is proxied through AEGIS under the caller's own access
   * rules. Pointing at the Strapi URL instead would bypass that entirely.
   */
  it("addresses the authorized proxy path, not a Strapi URL", () => {
    const path = cmsResourceFilePath("doc-123")

    expect(path).toBe("/cms/resources/doc-123/file/")
    expect(path).not.toContain("strapi")
    expect(path).not.toContain("http")
  })

  it("escapes the document id so a crafted value cannot escape the path", () => {
    expect(cmsResourceFilePath("a/b?x=1")).toBe(
      "/cms/resources/a%2Fb%3Fx%3D1/file/"
    )
  })

  /*
   * PH11.10 regression. The download used to be an `<a href>` at this route.
   * Authentication in this app is a bearer token injected by the axios request
   * interceptor, and a native anchor sends no such header, so the SEC-007 proxy
   * answered 401. These assertions pin that the request goes through the API
   * client (where the token and the refresh path live) and asks for a blob.
   */
  it("requests the file through the API client so the bearer token is sent", async () => {
    mockedGet.mockResolvedValueOnce({
      data: new Blob(["bytes"]),
      headers: {
        "content-disposition": "attachment; filename*=UTF-8''handbook.pdf",
      },
    } as never)

    await downloadCmsResource("doc-123")

    expect(mockedGet).toHaveBeenCalledTimes(1)
    const call = mockedGet.mock.calls[0]!
    const [path, config] = call
    expect(path).toBe("/cms/resources/doc-123/file/")
    expect(config).toMatchObject({ responseType: "blob" })
  })

  it("hands the bytes to the browser under the server's filename", async () => {
    vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:mock")
    const revokeObjectURL = vi
      .spyOn(URL, "revokeObjectURL")
      .mockImplementation(() => {})
    const clicked: HTMLAnchorElement[] = []
    const originalCreate = document.createElement.bind(document)
    vi.spyOn(document, "createElement").mockImplementation((tag: string) => {
      const element = originalCreate(tag)
      if (tag === "a") {
        element.addEventListener("click", (event) => {
          event.preventDefault()
          clicked.push(element as HTMLAnchorElement)
        })
      }
      return element
    })

    mockedGet.mockResolvedValueOnce({
      data: new Blob(["bytes"]),
      headers: {
        "content-disposition": "attachment; filename*=UTF-8''handbook.pdf",
      },
    } as never)

    await downloadCmsResource("doc-123")

    expect(clicked).toHaveLength(1)
    expect(clicked[0]!.download).toBe("handbook.pdf")
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:mock")

    vi.restoreAllMocks()
  })

  it("falls back to a generic filename when the header is absent", async () => {
    vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:mock")
    vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => {})
    const originalCreate = document.createElement.bind(document)
    const clicked: HTMLAnchorElement[] = []
    vi.spyOn(document, "createElement").mockImplementation((tag: string) => {
      const element = originalCreate(tag)
      if (tag === "a") {
        element.addEventListener("click", (event) => {
          event.preventDefault()
          clicked.push(element as HTMLAnchorElement)
        })
      }
      return element
    })

    mockedGet.mockResolvedValueOnce({
      data: new Blob(["bytes"]),
      headers: {},
    } as never)

    await downloadCmsResource("doc-123")

    expect(clicked[0]!.download).toBe("aegis-resource")

    vi.restoreAllMocks()
  })

  it("propagates a failure rather than reporting a silent success", async () => {
    const createObjectURL = vi.spyOn(URL, "createObjectURL")
    const failure = Object.assign(new Error("Request failed"), {
      isAxiosError: true,
      response: {
        status: 401,
        data: {
          success: false,
          error: {
            code: "AUTHENTICATION_REQUIRED",
            message: "Authentication credentials were not provided.",
          },
        },
      },
    })
    mockedGet.mockRejectedValueOnce(failure)

    await expect(downloadCmsResource("doc-123")).rejects.toThrow()
    // Nothing reached the browser: a failed download must not look successful.
    expect(createObjectURL).not.toHaveBeenCalled()

    vi.restoreAllMocks()
  })
})

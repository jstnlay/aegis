import { renderHook, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import type { ReactNode } from "react"
import { afterEach, describe, expect, it, vi } from "vitest"

import { apiClient } from "@/lib/api"
import { fetchAllPages } from "@/lib/pagination"
import {
  useAttendanceRecords,
  useAttendanceSummary,
  useCreateAttendance,
} from "@/features/attendance/api"

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

function recordWire(overrides: Record<string, unknown> = {}) {
  return {
    id: "ar-1",
    student: "sp-1",
    student_name: "Ana Cruz",
    student_id_code: "STU-001",
    section: "sec-1",
    section_name: "Section A",
    date: "2026-03-02",
    status: "present",
    recorded_by: "fp-9",
    recorded_by_name: "Dr. Reyes",
    created_at: "2026-03-02T08:00:00Z",
    updated_at: "2026-03-02T08:00:00Z",
    ...overrides,
  }
}

describe("useAttendanceRecords", () => {
  it("requests the unscoped list when no filters are given", async () => {
    mockedFetchAllPages.mockResolvedValue({ count: 1, results: [recordWire()] })

    const { result } = renderHook(() => useAttendanceRecords(), {
      wrapper: createWrapper(),
    })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(mockedFetchAllPages).toHaveBeenCalledWith("/attendance/records/")
  })

  it("maps every supported backend query parameter", async () => {
    mockedFetchAllPages.mockResolvedValue({ count: 0, results: [] })

    const { result } = renderHook(
      () =>
        useAttendanceRecords({
          student: "sp-1",
          section: "sec-1",
          status: "absent",
          dateFrom: "2026-03-01",
          dateTo: "2026-03-31",
        }),
      { wrapper: createWrapper() }
    )

    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    const url = mockedFetchAllPages.mock.calls[0]![0] as string
    expect(url).toContain("student=sp-1")
    expect(url).toContain("section=sec-1")
    expect(url).toContain("status=absent")
    expect(url).toContain("date_from=2026-03-01")
    expect(url).toContain("date_to=2026-03-31")
  })

  it("does not send empty filter values", async () => {
    mockedFetchAllPages.mockResolvedValue({ count: 0, results: [] })

    const { result } = renderHook(
      () => useAttendanceRecords({ student: "sp-1", status: undefined }),
      { wrapper: createWrapper() }
    )

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    const url = mockedFetchAllPages.mock.calls[0]![0] as string
    expect(url).not.toContain("status=")
    expect(url).not.toContain("section=")
  })
})

describe("useAttendanceSummary", () => {
  it("returns the bare array without pagination unwrapping", async () => {
    const payload = [
      {
        student: "sp-1",
        student_name: "Ana Cruz",
        student_id_code: "STU-001",
        section_name: "Section A",
        present_count: 8,
        late_count: 1,
        absent_count: 1,
        total_records: 10,
      },
    ]
    const get = vi.spyOn(apiClient, "get").mockResolvedValue({ data: payload })

    const { result } = renderHook(() => useAttendanceSummary("sp-1"), {
      wrapper: createWrapper(),
    })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    // The backend returns a bare list, NOT {count,next,results}.
    expect(get).toHaveBeenCalledWith("/attendance/summary/?student=sp-1")
    expect(result.current.data).toEqual(payload)
  })

  it("keeps multi-section rows separate instead of merging them", async () => {
    vi.spyOn(apiClient, "get").mockResolvedValue({
      data: [
        {
          student: "sp-1",
          student_name: "Ana Cruz",
          student_id_code: "STU-001",
          section_name: "Section A",
          present_count: 5,
          late_count: 0,
          absent_count: 1,
          total_records: 6,
        },
        {
          student: "sp-1",
          student_name: "Ana Cruz",
          student_id_code: "STU-001",
          section_name: "Section B",
          present_count: 3,
          late_count: 1,
          absent_count: 0,
          total_records: 4,
        },
      ],
    })

    const { result } = renderHook(() => useAttendanceSummary("sp-1"), {
      wrapper: createWrapper(),
    })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    // The summary is grouped by student+section, so a multi-section student
    // legitimately has several rows. The hook must not collapse them.
    expect(result.current.data).toHaveLength(2)
    expect(result.current.data?.map((r) => r.section_name)).toEqual([
      "Section A",
      "Section B",
    ])
  })

  it("resolves an empty summary to an empty array, not undefined", async () => {
    vi.spyOn(apiClient, "get").mockResolvedValue({ data: [] })

    const { result } = renderHook(() => useAttendanceSummary("sp-1"), {
      wrapper: createWrapper(),
    })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data).toEqual([])
    expect(result.current.data).not.toBeUndefined()
  })
})

describe("useCreateAttendance", () => {
  it("posts exactly the writable fields — recorded_by stays server-assigned", async () => {
    const post = vi
      .spyOn(apiClient, "post")
      .mockResolvedValue({ data: recordWire() })

    const { result } = renderHook(() => useCreateAttendance(), {
      wrapper: createWrapper(),
    })

    await result.current.mutateAsync({
      student: "sp-1",
      section: "sec-1",
      date: "2026-03-02",
      status: "present",
    })
    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(post).toHaveBeenCalledWith("/attendance/records/", {
      student: "sp-1",
      section: "sec-1",
      date: "2026-03-02",
      status: "present",
    })
    // `recorded_by` is a read_only_field; the client must never send it.
    const body = post.mock.calls[0]![1] as Record<string, unknown>
    expect(body).not.toHaveProperty("recorded_by")
  })

  it("surfaces a 409 duplicate conflict instead of swallowing it", async () => {
    vi.spyOn(apiClient, "post").mockRejectedValue(
      Object.assign(new Error("conflict"), {
        isAxiosError: true,
        response: { status: 409, data: {} },
      })
    )

    const { result } = renderHook(() => useCreateAttendance(), {
      wrapper: createWrapper(),
    })

    await expect(
      result.current.mutateAsync({
        student: "sp-1",
        section: "sec-1",
        date: "2026-03-02",
        status: "present",
      })
    ).rejects.toBeTruthy()

    await waitFor(() => expect(result.current.isError).toBe(true))
  })
})

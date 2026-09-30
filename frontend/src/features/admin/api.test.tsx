import { renderHook, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import type { ReactNode } from "react"
import { afterEach, describe, expect, it, vi } from "vitest"

import { apiClient } from "@/lib/api"
import {
  useLowPerformanceStudents,
  useRiskDistribution,
  useSchoolWideMetrics,
} from "@/features/admin/api"

vi.mock("@/lib/api", () => ({
  apiClient: { get: vi.fn() },
}))

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

  it("unwraps the distribution object for risk distribution", async () => {
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
      low: 10,
      moderate: 4,
      high: 2,
      insufficient_data: 1,
    })
  })

  it("unwraps the low-performance student list using backend fields only", async () => {
    mockedGet.mockResolvedValueOnce({
      data: {
        status: "ok",
        data: [
          { student_id: "sp-1", student_name: "Ana", average: 71.25 },
          { student_id: "sp-2", student_name: "Ben", average: 68.0 },
        ],
      },
    })

    const { result } = renderHook(() => useLowPerformanceStudents(), {
      wrapper: createWrapper(),
    })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(result.current.data).toHaveLength(2)
    expect(result.current.data?.[0]).toEqual({
      student_id: "sp-1",
      student_name: "Ana",
      average: 71.25,
    })
    expect(mockedGet).toHaveBeenCalledWith("/analytics/low-performance/")
  })
})

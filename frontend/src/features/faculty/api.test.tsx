import { renderHook, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import type { ReactNode } from "react"
import { afterEach, describe, expect, it, vi } from "vitest"

import { apiClient } from "@/lib/api"
import { fetchAllPages } from "@/lib/pagination"
import { useFacultyDashboardStats } from "@/features/faculty/api"

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

describe("useFacultyDashboardStats", () => {
  it("counts unique active students and uses backend count for pending totals", async () => {
    mockedFetchAllPages.mockResolvedValue({
      count: 5,
      results: [
        {
          id: "e1",
          student: "sp-1",
          student_name: "A",
          student_id: "S1",
          is_active: true,
        },
        {
          id: "e2",
          student: "sp-1",
          student_name: "A",
          student_id: "S1",
          is_active: true,
        },
        {
          id: "e3",
          student: "sp-2",
          student_name: "B",
          student_id: "S2",
          is_active: true,
        },
        {
          id: "e4",
          student: "sp-3",
          student_name: "C",
          student_id: "S3",
          is_active: false,
        },
      ],
    })
    mockedGet.mockImplementation(async (url: string) => {
      if (url.includes("status=draft")) {
        return {
          data: {
            count: 220,
            next: "http://localhost:8000/api/v1/academics/grades/?status=draft&page=2",
            previous: null,
            results: [{}],
          },
        }
      }
      return {
        data: { count: 7, next: null, previous: null, results: [{}] },
      }
    })

    const { result } = renderHook(() => useFacultyDashboardStats(), {
      wrapper: createWrapper(),
    })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    // Duplicate sp-1 enrollment counted once; inactive sp-3 excluded.
    expect(result.current.data?.total_students).toBe(2)
    // Pending totals come from the paginated `count`, not results.length (1).
    expect(result.current.data?.pending_grades).toBe(220)
    expect(result.current.data?.pending_submissions).toBe(7)
  })
})

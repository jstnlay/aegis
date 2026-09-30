import { renderHook, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import type { ReactNode } from "react"
import { afterEach, describe, expect, it, vi } from "vitest"

import { fetchAllPages } from "@/lib/pagination"
import { useLinkedStudents } from "@/features/parent/api"

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

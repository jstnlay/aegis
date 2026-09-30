import { renderHook, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import type { ReactNode } from "react"
import { afterEach, describe, expect, it, vi } from "vitest"

import { fetchAllPages } from "@/lib/pagination"
import {
  useAssessmentCompletion,
  useAtRiskStudents,
  useConsultations,
} from "@/features/guidance/api"

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

const riskAlerts = [
  {
    id: "ra-1",
    student: "sp-1",
    student_name: "Ana",
    risk_level: "high" as const,
    risk_factors: [],
    status: "active" as const,
    assigned_counselor_name: null,
    generated_at: "2025-01-01T00:00:00Z",
    last_updated: "2025-01-01T00:00:00Z",
  },
  // Same at-risk child, second alert -> must count once.
  {
    id: "ra-2",
    student: "sp-1",
    student_name: "Ana",
    risk_level: "moderate" as const,
    risk_factors: [],
    status: "under_monitoring" as const,
    assigned_counselor_name: null,
    generated_at: "2025-01-02T00:00:00Z",
    last_updated: "2025-01-02T00:00:00Z",
  },
  {
    id: "ra-3",
    student: "sp-2",
    student_name: "Ben",
    risk_level: "low" as const,
    risk_factors: [],
    status: "resolved" as const,
    assigned_counselor_name: null,
    generated_at: "2025-01-03T00:00:00Z",
    last_updated: "2025-01-03T00:00:00Z",
  },
  {
    id: "ra-4",
    student: "sp-3",
    student_name: "Cara",
    risk_level: "high" as const,
    risk_factors: [],
    status: "escalated" as const,
    assigned_counselor_name: null,
    generated_at: "2025-01-04T00:00:00Z",
    last_updated: "2025-01-04T00:00:00Z",
  },
]

const consultations = [
  {
    id: "c-1",
    student: "sp-1",
    student_name: "Ana",
    session_date: "2025-01-01",
    session_type: "individual",
    status: "ongoing" as const,
    priority_level: "high" as const,
    created_at: "2025-01-01T00:00:00Z",
  },
  {
    id: "c-2",
    student: "sp-2",
    student_name: "Ben",
    session_date: "2025-01-02",
    session_type: "group",
    status: "follow_up" as const,
    priority_level: "low" as const,
    created_at: "2025-01-02T00:00:00Z",
  },
  {
    id: "c-3",
    student: "sp-3",
    student_name: "Cara",
    session_date: "2025-01-03",
    session_type: "individual",
    status: "completed" as const,
    priority_level: "medium" as const,
    created_at: "2025-01-03T00:00:00Z",
  },
]

afterEach(() => {
  vi.clearAllMocks()
})

describe("useAtRiskStudents", () => {
  it("counts DISTINCT students at moderate/high risk only", async () => {
    mockedFetchAllPages.mockResolvedValue({ count: 4, results: riskAlerts })

    const { result } = renderHook(() => useAtRiskStudents(), {
      wrapper: createWrapper(),
    })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    // sp-1 (twice), sp-3 -> two distinct; sp-2 is low risk and excluded.
    expect(result.current.data).toEqual(["sp-1", "sp-3"])
  })
})

describe("useConsultations", () => {
  it("returns only ongoing and follow_up consultations", async () => {
    mockedFetchAllPages.mockResolvedValue({ count: 3, results: consultations })

    const { result } = renderHook(() => useConsultations(), {
      wrapper: createWrapper(),
    })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(result.current.data?.map((c) => c.status)).toEqual([
      "follow_up",
      "ongoing",
    ])
    expect(result.current.data?.some((c) => c.status === "completed")).toBe(
      false
    )
  })
})

describe("useAssessmentCompletion", () => {
  it("computes completed / total assessment results and pending follow-up", async () => {
    mockedFetchAllPages.mockImplementation(async (url: string) => {
      if (url.includes("assessment-results")) {
        return {
          count: 4,
          results: [
            {
              id: "ar-1",
              assessment: "a-1",
              student: "sp-1",
              status: "completed",
            },
            {
              id: "ar-2",
              assessment: "a-1",
              student: "sp-2",
              status: "completed",
            },
            {
              id: "ar-3",
              assessment: "a-2",
              student: "sp-1",
              status: "in_progress",
            },
            {
              id: "ar-4",
              assessment: "a-2",
              student: "sp-3",
              status: "in_progress",
            },
          ],
        }
      }
      if (url.includes("consultations")) {
        return { count: 3, results: consultations }
      }
      return { count: 4, results: riskAlerts }
    })

    const { result } = renderHook(() => useAssessmentCompletion(), {
      wrapper: createWrapper(),
    })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(result.current.data?.assessment_completion_rate).toBe(50)
    expect(result.current.data?.pending_follow_up).toBe(2)
    // active + under_monitoring + escalated (resolved excluded)
    expect(result.current.data?.active_cases).toBe(3)
    expect(result.current.data?.at_risk_students).toBe(2)
  })
})

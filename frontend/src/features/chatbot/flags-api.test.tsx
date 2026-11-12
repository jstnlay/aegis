import { renderHook, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import type { ReactNode } from "react"
import { describe, expect, it, vi } from "vitest"

import { apiClient } from "@/lib/api"
import {
  useChatbotDashboard,
  useFacultyFlags,
  useGuidanceFlags,
} from "@/features/chatbot/flags-api"
import {
  useAcceptNotice,
  useChatHistory,
  usePublicNotice,
} from "@/features/chatbot/api"

vi.mock("@/lib/api", () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
}))

const mockedGet = vi.mocked(apiClient.get)
const mockedPost = vi.mocked(apiClient.post)

function createWrapper() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  )
}

/**
 * The faculty feed is content-blind by contract.
 *
 * `FacultyFlagSerializer` sends severity, status and timestamps and nothing
 * else. This test pins the frontend side of that contract: the faculty hook
 * reads the same endpoint as the guidance hook, and the shape it hands the
 * page has no field a conversation could be rendered from.
 */
describe("faculty flag feed", () => {
  it("reads the flag list and hands back only blind rows", async () => {
    mockedGet.mockResolvedValueOnce({
      data: {
        results: [
          {
            id: "flag-1",
            severity: "high",
            status: "open",
            created_at: "2026-11-13T00:00:00Z",
            acknowledged_at: null,
            escalated_at: null,
          },
        ],
      },
    })

    const { result } = renderHook(() => useFacultyFlags(), {
      wrapper: createWrapper(),
    })

    await waitFor(() => expect(result.current.data).toHaveLength(1))
    expect(mockedGet).toHaveBeenCalledWith("/chatbot/flags/")
    const row = result.current.data?.[0]
    expect(row).toBeDefined()
    expect(Object.keys(row!).sort()).toEqual([
      "acknowledged_at",
      "created_at",
      "escalated_at",
      "id",
      "severity",
      "status",
    ])
  })
})

describe("guidance flag inbox", () => {
  it("passes the status and severity filters as query parameters", async () => {
    mockedGet.mockResolvedValueOnce({ data: { results: [] } })

    const { result } = renderHook(
      () => useGuidanceFlags({ status: "open", severity: "critical" }),
      { wrapper: createWrapper() }
    )

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(mockedGet).toHaveBeenCalledWith("/chatbot/flags/", {
      params: { status: "open", severity: "critical" },
    })
  })
})

describe("notice and history", () => {
  it("posts the accepted version to the notice endpoint", async () => {
    mockedPost.mockResolvedValueOnce({
      data: { detail: "Notice accepted.", version: "2026-11-01", accepted_at: "now" },
    })

    const { result } = renderHook(() => useAcceptNotice(), {
      wrapper: createWrapper(),
    })

    await result.current.mutateAsync({ version: "2026-11-01" })
    expect(mockedPost).toHaveBeenCalledWith("/chatbot/notice/", {
      version: "2026-11-01",
    })
  })

  it("reads the public notice without a token", async () => {
    mockedGet.mockResolvedValueOnce({
      data: { version: "2026-11-01", text: "Notice text." },
    })

    const { result } = renderHook(() => usePublicNotice(), {
      wrapper: createWrapper(),
    })

    await waitFor(() => expect(result.current.data?.version).toBe("2026-11-01"))
    expect(mockedGet).toHaveBeenCalledWith("/chatbot/notice/public/")
  })

  it("reads the caller's own turns from the history endpoint", async () => {
    mockedGet.mockResolvedValueOnce({
      data: {
        results: [
          {
            id: "m1",
            message: "Hello",
            reply: "Hi",
            intent: "greeting",
            urgency: "normal",
            severity: "low",
            sensitive: false,
            manual_review: false,
            created_at: "2026-11-13T00:00:00Z",
            flag_id: null,
          },
        ],
      },
    })

    const { result } = renderHook(() => useChatHistory(), {
      wrapper: createWrapper(),
    })

    await waitFor(() => expect(result.current.data).toHaveLength(1))
    expect(mockedGet).toHaveBeenCalledWith("/chatbot/history/")
  })
})

describe("administrator console", () => {
  it("reads the dashboard", async () => {
    mockedGet.mockResolvedValueOnce({
      data: {
        flags: {
          total: 1,
          open: 1,
          unacknowledged: 1,
          manual_review: 0,
          escalated: 0,
          by_severity: [],
          by_status: [],
        },
        messages: { last_7_days: 2, sensitive_last_7_days: 1 },
        keywords: { active: 3, total: 4 },
        acknowledgment: {
          timer_minutes: 15,
          per_severity: {
            critical: 15,
            high: 15,
            medium: 15,
            low: 15,
          },
          average_minutes: null,
        },
        model: {
          configured: false,
          sdk_installed: true,
          model: "gemini-3.8-flash",
          available: false,
        },
        encryption: {
          enabled: true,
          algorithm: "AES-SIV-512",
          key_count: 1,
          active_key_id: "k1",
          error: null,
        },
        false_positives: { total: 0, recent: [] },
      },
    })

    const { result } = renderHook(() => useChatbotDashboard(), {
      wrapper: createWrapper(),
    })

    await waitFor(() => expect(result.current.data?.flags.total).toBe(1))
    expect(mockedGet).toHaveBeenCalledWith("/chatbot/admin/dashboard/")
    // The console has to be able to say whether student text is encrypted.
    expect(result.current.data?.encryption.enabled).toBe(true)
  })
})

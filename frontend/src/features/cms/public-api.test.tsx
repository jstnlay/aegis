import { renderHook, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import type { ReactNode } from "react"
import { beforeEach, describe, expect, it, vi } from "vitest"

import {
  usePublicAnnouncements,
  usePublicResources,
} from "@/features/cms/public-api"
import { fetchAllPages } from "@/lib/pagination"

vi.mock("@/lib/pagination", () => ({
  fetchAllPages: vi.fn(),
}))

const mockedFetchAllPages = vi.mocked(fetchAllPages)

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>
}

/**
 * Regression: the public feed must unwrap the DRF pagination envelope.
 *
 * The first version read `response.data` from the proxy and rendered
 * `items.map(...)` over `{count, next, previous, results}` — which threw
 * `items.map is not a function` the moment a live CMS returned real content
 * and left the landing page as a crash screen. The 502 case never exposed it
 * because it short-circuits into the error branch, so only a live-content
 * run catches this.
 */
describe("public CMS feeds", () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it("returns the paginated results for announcements", async () => {
    mockedFetchAllPages.mockResolvedValue({
      count: 1,
      results: [
        {
          document_id: "doc-1",
          title: "Foundation Day",
          content: "On Friday.",
          announcement_type: "event",
          priority: "normal",
          target_roles: ["all"],
          target_sections: [],
          published_at: "2026-08-01T00:00:00Z",
          expires_at: null,
        },
      ],
    })

    const { result } = renderHook(() => usePublicAnnouncements(), { wrapper })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data).toHaveLength(1)
    expect(result.current.data?.[0]?.title).toBe("Foundation Day")
  })

  it("returns the paginated results for resources", async () => {
    mockedFetchAllPages.mockResolvedValue({
      count: 1,
      results: [
        {
          document_id: "res-1",
          title: "Handbook",
          resource_type: "document",
          target_audience: ["all"],
          is_active: true,
        },
      ],
    })

    const { result } = renderHook(() => usePublicResources(), { wrapper })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data).toHaveLength(1)
    expect(result.current.data?.[0]?.title).toBe("Handbook")
  })
})

import { afterEach, describe, expect, it, vi } from "vitest"

import { apiClient } from "@/lib/api"
import { fetchAllPages } from "@/lib/pagination"
import type { Page } from "@/types/api"

vi.mock("@/lib/api", () => ({
  apiClient: { get: vi.fn() },
}))

const mockedGet = vi.mocked(apiClient.get)

afterEach(() => {
  vi.clearAllMocks()
})

describe("fetchAllPages", () => {
  it("follows absolute `next` URLs and concatenates every page", async () => {
    const pageOne: Page<{ id: string }> = {
      count: 3,
      next: "http://localhost:8000/api/v1/academics/grades/?page=2",
      previous: null,
      results: [{ id: "a" }, { id: "b" }],
    }
    const pageTwo: Page<{ id: string }> = {
      count: 3,
      next: null,
      previous: "http://localhost:8000/api/v1/academics/grades/",
      results: [{ id: "c" }],
    }

    mockedGet
      .mockResolvedValueOnce({ data: pageOne })
      .mockResolvedValueOnce({ data: pageTwo })

    const result = await fetchAllPages<{ id: string }>("/academics/grades/")

    expect(result.results.map((r) => r.id)).toEqual(["a", "b", "c"])
    expect(result.count).toBe(3)
    expect(mockedGet).toHaveBeenNthCalledWith(
      1,
      "/academics/grades/?page_size=100",
      expect.objectContaining({ signal: undefined })
    )
    // The backend-provided absolute `next` URL is requested verbatim — the
    // client must not rewrite a URL the server handed it.
    expect(mockedGet).toHaveBeenNthCalledWith(
      2,
      "http://localhost:8000/api/v1/academics/grades/?page=2",
      expect.anything()
    )
  })

  it("stops when `next` is null and does not silently truncate", async () => {
    mockedGet.mockResolvedValueOnce({
      data: { count: 1, next: null, previous: null, results: [{ id: "only" }] },
    })

    const result = await fetchAllPages<{ id: string }>("/academics/sections/")

    expect(result.results).toHaveLength(1)
    expect(result.count).toBe(1)
    expect(mockedGet).toHaveBeenCalledTimes(1)
  })

  it("preserves the authoritative backend count rather than results.length", async () => {
    mockedGet.mockResolvedValueOnce({
      data: { count: 250, next: null, previous: null, results: [{ id: "x" }] },
    })

    const result = await fetchAllPages<{ id: string }>(
      "/academics/enrollments/"
    )

    expect(result.count).toBe(250)
    expect(result.results).toHaveLength(1)
  })
})

/**
 * The old loop stopped after 100 pages and returned whatever it had. At the
 * paginator's default `page_size` of 20 that is 2,000 records, so any list
 * longer than that was silently truncated while `count` still reported the
 * full total — a caller reading only `results` lost data with no signal.
 */
describe("fetchAllPages pagination limits", () => {
  const MAX_PAGE_SIZE = 100

  it("requests the backend's maximum page size on the first request", async () => {
    mockedGet.mockResolvedValueOnce({
      data: { count: 1, next: null, previous: null, results: [{ id: "a" }] },
    })

    await fetchAllPages<{ id: string }>("/academics/grades/")

    expect(mockedGet).toHaveBeenNthCalledWith(
      1,
      `/academics/grades/?page_size=${MAX_PAGE_SIZE}`,
      expect.anything()
    )
  })

  it("appends page_size with & when the URL already has a query string", async () => {
    mockedGet.mockResolvedValueOnce({
      data: { count: 1, next: null, previous: null, results: [] },
    })

    await fetchAllPages<{ id: string }>("/academics/grades/?status=finalized")

    expect(mockedGet).toHaveBeenNthCalledWith(
      1,
      `/academics/grades/?status=finalized&page_size=${MAX_PAGE_SIZE}`,
      expect.anything()
    )
  })

  it("does not override an explicit page_size the caller asked for", async () => {
    mockedGet.mockResolvedValueOnce({
      data: { count: 1, next: null, previous: null, results: [] },
    })

    await fetchAllPages<{ id: string }>("/academics/grades/?page_size=25")

    expect(mockedGet).toHaveBeenNthCalledWith(
      1,
      "/academics/grades/?page_size=25",
      expect.anything()
    )
  })

  it("does not truncate a list longer than the old 2,000-record ceiling", async () => {
    // 25 pages of 100 = 2,500 records, past the old guard.
    const total = 2500
    mockedGet.mockImplementation(async (url: string) => {
      const page = Number(
        new URL(url, "http://x").searchParams.get("page") ?? 1
      )
      const start = (page - 1) * MAX_PAGE_SIZE
      const size = Math.min(MAX_PAGE_SIZE, total - start)
      return {
        data: {
          count: total,
          next:
            start + size < total
              ? `http://x/api/v1/academics/enrollments/?page=${page + 1}&page_size=${MAX_PAGE_SIZE}`
              : null,
          previous: null,
          results: Array.from({ length: size }, (_, i) => ({
            id: `e${start + i}`,
          })),
        },
      }
    })

    const result = await fetchAllPages<{ id: string }>(
      "/academics/enrollments/"
    )

    expect(result.results).toHaveLength(total)
    expect(result.count).toBe(total)
    expect(mockedGet).toHaveBeenCalledTimes(25)
  })

  it("raises instead of returning a partial list when the page cap is hit", async () => {
    // An endpoint that never returns a null `next` must not hang or, worse,
    // hand back a prefix that looks complete.
    mockedGet.mockResolvedValue({
      data: {
        count: 10_000_000,
        next: "http://x/api/v1/academics/enrollments/?page=2",
        previous: null,
        results: [{ id: "a" }],
      },
    })

    await expect(
      fetchAllPages<{ id: string }>("/academics/enrollments/")
    ).rejects.toThrow(/incomplete list/)
  })
})

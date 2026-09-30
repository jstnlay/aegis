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
      "/academics/grades/",
      expect.objectContaining({ signal: undefined })
    )
    // The backend-provided absolute `next` URL is requested verbatim.
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

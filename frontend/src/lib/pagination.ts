import { apiClient } from "@/lib/api"
import type { Page } from "@/types/api"

/**
 * Fetches every page of a DRF PageNumberPagination list endpoint and
 * returns the concatenated results plus the authoritative total count.
 *
 * The backend paginator (core/pagination.py) envelopes responses as
 * { count, next, previous, results }, and `next` is an absolute URL the
 * client must preserve verbatim. Results are therefore de-duplicated by
 * the endpoint only — callers must do their own Set-based uniqueness.
 */
export async function fetchAllPages<T>(
  url: string,
  opts: { signal?: AbortSignal } = {}
): Promise<{ results: T[]; count: number }> {
  const all: T[] = []
  let next: string | null = url
  let count = 0
  let guard = 0

  while (next && guard < 100) {
    const { data }: { data: Page<T> } = await apiClient.get<Page<T>>(next, {
      signal: opts.signal,
    })
    count = data.count
    all.push(...data.results)
    next = data.next
    guard += 1
  }

  return { results: all, count }
}

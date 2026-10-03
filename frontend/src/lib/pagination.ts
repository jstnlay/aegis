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

/**
 * `StandardResultsPagination.max_page_size`. Requesting the maximum on the
 * first request is what keeps this loop short: at the default `page_size` of
 * 20, even a modest school would need hundreds of round trips per list.
 */
const MAX_PAGE_SIZE = 100

/**
 * Hard ceiling on requests for one logical list.
 *
 * At the maximum page size this is 50,000 records. It exists to stop an
 * endpoint that never returns a null `next` from looping forever — not as a
 * budget. Reaching it means the client *cannot* return a complete list, so it
 * raises instead of quietly handing back a prefix: a truncated roster reads as
 * "these are all the students" and silently hides records. Throwing routes the
 * failure through the same error state every page already renders.
 */
const MAX_PAGES = 500

/** Appends the maximum page size unless the caller already set one. */
function withMaxPageSize(url: string): string {
  if (/[?&]page_size=/.test(url)) return url
  return `${url}${url.includes("?") ? "&" : "?"}page_size=${MAX_PAGE_SIZE}`
}

export async function fetchAllPages<T>(
  url: string,
  opts: { signal?: AbortSignal } = {}
): Promise<{ results: T[]; count: number }> {
  const all: T[] = []
  let next: string | null = withMaxPageSize(url)
  let count = 0
  let pages = 0

  while (next) {
    if (pages >= MAX_PAGES) {
      throw new Error(
        `Stopped after ${MAX_PAGES} pages (${MAX_PAGES * MAX_PAGE_SIZE} records) ` +
          `without reaching the end of the list. Showing every record would ` +
          `require more requests than this client will make, so nothing is ` +
          `shown rather than an incomplete list. Narrow the request with a ` +
          `filter, or add server-side filtering for this endpoint.`
      )
    }

    const { data }: { data: Page<T> } = await apiClient.get<Page<T>>(next, {
      signal: opts.signal,
    })
    count = data.count
    all.push(...data.results)
    next = data.next
    pages += 1
  }

  return { results: all, count }
}

import * as React from "react"

/**
 * Client-side pagination for `DataTable`.
 *
 * Lives in its own module rather than beside the `DataTable` component so that
 * file exports only a component: `react-refresh` cannot fast-refresh a module
 * that mixes a component with a hook, and the rest of `components/ui` keeps
 * the component-only shape that rule exists to protect.
 */

/** Pagination state a `DataTable` renders controls from. */
export interface DataTablePagination {
  /** 1-based page currently shown. */
  page: number
  /** Rows per page. */
  pageSize: number
  /** Total rows available before slicing. */
  totalCount: number
  /** Called with the next 1-based page number. */
  onPageChange: (page: number) => void
}

export interface DataTablePaginationState<T> {
  pagination: DataTablePagination
  /** The slice of `rows` for the current page. */
  pageRows: T[]
  totalPages: number
}

/**
 * Derives pagination props and the current page's slice from a row array.
 *
 * Keeps the page/pageSize bookkeeping out of every caller while leaving the
 * slicing here, so the controls and the visible rows can never disagree about
 * how many rows there are.
 *
 * @param rows        the full filtered result set
 * @param pageSize    rows per page
 * @param resetKey    change this value to return to page 1; pass the active
 *                    filter/search expression. Omit for a list that is never
 *                    filtered.
 */
export function useDataTablePagination<T>(
  rows: readonly T[],
  pageSize = 10,
  resetKey?: string
): DataTablePaginationState<T> {
  const [page, setPage] = React.useState(1)
  const [prevResetKey, setPrevResetKey] = React.useState(resetKey)
  const totalCount = rows.length
  const totalPages = Math.max(1, Math.ceil(totalCount / pageSize))

  // A new filter/search result must not leave the reader stranded on a page
  // that no longer exists. Adjusting state during render (rather than in an
  // effect) is the documented React pattern for resetting derived state: React
  // re-runs this component immediately, before it commits to the DOM.
  if (resetKey !== prevResetKey) {
    setPrevResetKey(resetKey)
    setPage(1)
  }

  // Clamped for the case where the rows shrink without resetKey changing.
  const clampedPage = Math.min(page, totalPages)
  const start = (clampedPage - 1) * pageSize

  return {
    pagination: {
      page: clampedPage,
      pageSize,
      totalCount,
      onPageChange: setPage,
    },
    pageRows: rows.slice(start, start + pageSize),
    totalPages,
  }
}

import * as React from "react"

import {
  EmptyState,
  ErrorNote,
  LoadingState,
} from "@/components/feedback/Feedback"
import { Button } from "@/components/ui/button"
import type { DataTablePagination } from "@/components/ui/data-table-pagination"
import {
  Table,
  TableBody,
  TableCaption,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { cn } from "@/lib/utils"

/**
 * Minimal data table for the PH11.9 Admin and Parent screens.
 *
 * Scope, and why it is this small
 * ------------------------------
 * Every screen that needs a table in this phase renders one of three shapes:
 * a server-paginated list, a fully-fetched list narrowed client-side, or a
 * short two-column key/value block. Those three shapes are all that exist
 * today, so this component covers exactly them. It deliberately has no
 * sorting, no column resizing, no row selection, no inline editing and no
 * generic filter DSL - none of those are required by any screen in PH11.9, and
 * a speculative data-grid abstraction is exactly the kind of thing that rots
 * before it is used.
 *
 * The three list states are first-class parameters rather than something each
 * page reimplements. PH11.7 and PH11.8 each carried a private `ErrorNote` and a
 * private empty branch, and they had already drifted; `@/components/feedback`
 * now owns all three.
 *
 * Rows are keyed by `rowKey`, which the caller supplies. Defaulting to the
 * array index would silently mis-associate rows when a list is re-filtered.
 *
 * Pagination is optional and caller-driven: pass `pagination` to get
 * Previous/Next controls, omit it for a short list that needs none.
 * `useDataTablePagination` in `./data-table-pagination` produces the props.
 */

/** One column. `cell` renders the body; `header` renders the column heading. */
export interface DataTableColumn<T> {
  /** Stable identity for the column, also used as the React key. */
  key: string
  /** Visible column heading. */
  header: React.ReactNode
  /** Body cell content. */
  cell: (row: T) => React.ReactNode
  /** Extra classes for the header cell. */
  headerClassName?: string
  /** Extra classes for every body cell in this column. */
  cellClassName?: string
}

interface DataTableProps<T> {
  /**
   * Accessible name for the table, required so it is never unlabelled.
   *
   * Rendered as a real `<caption>` rather than an `aria-label` on a wrapper,
   * because the caption is what a screen reader announces for the table.
   */
  caption: string
  /** Column definitions. */
  columns: readonly DataTableColumn<T>[]
  /** Rows for the current page. */
  rows: readonly T[]
  /**
   * Stable key per row. Required: an index key would mis-associate rows as
   * soon as the list is filtered or re-ordered.
   */
  rowKey: (row: T, index: number) => string
  /** True while the request is in flight. */
  isLoading?: boolean
  /** Error message to show instead of the table. */
  error?: string | null
  /** Message to show when `rows` is empty. */
  emptyMessage: string
  /** Optional call to action rendered inside the empty state. */
  emptyAction?: React.ReactNode
  /** Optional pagination controls. Omit for a short unpaginated list. */
  pagination?: DataTablePagination
  /** Label for the loading state, announced to assistive technology. */
  loadingLabel?: string
  /** Extra classes for the wrapper. */
  className?: string
}

export function DataTable<T>({
  caption,
  columns,
  rows,
  rowKey,
  isLoading = false,
  error = null,
  emptyMessage,
  emptyAction,
  pagination,
  loadingLabel,
  className,
}: DataTableProps<T>) {
  // A first load shows the loading state. A refetch over rows the reader is
  // already looking at is left to the caller's own indicators, so this returns
  // the table whenever `rows` is non-empty: dropping rows mid-interaction would
  // lose the reader's place, which is worse than a brief staleness.
  if (error) return <ErrorNote message={error} />
  if (isLoading && rows.length === 0)
    return <LoadingState label={loadingLabel} />
  if (rows.length === 0) {
    return <EmptyState message={emptyMessage}>{emptyAction}</EmptyState>
  }

  return (
    <div className={cn("space-y-4", className)}>
      {/*
        The table primitive already wraps the table in `overflow-x-auto`, which
        is the responsive-overflow requirement: below the table's intrinsic
        width the table scrolls inside its own container rather than widening
        the page.
      */}
      <Table>
        <TableCaption className="sr-only">{caption}</TableCaption>
        <TableHeader>
          <TableRow>
            {columns.map((column) => (
              <TableHead
                key={column.key}
                className={column.headerClassName}
                scope="col"
              >
                {column.header}
              </TableHead>
            ))}
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((row, index) => (
            <TableRow key={rowKey(row, index)}>
              {columns.map((column) => (
                <TableCell key={column.key} className={column.cellClassName}>
                  {column.cell(row)}
                </TableCell>
              ))}
            </TableRow>
          ))}
        </TableBody>
      </Table>

      {pagination ? <PaginationControls {...pagination} /> : null}
    </div>
  )
}

function PaginationControls({
  page,
  pageSize,
  totalCount,
  onPageChange,
}: DataTablePagination) {
  const totalPages = Math.max(1, Math.ceil(totalCount / pageSize))
  if (totalPages <= 1) return null

  const firstRow = (page - 1) * pageSize + 1
  const lastRow = Math.min(page * pageSize, totalCount)

  return (
    <div className="flex flex-wrap items-center justify-between gap-3">
      <p className="text-sm text-muted-foreground">
        Showing {firstRow}–{lastRow} of {totalCount}
      </p>
      <div className="flex items-center gap-2">
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => onPageChange(page - 1)}
          disabled={page <= 1}
        >
          Previous
        </Button>
        <span className="text-sm text-muted-foreground">
          Page {page} of {totalPages}
        </span>
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => onPageChange(page + 1)}
          disabled={page >= totalPages}
        >
          Next
        </Button>
      </div>
    </div>
  )
}

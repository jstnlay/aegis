import { useId } from "react"
import * as React from "react"

import {
  EmptyState,
  ErrorNote,
  LoadingState,
} from "@/components/feedback/Feedback"
import { Button } from "@/components/ui/button"
import type { DataTablePagination } from "@/components/ui/data-table-pagination"
import {
  ariaSortFor,
  nextSortState,
  type DataTableSort,
} from "@/components/ui/data-table-sort"
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
 * Data table for the list screens, built in PH11.9 and extended in PH11.10.
 *
 * Scope, and why it is this small
 * ------------------------------
 * Every screen that needs a table renders one of three shapes: a paginated
 * list endpoint, a fully-fetched list narrowed client-side, or a short
 * two-column key/value block. Those three shapes are all that exist today, so
 * this component covers exactly them. It deliberately has no column resizing,
 * no row selection, no inline editing and no generic filter DSL - none of those
 * are required by any screen, and a speculative data-grid abstraction is
 * exactly the kind of thing that rots before it is used.
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
 *
 * PH11.10 added two things, both opt-in because neither suits every table:
 *
 * - **Sorting.** A column opts in by supplying `sortValue`. A column without
 *   one renders a plain, non-interactive heading. This is client-side sorting
 *   over rows the caller has already fetched, not server-side: the viewset
 *   behind these lists declares no `ordering` filter backend, so there is
 *   nothing to send. See `./data-table-sort`.
 * - **A page-size control.** Only rendered when `pageSizeOptions` is supplied,
 *   which callers do for lists long enough for the choice to be worth making.
 */

/** One column. `cell` renders the body; `header` renders the column heading. */
export interface DataTableColumn<T> {
  /** Stable identity for the column, also used as the React key. */
  key: string
  /** Visible column heading. */
  header: React.ReactNode
  /** Body cell content. */
  cell: (row: T) => React.ReactNode
  /**
   * The value this column sorts by, which opts it into sorting.
   *
   * Return `null` for "no value" — a missing score, an absent date — so it
   * sinks to the bottom in either direction rather than being treated as zero
   * or as the empty string. Omit this entirely for a column that should not be
   * sortable, such as one holding a row action.
   */
  sortValue?: (row: T) => string | number | boolean | Date | null | undefined
  /**
   * A second value consulted only when two rows tie on `sortValue`.
   *
   * Without it, re-sorting can leave equal rows in a different relative order
   * from the one the reader was already looking at.
   */
  sortTieBreak?: (row: T) => string | number | null | undefined
  /** Extra classes for the header cell. */
  headerClassName?: string
  /**
   * Extra classes for every body cell in this column.
   *
   * Cells wrap by default since PH11.11. Pass `"whitespace-nowrap"` here for a
   * column whose values must stay on one line — a code, a date, a short status —
   * and `"whitespace-normal align-top min-w-[16rem]"` for one holding free text,
   * which is the case that used to force a table wider than the screen.
   */
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
  /**
   * Extra attributes for a row's `<tr>`, for state the reader needs to be able
   * to see or assert beyond the cell contents — a `data-` attribute marking a
   * row's status, say. Use sparingly.
   *
   * Typed as a record rather than `<tr>`'s own props because the useful cases
   * are all `data-*` attributes, which that props type does not admit.
   */
  rowProps?: (row: T) => Record<string, string> | undefined
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
  /**
   * Current sort, or null for unsorted. Managed by the caller so the sort can
   * be combined with that caller's own filtering.
   */
  sort?: DataTableSort | null
  /** Called when a sortable column heading is activated. */
  onSortChange?: (sort: DataTableSort) => void
  /**
   * Page sizes the reader may choose, in addition to the current one.
   *
   * Omit for a short list: a control that only ever offers the size already in
   * use is noise. The caller receives the choice through
   * `onPageSizeChange`.
   */
  pageSizeOptions?: readonly number[]
  /** Called when the reader picks a different page size. */
  onPageSizeChange?: (pageSize: number) => void
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
  rowProps,
  isLoading = false,
  error = null,
  emptyMessage,
  emptyAction,
  pagination,
  sort = null,
  onSortChange,
  pageSizeOptions,
  onPageSizeChange,
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
        the page. PH11.2 §12.4 requires that behaviour explicitly. `scrollLabel`
        additionally makes that container focusable and named, so the overflow is
        reachable from the keyboard rather than only by dragging.
      */}
      <Table scrollLabel={caption}>
        <TableCaption className="sr-only">{caption}</TableCaption>
        <TableHeader>
          <TableRow>
            {columns.map((column) => {
              const sortable = column.sortValue !== undefined
              return (
                <TableHead
                  key={column.key}
                  className={cn(column.headerClassName, sortable && "p-0")}
                  scope="col"
                  aria-sort={ariaSortFor(sort, column.key)}
                >
                  {sortable ? (
                    <SortableHeading
                      column={column}
                      sort={sort}
                      onSortChange={onSortChange}
                    >
                      {column.header}
                    </SortableHeading>
                  ) : (
                    column.header
                  )}
                </TableHead>
              )
            })}
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((row, index) => (
            <TableRow key={rowKey(row, index)} {...(rowProps?.(row) ?? {})}>
              {columns.map((column) => (
                <TableCell key={column.key} className={column.cellClassName}>
                  {column.cell(row)}
                </TableCell>
              ))}
            </TableRow>
          ))}
        </TableBody>
      </Table>

      {pagination ? (
        <PaginationControls
          {...pagination}
          pageSizeOptions={pageSizeOptions}
          onPageSizeChange={onPageSizeChange}
        />
      ) : null}
    </div>
  )
}

/**
 * A column heading that sorts when activated.
 *
 * A real `<button>` inside the `<th>` rather than a click handler on the `th`
 * itself, so it is reachable by keyboard and announced as a button. `aria-sort`
 * lives on the `<th>`, which is where the table semantics expect it; the button
 * carries the label and the direction hint.
 */
function SortableHeading<T>({
  column,
  sort,
  onSortChange,
  children,
}: {
  column: DataTableColumn<T>
  sort: DataTableSort | null
  onSortChange?: (sort: DataTableSort) => void
  children: React.ReactNode
}) {
  const active = sort?.key === column.key
  const ascending = active && sort.direction === "asc"

  const hint = active
    ? ascending
      ? "sorted ascending"
      : "sorted descending"
    : "not sorted"

  return (
    <button
      type="button"
      className="flex h-10 w-full items-center gap-1.5 px-3 text-left font-semibold hover:bg-muted/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      disabled={!onSortChange}
      onClick={() => onSortChange?.(nextSortState(sort, column.key))}
    >
      <span className="truncate">{children}</span>
      {/*
        The glyph is decorative: the state is already carried by `aria-sort` on
        the header cell and by the visually-hidden hint below, so colour and
        shape are never the only signal.
      */}
      <span aria-hidden="true" className="text-muted-foreground">
        {active ? (ascending ? "▲" : "▼") : "↕"}
      </span>
      <span className="sr-only">{hint}</span>
    </button>
  )
}

function PaginationControls({
  page,
  pageSize,
  totalCount,
  onPageChange,
  pageSizeOptions,
  onPageSizeChange,
}: DataTablePagination & {
  pageSizeOptions?: readonly number[]
  onPageSizeChange?: (pageSize: number) => void
}) {
  const totalPages = Math.max(1, Math.ceil(totalCount / pageSize))

  const firstRow = (page - 1) * pageSize + 1
  const lastRow = Math.min(page * pageSize, totalCount)

  // The size control appears only when the caller offered more than the size
  // already in use, and only once there is enough to page through.
  const sizes = (pageSizeOptions ?? []).filter((size) => size !== pageSize)
  const showPageSize = totalPages > 1 && sizes.length > 0 && onPageSizeChange

  /*
   * `useId`, not the row count. PH11.9 derived this from `totalCount` and
   * claimed the row count was unique per rendered table; it is not. Two tables
   * on one screen with the same number of rows produced the same `<label for>`
   * and the same `<select id>`, and every `<label>` then resolved to the first
   * table's control. `useId` is per-instance, which is the property actually
   * required, so no caller can collide with another.
   *
   * Called before the early return below, because a hook may not be called
   * conditionally: the control is simply not rendered when there is one page,
   * but the hook still has to run on every render of this component.
   */
  const pageSizeId = `${useId()}-page-size`

  if (totalPages <= 1) return null

  return (
    <div className="flex flex-wrap items-center justify-between gap-3">
      {/*
        The range summary is the polite live region for the whole control: it is
        the one place that states what changed when the reader pages, changes the
        page size, or a sort reorders the rows. Without it the table silently
        mutates underneath a screen reader. `aria-live="polite"` rather than
        `role="status"` on the container, so the region exists before the text
        changes and is therefore reliably announced.
      */}
      <p aria-live="polite" className="text-sm text-muted-foreground">
        Showing {firstRow}–{lastRow} of {totalCount}
      </p>
      <div className="flex flex-wrap items-center gap-2">
        {showPageSize ? (
          <>
            <label
              htmlFor={pageSizeId}
              className="text-sm text-muted-foreground"
            >
              Rows per page
            </label>
            <select
              id={pageSizeId}
              value={pageSize}
              onChange={(event) => onPageSizeChange(Number(event.target.value))}
              className="h-8 rounded-md border border-input bg-background px-2 text-sm"
            >
              {/*
                The current size is always offered, so the select's value always
                matches an option after a change.
              */}
              <option value={pageSize}>{pageSize}</option>
              {sizes.map((size) => (
                <option key={size} value={size}>
                  {size}
                </option>
              ))}
            </select>
          </>
        ) : null}
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

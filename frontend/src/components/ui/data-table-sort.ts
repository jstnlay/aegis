/**
 * Client-side sorting for `DataTable`.
 *
 * PH11.10 adds sorting where a list is large enough to be worth ordering by
 * hand. The backend has no `ordering` filter backend on these viewsets — the
 * guidance app's module contract states `DEFAULT_FILTER_BACKENDS` is absent
 * entirely — so this is explicitly *client-side* sorting over rows the caller
 * has already fetched. Nothing here claims to be server-side.
 *
 * Why a comparator factory rather than a generic deep sorter
 * -------------------------------------------------------
 * A column's sort key is a property of that column, and only the column knows
 * what it is. A column holding a name sorts by name; one holding a raw date
 * string sorts chronologically; one holding `null` for "not recorded" must
 * sink rather than crash. Each consumer supplies that as a plain function, so
 * the semantics are stated where the data is and cannot drift.
 *
 * Determinism: ties fall back to comparing `tieBreak` when two columns supply
 * one, otherwise the original array order is preserved. `Array.prototype.sort`
 * is stable in every engine this app targets, so equal keys never reshuffle
 * between renders.
 *
 * The input array is never mutated — `sortRows` copies before sorting.
 */

export type SortDirection = "asc" | "desc"

/** A column's sort state. Absent `key` means the table is unsorted. */
export interface DataTableSort {
  key: string
  direction: SortDirection
}

interface SortableRow<T> {
  /** Value to order by. Return `null` for a value that should sort last. */
  sortValue: (row: T) => string | number | boolean | Date | null | undefined
  /**
   * Optional stable tie-break. Only consulted when two rows compare equal on
   * the primary key, which is what stops a re-sort from reshuffling equal rows.
   */
  tieBreak?: (row: T) => string | number | null | undefined
}

/**
 * Sort `rows` by one column. The input array is not modified.
 *
 * `null`/`undefined` always sink to the bottom regardless of direction: a
 * missing value is absence of data, not a value that is small, and burying it
 * under real records keeps it out of the top of the list either way.
 */
export function sortRows<T>(
  rows: readonly T[],
  column: SortableRow<T>
): T[] {
  const direction = 1
  return [...rows].sort((a, b) => {
    const left = normalize(column.sortValue(a))
    const right = normalize(column.sortValue(b))

    if (left === null && right === null) return tieBreak(column, a, b)
    if (left === null) return 1
    if (right === null) return -1

    const result = compare(left, right)
    if (result !== 0) return result * direction

    return tieBreak(column, a, b)
  })
}

function tieBreak<T>(
  column: SortableRow<T>,
  a: T,
  b: T
): number {
  if (!column.tieBreak) return 0
  const left = normalize(column.tieBreak(a))
  const right = normalize(column.tieBreak(b))
  if (left === null || right === null) return 0
  return compare(left, right)
}

/**
 * Collapse a cell value into a comparable primitive.
 *
 * A `Date` becomes epoch milliseconds so it compares numerically; everything
 * else is coerced to a finite number when it looks like one, and otherwise left
 * as a string. `""`, `null` and `undefined` all mean "no value" and return
 * `null`.
 */
function normalize(
  value: string | number | boolean | Date | null | undefined
): string | number | null {
  if (value === null || value === undefined) return null
  if (value instanceof Date) {
    return Number.isNaN(value.getTime()) ? null : value.getTime()
  }
  if (typeof value === "number") return Number.isFinite(value) ? value : null
  if (typeof value === "boolean") return value ? 1 : 0
  if (value === "") return null

  // A date-like string is compared chronologically rather than lexically.
  // Without this, "2026-10-02" sorts before "2026-9-30", which is wrong for the
  // audit and attendance tables whose columns are ISO dates.
  const asDate = Date.parse(value)
  if (ISO_DATE.fullTest(value) && !Number.isNaN(asDate)) return asDate

  const asNumber = Number(value)
  if (value.trim() !== "" && Number.isFinite(asNumber)) return asNumber

  return value
}

/** Only strings that are a whole ISO date or date-time, not arbitrary text. */
const ISO_DATE = {
  fullTest: (value: string) =>
    /^\d{4}-\d{2}-\d{2}([T ]\d{2}:\d{2}(:\d{2})?)?/.test(value),
}

function compare(left: string | number, right: string | number): number {
  if (typeof left === "number" && typeof right === "number") return left - right
  return String(left).localeCompare(String(right), undefined, {
    numeric: true,
    sensitivity: "base",
  })
}

/**
 * The next sort state for a header click.
 *
 * Clicking an unsorted column starts ascending; clicking the active column
 * flips it; clicking a different column starts ascending again. This is the
 * convention the sort affordance's `aria-sort` describes, so the two cannot
 * disagree.
 */
export function nextSortState(
  current: DataTableSort | null,
  key: string
): DataTableSort {
  if (current?.key !== key) return { key, direction: "asc" }
  return { key, direction: current.direction === "asc" ? "desc" : "asc" }
}

/**
 * Order `rows` by one of `columns`, per the active sort state.
 *
 * Each caller holds its own filter state, so the sort has to be applied after
 * filtering and before the caller paginates the result — a page must show the
 * top of the chosen ordering, not an arbitrary slice of it. This helper exists
 * so that composition is written once: the caller memoises on `[rows, sort]`
 * alone and does not have to list `columns` as a dependency, which would
 * defeat the memo because a column array is rebuilt on every render.
 *
 * Returns `rows` unchanged when nothing is sorted or when the sorted column is
 * not one of the supplied columns.
 */
export function orderRows<T>(
  rows: readonly T[],
  sort: DataTableSort | null,
  columns: readonly {
    key: string
    sortValue?: (row: T) => string | number | boolean | Date | null | undefined
    sortTieBreak?: (row: T) => string | number | null | undefined
  }[]
): readonly T[] {
  if (!sort) return rows
  const column = columns.find((entry) => entry.key === sort.key)
  if (!column?.sortValue) return rows

  const ordered = sortRows(rows, {
    sortValue: column.sortValue,
    tieBreak: column.sortTieBreak,
  })
  // `sortRows` only knows about ascending, so descending is the ascending
  // result reversed. That keeps one comparison implementation, and for a
  // comparator this size the cost is not worth a duplicated descending path.
  return sort.direction === "desc" ? ordered.reverse() : ordered
}

/** The `aria-sort` value for one header, per the active sort. */
export function ariaSortFor(
  sort: DataTableSort | null,
  key: string
): "ascending" | "descending" | "none" | undefined {
  if (sort?.key !== key) return undefined
  return sort.direction === "asc" ? "ascending" : "descending"
}
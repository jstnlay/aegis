import { fireEvent, render, screen, within } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

import { DataTable, type DataTableColumn } from "@/components/ui/data-table"
import { useDataTablePagination } from "@/components/ui/data-table-pagination"

interface Row {
  id: string
  code: string
  name: string
}

const ROWS: Row[] = [
  { id: "r1", code: "S-001", name: "Ana Reyes" },
  { id: "r2", code: "S-002", name: "Ben Cruz" },
  { id: "r3", code: "S-003", name: "Cara Diaz" },
]

const COLUMNS: readonly DataTableColumn<Row>[] = [
  { key: "code", header: "Code", cell: (row) => row.code },
  { key: "name", header: "Name", cell: (row) => row.name },
]

const rowKey = (row: Row) => row.id

describe("DataTable", () => {
  it("renders a caption, one header cell per column and one row per record", () => {
    render(
      <DataTable
        caption="Students"
        columns={COLUMNS}
        rows={ROWS}
        rowKey={rowKey}
        emptyMessage="No students"
      />
    )

    expect(screen.getByRole("table", { name: "Students" })).toBeInTheDocument()

    const [headerRow] = screen.getAllByRole("row")
    const headers = within(headerRow!).getAllByRole("columnheader")
    expect(headers).toHaveLength(2)
    expect(headers[0]).toHaveTextContent("Code")
    expect(headers[1]).toHaveTextContent("Name")
  })

  it("renders the caption as a real caption element", () => {
    const { container } = render(
      <DataTable
        caption="Students"
        columns={COLUMNS}
        rows={ROWS}
        rowKey={rowKey}
        emptyMessage="No students"
      />
    )

    const caption = container.querySelector("caption")
    expect(caption).not.toBeNull()
    expect(caption).toHaveTextContent("Students")
    // Visually hidden: the surrounding card already names the table, so the
    // caption exists for assistive technology only.
    expect(caption?.className).toContain("sr-only")
  })

  it("shows the caption text in the rendered markup", () => {
    render(
      <DataTable
        caption="Students"
        columns={COLUMNS}
        rows={ROWS}
        rowKey={rowKey}
        emptyMessage="No students"
      />
    )

    expect(screen.getByText("Students")).toBeInTheDocument()

    // 1 header row + 3 body rows. A <caption> is not a row.
    expect(screen.getAllByRole("row")).toHaveLength(4)
    expect(screen.getByText("Ana Reyes")).toBeInTheDocument()
    expect(screen.getByText("S-003")).toBeInTheDocument()
  })

  it("exposes the column headers as real column headers for screen readers", () => {
    render(
      <DataTable
        caption="Students"
        columns={COLUMNS}
        rows={ROWS}
        rowKey={rowKey}
        emptyMessage="No students"
      />
    )

    for (const header of screen.getAllByRole("columnheader")) {
      expect(header).toHaveAttribute("scope", "col")
    }
  })

  it("shows the loading state on a first load, when there are no rows yet", () => {
    render(
      <DataTable
        caption="Students"
        columns={COLUMNS}
        rows={[]}
        rowKey={rowKey}
        isLoading
        loadingLabel="Loading students"
        emptyMessage="No students"
      />
    )

    expect(screen.queryByRole("table")).not.toBeInTheDocument()
    const status = screen.getByRole("status")
    expect(status).toHaveAttribute("aria-busy", "true")
    expect(status).toHaveTextContent("Loading students")
  })

  it("keeps existing rows on screen during a refetch", () => {
    /*
     * A refetch over rows the reader is already looking at must not replace
     * the table with a spinner: that discards their place and any row they had
     * expanded. The caller decides how to signal staleness.
     */
    render(
      <DataTable
        caption="Students"
        columns={COLUMNS}
        rows={ROWS}
        rowKey={rowKey}
        isLoading
        emptyMessage="No students"
      />
    )

    expect(screen.getByRole("table", { name: "Students" })).toBeInTheDocument()
    expect(screen.getByText("Ana Reyes")).toBeInTheDocument()
    expect(screen.queryByRole("status")).not.toBeInTheDocument()
  })

  it("does not show the empty state while loading an empty result", () => {
    render(
      <DataTable
        caption="Students"
        columns={COLUMNS}
        rows={[]}
        rowKey={rowKey}
        isLoading
        emptyMessage="No students"
      />
    )

    expect(screen.queryByText("No students")).not.toBeInTheDocument()
    expect(screen.getByRole("status")).toBeInTheDocument()
  })

  it("shows an empty state, not an error, when there are no rows", () => {
    render(
      <DataTable
        caption="Students"
        columns={COLUMNS}
        rows={[]}
        rowKey={rowKey}
        emptyMessage="No students enrolled"
      />
    )

    expect(screen.queryByRole("table")).not.toBeInTheDocument()
    expect(screen.queryByRole("alert")).not.toBeInTheDocument()
    expect(screen.getByText("No students enrolled")).toBeInTheDocument()
  })

  it("renders the empty action alongside the empty message", () => {
    render(
      <DataTable
        caption="Students"
        columns={COLUMNS}
        rows={[]}
        rowKey={rowKey}
        emptyMessage="No students enrolled"
        emptyAction={<button type="button">Try again</button>}
      />
    )

    expect(
      screen.getByRole("button", { name: "Try again" })
    ).toBeInTheDocument()
  })

  it("announces the error and suppresses the table when the request failed", () => {
    render(
      <DataTable
        caption="Students"
        columns={COLUMNS}
        rows={ROWS}
        rowKey={rowKey}
        error="Unable to load students."
        emptyMessage="No students"
      />
    )

    expect(screen.queryByRole("table")).not.toBeInTheDocument()
    const alert = screen.getByRole("alert")
    expect(alert).toHaveTextContent("Unable to load students.")
  })

  it("prefers the error over the empty state", () => {
    render(
      <DataTable
        caption="Students"
        columns={COLUMNS}
        rows={[]}
        rowKey={rowKey}
        error="Unable to load students."
        emptyMessage="No students"
      />
    )

    expect(screen.getByRole("alert")).toBeInTheDocument()
    expect(screen.queryByText("No students")).not.toBeInTheDocument()
  })

  it("renders each column's cell for every row", () => {
    const columns: readonly DataTableColumn<Row>[] = [
      ...COLUMNS,
      {
        key: "label",
        header: "Badge",
        cell: (row) => <span>row-{row.id}</span>,
      },
    ]

    render(
      <DataTable
        caption="Students"
        columns={columns}
        rows={ROWS}
        rowKey={rowKey}
        emptyMessage="No students"
      />
    )

    expect(screen.getByText("row-r1")).toBeInTheDocument()
    expect(screen.getByText("row-r2")).toBeInTheDocument()
    expect(screen.getByText("row-r3")).toBeInTheDocument()
  })

  it("gives each row a distinct accessible key derived from rowKey", () => {
    const { container } = render(
      <DataTable
        caption="Students"
        columns={COLUMNS}
        rows={ROWS}
        rowKey={rowKey}
        emptyMessage="No students"
      />
    )

    const bodyRows = container.querySelectorAll("tbody tr")
    expect(bodyRows).toHaveLength(3)
    // React writes no key attribute, so assert identity through the rendered
    // cell content instead: an index key would still render this text, but a
    // duplicate-keyed row would collapse to fewer rows, which the count covers.
    expect(bodyRows[0]).toHaveTextContent("S-001")
    expect(bodyRows[2]).toHaveTextContent("S-003")
  })

  it("wraps the table so wide content scrolls instead of widening the page", () => {
    const { container } = render(
      <DataTable
        caption="Students"
        columns={COLUMNS}
        rows={ROWS}
        rowKey={rowKey}
        emptyMessage="No students"
      />
    )

    const scroller = container.querySelector('[data-slot="table-container"]')
    expect(scroller).not.toBeNull()
    expect(scroller?.className).toContain("overflow-x-auto")
  })

  it("omits pagination controls when no pagination is supplied", () => {
    render(
      <DataTable
        caption="Students"
        columns={COLUMNS}
        rows={ROWS}
        rowKey={rowKey}
        emptyMessage="No students"
      />
    )

    expect(
      screen.queryByRole("button", { name: "Next" })
    ).not.toBeInTheDocument()
  })

  it("renders pagination controls and reports the visible range", () => {
    render(
      <DataTable
        caption="Students"
        columns={COLUMNS}
        rows={ROWS}
        rowKey={rowKey}
        emptyMessage="No students"
        pagination={{
          page: 1,
          pageSize: 2,
          totalCount: 5,
          onPageChange: vi.fn(),
        }}
      />
    )

    expect(screen.getByText("Showing 1–2 of 5")).toBeInTheDocument()
    expect(screen.getByText("Page 1 of 3")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Previous" })).toBeDisabled()
    expect(screen.getByRole("button", { name: "Next" })).toBeEnabled()
  })

  it("disables Next on the final page", () => {
    render(
      <DataTable
        caption="Students"
        columns={COLUMNS}
        rows={ROWS}
        rowKey={rowKey}
        emptyMessage="No students"
        pagination={{
          page: 3,
          pageSize: 2,
          totalCount: 5,
          onPageChange: vi.fn(),
        }}
      />
    )

    expect(screen.getByText("Showing 5–5 of 5")).toBeInTheDocument()
    expect(screen.getByText("Page 3 of 3")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Next" })).toBeDisabled()
    expect(screen.getByRole("button", { name: "Previous" })).toBeEnabled()
  })

  it("hides pagination controls when everything fits on one page", () => {
    render(
      <DataTable
        caption="Students"
        columns={COLUMNS}
        rows={ROWS}
        rowKey={rowKey}
        emptyMessage="No students"
        pagination={{
          page: 1,
          pageSize: 10,
          totalCount: 3,
          onPageChange: vi.fn(),
        }}
      />
    )

    expect(
      screen.queryByRole("button", { name: "Next" })
    ).not.toBeInTheDocument()
  })

  it("calls onPageChange with the adjacent page number", () => {
    const onPageChange = vi.fn()

    render(
      <DataTable
        caption="Students"
        columns={COLUMNS}
        rows={ROWS}
        rowKey={rowKey}
        emptyMessage="No students"
        pagination={{
          page: 2,
          pageSize: 2,
          totalCount: 6,
          onPageChange,
        }}
      />
    )

    fireEvent.click(screen.getByRole("button", { name: "Next" }))
    expect(onPageChange).toHaveBeenCalledWith(3)

    fireEvent.click(screen.getByRole("button", { name: "Previous" }))
    expect(onPageChange).toHaveBeenCalledWith(1)
  })
})

describe("useDataTablePagination", () => {
  function Harness({
    rows,
    pageSize,
    resetKey,
  }: {
    rows: Row[]
    pageSize: number
    resetKey?: string
  }) {
    const { pagination, pageRows, totalPages } = useDataTablePagination(
      rows,
      pageSize,
      resetKey
    )

    return (
      <div>
        <p data-testid="range">
          {pagination.page} / {totalPages}
        </p>
        <ul>
          {pageRows.map((row) => (
            <li key={row.id}>{row.code}</li>
          ))}
        </ul>
        <button type="button" onClick={() => pagination.onPageChange(2)}>
          Go 2
        </button>
      </div>
    )
  }

  it("slices rows to the requested page size", () => {
    render(<Harness rows={ROWS} pageSize={2} />)

    expect(screen.getByText("S-001")).toBeInTheDocument()
    expect(screen.getByText("S-002")).toBeInTheDocument()
    expect(screen.queryByText("S-003")).not.toBeInTheDocument()
    expect(screen.getByTestId("range")).toHaveTextContent("1 / 2")
  })

  it("returns the remainder on the final page", () => {
    render(<Harness rows={ROWS} pageSize={2} />)

    fireEvent.click(screen.getByRole("button", { name: "Go 2" }))

    expect(screen.getByText("S-003")).toBeInTheDocument()
    expect(screen.queryByText("S-001")).not.toBeInTheDocument()
    expect(screen.getByTestId("range")).toHaveTextContent("2 / 2")
  })

  it("reports one page when there are no rows", () => {
    render(<Harness rows={[]} pageSize={10} />)
    expect(screen.getByTestId("range")).toHaveTextContent("1 / 1")
  })

  it("returns to page 1 when the filter key changes", () => {
    const { rerender } = render(
      <Harness rows={ROWS} pageSize={2} resetKey="all" />
    )

    fireEvent.click(screen.getByRole("button", { name: "Go 2" }))
    expect(screen.getByTestId("range")).toHaveTextContent("2 / 2")

    rerender(<Harness rows={ROWS} pageSize={2} resetKey="filtered" />)

    expect(screen.getByTestId("range")).toHaveTextContent("1 / 2")
  })

  it("clamps a page that no longer exists after rows shrink", () => {
    const { rerender } = render(
      <Harness rows={ROWS} pageSize={2} resetKey="all" />
    )

    fireEvent.click(screen.getByRole("button", { name: "Go 2" }))
    expect(screen.getByTestId("range")).toHaveTextContent("2 / 2")

    const onlyRow = ROWS[0]!
    rerender(<Harness rows={[onlyRow]} pageSize={2} resetKey="all" />)

    expect(screen.getByTestId("range")).toHaveTextContent("1 / 1")
    expect(screen.getByText("S-001")).toBeInTheDocument()
  })
})

describe("DataTable state precedence", () => {
  function Stateful({
    phase,
  }: {
    phase: "loading" | "error" | "empty" | "ready"
  }) {
    if (phase === "loading") {
      return (
        <DataTable
          caption="Students"
          columns={COLUMNS}
          rows={[]}
          rowKey={rowKey}
          isLoading
          emptyMessage="No students"
        />
      )
    }
    if (phase === "error") {
      return (
        <DataTable
          caption="Students"
          columns={COLUMNS}
          rows={ROWS}
          rowKey={rowKey}
          error="Request failed."
          emptyMessage="No students"
        />
      )
    }
    if (phase === "empty") {
      return (
        <DataTable
          caption="Students"
          columns={COLUMNS}
          rows={[]}
          rowKey={rowKey}
          emptyMessage="No students"
        />
      )
    }
    return (
      <DataTable
        caption="Students"
        columns={COLUMNS}
        rows={ROWS}
        rowKey={rowKey}
        emptyMessage="No students"
      />
    )
  }

  it("shows exactly one state, and never two", () => {
    // Each phase must be distinguishable by role alone, so a screen reader
    // hears exactly one thing: a busy region, an alert, or the table.
    //
    // PH11.11 added `role="status"` to `EmptyState`, so "empty" now reports one
    // status region where it previously reported none. The invariant this suite
    // protects is unchanged and still exact: one state per phase, and the three
    // states remain distinguishable — loading and empty are polite `status`,
    // error is the interrupting `alert`.
    const observed = (phase: "loading" | "error" | "empty" | "ready") => {
      const { unmount } = render(<Stateful phase={phase} />)
      const snapshot = {
        status: screen.queryAllByRole("status").length,
        alert: screen.queryAllByRole("alert").length,
        table: screen.queryAllByRole("table").length,
        emptyText: screen.queryAllByText("No students").length,
      }
      unmount()
      return snapshot
    }

    expect(observed("loading")).toEqual({
      status: 1,
      alert: 0,
      table: 0,
      emptyText: 0,
    })
    expect(observed("error")).toEqual({
      status: 0,
      alert: 1,
      table: 0,
      emptyText: 0,
    })
    expect(observed("empty")).toEqual({
      status: 1,
      alert: 0,
      table: 0,
      emptyText: 1,
    })
    expect(observed("ready")).toEqual({
      status: 0,
      alert: 0,
      table: 1,
      emptyText: 0,
    })
  })

  it("never renders an empty state as an error", () => {
    // The claim being protected is that an empty result is not a failure. The
    // empty state announces politely via `status`; only a failure announces via
    // `alert`, and the two are never both present.
    render(<Stateful phase="empty" />)

    expect(screen.queryAllByRole("alert")).toHaveLength(0)
    expect(screen.queryAllByRole("status")).toHaveLength(1)
  })
})

/**
 * PH11.10 additions: client-side sorting and the page-size control.
 *
 * Sorting is asserted through what a reader sees — the order of the rendered
 * rows and the `aria-sort` state — rather than by inspecting internals, because
 * those are the two things that can disagree and produce a table that claims
 * one order while showing another.
 */
describe("DataTable sorting", () => {
  interface SortableRow {
    id: string
    name: string
    score: number
  }

  const SORTABLE: SortableRow[] = [
    { id: "s1", name: "Cara", score: 9 },
    { id: "s2", name: "Ana", score: 100 },
    { id: "s3", name: "Bea", score: 10 },
  ]

  const SORTABLE_COLUMNS: readonly DataTableColumn<SortableRow>[] = [
    {
      key: "name",
      header: "Name",
      sortValue: (row) => row.name,
      cell: (row) => row.name,
    },
    {
      key: "score",
      header: "Score",
      sortValue: (row) => row.score,
      cell: (row) => row.score,
    },
    // No sortValue: must stay a plain, non-interactive heading.
    { key: "actions", header: "Actions", cell: (row) => row.id },
  ]

  const sortableRowKey = (row: SortableRow) => row.id

  function renderSortable(props: {
    sort?: { key: string; direction: "asc" | "desc" } | null
    onSortChange?: (sort: { key: string; direction: "asc" | "desc" }) => void
  }) {
    return render(
      <DataTable
        caption="Sortable"
        columns={SORTABLE_COLUMNS}
        rows={SORTABLE}
        rowKey={sortableRowKey}
        emptyMessage="Nothing"
        sort={props.sort ?? null}
        onSortChange={props.onSortChange ?? vi.fn()}
      />
    )
  }

  function renderedNames(): (string | null | undefined)[] {
    return screen
      .getAllByRole("row")
      .slice(1)
      .map((row) => within(row).getAllByRole("cell")[0]?.textContent)
  }

  it("leaves a table unsorted until a column is chosen", () => {
    renderSortable({})

    // The caller owns the ordering, so with no sort state the rows render as
    // supplied.
    expect(renderedNames()).toEqual(["Cara", "Ana", "Bea"])
  })

  it("reports a click on a sortable heading and leaves others inert", () => {
    const onSortChange = vi.fn()
    renderSortable({ onSortChange })

    // Only the two columns with a sortValue render a button.
    const buttons = screen.getAllByRole("button")
    expect(buttons).toHaveLength(2)
    expect(buttons[0]).toHaveTextContent("Name")
    expect(buttons[1]).toHaveTextContent("Score")

    // The actions column has no sortValue, so its heading is plain text.
    const actionsHeader = screen.getAllByRole("columnheader")[2]!
    expect(actionsHeader).toHaveTextContent("Actions")
    expect(actionsHeader.querySelector("button")).toBeNull()

    fireEvent.click(buttons[1]!)
    expect(onSortChange).toHaveBeenCalledWith({
      key: "score",
      direction: "asc",
    })
  })

  it("asks for the opposite direction on a second click of the same column", () => {
    const onSortChange = vi.fn()
    renderSortable({ sort: { key: "score", direction: "asc" }, onSortChange })

    fireEvent.click(screen.getByRole("button", { name: /Score/ }))
    expect(onSortChange).toHaveBeenCalledWith({
      key: "score",
      direction: "desc",
    })
  })

  it("starts a different column ascending", () => {
    const onSortChange = vi.fn()
    renderSortable({ sort: { key: "score", direction: "desc" }, onSortChange })

    fireEvent.click(screen.getByRole("button", { name: /Name/ }))
    expect(onSortChange).toHaveBeenCalledWith({
      key: "name",
      direction: "asc",
    })
  })

  it("marks only the active header with aria-sort", () => {
    renderSortable({ sort: { key: "name", direction: "asc" } })

    const headers = screen.getAllByRole("columnheader")
    expect(headers[0]).toHaveAttribute("aria-sort", "ascending")
    expect(headers[1]).not.toHaveAttribute("aria-sort")
    expect(headers[2]).not.toHaveAttribute("aria-sort")
  })

  it("reports a descending active header", () => {
    renderSortable({ sort: { key: "score", direction: "desc" } })

    const headers = screen.getAllByRole("columnheader")
    expect(headers[1]).toHaveAttribute("aria-sort", "descending")
  })

  it("states the direction in text as well as in the attribute", () => {
    renderSortable({ sort: { key: "name", direction: "desc" } })

    // Colour and a glyph are not the only signal.
    expect(
      screen.getByRole("button", { name: /sorted descending/i })
    ).toBeInTheDocument()
  })

  it("renders rows in the order the caller computed", () => {
    // The caller owns the sort, so this pins that the table renders what it is
    // given rather than imposing an order of its own.
    const sorted = [...SORTABLE].sort((a, b) => a.score - b.score)
    render(
      <DataTable
        caption="Sortable"
        columns={SORTABLE_COLUMNS}
        rows={sorted}
        rowKey={sortableRowKey}
        emptyMessage="Nothing"
        sort={{ key: "score", direction: "asc" }}
        onSortChange={vi.fn()}
      />
    )

    expect(renderedNames()).toEqual(["Cara", "Bea", "Ana"])
  })

  it("omits the sort affordance entirely when no column opts in", () => {
    render(
      <DataTable
        caption="Plain"
        columns={COLUMNS}
        rows={ROWS}
        rowKey={rowKey}
        emptyMessage="Nothing"
        onSortChange={vi.fn()}
      />
    )

    // Nothing to click, so no misleading control is offered.
    expect(screen.queryByRole("button")).not.toBeInTheDocument()
  })
})

describe("DataTable page size", () => {
  const many: Row[] = Array.from({ length: 45 }, (_, index) => ({
    id: `p${index}`,
    code: `S-${String(index).padStart(3, "0")}`,
    name: `Student ${index}`,
  }))

  const manyRowKey = (row: Row) => row.id

  function renderPaginated(props: {
    pageSize?: number
    pageSizeOptions?: readonly number[]
    onPageSizeChange?: (size: number) => void
  }) {
    function Harness() {
      const { pagination, pageRows, setPageSize } = useDataTablePagination(
        many,
        props.pageSize ?? 10
      )
      return (
        <DataTable
          caption="Many"
          columns={COLUMNS}
          rows={pageRows}
          rowKey={manyRowKey}
          emptyMessage="Nothing"
          pagination={pagination}
          pageSizeOptions={props.pageSizeOptions}
          onPageSizeChange={
            props.onPageSizeChange ?? ((size) => setPageSize(size))
          }
        />
      )
    }
    return render(<Harness />)
  }

  it("offers no size control when the caller supplies no options", () => {
    renderPaginated({})

    expect(screen.queryByLabelText(/rows per page/i)).not.toBeInTheDocument()
  })

  it("offers the caller's sizes and marks the current one selected", () => {
    renderPaginated({ pageSizeOptions: [10, 25, 50] })

    const select = screen.getByLabelText(/rows per page/i)
    expect(select).toHaveValue("10")
    expect(
      Array.from(select.querySelectorAll("option")).map((o) => o.value)
    ).toEqual(["10", "25", "50"])
  })

  it("reports a size change to the caller", () => {
    const onPageSizeChange = vi.fn()
    renderPaginated({ pageSizeOptions: [10, 25], onPageSizeChange })

    fireEvent.change(screen.getByLabelText(/rows per page/i), {
      target: { value: "25" },
    })
    expect(onPageSizeChange).toHaveBeenCalledWith(25)
  })

  it("returns to page 1 and re-slices when the size changes", () => {
    renderPaginated({ pageSize: 10, pageSizeOptions: [10, 25] })

    fireEvent.click(screen.getByRole("button", { name: "Next" }))
    expect(screen.getByText("Page 2 of 5")).toBeInTheDocument()

    fireEvent.change(screen.getByLabelText(/rows per page/i), {
      target: { value: "25" },
    })

    // 45 rows at 25 per page is two pages, and the reader starts at the first.
    expect(screen.getByText("Page 1 of 2")).toBeInTheDocument()
    expect(screen.getByText(/Showing 1–25 of 45/)).toBeInTheDocument()
  })

  it("hides the size control when everything fits on one page", () => {
    render(
      <DataTable
        caption="Few"
        columns={COLUMNS}
        rows={ROWS}
        rowKey={rowKey}
        emptyMessage="Nothing"
        pagination={{
          page: 1,
          pageSize: 50,
          totalCount: 3,
          onPageChange: vi.fn(),
        }}
        pageSizeOptions={[10, 50]}
        onPageSizeChange={vi.fn()}
      />
    )

    // No pagination controls at all, so no size control either.
    expect(screen.queryByLabelText(/rows per page/i)).not.toBeInTheDocument()
  })

  it("honours a caller re-configuring the page size", () => {
    function Harness() {
      const { pagination, pageRows } = useDataTablePagination(many, 20)
      return (
        <DataTable
          caption="Many"
          columns={COLUMNS}
          rows={pageRows}
          rowKey={manyRowKey}
          emptyMessage="Nothing"
          pagination={pagination}
        />
      )
    }
    render(<Harness />)

    expect(screen.getByText(/Showing 1–20 of 45/)).toBeInTheDocument()
  })
})

/**
 * PH11.11 additions: the page-size control's identity and the paginated range
 * announcement.
 *
 * The identity test is a regression test. PH11.9 derived the control's DOM id
 * from the table's row count and documented that the count was "unique per
 * rendered table"; it is not, so two tables on one screen with the same number
 * of rows produced a duplicate `<label for>` and `<select id>`, and every label
 * resolved to the first table's control. The id is now `useId`-derived, which is
 * per-instance by construction.
 */
describe("DataTable pagination accessibility", () => {
  const many: Row[] = Array.from({ length: 25 }, (_, index) => ({
    id: `r${index}`,
    code: `S-${index}`,
    name: `Student ${index}`,
  }))
  const manyRowKey = (row: Row) => row.id

  function Table({
    caption,
    totalCount,
  }: {
    caption: string
    totalCount: number
  }) {
    const rows = many.slice(0, Math.min(many.length, totalCount))
    return (
      <DataTable
        caption={caption}
        columns={COLUMNS}
        rows={rows}
        rowKey={manyRowKey}
        emptyMessage="Nothing"
        pagination={{
          page: 1,
          pageSize: 10,
          totalCount,
          onPageChange: vi.fn(),
        }}
        pageSizeOptions={[10, 25, 50]}
        onPageSizeChange={vi.fn()}
      />
    )
  }

  it("gives two tables with the same row count distinct control ids", () => {
    render(
      <>
        <Table caption="First" totalCount={25} />
        <Table caption="Second" totalCount={25} />
      </>
    )

    const selects = screen.getAllByLabelText(/rows per page/i)
    expect(selects).toHaveLength(2)

    // The defect this replaces: both controls shared one id, so this was 1.
    const ids = selects.map((select) => select.getAttribute("id"))
    expect(new Set(ids).size).toBe(2)

    // And each label must resolve to its own control, not the first one.
    const labels = screen.getAllByText(/rows per page/i)
    const [first, second] = labels
    const [firstId, secondId] = ids
    expect(first?.getAttribute("for")).toBe(firstId)
    expect(second?.getAttribute("for")).toBe(secondId)
    expect(firstId).toBeTruthy()
    expect(secondId).toBeTruthy()
  })

  it("announces the visible range politely so paging is not silent", () => {
    render(<Table caption="First" totalCount={25} />)

    // PH11.2 §16.7: dynamic content updates are announced. Without this the
    // table mutated underneath a screen reader with no indication that the rows
    // or the range had changed.
    const summary = screen.getByText(/Showing 1–10 of 25/)
    expect(summary).toHaveAttribute("aria-live", "polite")
  })

  it("makes the horizontal scroll container focusable and named", () => {
    render(
      <DataTable
        caption="Students"
        columns={COLUMNS}
        rows={ROWS}
        rowKey={rowKey}
        emptyMessage="Nothing"
      />
    )

    // PH11.2 §12.4 keeps tables as scrolling tables, so the overflow has to be
    // reachable from the keyboard (WCAG 2.1.1). The region is named from the
    // caption, which is the name a reader already knows the table by.
    const region = screen.getByRole("region", { name: "Students" })
    expect(region).toHaveAttribute("tabindex", "0")
    expect(region).toContainElement(screen.getByRole("table"))
  })
})

describe("DataTable rowProps", () => {
  it("applies caller row attributes to the row element", () => {
    render(
      <DataTable
        caption="Students"
        columns={COLUMNS}
        rows={ROWS}
        rowKey={rowKey}
        emptyMessage="Nothing"
        rowProps={(row) => ({ "data-code": row.code })}
      />
    )

    expect(screen.getAllByRole("row")[1]).toHaveAttribute("data-code", "S-001")
  })
})

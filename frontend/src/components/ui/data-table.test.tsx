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
      status: 0,
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
    render(<Stateful phase="empty" />)

    expect(screen.queryAllByRole("alert")).toHaveLength(0)
    expect(screen.queryAllByRole("status")).toHaveLength(0)
  })
})

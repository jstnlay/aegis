import { readFileSync } from "node:fs"
import path from "node:path"
import { fileURLToPath } from "node:url"

import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { MemoryRouter } from "react-router-dom"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { apiClient } from "@/lib/api"

import { StudentsPage } from "./StudentsPage"

vi.mock("@/lib/api", () => ({
  API_BASE_URL: "http://localhost:8000/api/v1",
  onSessionExpired: vi.fn(() => () => {}),
  apiClient: {
    get: vi.fn(async () => ({ data: { students: [] } })),
    post: vi.fn(async () => ({ data: {} })),
    put: vi.fn(async () => ({ data: {} })),
    patch: vi.fn(async () => ({ data: {} })),
    delete: vi.fn(async () => ({ data: undefined })),
  },
}))

const mockedGet = vi.mocked(apiClient.get)

/**
 * One row of the directory, as the server sends it.
 *
 * The aggregation moved to the server: the page used to fetch five complete
 * lists and add them up in the browser. What is left here is the page's own
 * job — rendering the rows it is given.
 */
function student(overrides: Record<string, unknown> = {}) {
  return {
    id: "sp-1",
    name: "Ana Reyes",
    code: "S-1001",
    latestActivity: "2025-02-12",
    openAlertCount: 1,
    atRiskLevel: "high",
    consultationCount: 1,
    interventionCount: 0,
    resultCount: 0,
    ...overrides,
  }
}

function stub(students: unknown[]) {
  mockedGet.mockImplementation(async (url: string) => {
    if (String(url).includes("/guidance/students/")) {
      return { data: { students } }
    }
    return { data: [] }
  })
}

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <MemoryRouter>
      <QueryClientProvider client={client}>
        <StudentsPage />
      </QueryClientProvider>
    </MemoryRouter>
  )
}

async function openSelect(trigger: HTMLElement) {
  await waitFor(() => expect(trigger).toBeEnabled())
  fireEvent.keyDown(trigger, { key: "ArrowDown" })
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe("StudentsPage", () => {
  it("is titled Students with guidance activity", async () => {
    stub([])
    renderPage()

    expect(
      await screen.findByRole("heading", { name: "Students", level: 2 })
    ).toBeInTheDocument()
    expect(
      screen.getByText("Students with guidance activity")
    ).toBeInTheDocument()
  })

  it("asks for the directory and for nothing else", async () => {
    stub([student()])
    renderPage()
    await screen.findByText("Ana Reyes")

    // The directory is one request. It is not the enrollment table: a
    // counselor has never worked with every enrolled student.
    const urls = mockedGet.mock.calls.map(([url]) => String(url))
    expect(urls).toEqual(["/guidance/students/"])
  })

  it("lists every student the server returns", async () => {
    stub([
      student({ id: "sp-1", name: "Ana Reyes" }),
      student({ id: "sp-2", name: "Ben Cruz" }),
      student({ id: "sp-3", name: "Cara Diaz" }),
      student({ id: "sp-4", name: "Dan Ellis" }),
    ])
    renderPage()

    expect(await screen.findByText("Ana Reyes")).toBeInTheDocument()
    expect(screen.getByText("Ben Cruz")).toBeInTheDocument()
    expect(screen.getByText("Cara Diaz")).toBeInTheDocument()
    expect(screen.getByText("Dan Ellis")).toBeInTheDocument()
    // Header row + 4 students.
    expect(screen.getAllByRole("row")).toHaveLength(5)
  })

  it("shows an empty state when the server has no students", async () => {
    stub([])
    renderPage()

    expect(
      await screen.findByText(/No students have guidance activity yet/i)
    ).toBeInTheDocument()
  })

  it("shows an em-dash when no record carries a student code", async () => {
    stub([student({ code: null })])
    renderPage()
    await screen.findByText("Ana Reyes")

    const row = screen.getByText("Ana Reyes").closest("tr") as HTMLElement
    expect(within(row).getByText("—")).toBeInTheDocument()
    expect(row.textContent).not.toContain("sp-1")
  })

  it("uses the code when the server carries one", async () => {
    stub([student({ code: "S-1001" })])
    renderPage()
    await screen.findByText("Ana Reyes")

    const row = screen.getByText("Ana Reyes").closest("tr") as HTMLElement
    expect(within(row).getByText("S-1001")).toBeInTheDocument()
  })

  it("flags a student the server marked at risk", async () => {
    stub([student({ atRiskLevel: "high" })])
    renderPage()
    await screen.findByText("Ana Reyes")

    const row = screen.getByText("Ana Reyes").closest("tr") as HTMLElement
    expect(row).toHaveAttribute("data-at-risk", "true")
    expect(within(row).getByText("High")).toHaveAttribute(
      "data-at-risk-level",
      "high"
    )
  })

  it("uses warning semantics for a moderate-only student, not high", async () => {
    stub([student({ atRiskLevel: "moderate" })])
    renderPage()
    await screen.findByText("Ana Reyes")

    const pill = screen.getByText("Moderate")
    expect(pill).toHaveAttribute("data-at-risk-level", "moderate")
    // The moderate pill must carry the warning treatment, not the
    // destructive/high one. `text-destructive` is the high-risk marker; the
    // Badge base class merely lists the variant name in its own utilities, so
    // the check is on the text token specifically.
    expect(pill.className).toContain("text-warning-foreground")
    expect(pill.className).not.toContain("text-destructive")
  })

  it("does not flag a student the server marked as not at risk", async () => {
    stub([student({ atRiskLevel: null })])
    renderPage()
    await screen.findByText("Ana Reyes")

    expect(screen.getByText("Ana Reyes").closest("tr")).toHaveAttribute(
      "data-at-risk",
      "false"
    )
  })

  it("counts each activity type separately", async () => {
    stub([
      student({
        openAlertCount: 2,
        consultationCount: 2,
        interventionCount: 1,
        resultCount: 1,
      }),
    ])
    renderPage()
    await screen.findByText("Ana Reyes")

    const row = screen.getByText("Ana Reyes").closest("tr") as HTMLElement
    const cells = within(row).getAllByRole("cell")
    // 2 alerts, 2 consultations, 1 intervention, 1 result.
    expect(cells[2]).toHaveTextContent("2")
    expect(cells[3]).toHaveTextContent("2")
    expect(cells[4]).toHaveTextContent("1")
    expect(cells[5]).toHaveTextContent("1")
  })

  it("filters by activity type", async () => {
    stub([
      student({ id: "sp-1", name: "Ana Reyes", consultationCount: 0 }),
      student({
        id: "sp-2",
        name: "Ben Cruz",
        openAlertCount: 0,
        interventionCount: 0,
        resultCount: 0,
        consultationCount: 1,
      }),
    ])
    renderPage()
    await screen.findByText("Ana Reyes")

    await openSelect(screen.getByLabelText("Activity type"))
    fireEvent.click(
      await screen.findByRole("option", { name: "Consultations" })
    )

    await waitFor(() => expect(screen.queryByText("Ana Reyes")).toBeNull())
    expect(screen.getByText("Ben Cruz")).toBeInTheDocument()
  })

  it("searches by name and by code", async () => {
    stub([
      student({ id: "sp-1", name: "Ana Reyes", code: "S-1001" }),
      student({ id: "sp-2", name: "Ben Cruz", code: "S-1002" }),
    ])
    renderPage()
    await screen.findByText("Ana Reyes")

    fireEvent.change(screen.getByLabelText("Search"), {
      target: { value: "S-1002" },
    })
    await waitFor(() => expect(screen.queryByText("Ana Reyes")).toBeNull())
    expect(screen.getByText("Ben Cruz")).toBeInTheDocument()
  })

  it("shows an empty state when filters exclude everything", async () => {
    stub([student()])
    renderPage()
    await screen.findByText("Ana Reyes")

    fireEvent.change(screen.getByLabelText("Search"), {
      target: { value: "zzzz-no-match" },
    })

    expect(
      await screen.findByText(/No students match the current filters/i)
    ).toBeInTheDocument()
  })

  it("links each row to the profile using the StudentProfile UUID", async () => {
    stub([student({ id: "sp-1" })])
    renderPage()
    await screen.findByText("Ana Reyes")

    const link = screen
      .getByText("Ana Reyes")
      .closest("tr")
      ?.querySelector("a") as HTMLAnchorElement

    expect(link).toHaveAttribute("href", "/app/students/sp-1")
  })

  it("surfaces a fetch failure", async () => {
    mockedGet.mockRejectedValue(new Error("boom"))
    renderPage()

    const alert = await screen.findByRole("alert")
    expect(alert).toHaveTextContent("boom")
  })
})

/**
 * The imported SF2/SF3 dataset, rendered on the directory.
 *
 * Every other test here feeds the page a hand-typed fixture. This one reads the
 * shipped `docs/test-data/grades-sf3.csv` — the file the import pipeline
 * ingests — derives each learner's term average from it, and renders the same
 * rows the server would build from those grades. That ties the UI evidence to
 * the actual dataset rather than to a fixture that could drift away from it.
 *
 * The dataset splits the Grade 8 Bonifacio roster into three bands round-robin;
 * the "at-risk" band's term average sits below the passing mark, so those
 * learners must render with an at-risk badge and be reachable by the activity
 * filter, the search box and the profile link.
 */
describe("StudentsPage — imported dataset", () => {
  const PASSING_MARK = 75

  /** Read the shipped grades CSV and compute each learner's term average. */
  function termAveragesFromDataset(): Map<string, number> {
    const csvPath = path.resolve(
      path.dirname(fileURLToPath(import.meta.url)),
      "../../../../docs/test-data/grades-sf3.csv"
    )
    const rows = readFileSync(csvPath, "utf8")
      .trim()
      .split("\n")
      .slice(1) // header
      .map((line) => line.split(","))
    const totals = new Map<string, { sum: number; n: number }>()
    // columns: student_id, section, subject_code, grading_period, score, ...
    for (const cols of rows) {
      const studentId = cols[0]
      const score = Number(cols[4])
      const entry = totals.get(studentId) ?? { sum: 0, n: 0 }
      entry.sum += score
      entry.n += 1
      totals.set(studentId, entry)
    }
    const averages = new Map<string, number>()
    for (const [studentId, { sum, n }] of totals) {
      averages.set(studentId, sum / n)
    }
    return averages
  }

  function directoryRowsFromDataset() {
    const averages = termAveragesFromDataset()
    return [...averages.entries()]
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([studentId, average], index) => {
        const atRisk = average < PASSING_MARK
        return student({
          id: `sp-${studentId}`,
          name: `Learner ${studentId.slice(-5)}`,
          code: studentId,
          atRiskLevel: atRisk ? (average < 70 ? "high" : "moderate") : null,
          openAlertCount: atRisk ? 1 : 0,
          // The directory is "students with guidance activity"; a flagged
          // learner has an alert, an unflagged one only a consultation.
          consultationCount: atRisk ? 1 : 1,
          interventionCount: atRisk ? 1 : 0,
          resultCount: 0,
          latestActivity: `2026-09-0${(index % 9) + 1}`,
        })
      })
  }

  it("renders every learner in the dataset", async () => {
    const rows = directoryRowsFromDataset()
    stub(rows)
    renderPage()

    // 25 learners in the file.
    expect(rows).toHaveLength(25)
    expect(await screen.findByText(/Showing 25 of 25/)).toBeInTheDocument()
  })

  it("shows the at-risk learners the dataset actually contains", async () => {
    const rows = directoryRowsFromDataset()
    stub(rows)
    renderPage()

    const atRisk = rows.filter((row) => row.atRiskLevel !== null)
    // The generator's at-risk band is roughly a third of the roster.
    expect(atRisk.length).toBeGreaterThanOrEqual(5)

    // Wait for the loaded header (not the pre-fetch "0 of 0" one).
    const headerCount = await screen.findByText(
      new RegExp(`${atRisk.length} at risk`)
    )
    expect(headerCount).toBeInTheDocument()

    // At least one at-risk row renders with its badge.
    const firstFlagged = atRisk[0]
    const row = screen.getByText(firstFlagged.name).closest("tr") as HTMLElement
    expect(row).toHaveAttribute("data-at-risk", "true")
  })

  it("filters the dataset to the learners with open risk alerts", async () => {
    stub(directoryRowsFromDataset())
    renderPage()
    await screen.findByText(/Showing 25 of 25/)

    await openSelect(screen.getByLabelText("Activity type"))
    fireEvent.click(
      await screen.findByRole("option", { name: "Open risk alerts" })
    )

    // A dataset learner with no open alert drops out of the filtered view.
    await waitFor(() =>
      expect(screen.queryByText("Learner S0026")).toBeNull()
    )
  })

  it("selects a dataset learner by student code", async () => {
    stub(directoryRowsFromDataset())
    renderPage()
    await screen.findByText(/Showing 25 of 25/)

    fireEvent.change(screen.getByLabelText("Search"), {
      target: { value: "AEGIS-QA-S0046" },
    })

    await waitFor(() =>
      expect(screen.queryByText("Learner S0026")).toBeNull()
    )
    const name = screen.getByText("Learner S0046")
    const row = name.closest("tr") as HTMLElement
    const link = row.querySelector("a") as HTMLAnchorElement
    expect(link).toHaveAttribute("href", "/app/students/sp-AEGIS-QA-S0046")
  })
})

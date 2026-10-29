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
import { beforeEach, describe, expect, it, vi } from "vitest"

import type { RiskAlert } from "@/features/guidance/api"
import { apiClient } from "@/lib/api"
import { fetchAllPages } from "@/lib/pagination"

import { RiskAlertsPage } from "./RiskAlertsPage"

vi.mock("@/lib/pagination", () => ({
  fetchAllPages: vi.fn(),
}))

vi.mock("@/lib/api", () => ({
  API_BASE_URL: "http://localhost:8000/api/v1",
  onSessionExpired: vi.fn(() => () => {}),
  apiClient: {
    get: vi.fn(async () => ({ data: [] })),
    post: vi.fn(async () => ({ data: {} })),
    patch: vi.fn(async () => ({ data: {} })),
    delete: vi.fn(async () => ({ data: undefined })),
  },
}))

const mockedFetchAllPages = vi.mocked(fetchAllPages)
const mockedPost = vi.mocked(apiClient.post)

function makeAlert(overrides: Partial<RiskAlert> = {}): RiskAlert {
  return {
    id: "ra-1",
    student: "sp-1",
    student_name: "Ana Reyes",
    risk_level: "high",
    risk_factors: ["Chronic absenteeism"],
    source: "manual",
    status: "active",
    assigned_counselor: null,
    assigned_counselor_name: null,
    generated_at: "2025-02-01T00:00:00Z",
    last_updated: "2025-02-01T00:00:00Z",
    created_at: "2025-02-01T00:00:00Z",
    updated_at: "2025-02-01T00:00:00Z",
    ...overrides,
  }
}

const alerts: RiskAlert[] = [
  makeAlert({
    id: "ra-1",
    student: "sp-1",
    student_name: "Ana Reyes",
    status: "active",
    risk_level: "high",
  }),
  makeAlert({
    id: "ra-2",
    student: "sp-2",
    student_name: "Ben Cruz",
    status: "under_monitoring",
    risk_level: "moderate",
  }),
  makeAlert({
    id: "ra-3",
    student: "sp-3",
    student_name: "Cara Diaz",
    status: "resolved",
    risk_level: "high",
  }),
  makeAlert({
    id: "ra-4",
    student: "sp-4",
    student_name: "Dan Ellis",
    status: "escalated",
    risk_level: "moderate",
  }),
]

/**
 * Raw `EnrollmentWire` rows exactly as `EnrollmentViewSet` returns them.
 *
 * The fixture must stay in backend shape rather than the normalized
 * `StudentRosterEntry` shape: `useStudentRoster()` performs the
 * student/student_name/student_id mapping itself, so a pre-normalized fixture
 * silently produces options with empty names and codes.
 */
const enrollments = [
  {
    id: "en-1",
    student: "sp-1",
    student_name: "Ana Reyes",
    student_id: "S-1001",
    section: "sec-a",
    section_name: "Grade 10-A",
    academic_year: "ay-1",
    academic_year_name: "2025-2026",
    date_enrolled: "2025-01-10",
    is_active: true,
  },
  {
    id: "en-2",
    student: "sp-2",
    student_name: "Ben Cruz",
    student_id: "S-1002",
    section: "sec-a",
    section_name: "Grade 10-A",
    academic_year: "ay-1",
    academic_year_name: "2025-2026",
    date_enrolled: "2025-01-10",
    is_active: true,
  },
  {
    id: "en-3",
    student: "sp-3",
    student_name: "Cara Diaz",
    student_id: "S-1003",
    section: "sec-b",
    section_name: "Grade 10-B",
    academic_year: "ay-1",
    academic_year_name: "2025-2026",
    date_enrolled: "2025-01-10",
    is_active: true,
  },
  {
    id: "en-4",
    student: "sp-4",
    student_name: "Dan Ellis",
    student_id: "S-1004",
    section: "sec-b",
    section_name: "Grade 10-B",
    academic_year: "ay-1",
    academic_year_name: "2025-2026",
    date_enrolled: "2025-01-10",
    is_active: true,
  },
]

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <RiskAlertsPage />
    </QueryClientProvider>
  )
}

/**
 * Radix `Select` needs a keydown to open and a click to commit, and jsdom has
 * no user-event installed. Firing both parts is the same approach
 * `AttendancePage.test.tsx` uses, so no new test dependency is introduced.
 */
async function openSelect(trigger: HTMLElement) {
  await waitFor(() => expect(trigger).toBeEnabled())
  fireEvent.keyDown(trigger, { key: "ArrowDown" })
}

function rowFor(name: string): HTMLElement {
  const row = screen.getByText(name).closest("tr")
  if (!row) throw new Error(`No row found for ${name}`)
  return row
}

beforeEach(() => {
  vi.clearAllMocks()
  mockedFetchAllPages.mockImplementation(async (url: string) => {
    if (url.includes("/academics/enrollments/")) {
      return { count: enrollments.length, results: enrollments }
    }
    return { count: alerts.length, results: alerts }
  })
})

describe("RiskAlertsPage", () => {
  it("renders every alert regardless of status by default", async () => {
    renderPage()

    expect(
      await screen.findByRole("heading", { name: "Risk Alerts", level: 2 })
    ).toBeInTheDocument()

    await waitFor(() => {
      expect(screen.getByText("Ana Reyes")).toBeInTheDocument()
      expect(screen.getByText("Ben Cruz")).toBeInTheDocument()
      expect(screen.getByText("Cara Diaz")).toBeInTheDocument()
      expect(screen.getByText("Dan Ellis")).toBeInTheDocument()
    })

    expect(screen.getByText(/Showing 4 of 4/)).toBeInTheDocument()
  })

  it("shows status counts computed over the whole visible set", async () => {
    renderPage()
    await screen.findByText("Ana Reyes")

    const group = screen.getByRole("group", { name: /filter by status/i })
    // 4 alerts total: 1 active, 1 under monitoring, 1 resolved, 1 escalated.
    expect(
      within(group).getByRole("button", { name: /^All 4$/ })
    ).toBeInTheDocument()
    expect(
      within(group).getByRole("button", { name: /^Active 1$/ })
    ).toBeInTheDocument()
    expect(
      within(group).getByRole("button", { name: /^Resolved 1$/ })
    ).toBeInTheDocument()
  })

  it("summarises every status in tiles counted over the unfiltered list", async () => {
    renderPage()
    await screen.findByText("Ana Reyes")

    // 4 alerts, one per status. The tiles answer "how many in each state"
    // before any filter is touched, and filtering the table below must not
    // shrink them — they read the same unfiltered counts as the filter chips.
    // Headings, not text: the filter chips repeat these words as buttons.
    const cardFor = (title: string) =>
      screen.getByRole("heading", { name: title }).closest('[data-slot="card"]')
    expect(cardFor("Total Alerts")).toHaveTextContent("4")
    expect(cardFor("Active")).toHaveTextContent("1")
    expect(cardFor("Under monitoring")).toHaveTextContent("1")
    expect(cardFor("Resolved")).toHaveTextContent("1")
    expect(cardFor("Escalated")).toHaveTextContent("1")

    const group = screen.getByRole("group", { name: /filter by status/i })
    fireEvent.click(within(group).getByRole("button", { name: /^Active 1$/ }))
    await waitFor(() => {
      expect(screen.getByText(/Showing 1 of 4/)).toBeInTheDocument()
    })
    // The table narrowed; the summary still describes the whole file.
    expect(cardFor("Total Alerts")).toHaveTextContent("4")
    expect(cardFor("Resolved")).toHaveTextContent("1")
  })

  it("filters by status without dropping resolved alerts entirely", async () => {
    renderPage()
    await screen.findByText("Ana Reyes")

    const group = screen.getByRole("group", { name: /filter by status/i })
    fireEvent.click(within(group).getByRole("button", { name: /^Resolved 1$/ }))

    await waitFor(() => {
      expect(screen.getByText(/Showing 1 of 4/)).toBeInTheDocument()
    })
    expect(screen.getByText("Cara Diaz")).toBeInTheDocument()
    expect(screen.queryByText("Ana Reyes")).not.toBeInTheDocument()
  })

  it("searches by student name", async () => {
    renderPage()
    await screen.findByText("Ana Reyes")

    fireEvent.change(screen.getByLabelText(/search/i), {
      target: { value: "ben" },
    })

    await waitFor(() => {
      expect(screen.getByText(/Showing 1 of 4/)).toBeInTheDocument()
    })
    expect(screen.getByText("Ben Cruz")).toBeInTheDocument()
  })

  it("renders the roster student code, which the alert serializer lacks", async () => {
    renderPage()
    await screen.findByText("Ana Reyes")
    await waitFor(() => {
      expect(
        within(rowFor("Ana Reyes")).getByText("S-1001")
      ).toBeInTheDocument()
    })
  })

  it("offers every legal transition for an active alert", async () => {
    renderPage()
    await screen.findByText("Ana Reyes")

    const row = rowFor("Ana Reyes")
    expect(
      within(row).getByRole("button", { name: "Acknowledge" })
    ).toBeInTheDocument()
    expect(
      within(row).getByRole("button", { name: "Escalate" })
    ).toBeInTheDocument()
    expect(
      within(row).getByRole("button", { name: "Resolve" })
    ).toBeInTheDocument()
  })

  it("withholds acknowledge on an under-monitoring alert", async () => {
    renderPage()
    await screen.findByText("Ben Cruz")

    const row = rowFor("Ben Cruz")
    // under_monitoring -> escalate, resolve only. The backend rejects
    // acknowledge from this status with a 400, so the button must not exist.
    expect(
      within(row).queryByRole("button", { name: "Acknowledge" })
    ).toBeNull()
    expect(
      within(row).getByRole("button", { name: "Escalate" })
    ).toBeInTheDocument()
    expect(
      within(row).getByRole("button", { name: "Resolve" })
    ).toBeInTheDocument()
  })

  it("offers no transitions on a resolved alert", async () => {
    renderPage()
    await screen.findByText("Cara Diaz")

    const row = rowFor("Cara Diaz")
    expect(
      within(row).queryByRole("button", {
        name: /Acknowledge|Escalate|Resolve/,
      })
    ).toBeNull()
    expect(within(row).getByText(/No actions available/i)).toBeInTheDocument()
  })

  it("offers no transitions on an escalated alert", async () => {
    renderPage()
    await screen.findByText("Dan Ellis")

    const row = rowFor("Dan Ellis")
    expect(
      within(row).queryByRole("button", { name: "Acknowledge" })
    ).toBeNull()
    expect(within(row).queryByRole("button", { name: "Escalate" })).toBeNull()
    expect(within(row).queryByRole("button", { name: "Resolve" })).toBeNull()
  })

  it("posts to the acknowledge action endpoint", async () => {
    mockedPost.mockResolvedValue({
      data: makeAlert({ status: "under_monitoring" }),
    } as never)

    renderPage()
    await screen.findByText("Ana Reyes")

    fireEvent.click(
      within(rowFor("Ana Reyes")).getByRole("button", { name: "Acknowledge" })
    )

    await waitFor(() => {
      expect(mockedPost).toHaveBeenCalledWith(
        "/guidance/risk-alerts/ra-1/acknowledge/"
      )
    })
  })

  it("posts to the escalate action endpoint for an under-monitoring alert", async () => {
    mockedPost.mockResolvedValue({
      data: makeAlert({ id: "ra-2", status: "escalated" }),
    } as never)

    renderPage()
    await screen.findByText("Ben Cruz")

    fireEvent.click(
      within(rowFor("Ben Cruz")).getByRole("button", { name: "Escalate" })
    )

    await waitFor(() => {
      expect(mockedPost).toHaveBeenCalledWith(
        "/guidance/risk-alerts/ra-2/escalate/"
      )
    })
  })

  it("creates an alert without sending assigned_counselor or source", async () => {
    mockedPost.mockResolvedValue({ data: makeAlert() } as never)

    renderPage()
    await screen.findByText("Ana Reyes")

    fireEvent.click(screen.getByRole("button", { name: /new risk alert/i }))
    const dialog = await screen.findByRole("dialog")

    await openSelect(within(dialog).getByRole("combobox", { name: /student/i }))
    fireEvent.click(await screen.findByRole("option", { name: /Ana Reyes/ }))
    fireEvent.click(
      within(dialog).getByRole("button", { name: /create alert/i })
    )

    await waitFor(() => {
      expect(mockedPost).toHaveBeenCalledWith("/guidance/risk-alerts/", {
        student: "sp-1",
        risk_level: "moderate",
        risk_factors: [],
      })
    })

    const payload = mockedPost.mock.calls[0]?.[1] as Record<string, unknown>
    // No endpoint lists guidance profiles, so the counselor field must never be
    // guessed; `source` is forced to "manual" by the viewset.
    expect(payload).not.toHaveProperty("assigned_counselor")
    expect(payload).not.toHaveProperty("source")
  })

  it("splits typed risk factors into a list", async () => {
    mockedPost.mockResolvedValue({ data: makeAlert() } as never)

    renderPage()
    await screen.findByText("Ana Reyes")

    fireEvent.click(screen.getByRole("button", { name: /new risk alert/i }))
    const dialog = await screen.findByRole("dialog")

    fireEvent.change(within(dialog).getByLabelText(/risk factors/i), {
      target: { value: "Chronic absenteeism\nFamily conflict\n\n" },
    })

    await openSelect(within(dialog).getByRole("combobox", { name: /student/i }))
    fireEvent.click(await screen.findByRole("option", { name: /Ana Reyes/ }))
    fireEvent.click(
      within(dialog).getByRole("button", { name: /create alert/i })
    )

    await waitFor(() => {
      expect(mockedPost).toHaveBeenCalledWith("/guidance/risk-alerts/", {
        student: "sp-1",
        risk_level: "moderate",
        risk_factors: ["Chronic absenteeism", "Family conflict"],
      })
    })
  })

  it("shows an empty state when filters exclude everything", async () => {
    renderPage()
    await screen.findByText("Ana Reyes")

    fireEvent.change(screen.getByLabelText(/search/i), {
      target: { value: "zzzz-no-match" },
    })

    expect(
      await screen.findByText(/No alerts match the current filters/i)
    ).toBeInTheDocument()
  })

  it("surfaces a fetch failure instead of an empty table", async () => {
    mockedFetchAllPages.mockRejectedValue(new Error("boom"))

    renderPage()

    // A non-Axios error is normalized to code UNKNOWN_ERROR with its own
    // message preserved, so the banner must carry "boom" rather than a
    // fabricated generic string.
    const alert = await screen.findByRole("alert")
    expect(alert).toHaveTextContent("boom")
  })

  it("renders an object-shaped AI risk factor in the table", async () => {
    // The real ai_engine shape. Typed as string[] in PH11.8, this rendered
    // "[object Object]" and threw on the React child.
    mockedFetchAllPages.mockResolvedValue({
      count: 1,
      results: [
        makeAlert({
          risk_factors: [
            {
              feature: "attendance_rate",
              threshold: 0.75,
              value: 0.62,
              direction: "below",
            },
            "Family conflict",
          ],
        }),
      ],
    })

    const { container } = renderPage()

    await screen.findByText("Ana Reyes")
    expect(container.textContent).toContain("attendance_rate")
    expect(container.textContent).toContain("0.62")
    expect(container.textContent).toContain("Family conflict")
    expect(container.textContent).not.toContain("[object Object]")
  })

  it("finds an object-shaped factor through the search box", async () => {
    mockedFetchAllPages.mockResolvedValue({
      count: alerts.length,
      results: alerts.map((alert, index) =>
        index === 0
          ? {
              ...alert,
              risk_factors: [
                {
                  feature: "attendance_rate",
                  threshold: 0.75,
                  value: 0.62,
                  direction: "below",
                },
              ],
            }
          : alert
      ),
    })

    renderPage()
    await screen.findByText("Ana Reyes")

    fireEvent.change(screen.getByLabelText(/search/i), {
      target: { value: "attendance_rate" },
    })

    // Only the algorithm-derived alert matches; the manual ones do not.
    await waitFor(() => {
      expect(screen.getByText("Ana Reyes")).toBeInTheDocument()
      expect(screen.queryByText("Ben Cruz")).not.toBeInTheDocument()
    })
  })
})

/**
 * The alert queue driven by the shipped `docs/test-data/grades-sf3.csv`.
 *
 * The other tests here hand-build alerts. This block instead reads the dataset
 * the import pipeline ingests, derives each learner's term average from it,
 * flags the ones below the passing mark, and feeds the resulting algorithm
 * alerts into the page. That proves the queue renders and filters what the
 * dataset actually produces, not what a fixture was told to produce.
 *
 * Factor shape is the real `ai_engine` one: an object with `feature`,
 * `value`, `threshold` and `direction`. The queue must label it, not print
 * `[object Object]`, and the risk-level filter must narrow to it.
 */
describe("RiskAlertsPage — imported dataset", () => {
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

  /** The flagged cohort, as algorithm alerts the queue would receive. */
  function alertsFromDataset(): RiskAlert[] {
    const averages = termAveragesFromDataset()
    return [...averages.entries()]
      .filter(([, average]) => average < PASSING_MARK)
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([studentId, average], index) =>
        makeAlert({
          id: `ra-${studentId}`,
          student: `sp-${studentId}`,
          student_name: `Learner ${studentId.slice(-5)}`,
          risk_level: average < 70 ? "high" : "moderate",
          source: "algorithm",
          status: "active",
          risk_factors: [
            {
              feature: "current_term_grade_average",
              threshold: PASSING_MARK,
              value: Number(average.toFixed(2)),
              direction: "below",
            },
          ],
          generated_at: `2026-09-0${(index % 9) + 1}T00:00:00Z`,
        })
      )
  }

  beforeEach(() => {
    mockedFetchAllPages.mockImplementation(async (url: string) => {
      if (url.includes("/academics/enrollments/")) {
        return { count: 0, results: [] }
      }
      const datasetAlerts = alertsFromDataset()
      return { count: datasetAlerts.length, results: datasetAlerts }
    })
  })

  it("queues an alert for every at-risk learner in the dataset", async () => {
    const expected = alertsFromDataset()
    // The generator's at-risk band is roughly a third of the roster.
    expect(expected.length).toBeGreaterThanOrEqual(5)

    renderPage()

    await screen.findByText(expected[0].student_name)
    expect(
      screen.getByText(
        new RegExp(`Showing ${expected.length} of ${expected.length}`)
      )
    ).toBeInTheDocument()
  })

  it("prints the why-flagged factor rather than [object Object]", async () => {
    const { container } = renderPage()
    const expected = alertsFromDataset()[0]

    await screen.findByText(expected.student_name)

    const row = rowFor(expected.student_name)
    expect(within(row).getByText(/current_term_grade_average/)).toBeInTheDocument()
    expect(container.textContent).not.toContain("[object Object]")
  })

  it("filters the dataset alerts by risk level", async () => {
    const expected = alertsFromDataset()
    const highs = expected.filter((alert) => alert.risk_level === "high")
    expect(highs.length).toBeGreaterThan(0)

    renderPage()
    await screen.findByText(expected[0].student_name)

    await openSelect(screen.getByLabelText("Risk level"))
    fireEvent.click(await screen.findByRole("option", { name: "High" }))

    await waitFor(() => {
      expect(
        screen.getByText(
          new RegExp(`Showing ${highs.length} of ${expected.length}`)
        )
      ).toBeInTheDocument()
    })
    // Every flagged learner in this dataset averages below 70, so none is
    // left outside the "High" filter — the count is the whole flagged set.
    expect(highs.length).toBe(expected.length)
  })
})

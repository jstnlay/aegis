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

import { fetchAllPages } from "@/lib/pagination"

import { StudentsPage } from "./StudentsPage"

vi.mock("@/lib/pagination", () => ({
  fetchAllPages: vi.fn(),
}))

vi.mock("@/lib/api", () => ({
  API_BASE_URL: "http://localhost:8000/api/v1",
  onSessionExpired: vi.fn(() => () => {}),
  apiClient: {
    get: vi.fn(async () => ({ data: [] })),
    post: vi.fn(async () => ({ data: {} })),
    put: vi.fn(async () => ({ data: {} })),
    patch: vi.fn(async () => ({ data: {} })),
    delete: vi.fn(async () => ({ data: undefined })),
  },
}))

const mockedFetchAllPages = vi.mocked(fetchAllPages)

function alert(overrides: Record<string, unknown> = {}) {
  return {
    id: "ra-1",
    student: "sp-1",
    student_name: "Ana Reyes",
    risk_level: "high",
    risk_factors: [],
    source: "manual",
    status: "active",
    assigned_counselor: null,
    assigned_counselor_name: null,
    generated_at: "2025-02-10T00:00:00Z",
    last_updated: "2025-02-10T00:00:00Z",
    created_at: "2025-02-10T00:00:00Z",
    updated_at: "2025-02-10T00:00:00Z",
    ...overrides,
  }
}

function consultation(overrides: Record<string, unknown> = {}) {
  return {
    id: "c-1",
    student: "sp-1",
    student_name: "Ana Reyes",
    counselor: "gp-1",
    counselor_name: "Robin Vega",
    session_date: "2025-02-12",
    session_time: "09:30:00",
    session_type: "individual_counseling",
    concern_categories: [],
    session_notes: "Session notes.",
    recommendations: null,
    next_session_date: null,
    priority_level: "medium",
    status: "ongoing",
    created_at: "2025-02-12T00:00:00Z",
    updated_at: "2025-02-12T00:00:00Z",
    ...overrides,
  }
}

function intervention(overrides: Record<string, unknown> = {}) {
  return {
    id: "i-1",
    student: "sp-1",
    student_name: "Ana Reyes",
    risk_alert: null,
    risk_alert_student: null,
    assigned_counselor: "gp-1",
    assigned_counselor_name: "Robin Vega",
    plan_start_date: "2025-01-05",
    target_review_date: null,
    status: "active",
    created_at: "2025-01-05T00:00:00Z",
    updated_at: "2025-01-05T00:00:00Z",
    ...overrides,
  }
}

function result(overrides: Record<string, unknown> = {}) {
  return {
    id: "ar-1",
    assessment: "a-1",
    assessment_title: "Wellness Check-In",
    student: "sp-1",
    student_name: "Ana Reyes",
    student_id: "S-1001",
    score: "8.00",
    total_possible: "10.00",
    percentage: "80.00",
    status: "completed",
    started_at: "2025-02-01T00:00:00Z",
    completed_at: "2025-02-01T01:00:00Z",
    ...overrides,
  }
}

function note(overrides: Record<string, unknown> = {}) {
  return {
    id: "bn-1",
    student: "sp-1",
    student_name: "Ana Reyes",
    student_id_code: "S-1001",
    recorded_by: "f-1",
    recorded_by_name: "Sam Faculty",
    note_type: "positive",
    note_text: "Helped a classmate.",
    date_recorded: "2025-01-20",
    created_at: "2025-01-20T00:00:00Z",
    updated_at: "2025-01-20T00:00:00Z",
    ...overrides,
  }
}

function stub(fixtures: {
  alerts?: unknown[]
  consultations?: unknown[]
  interventions?: unknown[]
  results?: unknown[]
  notes?: unknown[]
}) {
  mockedFetchAllPages.mockImplementation(async (url: string) => {
    const bag = url.includes("/guidance/risk-alerts/")
      ? fixtures.alerts
      : url.includes("/guidance/consultations/")
        ? fixtures.consultations
        : url.includes("/guidance/interventions/")
          ? fixtures.interventions
          : url.includes("/assessments/assessment-results/")
            ? fixtures.results
            : url.includes("/guidance/behavioral-notes/")
              ? fixtures.notes
              : undefined
    const results = bag ?? []
    return { count: results.length, results }
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
    stub({})
    renderPage()

    expect(
      await screen.findByRole("heading", { name: "Students", level: 2 })
    ).toBeInTheDocument()
    expect(
      screen.getByText("Students with guidance activity")
    ).toBeInTheDocument()
  })

  it("never requests the enrollment endpoint", async () => {
    stub({ alerts: [alert()] })
    renderPage()
    await screen.findByText("Ana Reyes")

    // The directory must be built from guidance activity only. An enrollment
    // fetch would mean the roster is back.
    expect(
      mockedFetchAllPages.mock.calls.filter(([url]) =>
        String(url).includes("/academics/enrollments/")
      )
    ).toHaveLength(0)
  })

  it("lists a student discovered from each of the four activity sources", async () => {
    stub({
      alerts: [
        alert({ id: "ra-1", student: "sp-1", student_name: "Ana Reyes" }),
      ],
      consultations: [
        consultation({ id: "c-1", student: "sp-2", student_name: "Ben Cruz" }),
      ],
      interventions: [
        intervention({
          id: "i-1",
          student: "sp-3",
          student_name: "Cara Diaz",
        }),
      ],
      results: [
        result({
          id: "ar-1",
          student: "sp-4",
          student_name: "Dan Ellis",
          student_id: "S-1004",
        }),
      ],
    })
    renderPage()

    expect(await screen.findByText("Ana Reyes")).toBeInTheDocument()
    expect(screen.getByText("Ben Cruz")).toBeInTheDocument()
    expect(screen.getByText("Cara Diaz")).toBeInTheDocument()
    expect(screen.getByText("Dan Ellis")).toBeInTheDocument()
    // Header row + 4 students.
    expect(screen.getAllByRole("row")).toHaveLength(5)
  })

  it("omits a student who appears only in behavioral notes", async () => {
    // Notes contribute a code but are not themselves an activity type, so a
    // student with nothing but a note is not a guidance student.
    stub({ notes: [note()] })
    renderPage()

    expect(
      await screen.findByText(/No students have guidance activity yet/i)
    ).toBeInTheDocument()
  })

  it("shows an em-dash when no guidance record carries a student code", async () => {
    stub({ alerts: [alert()] })
    renderPage()
    await screen.findByText("Ana Reyes")

    const row = screen.getByText("Ana Reyes").closest("tr") as HTMLElement
    // RiskAlert carries no student number, so the code cell must be an em-dash
    // rather than a raw UUID.
    expect(within(row).getByText("—")).toBeInTheDocument()
    expect(row.textContent).not.toContain("sp-1")
  })

  it("uses the code when a source does carry one", async () => {
    stub({ results: [result()] })
    renderPage()
    await screen.findByText("Ana Reyes")

    const row = screen.getByText("Ana Reyes").closest("tr") as HTMLElement
    expect(within(row).getByText("S-1001")).toBeInTheDocument()
  })

  it("counts only open alerts, and flags at risk only for open moderate/high", async () => {
    stub({
      alerts: [
        alert({ id: "ra-1", status: "active", risk_level: "high" }),
        alert({ id: "ra-2", status: "resolved", risk_level: "high" }),
        alert({ id: "ra-3", status: "escalated", risk_level: "moderate" }),
      ],
    })
    renderPage()
    await screen.findByText("Ana Reyes")

    const row = screen.getByText("Ana Reyes").closest("tr") as HTMLElement
    // Two open alerts (active + escalated); the resolved one does not count.
    expect(within(row).getByText("2")).toBeInTheDocument()
    expect(row).toHaveAttribute("data-at-risk", "true")
    // high wins over moderate.
    expect(within(row).getByText("High")).toHaveAttribute(
      "data-at-risk-level",
      "high"
    )
  })

  it("uses warning semantics for a moderate-only student, not high", async () => {
    stub({ alerts: [alert({ risk_level: "moderate" })] })
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

  it("does not flag a student whose only escalating alert is resolved", async () => {
    stub({ alerts: [alert({ status: "resolved", risk_level: "high" })] })
    renderPage()
    await screen.findByText("Ana Reyes")

    const row = screen.getByText("Ana Reyes").closest("tr") as HTMLElement
    expect(row).toHaveAttribute("data-at-risk", "false")
    expect(within(row).queryByText("High")).toBeNull()
  })

  it("does not flag a student whose only open alert is low", async () => {
    stub({ alerts: [alert({ risk_level: "low" })] })
    renderPage()
    await screen.findByText("Ana Reyes")

    expect(screen.getByText("Ana Reyes").closest("tr")).toHaveAttribute(
      "data-at-risk",
      "false"
    )
  })

  it("counts each activity type separately", async () => {
    stub({
      alerts: [
        alert({ id: "ra-1", status: "active" }),
        alert({ id: "ra-2", status: "active", risk_level: "low" }),
      ],
      consultations: [consultation({ id: "c-1" }), consultation({ id: "c-2" })],
      interventions: [intervention()],
      results: [result()],
    })
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
    stub({
      alerts: [
        alert({ id: "ra-1", student: "sp-1", student_name: "Ana Reyes" }),
      ],
      consultations: [
        consultation({ id: "c-1", student: "sp-2", student_name: "Ben Cruz" }),
      ],
    })
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
    stub({
      alerts: [
        alert({ id: "ra-1", student: "sp-1", student_name: "Ana Reyes" }),
      ],
      results: [
        result({
          id: "ar-1",
          student: "sp-2",
          student_name: "Ben Cruz",
          student_id: "S-1002",
        }),
      ],
    })
    renderPage()
    await screen.findByText("Ana Reyes")

    fireEvent.change(screen.getByLabelText("Search"), {
      target: { value: "S-1002" },
    })
    await waitFor(() => expect(screen.queryByText("Ana Reyes")).toBeNull())
    expect(screen.getByText("Ben Cruz")).toBeInTheDocument()
  })

  it("shows an empty state when filters exclude everything", async () => {
    stub({ alerts: [alert()] })
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
    stub({ alerts: [alert()] })
    renderPage()
    await screen.findByText("Ana Reyes")

    const link = screen
      .getByText("Ana Reyes")
      .closest("tr")
      ?.querySelector("a") as HTMLAnchorElement

    expect(link).toHaveAttribute("href", "/app/students/sp-1")
  })

  it("surfaces a fetch failure", async () => {
    mockedFetchAllPages.mockRejectedValue(new Error("boom"))
    renderPage()

    const alert = await screen.findByRole("alert")
    expect(alert).toHaveTextContent("boom")
  })
})

import { render, screen, waitFor, within } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { apiClient } from "@/lib/api"
import { fetchAllPages } from "@/lib/pagination"

import { StudentProfilePage } from "./StudentProfilePage"

vi.mock("@/lib/pagination", () => ({
  fetchAllPages: vi.fn(),
}))

vi.mock("@/lib/api", () => ({
  API_BASE_URL: "http://localhost:8000/api/v1",
  onSessionExpired: vi.fn(() => () => {}),
  apiClient: {
    get: vi.fn(),
    post: vi.fn(async () => ({ data: {} })),
    patch: vi.fn(async () => ({ data: {} })),
    delete: vi.fn(async () => ({ data: undefined })),
  },
}))

const mockedFetchAllPages = vi.mocked(fetchAllPages)
const mockedGet = vi.mocked(apiClient.get)

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
    id: "en-9",
    student: "sp-9",
    student_name: "Other Student",
    student_id: "S-9999",
    section: "sec-c",
    section_name: "Grade 12-A",
    academic_year: "ay-1",
    academic_year_name: "2025-2026",
    date_enrolled: "2025-01-10",
    is_active: true,
  },
]

const grades = [
  {
    id: "g-1",
    subject_name: "Mathematics",
    subject_code: "MATH-10",
    section_name: "Grade 10-A",
    grading_period_name: "Term 1",
    score: "88.50",
    letter_grade: "B+",
  },
  {
    id: "g-2",
    subject_name: "English",
    subject_code: "ENG-10",
    section_name: "Grade 10-A",
    grading_period_name: null,
    score: null,
    letter_grade: "A",
  },
]

const riskAlerts = [
  {
    id: "ra-1",
    student: "sp-1",
    student_name: "Ana Reyes",
    risk_level: "high",
    // The real ai_engine decision-path shape. PH11.8 typed this as string[],
    // so an algorithm alert rendered "[object Object]" on this page.
    risk_factors: [
      {
        feature: "attendance_rate",
        threshold: 0.75,
        value: 0.62,
        direction: "below",
      },
    ],
    source: "algorithm",
    status: "active",
    assigned_counselor: null,
    assigned_counselor_name: null,
    generated_at: "2025-01-30T00:00:00Z",
    last_updated: "2025-01-30T00:00:00Z",
    created_at: "2025-01-30T00:00:00Z",
    updated_at: "2025-01-30T00:00:00Z",
  },
  {
    id: "ra-2",
    student: "sp-9",
    student_name: "Other Student",
    risk_level: "high",
    risk_factors: [],
    source: "algorithm",
    status: "active",
    assigned_counselor: null,
    assigned_counselor_name: null,
    generated_at: "2025-01-30T00:00:00Z",
    last_updated: "2025-01-30T00:00:00Z",
    created_at: "2025-01-30T00:00:00Z",
    updated_at: "2025-01-30T00:00:00Z",
  },
]

const consultations = [
  {
    id: "c-1",
    student: "sp-1",
    student_name: "Ana Reyes",
    counselor: "gp-1",
    counselor_name: "Robin Vega",
    session_date: "2025-02-10",
    session_time: "09:30:00",
    session_type: "individual_counseling",
    concern_categories: ["academic"],
    session_notes: "Reviewed midterm results.",
    recommendations: null,
    next_session_date: null,
    priority_level: "high",
    status: "ongoing",
    created_at: "2025-02-10T00:00:00Z",
    updated_at: "2025-02-10T00:00:00Z",
  },
  {
    id: "c-9",
    student: "sp-9",
    student_name: "Other Student",
    counselor: "gp-9",
    counselor_name: "Other Counselor",
    session_date: "2025-02-10",
    session_time: "09:30:00",
    session_type: "group",
    concern_categories: [],
    session_notes: "Not this student.",
    recommendations: null,
    next_session_date: null,
    priority_level: "low",
    status: "ongoing",
    created_at: "2025-02-10T00:00:00Z",
    updated_at: "2025-02-10T00:00:00Z",
  },
]

const interventions = [
  {
    id: "i-1",
    student: "sp-1",
    student_name: "Ana Reyes",
    risk_alert: "ra-1",
    risk_alert_student: "Ana Reyes",
    assigned_counselor: "gp-1",
    assigned_counselor_name: "Robin Vega",
    plan_start_date: "2025-02-01",
    target_review_date: "2025-03-01",
    status: "active",
    created_at: "2025-02-01T00:00:00Z",
    updated_at: "2025-02-01T00:00:00Z",
  },
]

const behavioralNotes = [
  {
    id: "bn-1",
    student: "sp-1",
    student_name: "Ana Reyes",
    student_id_code: "S-1001",
    recorded_by: "f-1",
    recorded_by_name: "Sam Faculty",
    note_type: "positive",
    note_text: "Helped a classmate during group work.",
    date_recorded: "2025-02-05",
    created_at: "2025-02-05T00:00:00Z",
    updated_at: "2025-02-05T00:00:00Z",
  },
]

const assessments = [
  {
    id: "a-1",
    title: "Wellness Check-In",
    description: null,
    assessment_type: "wellness",
    is_published: true,
    created_at: "2025-01-01T00:00:00Z",
    target_sections: [],
    target_students: [],
  },
]

const assessmentResults = [
  {
    id: "ar-1",
    student: "sp-1",
    assessment: "a-1",
    assessment_title: "Wellness Check-In",
    student_name: "Ana Reyes",
    student_id: "S-1001",
    score: "8.00",
    total_possible: "10.00",
    percentage: "80.00",
    status: "completed",
    started_at: "2025-02-01T00:00:00Z",
    completed_at: "2025-02-01T01:00:00Z",
  },
]

const report = {
  student: "sp-1",
  student_name: "Ana Reyes",
  student_id_code: "S-1001",
  behavioral_note_counts: { positive: 1, warning: 0, incident: 2 },
  consultation_summary: {
    total: 1,
    by_status: { ongoing: 1 },
    by_priority: { high: 1 },
  },
  intervention_summary: { total: 1, active: 1, completed: 0, cancelled: 0 },
  risk_alert_history: [
    {
      id: "ra-1",
      risk_level: "high",
      status: "active",
      source: "manual",
      generated_at: "2025-01-30T00:00:00Z",
    },
  ],
}

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <MemoryRouter initialEntries={["/app/students/sp-1"]}>
      <QueryClientProvider client={client}>
        <Routes>
          <Route
            path="/app/students/:studentId"
            element={<StudentProfilePage />}
          />
        </Routes>
      </QueryClientProvider>
    </MemoryRouter>
  )
}

/**
 * Wait for the student identity heading.
 *
 * The page cannot render its heading until `useGuidanceStudents` resolves, and
 * that query is gated behind five other queries:
 *
 *     enabled: !alertsQuery.isLoading && !consultationsQuery.isLoading &&
 *              !interventionsQuery.isLoading && !resultsQuery.isLoading &&
 *              !notesQuery.isLoading
 *
 * So a single assertion waits out six sequential resolution rounds rather than
 * one. Testing Library's default `findBy` timeout is 1000ms, which is ample when
 * this file runs alone but not when the whole suite runs in parallel and the
 * worker is competing for CPU — the query chain then resolves slower than the
 * default allows and the wait times out even though nothing is wrong.
 *
 * The wait budget is raised rather than the assertion changed: the heading and
 * its name are still required exactly as before. This test file was flaky at
 * PH11.9's baseline commit (reproduced 3 failures in 4 full-suite runs, passing
 * when the file runs alone), so the flake predates this phase.
 *
 * `level: 2` since PH11.11. This page was mounted directly, without the shell,
 * so it used to carry the document's own `h1`. Under `AppShell` the header owns
 * the `h1` and the page's title sits one level below it, which is why the level
 * is now asserted as 2 rather than dropped — the heading is still required, and
 * the level is still pinned, because a silent change of either is exactly the
 * regression this helper exists to catch.
 */
const RESOLVE_TIMEOUT_MS = 5000

function findStudentHeading() {
  return screen.findByRole(
    "heading",
    { name: "Ana Reyes", level: 2 },
    { timeout: RESOLVE_TIMEOUT_MS }
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  mockedFetchAllPages.mockImplementation(async (url: string) => {
    if (url.includes("/academics/enrollments/")) {
      return { count: enrollments.length, results: enrollments }
    }
    if (url.includes("/academics/grades/")) {
      return { count: grades.length, results: grades }
    }
    if (url.includes("/guidance/risk-alerts/")) {
      return { count: riskAlerts.length, results: riskAlerts }
    }
    if (url.includes("/guidance/consultations/")) {
      return { count: consultations.length, results: consultations }
    }
    if (url.includes("/guidance/interventions/")) {
      return { count: interventions.length, results: interventions }
    }
    if (url.includes("/guidance/behavioral-notes/")) {
      return { count: behavioralNotes.length, results: behavioralNotes }
    }
    if (url.includes("/assessments/assessments/")) {
      return { count: assessments.length, results: assessments }
    }
    if (url.includes("/assessments/assessment-results/")) {
      return { count: assessmentResults.length, results: assessmentResults }
    }
    return { count: 0, results: [] }
  })
  mockedGet.mockImplementation(async (url: string) => {
    if (url.startsWith("/guidance/reports/student/")) {
      return { data: report } as never
    }
    if (url.startsWith("/attendance/summary/")) {
      return {
        data: [
          {
            student: "sp-1",
            student_name: "Ana Reyes",
            student_id_code: "S-1001",
            section_name: "Grade 10-A",
            present_count: 10,
            late_count: 1,
            absent_count: 2,
            total_records: 13,
          },
        ],
      } as never
    }
    return { data: [] } as never
  })
})

describe("StudentProfilePage", () => {
  it("shows the guidance-activity identity for the routed student", async () => {
    renderPage()

    expect(await findStudentHeading()).toBeInTheDocument()
    // The code comes from a guidance record (the assessment result fixture),
    // not from an enrollment roster.
    expect(screen.getByText("S-1001")).toBeInTheDocument()
  })

  it("shows an em-dash when no guidance record carries a code", async () => {
    // Ana's only activity here is a risk alert, which has no code field.
    mockedFetchAllPages.mockImplementation(async (url: string) => {
      if (url.includes("/academics/enrollments/")) {
        return { count: enrollments.length, results: enrollments }
      }
      if (url.includes("/guidance/risk-alerts/")) {
        return { count: riskAlerts.length, results: riskAlerts }
      }
      return { count: 0, results: [] }
    })

    renderPage()

    // Assert on the identity header's stable `data-student-code` hook rather
    // than a global `findByText("—")`. The grades table renders its own "—" in
    // up to three cells per row, so a document-wide text query resolves
    // differently depending on which independent query happened to settle
    // first — it passed or threw "Found multiple elements" purely on timing.
    const absent = await findStudentHeading()
    await waitFor(() => {
      expect(
        within(absent.parentElement as HTMLElement).getByText("—")
      ).toHaveAttribute("data-student-code", "absent")
    })
  })

  it("requests the server-filtered grade endpoint for this student only", async () => {
    renderPage()
    await findStudentHeading()

    expect(mockedFetchAllPages).toHaveBeenCalledWith(
      "/academics/grades/?student=sp-1&status=finalized"
    )
  })

  it("requests the server-filtered attendance summary for this student", async () => {
    renderPage()
    await findStudentHeading()

    expect(mockedGet).toHaveBeenCalledWith("/attendance/summary/?student=sp-1")
  })

  it("normalizes decimal grade strings to numbers", async () => {
    renderPage()
    await findStudentHeading()

    // "88.50" arrives as a DRF decimal string; it must not render as such.
    expect(await screen.findByText("88.5")).toBeInTheDocument()
  })

  it("shows a dash for an unset grade score", async () => {
    renderPage()
    await findStudentHeading()

    await screen.findByText("English")
    const row = screen.getByText("English").closest("tr") as HTMLElement
    expect(within(row).getAllByText("—").length).toBeGreaterThanOrEqual(1)
  })

  it("shows attendance record counts and no invented rate", async () => {
    renderPage()
    await findStudentHeading()

    const present = await screen.findByText("Present")
    const presentCard = present.parentElement as HTMLElement
    expect(within(presentCard).getByText("10")).toBeInTheDocument()

    // The endpoint has no possible-day denominator, so the attendance block
    // offers counts only — no percentage, and it says so.
    const attendanceHeading = screen.getByText("Attendance", {
      selector: "[data-slot='card-title']",
    })
    const attendanceCard = attendanceHeading.closest(
      "[data-slot='card']"
    ) as HTMLElement
    expect(attendanceCard.textContent).not.toContain("%")
    expect(
      screen.getByText(/does not report total possible school days/i)
    ).toBeInTheDocument()
  })

  it("keeps another student's records out of the profile", async () => {
    renderPage()
    await findStudentHeading()

    await screen.findByText("Reviewed midterm results.")
    expect(screen.queryByText("Not this student.")).toBeNull()
    expect(screen.queryByText("Other Student")).toBeNull()
  })

  it("marks the student at risk with the level that actually applies", async () => {
    renderPage()
    await findStudentHeading()

    const badge = await screen.findByText(/At risk \(High\)/)
    expect(badge).toHaveAttribute("data-at-risk", "true")
    expect(badge).toHaveAttribute("data-at-risk-level", "high")
  })

  it("uses warning semantics when the worst open alert is moderate", async () => {
    mockedFetchAllPages.mockImplementation(async (url: string) => {
      if (url.includes("/guidance/risk-alerts/")) {
        return {
          count: 1,
          results: [{ ...riskAlerts[0], risk_level: "moderate" }],
        }
      }
      if (url.includes("/academics/enrollments/")) {
        return { count: enrollments.length, results: enrollments }
      }
      return { count: 0, results: [] }
    })

    renderPage()
    await findStudentHeading()

    const badge = await screen.findByText(/At risk \(Moderate\)/)
    expect(badge).toHaveAttribute("data-at-risk-level", "moderate")
    // Moderate must not be painted with the destructive/high treatment.
    expect(badge.className).toContain("text-warning-foreground")
    expect(badge.className).not.toContain("text-destructive")
  })

  it("does not mark a student at risk when their only moderate/high alert is resolved", async () => {
    mockedFetchAllPages.mockImplementation(async (url: string) => {
      if (url.includes("/guidance/risk-alerts/")) {
        return {
          count: 1,
          results: [{ ...riskAlerts[0], status: "resolved" }],
        }
      }
      if (url.includes("/academics/enrollments/")) {
        return { count: enrollments.length, results: enrollments }
      }
      return { count: 0, results: [] }
    })

    renderPage()
    await findStudentHeading()

    // The alert still renders in the history, but the at-risk badge must not.
    await waitFor(() => expect(screen.queryByText("At risk")).toBeNull())
    expect(screen.getByText("resolved")).toBeInTheDocument()
  })

  it("renders the summary tiles from own-counselor data, not report totals", async () => {
    renderPage()
    await findStudentHeading()

    // The fixture's report claims total 1 for both, matching the counselor's
    // own single record, so this only proves the tiles render.
    const consultTile = document.querySelector(
      '[data-count-source="own-consultations"]'
    ) as HTMLElement
    expect(consultTile).toHaveTextContent("Your consultations")
    expect(within(consultTile).getByText("1")).toBeInTheDocument()

    const interventionTile = document.querySelector(
      '[data-count-source="own-interventions"]'
    ) as HTMLElement
    expect(within(interventionTile).getByText("1")).toBeInTheDocument()
  })

  /**
   * Regression: `GuidanceReportView` filters `ConsultationRecord` and
   * `Intervention` by `student` only, with no counselor scope, so its summary
   * totals include every counselor's records. The tiles must therefore come
   * from the caller's own collections, which cannot disagree with the lists
   * rendered directly below them.
   */
  it("ignores report totals that include other counselors", async () => {
    mockedGet.mockImplementation(async (url: string) => {
      if (url.startsWith("/guidance/reports/student/")) {
        return {
          data: {
            ...report,
            // Three of each: two belong to colleagues.
            consultation_summary: { total: 3, by_status: {}, by_priority: {} },
            intervention_summary: {
              total: 3,
              active: 3,
              completed: 0,
              cancelled: 0,
            },
          },
        } as never
      }
      if (url.startsWith("/attendance/summary/")) {
        return { data: [] } as never
      }
      return { data: [] } as never
    })

    renderPage()
    await findStudentHeading()

    // The counselor recorded exactly one of each.
    const consultTile = document.querySelector(
      '[data-count-source="own-consultations"]'
    ) as HTMLElement
    expect(within(consultTile).getByText("1")).toBeInTheDocument()
    expect(consultTile.textContent).not.toContain("3")

    const interventionTile = document.querySelector(
      '[data-count-source="own-interventions"]'
    ) as HTMLElement
    expect(within(interventionTile).getByText("1")).toBeInTheDocument()
    expect(interventionTile.textContent).not.toContain("3")

    // And the counts match the rendered lists.
    expect(screen.getAllByText("Reviewed midterm results.")).toHaveLength(1)
  })

  it("renders behavioral note counts from the report", async () => {
    renderPage()
    await findStudentHeading()

    expect(
      await screen.findByText(/Positive 1 · Warning 0 · Incident 2/)
    ).toBeInTheDocument()
  })

  it("renders the student's own assessment results with a percentage", async () => {
    renderPage()
    await findStudentHeading()

    expect(await screen.findByText("Wellness Check-In")).toBeInTheDocument()
    // `percentage` is a 0-100 decimal, not a 0-1 ratio.
    expect(screen.getByText("80%")).toBeInTheDocument()
  })

  it("reports no attendance rather than fake zeros when the summary is empty", async () => {
    mockedGet.mockImplementation(async (url: string) => {
      if (url.startsWith("/attendance/summary/")) return { data: [] } as never
      if (url.startsWith("/guidance/reports/student/")) {
        return { data: report } as never
      }
      return { data: [] } as never
    })

    renderPage()
    await findStudentHeading()

    expect(
      await screen.findByText(/No attendance records found/i)
    ).toBeInTheDocument()
  })

  it("keeps one section working when the grade endpoint fails", async () => {
    mockedFetchAllPages.mockImplementation(async (url: string) => {
      if (url.includes("/academics/grades/")) throw new Error("grades down")
      if (url.includes("/academics/enrollments/")) {
        return { count: enrollments.length, results: enrollments }
      }
      if (url.includes("/guidance/behavioral-notes/")) {
        return { count: behavioralNotes.length, results: behavioralNotes }
      }
      return { count: 0, results: [] }
    })

    renderPage()
    await findStudentHeading()

    expect(await screen.findByText("grades down")).toBeInTheDocument()
    // Behavioral notes still render.
    expect(
      await screen.findByText("Helped a classmate during group work.")
    ).toBeInTheDocument()
  })

  it("links back to the roster", async () => {
    renderPage()
    await findStudentHeading()

    expect(
      screen.getByRole("link", { name: /back to roster/i })
    ).toHaveAttribute("href", "/app/students")
  })
})

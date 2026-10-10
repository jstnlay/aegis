import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import type { ReactNode } from "react"
import { AxiosError, AxiosHeaders } from "axios"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { FacultyAdvisoryPage } from "./FacultyAdvisoryPage"
import { apiClient } from "@/lib/api"
import { fetchAllPages } from "@/lib/pagination"

/**
 * TC-FAC-07 / TC-FAC-08 — the faculty advisory surface.
 *
 * The QA log recorded "Add behavioral note" and "Reject blank note" as
 * implemented-but-failing because no faculty UI existed: the endpoint was
 * already there (`BehavioralNoteViewSet`, `IsFacultyUser`, section-scoped).
 * These tests pin the frontend half — the scoped roster, a saved note going
 * to the real endpoint, and the blank rejection using the server's own
 * wording without firing a request.
 *
 * TC-FAC-03 / TC-FAC-04 — the manage-profile dialog on the same roster: the
 * saved values load, the full write contract is what gets sent, and a
 * server rejection names the field instead of saving an incomplete record.
 */

vi.mock("@/lib/api", () => ({
  apiClient: { get: vi.fn(), post: vi.fn(), patch: vi.fn() },
}))

vi.mock("@/lib/pagination", () => ({
  fetchAllPages: vi.fn(),
}))

const mockedPost = vi.mocked(apiClient.post)
const mockedPatch = vi.mocked(apiClient.patch)
const mockedGet = vi.mocked(apiClient.get)
const mockedFetchAllPages = vi.mocked(fetchAllPages)

const roster = [
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
    // Inactive enrollments are filtered out: the server's create path only
    // accepts an active enrollment, so offering this student would only
    // produce a failed save.
    id: "en-2",
    student: "sp-2",
    student_name: "Inactive Student",
    student_id: "S-1002",
    section: "sec-a",
    section_name: "Grade 10-A",
    academic_year: "ay-1",
    academic_year_name: "2025-2026",
    date_enrolled: "2025-01-10",
    is_active: false,
  },
]

const savedNote = {
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
}

const gradeLevels = [
  { id: "gl-7", name: "Grade 7", level_number: 7 },
  { id: "gl-8", name: "Grade 8", level_number: 8 },
]

const sections = [
  {
    id: "sec-a",
    name: "Grade 10-A",
    grade_level: "gl-7",
    grade_level_name: "Grade 7",
    academic_year: "ay-1",
    adviser: "fp-1",
    adviser_name: "Sam Faculty",
  },
  {
    id: "sec-b",
    name: "Newton",
    grade_level: "gl-8",
    grade_level_name: "Grade 8",
    academic_year: "ay-1",
    adviser: null,
    adviser_name: null,
  },
]

const savedProfile = {
  id: "sp-1",
  student_name: "Ana Reyes",
  student_id: "S-1001",
  grade_level: "gl-7",
  section: "sec-a",
  guardian_contact: "0917-555-0100",
  date_of_birth: "2010-04-15",
  is_active: true,
}

/** `/attendance/summary/` rows for the roster's active student. */
const attendanceSummary = [
  {
    student: "sp-1",
    student_name: "Ana Reyes",
    student_id_code: "S-1001",
    section_name: "Grade 10-A",
    present_count: 12,
    late_count: 2,
    absent_count: 1,
    total_records: 15,
  },
]

/** One grade for the same student, so the class average is real. */
const facultyGrades = [
  {
    id: "g-1",
    student: "sp-1",
    student_name: "Ana Reyes",
    student_id: "S-1001",
    subject_assignment: "sa-1",
    subject_name: "Mathematics",
    subject_code: "MATH-101",
    section_name: "Grade 10-A",
    grading_period: "gp-1",
    grading_period_name: "First Quarter",
    score: 90,
    letter_grade: "A",
    remarks: null,
    encoded_by: "fp-1",
    encoded_by_name: "Sam Faculty",
    status: "draft",
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  },
]

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  )
  return render(<FacultyAdvisoryPage />, { wrapper })
}

/**
 * Render and wait for the roster query to land.
 *
 * The roster backs the summary table, the note form's student list and the
 * manage-profile action, so a test that interacts with any of them must
 * wait for a roster row rather than for a summary caption (which renders
 * while the roster is still loading).
 */
async function renderLoadedPage() {
  renderPage()
  return screen.findByRole("button", { name: /manage profile/i })
}

function validationError(field: string, message: string): AxiosError {
  // The envelope `BehavioralNoteSerializer` failures arrive in.
  return new AxiosError(
    "Request failed with status code 400",
    undefined,
    undefined,
    undefined,
    {
      data: {
        success: false,
        error: {
          code: "VALIDATION_ERROR",
          message: "Some fields are invalid.",
          details: { [field]: [message] },
        },
      },
      status: 400,
      statusText: "",
      headers: new AxiosHeaders(),
      config: { headers: new AxiosHeaders() },
    }
  )
}

beforeEach(() => {
  mockedFetchAllPages.mockImplementation(async (url: string) => {
    if (url === "/academics/enrollments/") {
      return { count: roster.length, results: roster }
    }
    if (url === "/guidance/behavioral-notes/") {
      return { count: 1, results: [savedNote] }
    }
    if (url === "/academics/grade-levels/") {
      return { count: gradeLevels.length, results: gradeLevels }
    }
    if (url === "/academics/sections/") {
      return { count: sections.length, results: sections }
    }
    return { count: 0, results: [] }
  })
  mockedGet.mockImplementation(async (url: string) => {
    // `/attendance/summary/` returns a bare array, not an envelope.
    if (url === "/attendance/summary/") {
      return { data: attendanceSummary }
    }
    if (url === "/academics/student-profiles/sp-1/") {
      return { data: savedProfile }
    }
    return { data: [] }
  })
  mockedPost.mockResolvedValue({ data: savedNote })
  mockedPatch.mockResolvedValue({ data: savedProfile })
})

describe("FacultyAdvisoryPage roster", () => {
  it("lists the scoped active enrollments and the saved notes", async () => {
    renderPage()

    expect(await screen.findAllByText("Ana Reyes")).not.toHaveLength(0)
    // The ID appears in both the roster and the summary table, so the roster
    // assertion is "at least one of them", not "exactly one".
    expect(screen.getAllByText("S-1001").length).toBeGreaterThan(0)
    expect(screen.getAllByText("Grade 10-A").length).toBeGreaterThan(0)
    // Inactive enrollment is not offered.
    expect(screen.queryByText("Inactive Student")).not.toBeInTheDocument()
    // The notes list renders the saved note.
    expect(
      screen.getByText("Helped a classmate during group work.")
    ).toBeInTheDocument()
  })

  it("shows an empty state rather than a silent blank list", async () => {
    mockedFetchAllPages.mockResolvedValue({ count: 0, results: [] })
    renderPage()

    expect(
      await screen.findAllByText(
        /No students are enrolled in your sections yet/i
      )
    ).not.toHaveLength(0)
  })
})

describe("FacultyAdvisoryPage note creation (TC-FAC-07)", () => {
  it("saves a note to the real endpoint and confirms it", async () => {
    await renderLoadedPage()

    fireEvent.click(screen.getByRole("button", { name: "Student" }))
    fireEvent.click(
      await screen.findByRole("option", { name: /Ana Reyes \(S-1001\)/ })
    )

    fireEvent.change(screen.getByPlaceholderText("What did you observe?"), {
      target: { value: "Stayed after class to help a classmate." },
    })
    fireEvent.click(
      screen.getByRole("button", { name: /save behavioral note/i })
    )

    await waitFor(() =>
      expect(mockedPost).toHaveBeenCalledWith(
        "/guidance/behavioral-notes/",
        expect.objectContaining({
          student: "sp-1",
          note_type: "positive",
          note_text: "Stayed after class to help a classmate.",
          date_recorded: expect.stringMatching(/^\d{4}-\d{2}-\d{2}$/),
        })
      )
    )
    expect(await screen.findByRole("status")).toHaveTextContent(
      /saved to the student/i
    )
  })
})

describe("FacultyAdvisoryPage blank rejection (TC-FAC-08)", () => {
  it("rejects a blank note with the server's wording and sends nothing", async () => {
    await renderLoadedPage()

    fireEvent.click(
      screen.getByRole("button", { name: /save behavioral note/i })
    )

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Note text cannot be empty."
    )
    // No round trip for the obvious client-side case.
    expect(mockedPost).not.toHaveBeenCalled()
    // The form stays usable so the user can type and resubmit.
    expect(
      screen.getByRole("button", { name: /save behavioral note/i })
    ).toBeEnabled()
  })

  it("surfaces the server's own field validation when it rejects the save", async () => {
    // The serializer refuses a future date; the client mirrors the date input's
    // `max`, but a stale tab or clock skew means the server stays the
    // authority and its message must be the one the user sees.
    mockedPost.mockRejectedValue(
      validationError("date_recorded", "Date recorded cannot be in the future.")
    )
    await renderLoadedPage()

    fireEvent.change(screen.getByPlaceholderText("What did you observe?"), {
      target: { value: "Helped a classmate during group work." },
    })
    fireEvent.change(screen.getByLabelText(/date recorded/i), {
      target: { value: "2999-01-01" },
    })
    fireEvent.click(
      screen.getByRole("button", { name: /save behavioral note/i })
    )

    const alert = await screen.findByRole("alert")
    expect(alert).toHaveTextContent("Date recorded cannot be in the future.")
    await waitFor(() => expect(mockedPost).toHaveBeenCalled())
  })
})

describe("FacultyAdvisoryPage profile management (TC-FAC-03/04)", () => {
  async function openManageProfile() {
    await renderLoadedPage()
    fireEvent.click(screen.getByRole("button", { name: /manage profile/i }))
    return screen.findByRole("dialog")
  }

  it("opens the manage form with the server's saved values (TC-FAC-03)", async () => {
    const dialog = await openManageProfile()

    await within(dialog).findByText(/ana reyes \(s-1001\)/i)
    expect(
      (within(dialog).getByLabelText(/guardian contact/i) as HTMLInputElement)
        .value
    ).toBe("0917-555-0100")
    expect(
      (within(dialog).getByLabelText(/date of birth/i) as HTMLInputElement)
        .value
    ).toBe("2010-04-15")
    // Reference data is loaded for the required selects.
    expect(mockedFetchAllPages).toHaveBeenCalledWith("/academics/grade-levels/")
    expect(mockedFetchAllPages).toHaveBeenCalledWith("/academics/sections/")
  })

  it("saves the profile with the full write contract and closes", async () => {
    const dialog = await openManageProfile()
    await within(dialog).findByText(/ana reyes \(s-1001\)/i)

    fireEvent.click(
      within(dialog).getByRole("button", { name: /save profile/i })
    )

    await waitFor(() =>
      expect(mockedPatch).toHaveBeenCalledWith(
        "/academics/student-profiles/sp-1/",
        {
          grade_level: "gl-7",
          section: "sec-a",
          guardian_contact: "0917-555-0100",
          date_of_birth: "2010-04-15",
        }
      )
    )
    await waitFor(() =>
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
    )
  })

  it("keeps the dialog open and names the field when the server rejects (TC-FAC-04)", async () => {
    mockedPatch.mockRejectedValue(
      validationError("guardian_contact", "This field may not be null.")
    )
    const dialog = await openManageProfile()
    await within(dialog).findByText(/ana reyes \(s-1001\)/i)

    fireEvent.click(
      within(dialog).getByRole("button", { name: /save profile/i })
    )

    expect(
      await within(dialog).findByText("This field may not be null.")
    ).toBeInTheDocument()
    // The incomplete profile was not accepted as saved.
    expect(screen.getByRole("dialog")).toBeInTheDocument()
  })

  /**
   * Regression: reopening the dialog after a save used to render the cached
   * pre-save profile, so the form showed the values the save had just
   * corrected (found by driving the real page in a browser — the API had the
   * new value, the dialog still showed the old one).
   */
  it("reopens on the freshly saved profile, not the cached pre-save one", async () => {
    const dialog = await openManageProfile()
    await within(dialog).findByText(/ana reyes \(s-1001\)/i)

    fireEvent.change(within(dialog).getByLabelText(/guardian contact/i), {
      target: { value: "0917-555-0199" },
    })
    fireEvent.click(
      within(dialog).getByRole("button", { name: /save profile/i })
    )
    await waitFor(() =>
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
    )

    // The server now returns the saved value for any later read.
    mockedGet.mockImplementation(async (url: string) => {
      if (url === "/academics/student-profiles/sp-1/") {
        return { data: { ...savedProfile, guardian_contact: "0917-555-0199" } }
      }
      if (url === "/attendance/summary/") return { data: attendanceSummary }
      return { data: [] }
    })

    fireEvent.click(screen.getByRole("button", { name: /manage profile/i }))

    const reopened = await screen.findByRole("dialog")
    // While the fresh copy is in flight the form must not seed stale values.
    expect(within(reopened).queryByLabelText(/guardian contact/i)).toBeNull()
    await waitFor(() =>
      expect(
        (
          within(reopened).getByLabelText(
            /guardian contact/i
          ) as HTMLInputElement
        ).value
      ).toBe("0917-555-0199")
    )
  })

  it("says the profile is gone when the student left the faculty's scope", async () => {
    mockedGet.mockRejectedValue(
      new AxiosError("Not found", undefined, undefined, undefined, {
        data: {
          success: false,
          error: { code: "NOT_FOUND", message: "Not found.", details: null },
        },
        status: 404,
        statusText: "",
        headers: new AxiosHeaders(),
        config: { headers: new AxiosHeaders() },
      })
    )
    const dialog = await openManageProfile()

    expect(
      await within(dialog).findByText(/not available to you any more/i)
    ).toBeInTheDocument()
  })
})

describe("FacultyAdvisoryPage class summary (TC-FAC-17)", () => {
  beforeEach(() => {
    mockedFetchAllPages.mockImplementation(async (url: string) => {
      if (url === "/academics/enrollments/") {
        return { count: roster.length, results: roster }
      }
      if (url.startsWith("/academics/grades")) {
        return { count: facultyGrades.length, results: facultyGrades }
      }
      return { count: 0, results: [] }
    })
  })

  it("shows real attendance counts and the grade average per student", async () => {
    await renderLoadedPage()

    // The summary table only leaves its loading state once all three
    // sources resolve, so the caption is not a safe wait — a row is.
    expect(await screen.findByText("12")).toBeInTheDocument()
    expect(screen.getByText("15")).toBeInTheDocument()
    // The single recorded score of 90.
    expect(screen.getByText("90.00")).toBeInTheDocument()
  })

  it("downloads the same summary through the export endpoint", async () => {
    mockedGet.mockImplementation(async (url: string) => {
      if (url === "/data-import/exports/advisory/") {
        return {
          data: new Blob(["student_id\nSTU-001\n"], { type: "text/csv" }),
          headers: {
            "content-disposition":
              "attachment; filename*=UTF-8''aegis_advisory_export.csv",
          },
        }
      }
      return { data: [] }
    })
    await renderLoadedPage()

    fireEvent.click(
      screen.getByRole("button", { name: /download summary \(csv\)/i })
    )

    await waitFor(() =>
      expect(mockedGet).toHaveBeenCalledWith("/data-import/exports/advisory/", {
        params: { file_format: "csv" },
        responseType: "blob",
      })
    )
  })
})

import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { AttendancePage } from "@/features/attendance/AttendancePage"
import { apiClient } from "@/lib/api"
import { fetchAllPages } from "@/lib/pagination"
import type { Role, User } from "@/types/auth"

vi.mock("@/features/auth/AuthContext", () => ({
  useAuth: () => ({ user: authState.user }),
}))

vi.mock("@/lib/pagination", () => ({
  fetchAllPages: vi.fn(async () => ({ count: 0, results: [] })),
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

const authState = vi.hoisted(() => ({ user: null as User | null }))
const mockedFetchAllPages = vi.mocked(fetchAllPages)

function makeUser(role: Role, id = `u-${role}`): User {
  return {
    id,
    email: `${role}@school.edu`,
    username: role,
    first_name: "Test",
    last_name: role,
    role,
    phone_number: null,
    address: null,
    language_preference: null,
    is_active: true,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  }
}

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <AttendancePage />
    </QueryClientProvider>
  )
}

function enrollment(overrides: Record<string, unknown> = {}) {
  return {
    id: `enr-${Math.random().toString(36).slice(2, 8)}`,
    student: "sp-1",
    student_name: "Ana Cruz",
    student_id: "STU-001",
    section: "sec-1",
    section_name: "Section A",
    academic_year: "ay-1",
    academic_year_name: "2025-2026",
    date_enrolled: null,
    is_active: true,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    ...overrides,
  }
}

function section(overrides: Record<string, unknown> = {}) {
  return {
    id: "sec-1",
    name: "Einstein",
    grade_level: "gl-1",
    grade_level_name: "Grade 7",
    academic_year: "ay-1",
    adviser: "fp-9",
    adviser_name: "Dr. Reyes",
    ...overrides,
  }
}

function record(overrides: Record<string, unknown> = {}) {
  return {
    id: "ar-1",
    student: "sp-1",
    student_name: "Ana Cruz",
    student_id_code: "STU-001",
    section: "sec-1",
    section_name: "Einstein",
    date: "2026-03-02",
    status: "present",
    recorded_by: "fp-9",
    recorded_by_name: "Dr. Reyes",
    created_at: "2026-03-02T08:00:00Z",
    updated_at: "2026-03-02T08:00:00Z",
    ...overrides,
  }
}

/**
 * The roster selects are searchable listboxes: a button trigger opens a
 * popover with a filter input and `role="option"` rows. Clicking the trigger
 * then the option exercises the real component with no extra dependency.
 */
async function openSearchSelect(trigger: HTMLElement) {
  // The trigger renders disabled while its options load; a disabled trigger
  // ignores clicks, so wait for it to become interactive.
  await waitFor(() => expect(trigger).toBeEnabled())
  fireEvent.click(trigger)
}

function chooseOption(option: HTMLElement) {
  fireEvent.click(option)
}

/** Routes the paginated helper by URL so each hook gets its own fixture. */
function routePagedRequests(routes: {
  records?: unknown[]
  sections?: unknown[]
  enrollments?: unknown[]
}) {
  mockedFetchAllPages.mockImplementation(async (url: string) => {
    if (url.startsWith("/attendance/records/")) {
      const results = routes.records ?? []
      return { count: results.length, results }
    }
    if (url.startsWith("/academics/sections/")) {
      const results = routes.sections ?? []
      return { count: results.length, results }
    }
    if (url.startsWith("/academics/enrollments/")) {
      const results = routes.enrollments ?? []
      return { count: results.length, results }
    }
    return { count: 0, results: [] }
  })
}

beforeEach(() => {
  authState.user = null
  vi.clearAllMocks()
  mockedFetchAllPages.mockResolvedValue({ count: 0, results: [] })
  // Restated every test rather than left to the mock factory: `clearAllMocks`
  // clears calls, not implementations, so a URL-routed `get` override from
  // one test would otherwise keep serving its fixture to the tests after it.
  vi.mocked(apiClient.get).mockResolvedValue({ data: [] })
})

describe("AttendancePage (student)", () => {
  beforeEach(() => {
    authState.user = makeUser("student")
  })

  it("renders the attendance heading", async () => {
    renderPage()
    expect(
      await screen.findByRole("heading", { name: "Attendance", level: 2 })
    ).toBeInTheDocument()
  })

  it("shows both records and summary surfaces", async () => {
    renderPage()
    expect(await screen.findByText("Records")).toBeInTheDocument()
    expect(screen.getByText("Summary")).toBeInTheDocument()
  })

  it("does not offer the faculty recording form", () => {
    renderPage()
    expect(screen.queryByText(/Take attendance/i)).not.toBeInTheDocument()
  })

  it("requests the student-scoped attendance endpoints", async () => {
    mockedFetchAllPages.mockResolvedValue({
      count: 0,
      results: [
        {
          id: "enr-1",
          student: "sp-1",
          student_name: "Ana Cruz",
          student_id: "STU-001",
          section: "sec-1",
          section_name: "Section A",
          academic_year: "ay-1",
          academic_year_name: "2025-2026",
          date_enrolled: null,
          is_active: true,
          created_at: "2026-01-01T00:00:00Z",
          updated_at: "2026-01-01T00:00:00Z",
        },
      ],
    })

    renderPage()

    await waitFor(() => {
      const urls = mockedFetchAllPages.mock.calls.map((c) => String(c[0]))
      expect(urls.some((u) => u.startsWith("/attendance/records/"))).toBe(true)
    })
  })

  /**
   * Round 3 of the manual-QA UX pass: the per-section six-pixel rate bars
   * became one stacked present/late/absent chart, and the rate moved into the
   * summary table as a column.
   *
   * The bars repeated, as a length, the rate the line above them already
   * stated; the stacked counts answer the question the card is actually
   * asking — which section is behind, and why. What has to survive is that
   * every number stays readable without colour or hover: the plot's label
   * carries the counts and the computed rate, the three series are named in
   * text, and the rate is a table column.
   */
  it("charts each section's records and keeps the rate in the summary table", async () => {
    vi.mocked(apiClient.get).mockImplementation(async (url: string) => {
      if (String(url).startsWith("/attendance/summary/")) {
        return {
          data: [
            {
              student: "sp-1",
              student_name: "Ana Cruz",
              student_id_code: "STU-001",
              section_name: "Einstein",
              present_count: 24,
              late_count: 1,
              absent_count: 1,
              total_records: 26,
            },
          ],
        }
      }
      return { data: [] }
    })

    renderPage()

    const plot = await screen.findByRole("img", {
      name: /Stacked bar chart of attendance records by section/i,
    })
    // 24 present + 1 late out of 26 records — the same rate the table shows.
    expect(plot.getAttribute("aria-label")).toContain(
      "Einstein: 24 present, 1 late, 1 absent, 96% rate"
    )

    // The three series are named in text beside the plot, not left to colour.
    // The summary table's column headers read the same three words, so the
    // lookup is scoped to the chart's own block rather than the whole page.
    const chartBlock = plot.parentElement as HTMLElement
    expect(
      within(chartBlock).getAllByText(/^(Present|Late|Absent)$/)
    ).toHaveLength(3)

    // The rate is a column of the table rather than a hover-only tooltip.
    expect(
      screen.getByRole("columnheader", { name: "Rate" })
    ).toBeInTheDocument()
    expect(screen.getByText("96%")).toBeInTheDocument()
  })
})

describe("AttendancePage (faculty)", () => {
  beforeEach(() => {
    authState.user = makeUser("faculty")
  })

  it("offers the take-attendance form", async () => {
    renderPage()
    expect(await screen.findByText(/Take attendance/i)).toBeInTheDocument()
  })

  it("never asks the user to type a raw StudentProfile UUID", async () => {
    renderPage()
    await screen.findByText(/Take attendance/i)
    expect(screen.queryByText(/Student UUID/i)).not.toBeInTheDocument()
    expect(
      screen.queryByPlaceholderText(/StudentProfile UUID/i)
    ).not.toBeInTheDocument()
  })

  it("loads active enrolments for the selected section and offers student + ID", async () => {
    routePagedRequests({
      sections: [section()],
      enrollments: [
        enrollment({
          student: "sp-1",
          student_name: "Ana Cruz",
          student_id: "STU-001",
        }),
        enrollment({
          student: "sp-2",
          student_name: "Ben Diaz",
          student_id: "STU-002",
        }),
      ],
    })

    renderPage()

    await openSearchSelect(
      await screen.findByRole("button", { name: "Section" })
    )
    chooseOption(await screen.findByRole("option", { name: "Einstein" }))

    await waitFor(() => {
      const urls = mockedFetchAllPages.mock.calls.map((c) => String(c[0]))
      expect(urls).toContain("/academics/enrollments/")
    })

    await openSearchSelect(screen.getByRole("button", { name: "Student" }))
    expect(
      await screen.findByRole("option", { name: /Ana Cruz — STU-001/ })
    ).toBeInTheDocument()
    expect(
      screen.getByRole("option", { name: /Ben Diaz — STU-002/ })
    ).toBeInTheDocument()
  })

  it("excludes inactive enrolments from the student selector", async () => {
    routePagedRequests({
      sections: [section()],
      enrollments: [
        enrollment({
          student: "sp-1",
          student_name: "Ana Cruz",
          student_id: "STU-001",
        }),
        enrollment({
          student: "sp-9",
          student_name: "Withdrawn Kid",
          student_id: "STU-009",
          is_active: false,
        }),
      ],
    })

    renderPage()

    await openSearchSelect(
      await screen.findByRole("button", { name: "Section" })
    )
    chooseOption(await screen.findByRole("option", { name: "Einstein" }))
    await openSearchSelect(screen.getByRole("button", { name: "Student" }))

    expect(
      await screen.findByRole("option", { name: /Ana Cruz — STU-001/ })
    ).toBeInTheDocument()
    expect(screen.queryByText(/Withdrawn Kid/)).not.toBeInTheDocument()
  })

  it("submits the create payload with the enrolment's StudentProfile UUID and no recorded_by", async () => {
    const post = vi
      .spyOn(apiClient, "post")
      .mockResolvedValue({ data: record() })
    routePagedRequests({
      sections: [section()],
      enrollments: [
        enrollment({
          student: "sp-42",
          student_name: "Ana Cruz",
          student_id: "STU-001",
        }),
      ],
    })

    renderPage()

    await openSearchSelect(
      await screen.findByRole("button", { name: "Section" })
    )
    chooseOption(await screen.findByRole("option", { name: "Einstein" }))
    await openSearchSelect(screen.getByRole("button", { name: "Student" }))
    chooseOption(
      await screen.findByRole("option", { name: /Ana Cruz — STU-001/ })
    )

    fireEvent.change(screen.getByLabelText(/Date/i), {
      target: { value: "2026-03-02" },
    })
    fireEvent.click(screen.getByRole("button", { name: /Record attendance/i }))

    await waitFor(() => expect(post).toHaveBeenCalled())

    const [url, body] = post.mock.calls[0] as [string, Record<string, unknown>]
    expect(url).toBe("/attendance/records/")
    expect(body).toEqual({
      student: "sp-42",
      section: "sec-1",
      date: "2026-03-02",
      status: "present",
    })
    expect(body).not.toHaveProperty("recorded_by")

    // A successful create reports itself instead of leaving the form silent.
    expect(await screen.findByRole("status")).toHaveTextContent(
      /Attendance recorded/i
    )
    expect(screen.getByLabelText(/Date/i)).toHaveValue("")
  })

  it("caps the date input at today so future dates cannot be chosen", async () => {
    renderPage()
    const dateInput = await screen.findByLabelText(/Date/i)
    const today = new Date()
    const iso = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}-${String(today.getDate()).padStart(2, "0")}`
    expect(dateInput).toHaveAttribute("max", iso)
  })

  it("surfaces a duplicate student/date conflict from the backend", async () => {
    // `api.ts` rejects with an already-normalized `ApiClientError`, which is
    // what `normalizeApiError` passes through untouched. The backend builds it
    // from `core/exceptions.py`, so the payload is the standard envelope rather
    // than a bare DRF `detail`.
    vi.spyOn(apiClient, "post").mockRejectedValue({
      name: "ApiClientError",
      message: "Attendance already recorded for this student and date.",
      code: "CONFLICT",
      status: 409,
      details: null,
      isNetworkError: false,
      isCancelled: false,
      isPasswordChangeRequired: false,
    })
    routePagedRequests({
      sections: [section()],
      enrollments: [
        enrollment({
          student: "sp-42",
          student_name: "Ana Cruz",
          student_id: "STU-001",
        }),
      ],
    })

    renderPage()

    await openSearchSelect(
      await screen.findByRole("button", { name: "Section" })
    )
    chooseOption(await screen.findByRole("option", { name: "Einstein" }))
    await openSearchSelect(screen.getByRole("button", { name: "Student" }))
    chooseOption(
      await screen.findByRole("option", { name: /Ana Cruz — STU-001/ })
    )

    fireEvent.change(screen.getByLabelText(/Date/i), {
      target: { value: "2026-03-02" },
    })
    fireEvent.click(screen.getByRole("button", { name: /Record attendance/i }))

    expect(
      await screen.findByText(/Attendance already recorded/i)
    ).toBeInTheDocument()
  })

  it("shows no edit or delete actions even when recorded_by equals the User id", async () => {
    // The strongest possible trap: a `recorded_by` that happens to string-match
    // the caller's User id must still not unlock actions, because the field is a
    // FacultyProfile UUID and the two spaces are not comparable.
    authState.user = makeUser("faculty", "fp-9")
    routePagedRequests({ records: [record({ recorded_by: "fp-9" })] })

    renderPage()

    expect(await screen.findByText("Dr. Reyes")).toBeInTheDocument()
    expect(
      screen.queryByRole("button", { name: /Toggle/i })
    ).not.toBeInTheDocument()
    expect(
      screen.queryByRole("button", { name: /Delete/i })
    ).not.toBeInTheDocument()
  })

  it("has no Actions column at all", async () => {
    routePagedRequests({ records: [record()] })

    renderPage()

    await screen.findByText("Dr. Reyes")
    expect(
      screen.queryByRole("columnheader", { name: /Actions/i })
    ).not.toBeInTheDocument()
    expect(screen.queryByText(/Not recorded by you/i)).not.toBeInTheDocument()
  })

  it("explains why edit and delete are unavailable in this surface", async () => {
    routePagedRequests({ records: [record()] })

    renderPage()

    const note = await screen.findByText(
      /Editing and deleting a record is not available/i
    )
    expect(note).toBeInTheDocument()
    expect(document.body.textContent ?? "").toContain("/accounts/me/")
    // The note must not overstate the frontend's ability to check ownership.
    expect(document.body.textContent ?? "").toMatch(
      /does not return the caller.s FacultyProfile identifier/i
    )
  })

  it("does not offer a grade-encoding surface", () => {
    renderPage()
    expect(screen.queryByText(/Encode a grade/i)).not.toBeInTheDocument()
  })
})

describe("AttendancePage (unauthenticated)", () => {
  it("renders nothing without a user", () => {
    authState.user = null
    const { container } = renderPage()
    expect(container).toBeEmptyDOMElement()
  })
})

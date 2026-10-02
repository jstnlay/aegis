import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { beforeEach, describe, expect, it, vi } from "vitest"

import type { Consultation } from "@/features/guidance/api"
import { apiClient } from "@/lib/api"
import { fetchAllPages } from "@/lib/pagination"

import { ConsultationsPage } from "./ConsultationsPage"

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
const mockedPatch = vi.mocked(apiClient.patch)

function makeConsultation(overrides: Partial<Consultation> = {}): Consultation {
  return {
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
    priority_level: "medium",
    status: "ongoing",
    created_at: "2025-02-10T10:00:00Z",
    updated_at: "2025-02-10T10:00:00Z",
    ...overrides,
  }
}

const consultations: Consultation[] = [
  makeConsultation({
    id: "c-1",
    student: "sp-1",
    student_name: "Ana Reyes",
    session_date: "2025-02-10",
    status: "ongoing",
    priority_level: "high",
  }),
  makeConsultation({
    id: "c-2",
    student: "sp-2",
    student_name: "Ben Cruz",
    session_date: "2025-02-08",
    status: "completed",
    priority_level: "low",
    next_session_date: "2025-03-01",
    concern_categories: ["family", "bullying"],
  }),
  makeConsultation({
    id: "c-3",
    student: "sp-3",
    student_name: "Cara Diaz",
    session_date: "2025-02-05",
    status: "follow_up",
    priority_level: "medium",
    concern_categories: [],
  }),
  makeConsultation({
    id: "c-4",
    student: "sp-4",
    student_name: "Dan Ellis",
    session_date: "2025-02-01",
    status: "ongoing",
    priority_level: "low",
  }),
]

/** Raw `EnrollmentWire` rows, not the normalized roster shape. */
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
      <ConsultationsPage />
    </QueryClientProvider>
  )
}

/**
 * Radix `Select` needs a keydown to open and a click to commit. This is the
 * same approach `AttendancePage.test.tsx` uses, so no new dependency is added.
 *
 * The option is queried without `hidden: true` on purpose: Radix mirrors the
 * items into a hidden native `<select>`, so including hidden nodes yields two
 * matches per option.
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
    return { count: consultations.length, results: consultations }
  })
})

describe("ConsultationsPage", () => {
  it("renders every consultation regardless of status by default", async () => {
    renderPage()

    expect(
      await screen.findByRole("heading", { name: "Consultations", level: 1 })
    ).toBeInTheDocument()
    expect(await screen.findByText("Ana Reyes")).toBeInTheDocument()
    expect(screen.getByText("Ben Cruz")).toBeInTheDocument()
    expect(screen.getByText("Cara Diaz")).toBeInTheDocument()
    expect(screen.getByText("Dan Ellis")).toBeInTheDocument()
  })

  it("states that the list is counselor-scoped rather than school-wide", async () => {
    renderPage()

    expect(
      await screen.findByText(/only your own consultations/i)
    ).toBeInTheDocument()
  })

  it("orders rows newest session first using the backend ordering field", async () => {
    renderPage()
    await screen.findByText("Ana Reyes")

    const names = screen
      .getAllByRole("row")
      .slice(1)
      .map((row) => row.querySelector("td")?.textContent ?? "")

    expect(names[0]).toContain("Ana Reyes")
    expect(names[3]).toContain("Dan Ellis")
  })

  it("shows the count of each status on the filter chips", async () => {
    renderPage()
    await screen.findByText("Ana Reyes")

    const chips = within(
      screen.getByRole("group", { name: /filter by status/i })
    )
    expect(chips.getByRole("button", { name: /^All 4$/ })).toBeInTheDocument()
    expect(
      chips.getByRole("button", { name: /^Ongoing 2$/ })
    ).toBeInTheDocument()
    expect(
      chips.getByRole("button", { name: /^Completed 1$/ })
    ).toBeInTheDocument()
    expect(
      chips.getByRole("button", { name: /^Follow up 1$/ })
    ).toBeInTheDocument()
  })

  it("narrows to a single status without touching the other chip totals", async () => {
    renderPage()
    await screen.findByText("Ana Reyes")

    fireEvent.click(screen.getByRole("button", { name: /^Completed 1$/ }))

    await waitFor(() => expect(screen.queryByText("Ana Reyes")).toBeNull())
    expect(screen.getByText("Ben Cruz")).toBeInTheDocument()

    // Totals describe the whole list, so Completed must still read 1 even
    // though it is the active filter.
    const chips = within(
      screen.getByRole("group", { name: /filter by status/i })
    )
    expect(
      chips.getByRole("button", { name: /^Ongoing 2$/ })
    ).toBeInTheDocument()
  })

  it("filters by priority", async () => {
    renderPage()
    await screen.findByText("Ana Reyes")

    const trigger = screen.getByLabelText("Priority")
    await openSelect(trigger)
    fireEvent.click(await screen.findByRole("option", { name: "Low" }))

    await waitFor(() => expect(screen.queryByText("Ana Reyes")).toBeNull())
    expect(screen.getByText("Dan Ellis")).toBeInTheDocument()
  })

  it("searches across student name, notes, and concern categories", async () => {
    renderPage()
    await screen.findByText("Ana Reyes")

    fireEvent.change(screen.getByLabelText("Search"), {
      target: { value: "bullying" },
    })

    await waitFor(() => expect(screen.queryByText("Ana Reyes")).toBeNull())
    expect(screen.getByText("Ben Cruz")).toBeInTheDocument()
  })

  it("shows an empty state when filters exclude everything", async () => {
    renderPage()
    await screen.findByText("Ana Reyes")

    fireEvent.change(screen.getByLabelText("Search"), {
      target: { value: "zzzz-no-match" },
    })

    expect(
      await screen.findByText(/No consultations match the current filters/i)
    ).toBeInTheDocument()
  })

  it("renders the roster student code, which the serializer lacks", async () => {
    renderPage()
    await screen.findByText("Ana Reyes")

    await waitFor(() => {
      expect(
        within(rowFor("Ana Reyes")).getByText("S-1001")
      ).toBeInTheDocument()
    })
  })

  it("renders each concern category as its own badge and uses a dash when empty", async () => {
    renderPage()
    await screen.findByText("Ben Cruz")

    const row = rowFor("Ben Cruz")
    expect(within(row).getByText("Family")).toBeInTheDocument()
    expect(within(row).getByText("Bullying")).toBeInTheDocument()

    const emptyRow = rowFor("Cara Diaz")
    // Cara Diaz has no concern categories and no scheduled next session, so the
    // row carries exactly two dashes.
    expect(within(emptyRow).getAllByText("—")).toHaveLength(2)
  })

  it("trims the seconds off the session time", async () => {
    renderPage()
    await screen.findByText("Ana Reyes")

    expect(within(rowFor("Ana Reyes")).getByText("09:30")).toBeInTheDocument()
  })

  it("shows a dash when there is no scheduled next session", async () => {
    renderPage()
    await screen.findByText("Ana Reyes")

    expect(within(rowFor("Ana Reyes")).getByText("—")).toBeInTheDocument()
    // Ben Cruz has one, rendered as the raw DateField string.
    expect(
      within(rowFor("Ben Cruz")).getByText("2025-03-01")
    ).toBeInTheDocument()
  })

  it("surfaces a fetch failure instead of an empty table", async () => {
    mockedFetchAllPages.mockRejectedValue(new Error("boom"))

    renderPage()

    const alert = await screen.findByRole("alert")
    expect(alert).toHaveTextContent("boom")
  })

  it("creates a consultation with the exact payload contract", async () => {
    mockedPost.mockResolvedValue({ data: makeConsultation() } as never)

    renderPage()
    await screen.findByText("Ana Reyes")

    fireEvent.click(screen.getByRole("button", { name: /new consultation/i }))
    const dialog = await screen.findByRole("dialog")

    await openSelect(within(dialog).getByRole("combobox", { name: /student/i }))
    fireEvent.click(await screen.findByRole("option", { name: /Ana Reyes/ }))

    fireEvent.change(within(dialog).getByLabelText("Session date"), {
      target: { value: "2025-03-04" },
    })
    fireEvent.change(within(dialog).getByLabelText(/session time/i), {
      target: { value: "10:15" },
    })
    fireEvent.change(within(dialog).getByLabelText(/session notes/i), {
      target: { value: "  Follow-up session.  " },
    })
    fireEvent.click(within(dialog).getByRole("button", { name: "Academic" }))
    fireEvent.click(
      within(dialog).getByRole("button", { name: "Create consultation" })
    )

    await waitFor(() => {
      expect(mockedPost).toHaveBeenCalledWith("/guidance/consultations/", {
        student: "sp-1",
        session_date: "2025-03-04",
        session_time: "10:15",
        session_type: "individual_counseling",
        concern_categories: ["academic"],
        session_notes: "Follow-up session.",
        priority_level: "medium",
        next_session_date: null,
      })
    })

    // `counselor` is a read-only serializer field set from the caller.
    const payload = mockedPost.mock.calls[0]?.[1] as Record<string, unknown>
    expect(payload).not.toHaveProperty("counselor")
  })

  it("toggles a concern category off again when clicked twice", async () => {
    mockedPost.mockResolvedValue({ data: makeConsultation() } as never)

    renderPage()
    await screen.findByText("Ana Reyes")

    fireEvent.click(screen.getByRole("button", { name: /new consultation/i }))
    const dialog = await screen.findByRole("dialog")

    await openSelect(within(dialog).getByRole("combobox", { name: /student/i }))
    fireEvent.click(await screen.findByRole("option", { name: /Ana Reyes/ }))

    fireEvent.change(within(dialog).getByLabelText("Session date"), {
      target: { value: "2025-03-04" },
    })
    fireEvent.change(within(dialog).getByLabelText(/session time/i), {
      target: { value: "10:15" },
    })
    fireEvent.change(within(dialog).getByLabelText(/session notes/i), {
      target: { value: "Notes." },
    })

    const family = within(dialog).getByRole("button", { name: "Family" })
    fireEvent.click(family)
    fireEvent.click(family)

    fireEvent.click(
      within(dialog).getByRole("button", { name: "Create consultation" })
    )

    await waitFor(() => {
      expect(mockedPost).toHaveBeenCalledWith(
        "/guidance/consultations/",
        expect.objectContaining({ concern_categories: [] })
      )
    })
  })

  it("blocks submission until the required session notes are non-blank", async () => {
    renderPage()
    await screen.findByText("Ana Reyes")

    fireEvent.click(screen.getByRole("button", { name: /new consultation/i }))
    const dialog = await screen.findByRole("dialog")

    await openSelect(within(dialog).getByRole("combobox", { name: /student/i }))
    fireEvent.click(await screen.findByRole("option", { name: /Ana Reyes/ }))

    fireEvent.change(within(dialog).getByLabelText("Session date"), {
      target: { value: "2025-03-04" },
    })
    fireEvent.change(within(dialog).getByLabelText(/session time/i), {
      target: { value: "10:15" },
    })

    const submit = within(dialog).getByRole("button", {
      name: "Create consultation",
    })
    expect(submit).toBeDisabled()

    fireEvent.change(within(dialog).getByLabelText(/session notes/i), {
      target: { value: "   " },
    })
    expect(submit).toBeDisabled()

    fireEvent.change(within(dialog).getByLabelText(/session notes/i), {
      target: { value: "Real notes." },
    })
    expect(submit).toBeEnabled()
  })

  it("patches status and case-management fields without touching session identity", async () => {
    mockedPatch.mockResolvedValue({
      data: makeConsultation({ status: "completed" }),
    } as never)

    renderPage()
    await screen.findByText("Ana Reyes")

    fireEvent.click(
      within(rowFor("Ana Reyes")).getByRole("button", { name: "Update" })
    )
    const dialog = await screen.findByRole("dialog")

    await openSelect(within(dialog).getByRole("combobox", { name: /^Status$/ }))
    fireEvent.click(await screen.findByRole("option", { name: "Completed" }))

    fireEvent.change(within(dialog).getByLabelText(/recommendations/i), {
      target: { value: "Weekly check-ins." },
    })
    fireEvent.change(within(dialog).getByLabelText(/next session date/i), {
      target: { value: "2025-03-11" },
    })
    fireEvent.click(
      within(dialog).getByRole("button", { name: /save changes/i })
    )

    await waitFor(() => {
      expect(mockedPatch).toHaveBeenCalledWith("/guidance/consultations/c-1/", {
        status: "completed",
        priority_level: "high",
        session_notes: "Reviewed midterm results.",
        recommendations: "Weekly check-ins.",
        next_session_date: "2025-03-11",
      })
    })

    const payload = mockedPatch.mock.calls[0]?.[1] as Record<string, unknown>
    expect(payload).not.toHaveProperty("student")
    expect(payload).not.toHaveProperty("session_date")
    expect(payload).not.toHaveProperty("counselor")
  })

  it("sends null for a cleared next session date", async () => {
    mockedPatch.mockResolvedValue({
      data: makeConsultation({ next_session_date: null }),
    } as never)

    renderPage()
    await screen.findByText("Ben Cruz")

    fireEvent.click(
      within(rowFor("Ben Cruz")).getByRole("button", { name: "Update" })
    )
    const dialog = await screen.findByRole("dialog")

    const nextDate = within(dialog).getByLabelText(/next session date/i)
    expect(nextDate).toHaveValue("2025-03-01")

    fireEvent.change(nextDate, { target: { value: "" } })
    fireEvent.click(
      within(dialog).getByRole("button", { name: /save changes/i })
    )

    await waitFor(() => {
      expect(mockedPatch).toHaveBeenCalledWith(
        "/guidance/consultations/c-2/",
        expect.objectContaining({ next_session_date: null })
      )
    })
  })

  it("surfaces a failed create without closing the dialog", async () => {
    mockedPost.mockRejectedValue(new Error("Session notes cannot be empty."))

    renderPage()
    await screen.findByText("Ana Reyes")

    fireEvent.click(screen.getByRole("button", { name: /new consultation/i }))
    const dialog = await screen.findByRole("dialog")

    await openSelect(within(dialog).getByRole("combobox", { name: /student/i }))
    fireEvent.click(await screen.findByRole("option", { name: /Ana Reyes/ }))

    fireEvent.change(within(dialog).getByLabelText("Session date"), {
      target: { value: "2025-03-04" },
    })
    fireEvent.change(within(dialog).getByLabelText(/session time/i), {
      target: { value: "10:15" },
    })
    fireEvent.change(within(dialog).getByLabelText(/session notes/i), {
      target: { value: "Notes." },
    })
    fireEvent.click(
      within(dialog).getByRole("button", { name: "Create consultation" })
    )

    const alert = await within(dialog).findByRole("alert")
    expect(alert).toHaveTextContent("Session notes cannot be empty.")
    // Still mounted so the entered values are not lost.
    expect(within(dialog).getByLabelText(/session notes/i)).toHaveValue(
      "Notes."
    )
  })
})

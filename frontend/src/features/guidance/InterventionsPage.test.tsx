import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { beforeEach, describe, expect, it, vi } from "vitest"

import type { Intervention, RiskAlert } from "@/features/guidance/api"
import { apiClient } from "@/lib/api"
import { fetchAllPages } from "@/lib/pagination"

import { InterventionsPage } from "./InterventionsPage"

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
const mockedPost = vi.mocked(apiClient.post)
const mockedPatch = vi.mocked(apiClient.patch)

function makeIntervention(overrides: Partial<Intervention> = {}): Intervention {
  return {
    id: "i-1",
    student: "sp-1",
    student_name: "Ana Reyes",
    risk_alert: null,
    risk_alert_student: null,
    assigned_counselor: "gp-1",
    assigned_counselor_name: "Robin Vega",
    plan_start_date: "2025-02-01",
    target_review_date: "2025-03-01",
    status: "active",
    created_at: "2025-02-01T00:00:00Z",
    updated_at: "2025-02-01T00:00:00Z",
    ...overrides,
  }
}

const interventions: Intervention[] = [
  makeIntervention({ id: "i-1", student: "sp-1", student_name: "Ana Reyes" }),
  makeIntervention({
    id: "i-2",
    student: "sp-2",
    student_name: "Ben Cruz",
    status: "completed",
    target_review_date: null,
    risk_alert: "ra-9",
    // The serializer resolves this from the *linked alert's* student, which the
    // backend does not require to be this plan's own student.
    risk_alert_student: "Mismatched Student",
  }),
  makeIntervention({
    id: "i-3",
    student: "sp-3",
    student_name: "Cara Diaz",
    status: "cancelled",
  }),
  makeIntervention({
    id: "i-4",
    student: "sp-4",
    student_name: "Dan Ellis",
  }),
]

const alerts: RiskAlert[] = [
  {
    id: "ra-1",
    student: "sp-1",
    student_name: "Ana Reyes",
    risk_level: "high",
    risk_factors: [],
    source: "manual",
    status: "active",
    assigned_counselor: null,
    assigned_counselor_name: null,
    generated_at: "2025-01-30T00:00:00Z",
    last_updated: "2025-01-30T00:00:00Z",
    created_at: "2025-01-30T00:00:00Z",
    updated_at: "2025-01-30T00:00:00Z",
  },
]

const steps = [
  {
    id: "st-1",
    intervention: "i-1",
    title: "Weekly check-in",
    description: "Meet in the counseling office.",
    status: "in_progress" as const,
    order: 1,
    created_at: "2025-02-01T00:00:00Z",
    updated_at: "2025-02-01T00:00:00Z",
  },
  {
    id: "st-2",
    intervention: "i-1",
    title: "Family conference",
    description: "",
    status: "pending" as const,
    order: 2,
    created_at: "2025-02-01T00:00:00Z",
    updated_at: "2025-02-01T00:00:00Z",
  },
]

const notes = [
  {
    id: "n-1",
    intervention: "i-1",
    note_text: "Student engaged well and set goals.",
    recorded_by: "gp-1",
    recorded_by_name: "Robin Vega",
    next_follow_up: "2025-02-15",
    created_at: "2025-02-08T00:00:00Z",
    updated_at: "2025-02-08T00:00:00Z",
  },
]

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
      <InterventionsPage />
    </QueryClientProvider>
  )
}

/**
 * Radix `Select` needs a keydown to open and a click to commit. Options are
 * queried without `hidden: true` on purpose: Radix mirrors items into a hidden
 * native `<select>`, so including hidden nodes yields two matches per option.
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
    if (url.includes("/guidance/interventions/")) {
      return { count: interventions.length, results: interventions }
    }
    if (url.includes("/guidance/risk-alerts/")) {
      return { count: alerts.length, results: alerts }
    }
    return { count: 0, results: [] }
  })
  mockedGet.mockImplementation(async (url: string) => {
    if (url.endsWith("/steps/")) return { data: steps } as never
    if (url.endsWith("/notes/")) return { data: notes } as never
    return { data: [] } as never
  })
})

describe("InterventionsPage", () => {
  it("renders every plan regardless of status by default", async () => {
    renderPage()

    expect(
      await screen.findByRole("heading", { name: "Interventions", level: 2 })
    ).toBeInTheDocument()
    expect(await screen.findByText("Ana Reyes")).toBeInTheDocument()
    expect(screen.getByText("Ben Cruz")).toBeInTheDocument()
    expect(screen.getByText("Cara Diaz")).toBeInTheDocument()
    expect(screen.getByText("Dan Ellis")).toBeInTheDocument()
  })

  it("states that plans are counselor-scoped rather than school-wide", async () => {
    renderPage()

    expect(
      await screen.findByText(/only plans assigned to you/i)
    ).toBeInTheDocument()
  })

  it("shows the count of each status on the filter chips", async () => {
    renderPage()
    await screen.findByText("Ana Reyes")

    const chips = within(
      screen.getByRole("group", { name: /filter by status/i })
    )
    expect(chips.getByRole("button", { name: /^All 4$/ })).toBeInTheDocument()
    expect(
      chips.getByRole("button", { name: /^Active 2$/ })
    ).toBeInTheDocument()
    expect(
      chips.getByRole("button", { name: /^Completed 1$/ })
    ).toBeInTheDocument()
    expect(
      chips.getByRole("button", { name: /^Cancelled 1$/ })
    ).toBeInTheDocument()
  })

  it("narrows to a single status", async () => {
    renderPage()
    await screen.findByText("Ana Reyes")

    fireEvent.click(screen.getByRole("button", { name: /^Completed 1$/ }))

    await waitFor(() => expect(screen.queryByText("Ana Reyes")).toBeNull())
    expect(screen.getByText("Ben Cruz")).toBeInTheDocument()
  })

  it("searches by student name", async () => {
    renderPage()
    await screen.findByText("Ana Reyes")

    fireEvent.change(screen.getByLabelText("Search"), {
      target: { value: "cara" },
    })

    await waitFor(() => expect(screen.queryByText("Ana Reyes")).toBeNull())
    expect(screen.getByText("Cara Diaz")).toBeInTheDocument()
  })

  it("shows an empty state when filters exclude everything", async () => {
    renderPage()
    await screen.findByText("Ana Reyes")

    fireEvent.change(screen.getByLabelText("Search"), {
      target: { value: "zzzz-no-match" },
    })

    expect(
      await screen.findByText(/No interventions match the current filters/i)
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

  it("renders a dash when the plan has no target review date", async () => {
    renderPage()
    await screen.findByText("Ben Cruz")

    expect(within(rowFor("Ben Cruz")).getByText("—")).toBeInTheDocument()
    expect(
      within(rowFor("Ana Reyes")).getByText("2025-03-01")
    ).toBeInTheDocument()
  })

  it("surfaces a fetch failure instead of an empty table", async () => {
    mockedFetchAllPages.mockRejectedValue(new Error("boom"))

    renderPage()

    const alert = await screen.findByRole("alert")
    expect(alert).toHaveTextContent("boom")
  })

  it("creates a plan with the exact payload contract", async () => {
    mockedPost.mockResolvedValue({ data: makeIntervention() } as never)

    renderPage()
    await screen.findByText("Ana Reyes")

    fireEvent.click(screen.getByRole("button", { name: /new intervention/i }))
    const dialog = await screen.findByRole("dialog")

    await openSelect(within(dialog).getByRole("combobox", { name: /student/i }))
    fireEvent.click(await screen.findByRole("option", { name: /Ana Reyes/ }))

    fireEvent.change(within(dialog).getByLabelText(/plan start date/i), {
      target: { value: "2025-03-01" },
    })
    await openSelect(
      within(dialog).getByRole("combobox", { name: /linked risk alert/i })
    )
    fireEvent.click(await screen.findByRole("option", { name: /High/ }))
    fireEvent.click(
      within(dialog).getByRole("button", { name: "Create intervention" })
    )

    await waitFor(() => {
      expect(mockedPost).toHaveBeenCalledWith("/guidance/interventions/", {
        student: "sp-1",
        plan_start_date: "2025-03-01",
        target_review_date: null,
        risk_alert: "ra-1",
      })
    })

    // `assigned_counselor` and `status` are read-only serializer fields.
    const payload = mockedPost.mock.calls[0]?.[1] as Record<string, unknown>
    expect(payload).not.toHaveProperty("assigned_counselor")
    expect(payload).not.toHaveProperty("status")
  })

  it("offers only the selected student's risk alerts", async () => {
    renderPage()
    await screen.findByText("Ana Reyes")

    fireEvent.click(screen.getByRole("button", { name: /new intervention/i }))
    const dialog = await screen.findByRole("dialog")

    await openSelect(within(dialog).getByRole("combobox", { name: /student/i }))
    fireEvent.click(await screen.findByRole("option", { name: /Ana Reyes/ }))

    await openSelect(
      within(dialog).getByRole("combobox", { name: /linked risk alert/i })
    )

    // Ana Reyes owns the only alert in the fixture.
    expect(
      await screen.findByRole("option", { name: /High/ })
    ).toBeInTheDocument()
    expect(
      screen.getByRole("option", { name: "No linked alert" })
    ).toBeInTheDocument()
    expect(screen.queryByRole("option", { name: /Moderate/ })).toBeNull()
  })

  it("blocks a review date that precedes the plan start date", async () => {
    renderPage()
    await screen.findByText("Ana Reyes")

    fireEvent.click(screen.getByRole("button", { name: /new intervention/i }))
    const dialog = await screen.findByRole("dialog")

    await openSelect(within(dialog).getByRole("combobox", { name: /student/i }))
    fireEvent.click(await screen.findByRole("option", { name: /Ana Reyes/ }))

    fireEvent.change(within(dialog).getByLabelText(/plan start date/i), {
      target: { value: "2025-03-01" },
    })
    fireEvent.change(within(dialog).getByLabelText(/target review date/i), {
      target: { value: "2025-02-01" },
    })

    expect(
      await within(dialog).findByText(/cannot be earlier than the plan start/i)
    ).toBeInTheDocument()
    expect(
      within(dialog).getByRole("button", { name: "Create intervention" })
    ).toBeDisabled()
  })

  it("loads steps and notes through the bare-array endpoints", async () => {
    renderPage()
    await screen.findByText("Ana Reyes")

    fireEvent.click(
      within(rowFor("Ana Reyes")).getByRole("button", { name: /manage plan/i })
    )
    const dialog = await screen.findByRole("dialog")

    expect(
      await within(dialog).findByText("Weekly check-in")
    ).toBeInTheDocument()
    expect(within(dialog).getByText("Family conference")).toBeInTheDocument()
    expect(
      within(dialog).getByText(/Student engaged well and set goals\./)
    ).toBeInTheDocument()

    expect(mockedGet).toHaveBeenCalledWith("/guidance/interventions/i-1/steps/")
    expect(mockedGet).toHaveBeenCalledWith("/guidance/interventions/i-1/notes/")
    // Bare arrays must never go through the paginating helper.
    expect(mockedFetchAllPages).not.toHaveBeenCalledWith(
      expect.stringContaining("/steps/")
    )
    expect(mockedFetchAllPages).not.toHaveBeenCalledWith(
      expect.stringContaining("/notes/")
    )
  })

  it("does not render the linked alert's student name, which can disagree", async () => {
    renderPage()
    await screen.findByText("Ben Cruz")

    // i-2 carries `risk_alert_student: "Mismatched Student"`. It must never
    // appear, because it names a different student than the plan's own row.
    expect(screen.queryByText("Mismatched Student")).toBeNull()
    // The plan's real student is still shown.
    expect(within(rowFor("Ben Cruz")).getByText("Ben Cruz")).toBeInTheDocument()
  })

  it("creates a step at the nested steps endpoint", async () => {
    mockedPost.mockResolvedValue({ data: steps[0] } as never)

    renderPage()
    await screen.findByText("Ana Reyes")

    fireEvent.click(
      within(rowFor("Ana Reyes")).getByRole("button", { name: /manage plan/i })
    )
    const dialog = await screen.findByRole("dialog")
    await within(dialog).findByText("Weekly check-in")

    const form = within(dialog).getByRole("form", { name: "Add step" })
    fireEvent.change(within(form).getByLabelText(/step title/i), {
      target: { value: "  Tutoring referral  " },
    })
    fireEvent.change(within(form).getByLabelText(/^order$/i), {
      target: { value: "3" },
    })
    fireEvent.click(within(form).getByRole("button", { name: "Add step" }))

    await waitFor(() => {
      expect(mockedPost).toHaveBeenCalledWith(
        "/guidance/interventions/i-1/steps/",
        {
          title: "Tutoring referral",
          description: "",
          status: "pending",
          order: 3,
        }
      )
    })
  })

  it("rejects a step order below 1, matching the backend clean()", async () => {
    renderPage()
    await screen.findByText("Ana Reyes")

    fireEvent.click(
      within(rowFor("Ana Reyes")).getByRole("button", { name: /manage plan/i })
    )
    const dialog = await screen.findByRole("dialog")
    await within(dialog).findByText("Weekly check-in")

    const form = within(dialog).getByRole("form", { name: "Add step" })
    fireEvent.change(within(form).getByLabelText(/step title/i), {
      target: { value: "Bad order" },
    })
    fireEvent.change(within(form).getByLabelText(/^order$/i), {
      target: { value: "0" },
    })

    expect(
      await within(form).findByText(/Order must be 1 or greater/i)
    ).toBeInTheDocument()
    expect(
      within(form).getByRole("button", { name: "Add step" })
    ).toBeDisabled()
  })

  it("patches a step at the nested step endpoint", async () => {
    mockedPatch.mockResolvedValue({ data: steps[0] } as never)

    renderPage()
    await screen.findByText("Ana Reyes")

    fireEvent.click(
      within(rowFor("Ana Reyes")).getByRole("button", { name: /manage plan/i })
    )
    const dialog = await screen.findByRole("dialog")
    await within(dialog).findByText("Weekly check-in")

    fireEvent.click(
      // PH11.11: the per-step trigger now carries an `aria-label` naming the
      // step's order and title, because a plan's steps each rendered a button
      // whose only accessible name was "Update".
      within(
        dialog.querySelector('[data-step-id="st-1"]') as HTMLElement
      ).getByRole("button", { name: "Update step 1, Weekly check-in" })
    )
    const editDialog = await screen.findByRole("dialog")

    await openSelect(
      within(editDialog).getByRole("combobox", { name: "Status" })
    )
    fireEvent.click(await screen.findByRole("option", { name: "Completed" }))

    fireEvent.change(within(editDialog).getByLabelText(/^order$/i), {
      target: { value: "5" },
    })
    fireEvent.click(
      within(editDialog).getByRole("button", { name: /save step/i })
    )

    await waitFor(() => {
      expect(mockedPatch).toHaveBeenCalledWith(
        "/guidance/interventions/i-1/steps/st-1/",
        {
          title: "Weekly check-in",
          description: "Meet in the counseling office.",
          status: "completed",
          order: 5,
        }
      )
    })

    const payload = mockedPatch.mock.calls[0]?.[1] as Record<string, unknown>
    // `intervention` comes from the URL, not the body.
    expect(payload).not.toHaveProperty("intervention")
  })

  it("creates a progress note through the nested notes endpoint", async () => {
    mockedPost.mockResolvedValue({ data: notes[0] } as never)

    renderPage()
    await screen.findByText("Ana Reyes")

    fireEvent.click(
      within(rowFor("Ana Reyes")).getByRole("button", { name: /manage plan/i })
    )
    const dialog = await screen.findByRole("dialog")
    await within(dialog).findByText("Weekly check-in")

    const form = within(dialog).getByRole("form", {
      name: "Add progress note",
    })
    fireEvent.change(within(form).getByLabelText(/progress note/i), {
      target: { value: "  Tutor confirmed weekly slot.  " },
    })
    fireEvent.click(within(form).getByRole("button", { name: "Add note" }))

    await waitFor(() => {
      expect(mockedPost).toHaveBeenCalledWith(
        "/guidance/interventions/i-1/notes/",
        { note_text: "Tutor confirmed weekly slot.", next_follow_up: null }
      )
    })
  })

  it("never calls a delete verb, which the router does not offer for steps", async () => {
    renderPage()
    await screen.findByText("Ana Reyes")

    fireEvent.click(
      within(rowFor("Ana Reyes")).getByRole("button", { name: /manage plan/i })
    )
    const dialog = await screen.findByRole("dialog")
    await within(dialog).findByText("Weekly check-in")

    expect(within(dialog).queryByRole("button", { name: /delete/i })).toBeNull()
    expect(apiClient.delete).not.toHaveBeenCalled()
  })

  it("never posts to the complete action endpoint", async () => {
    mockedPost.mockResolvedValue({ data: makeIntervention() } as never)

    renderPage()
    await screen.findByText("Ana Reyes")

    fireEvent.click(
      within(rowFor("Ana Reyes")).getByRole("button", { name: /manage plan/i })
    )
    await screen.findByRole("dialog")

    expect(screen.queryByRole("button", { name: /^complete/i })).toBeNull()
    expect(mockedPost).not.toHaveBeenCalledWith(
      expect.stringContaining("/complete/"),
      expect.anything()
    )
  })

  it("surfaces a steps fetch failure inside the plan dialog", async () => {
    mockedGet.mockImplementation(async (url: string) => {
      if (url.endsWith("/steps/")) throw new Error("steps unavailable")
      return { data: notes } as never
    })

    renderPage()
    await screen.findByText("Ana Reyes")

    fireEvent.click(
      within(rowFor("Ana Reyes")).getByRole("button", { name: /manage plan/i })
    )
    const dialog = await screen.findByRole("dialog")

    const alert = await within(dialog).findByText("steps unavailable")
    expect(alert).toBeInTheDocument()
    // The notes section still renders independently.
    expect(
      within(dialog).getByText(/Student engaged well and set goals\./)
    ).toBeInTheDocument()
  })
})

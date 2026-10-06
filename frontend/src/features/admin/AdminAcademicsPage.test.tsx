import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { AdminAcademicsPage } from "./AdminAcademicsPage"
import { apiClient } from "@/lib/api"
import { fetchAllPages } from "@/lib/pagination"

/**
 * PH11.10 regression tests for the academic-structure create forms.
 *
 * The page's `Field` helper used to own its own `useState` and hand the child
 * its *own* setter. The parent card therefore never received the typed value,
 * so `canSubmit` — which reads the parent form object — stayed `false` for six
 * of the seven create forms and their submit buttons were permanently
 * disabled. These tests assert the actual behaviour: typing enables submission,
 * the typed value reaches the handler, and a missing required field blocks it.
 */

vi.mock("@/lib/api", () => ({
  apiClient: { get: vi.fn(), post: vi.fn() },
}))

vi.mock("@/lib/pagination", () => ({
  fetchAllPages: vi.fn(),
}))

const mockedPost = vi.mocked(apiClient.post)
const mockedFetchAllPages = vi.mocked(fetchAllPages)

const RESOURCE_BY_SEGMENT: Record<string, unknown[]> = {
  "academic-years": [
    { id: "ay-1", name: "SY 2026-2027", start_date: "2026-06-01", end_date: "2027-05-31", is_current: true },
  ],
  "grade-levels": [
    { id: "gl-1", name: "Grade 8", level_number: 8 },
    { id: "gl-2", name: "Grade 9", level_number: 9 },
  ],
  sections: [{ id: "sec-1", name: "Bonifacio", grade_level_name: "Grade 8" }],
  subjects: [
    { id: "sub-1", name: "Mathematics", code: "MATH-8", grade_level_name: "Grade 8" },
  ],
  "subject-assignments": [],
  "grading-periods": [],
  enrollments: [],
}

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <AdminAcademicsPage />
    </QueryClientProvider>
  )
}

async function openTab(name: RegExp) {
  renderPage()
  const tab = await screen.findByRole("tab", { name })
  tab.click()
}

/** The dialog/form control identified by its label. */
function field(label: RegExp): HTMLElement {
  return screen.getByLabelText(label)
}

beforeEach(() => {
  vi.clearAllMocks()

  mockedFetchAllPages.mockImplementation(async (url: string) => {
    const segment = url.split("/").filter(Boolean).pop() ?? ""
    return { count: 0, results: RESOURCE_BY_SEGMENT[segment] ?? [] }
  })

  mockedPost.mockResolvedValue({ data: {} } as never)
})

describe("AdminAcademicsPage create forms", () => {
  it("keeps a required create disabled until every required field is filled", async () => {
    await openTab(/Academic years/i)

    const submit = screen.getByRole("button", { name: /Create academic year/i })
    expect(submit).toBeDisabled()

    // Two of the three fields: still incomplete.
    fireChange(field(/^Name$/), "SY 2026-2027")
    fireChange(field(/Start date/i), "2026-06-01")
    await waitFor(() => expect(submit).toBeDisabled())

    fireChange(field(/End date/i), "2027-05-31")
    await waitFor(() => expect(submit).toBeEnabled())
  })

  it("sends the typed values to the create handler", async () => {
    await openTab(/Academic years/i)

    fireChange(field(/^Name$/), "SY 2026-2027")
    fireChange(field(/Start date/i), "2026-06-01")
    fireChange(field(/End date/i), "2027-05-31")

    const submit = screen.getByRole("button", {
      name: /Create academic year/i,
    })
    await waitFor(() => expect(submit).toBeEnabled())
    submit.click()

    await waitFor(() => expect(mockedPost).toHaveBeenCalledTimes(1))
    const call = mockedPost.mock.calls[0]!
    const [url, body] = call
    expect(url).toBe("/academics/academic-years/")
    expect(body).toMatchObject({
      name: "SY 2026-2027",
      start_date: "2026-06-01",
      end_date: "2027-05-31",
    })
  })

  it("enables the grade-level form, whose two fields were both dead", async () => {
    await openTab(/Grade levels/i)

    const submit = screen.getByRole("button", { name: /Create grade level/i })
    expect(submit).toBeDisabled()

    fireChange(field(/^Name$/), "Grade 10")
    fireChange(field(/Level number/i), "10")

    await waitFor(() => expect(submit).toBeEnabled())
    submit.click()

    await waitFor(() => expect(mockedPost).toHaveBeenCalledTimes(1))
    expect(mockedPost.mock.calls[0]![1]).toMatchObject({
      name: "Grade 10",
      level_number: 10,
    })
  })

  it("enables the section form, which mixes a text field and a select", async () => {
    await openTab(/^Sections$/i)

    const submit = screen.getByRole("button", { name: /Create section/i })
    expect(submit).toBeDisabled()

    fireChange(field(/^Name$/), "Bonifacio")
    await waitFor(() => expect(submit).toBeDisabled())

    await chooseOption(
      screen.getByRole("combobox", { name: /grade level/i }),
      "Grade 8"
    )
    await chooseOption(
      screen.getByRole("combobox", { name: /academic year/i }),
      "SY 2026-2027"
    )
    await waitFor(() => expect(submit).toBeEnabled())
    submit.click()

    await waitFor(() => expect(mockedPost).toHaveBeenCalledTimes(1))
    expect(mockedPost.mock.calls[0]![1]).toMatchObject({
      name: "Bonifacio",
      grade_level: "gl-1",
      academic_year: "ay-1",
    })
  })

  it("enables the grading-period form, which has four text fields", async () => {
    await openTab(/Grading periods/i)

    const submit = screen.getByRole("button", {
      name: /Create grading period/i,
    })
    expect(submit).toBeDisabled()

    fireChange(field(/^Name$/), "First Term")
    fireChange(field(/Order/i), "1")
    fireChange(field(/Start date/i), "2026-06-01")
    fireChange(field(/End date/i), "2026-09-30")
    await chooseOption(
      screen.getByRole("combobox", { name: /academic year/i }),
      "SY 2026-2027"
    )

    await waitFor(() => expect(submit).toBeEnabled())
    submit.click()

    await waitFor(() => expect(mockedPost).toHaveBeenCalledTimes(1))
    expect(mockedPost.mock.calls[0]![1]).toMatchObject({
      name: "First Term",
      order: 1,
      start_date: "2026-06-01",
      end_date: "2026-09-30",
    })
  })

  it("requires a faculty member before a subject assignment can be created", async () => {
    // `SubjectAssignment.faculty` is a required foreign key. PH11.10 added the
    // administrator roster endpoint, so the picker is populated from real
    // records and the form no longer offers a submit that always 400s.
    mockedFetchAllPages.mockImplementation(async (url: string) => {
      if (url.includes("/accounts/faculty-profiles/")) {
        return {
          count: 1,
          results: [
            { id: "fp-1", name: "Ana Rivera", employee_id: "FAC-001" },
          ],
        }
      }
      const segment = url.split("/").filter(Boolean).pop() ?? ""
      return { count: 0, results: RESOURCE_BY_SEGMENT[segment] ?? [] }
    })

    await openTab(/Subject assignments/i)

    const submit = screen.getByRole("button", {
      name: /Create assignment/i,
    })

    await chooseOption(
      screen.getByRole("combobox", { name: /^subject$/i }),
      "Mathematics (MATH-8)"
    )
    await chooseOption(
      screen.getByRole("combobox", { name: /^section$/i }),
      "Bonifacio"
    )
    await chooseOption(
      screen.getByRole("combobox", { name: /academic year/i }),
      "SY 2026-2027"
    )
    // Faculty is still unset, so the required foreign key keeps it blocked.
    await waitFor(() => expect(submit).toBeDisabled())

    const faculty = await screen.findByRole("combobox", { name: /faculty/i })
    await chooseOption(faculty, "Ana Rivera (FAC-001)")

    await waitFor(() => expect(submit).toBeEnabled())
    submit.click()

    await waitFor(() => expect(mockedPost).toHaveBeenCalledTimes(1))
    expect(mockedPost.mock.calls[0]![1]).toMatchObject({
      subject: "sub-1",
      section: "sec-1",
      academic_year: "ay-1",
      faculty: "fp-1",
    })
  })
})

describe("AdminAcademicsPage field-level validation", () => {
  it("shows a server field error against its input and not only in a banner", async () => {
    mockedPost.mockRejectedValueOnce({
      name: "ApiClientError",
      code: "VALIDATION_ERROR",
      message: "academic year: Academic year with this name already exists.",
      status: 400,
      details: {
        name: ["An academic year with this name already exists."],
      },
      isNetworkError: false,
      isCancelled: false,
      isPasswordChangeRequired: false,
    })

    await openTab(/Academic years/i)

    fireChange(field(/^Name$/), "SY 2026-2027")
    fireChange(field(/Start date/i), "2026-06-01")
    fireChange(field(/End date/i), "2027-05-31")

    const submit = screen.getByRole("button", {
      name: /Create academic year/i,
    })
    await waitFor(() => expect(submit).toBeEnabled())
    submit.click()

    const message = await screen.findByText(
      "An academic year with this name already exists."
    )
    // The message is bound to the input it belongs to.
    const input = field(/^Name$/)
    expect(input).toHaveAttribute("aria-invalid", "true")
    expect(input.getAttribute("aria-describedby")).toBe(message.id)
  })

  it("keeps a non-field failure in the banner", async () => {
    mockedPost.mockRejectedValueOnce({
      name: "ApiClientError",
      code: "PERMISSION_DENIED",
      message: "You do not have permission to perform this action.",
      status: 403,
      isNetworkError: false,
      isCancelled: false,
      isPasswordChangeRequired: false,
    })

    await openTab(/Academic years/i)

    fireChange(field(/^Name$/), "SY 2026-2027")
    fireChange(field(/Start date/i), "2026-06-01")
    fireChange(field(/End date/i), "2027-05-31")

    const submit = screen.getByRole("button", {
      name: /Create academic year/i,
    })
    await waitFor(() => expect(submit).toBeEnabled())
    submit.click()

    const alert = await screen.findByRole("alert")
    expect(alert).toHaveTextContent(/do not have permission/i)
    expect(field(/^Name$/)).not.toHaveAttribute("aria-invalid")
  })
})

/** Set a controlled input's value and fire the change React listens for. */
function fireChange(input: HTMLElement, value: string) {
  fireEvent.change(input, { target: { value } })
}

/** Open a Radix select, the same way the existing page suites do. */
async function openSelect(trigger: HTMLElement) {
  await waitFor(() => expect(trigger).toBeEnabled())
  fireEvent.keyDown(trigger, { key: "ArrowDown" })
}

/** Pick the option whose visible text matches, then wait for the value to land. */
async function chooseOption(
  trigger: HTMLElement,
  optionText: RegExp | string
) {
  await openSelect(trigger)
  const option = await screen.findByRole("option", { name: optionText })
  fireEvent.click(option)
}
import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { beforeEach, describe, expect, it, vi } from "vitest"

import {
  nextQuestionOrder,
  type AssessmentQuestion,
} from "@/features/guidance/api"
import { apiClient } from "@/lib/api"
import { fetchAllPages } from "@/lib/pagination"

import { AssessmentsPage } from "./AssessmentsPage"

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
const mockedPost = vi.mocked(apiClient.post)

const questions = [
  {
    id: "q-1",
    assessment: "a-1",
    question_text: "How are you feeling?",
    question_type: "likert",
    order: 1,
    options: ["Good", "Okay", "Low"],
    correct_answer: null,
    created_at: "2025-01-15T00:00:00Z",
    updated_at: "2025-01-15T00:00:00Z",
  },
]

const assessments = [
  {
    id: "a-1",
    title: "Wellness Check-In",
    description: "Monthly pulse.",
    assessment_type: "wellness",
    creator_role: "guidance",
    created_by: "u-1",
    created_by_name: "Robin Vega",
    time_limit_minutes: 15,
    is_published: true,
    published_at: "2025-01-20T00:00:00Z",
    deadline: null,
    question_count: 4,
    created_at: "2025-01-15T00:00:00Z",
    updated_at: "2025-01-20T00:00:00Z",
  },
  {
    id: "a-2",
    title: "Behavior Review",
    description: null,
    assessment_type: "behavioral",
    creator_role: "guidance",
    created_by: "u-1",
    created_by_name: "Robin Vega",
    time_limit_minutes: null,
    is_published: false,
    published_at: null,
    deadline: null,
    question_count: 0,
    created_at: "2025-02-01T00:00:00Z",
    updated_at: "2025-02-01T00:00:00Z",
  },
  {
    id: "a-3",
    title: "Midyear Reflection",
    description: "Closed out.",
    assessment_type: "wellness",
    creator_role: "guidance",
    created_by: "u-1",
    created_by_name: "Robin Vega",
    time_limit_minutes: 20,
    is_published: true,
    published_at: "2025-01-05T00:00:00Z",
    deadline: "2025-03-01",
    question_count: 6,
    created_at: "2025-01-01T00:00:00Z",
    updated_at: "2025-01-05T00:00:00Z",
  },
]

// Decimals arrive as DRF strings and are normalized by the hook.
const results = [
  {
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
  },
  {
    id: "ar-2",
    assessment: "a-1",
    assessment_title: "Wellness Check-In",
    student: "sp-2",
    student_name: "Ben Cruz",
    student_id: "S-1002",
    score: "5.00",
    total_possible: "10.00",
    percentage: "50.00",
    status: "in_progress",
    started_at: "2025-02-02T00:00:00Z",
    completed_at: null,
  },
  {
    id: "ar-3",
    assessment: "a-2",
    assessment_title: "Behavior Review",
    student: "sp-3",
    student_name: "Cara Diaz",
    student_id: "S-1003",
    score: null,
    total_possible: null,
    percentage: null,
    status: "in_progress",
    started_at: "2025-02-03T00:00:00Z",
    completed_at: null,
  },
]

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <AssessmentsPage />
    </QueryClientProvider>
  )
}

async function openSelect(trigger: HTMLElement) {
  await waitFor(() => expect(trigger).toBeEnabled())
  fireEvent.keyDown(trigger, { key: "ArrowDown" })
}

beforeEach(() => {
  vi.clearAllMocks()
  mockedFetchAllPages.mockImplementation(async (url: string) => {
    if (url.includes("/assessments/assessments/")) {
      return { count: assessments.length, results: assessments }
    }
    if (url.includes("/assessments/assessment-results/")) {
      return { count: results.length, results }
    }
    if (url.includes("/assessments/assessment-questions/")) {
      return { count: questions.length, results: questions }
    }
    return { count: 0, results: [] }
  })
})

describe("AssessmentsPage", () => {
  it("renders the counselor's assessments", async () => {
    renderPage()

    expect(
      await screen.findByRole("heading", { name: "Assessments", level: 1 })
    ).toBeInTheDocument()
    expect(await screen.findByText("Wellness Check-In")).toBeInTheDocument()
    expect(screen.getByText("Behavior Review")).toBeInTheDocument()
    expect(screen.getByText("Midyear Reflection")).toBeInTheDocument()
  })

  it("shows published and draft state", async () => {
    renderPage()
    await screen.findByText("Wellness Check-In")

    const publishedCard = (
      screen.getByText("Wellness Check-In") as HTMLElement
    ).closest("[data-assessment-id]") as HTMLElement
    expect(within(publishedCard).getByText("Published")).toHaveAttribute(
      "data-published",
      "true"
    )

    const draftCard = (
      screen.getByText("Behavior Review") as HTMLElement
    ).closest("[data-assessment-id]") as HTMLElement
    expect(within(draftCard).getByText("Draft")).toHaveAttribute(
      "data-published",
      "false"
    )
  })

  it("renders the question count and time limit", async () => {
    renderPage()
    await screen.findByText("Wellness Check-In")

    expect(screen.getByText(/4 questions · 15 min limit/)).toBeInTheDocument()
    expect(screen.getByText(/0 questions · no time limit/)).toBeInTheDocument()
  })

  it("omits a description when the field is null", async () => {
    renderPage()
    await screen.findByText("Behavior Review")

    // a-2 has `description: null`; only the two non-null ones render.
    expect(screen.getByText("Monthly pulse.")).toBeInTheDocument()
    expect(screen.getByText("Closed out.")).toBeInTheDocument()
  })

  it("renders normalized decimals, not raw DRF strings", async () => {
    renderPage()
    await screen.findByText("Wellness Check-In")

    expect(await screen.findByText("8 / 10")).toBeInTheDocument()
    expect(screen.getByText("80%")).toBeInTheDocument()
  })

  it("treats percentage as 0-100, not a 0-1 ratio", async () => {
    renderPage()
    await screen.findByText("Wellness Check-In")

    // "80.00" must render as 80%, never as 0.8 or 8000%.
    expect(screen.getByText("80%")).toBeInTheDocument()
    expect(screen.queryByText("0.8%")).toBeNull()
  })

  it("shows dashes for an unscored in-progress result", async () => {
    renderPage()
    await screen.findByText("Behavior Review")

    const row = document.querySelector('[data-result-id="ar-3"]') as HTMLElement
    expect(within(row).getAllByText("—").length).toBeGreaterThanOrEqual(2)
  })

  it("renders in-progress and completed result states", async () => {
    renderPage()
    await screen.findByText("Wellness Check-In")

    const completed = document.querySelector(
      '[data-result-id="ar-1"]'
    ) as HTMLElement
    expect(within(completed).getByText("Completed")).toHaveAttribute(
      "data-result-status",
      "completed"
    )

    const inProgress = document.querySelector(
      '[data-result-id="ar-2"]'
    ) as HTMLElement
    expect(within(inProgress).getByText("In progress")).toHaveAttribute(
      "data-result-status",
      "in_progress"
    )
  })

  it("groups results under the right assessment", async () => {
    renderPage()
    await screen.findByText("Behavior Review")

    const wellnessCard = (
      screen.getByText("Wellness Check-In") as HTMLElement
    ).closest("[data-assessment-id]") as HTMLElement
    // Two results belong to a-1 and must not leak into a-2.
    expect(within(wellnessCard).queryByText("Cara Diaz")).toBeNull()

    const behaviorCard = (
      screen.getByText("Behavior Review") as HTMLElement
    ).closest("[data-assessment-id]") as HTMLElement
    expect(within(behaviorCard).getByText("Cara Diaz")).toBeInTheDocument()
  })

  it("shows a per-assessment empty state when nothing was recorded", async () => {
    renderPage()
    await screen.findByText("Midyear Reflection")

    const card = (
      screen.getByText("Midyear Reflection") as HTMLElement
    ).closest("[data-assessment-id]") as HTMLElement
    expect(
      within(card).getByText(/No results recorded for this assessment/i)
    ).toBeInTheDocument()
  })

  it("filters by published state", async () => {
    renderPage()
    await screen.findByText("Behavior Review")

    await openSelect(screen.getByLabelText("Status"))
    fireEvent.click(await screen.findByRole("option", { name: "Draft" }))

    await waitFor(() =>
      expect(screen.queryByText("Wellness Check-In")).toBeNull()
    )
    expect(screen.getByText("Behavior Review")).toBeInTheDocument()
  })

  it("filters by assessment type", async () => {
    renderPage()
    await screen.findByText("Wellness Check-In")

    await openSelect(screen.getByLabelText("Type"))
    fireEvent.click(await screen.findByRole("option", { name: "Behavioral" }))

    await waitFor(() =>
      expect(screen.queryByText("Wellness Check-In")).toBeNull()
    )
    expect(screen.getByText("Behavior Review")).toBeInTheDocument()
  })

  it("searches title and description", async () => {
    renderPage()
    await screen.findByText("Wellness Check-In")

    fireEvent.change(screen.getByLabelText("Search"), {
      target: { value: "closed out" },
    })

    await waitFor(() =>
      expect(screen.queryByText("Wellness Check-In")).toBeNull()
    )
    expect(screen.getByText("Midyear Reflection")).toBeInTheDocument()
  })

  it("shows an empty state when filters exclude everything", async () => {
    renderPage()
    await screen.findByText("Wellness Check-In")

    fireEvent.change(screen.getByLabelText("Search"), {
      target: { value: "zzzz-no-match" },
    })

    expect(
      await screen.findByText(/No assessments match the current filters/i)
    ).toBeInTheDocument()
  })

  it("surfaces a fetch failure", async () => {
    mockedFetchAllPages.mockRejectedValue(new Error("boom"))

    renderPage()

    const alert = await screen.findByRole("alert")
    expect(alert).toHaveTextContent("boom")
  })
})

describe("nextQuestionOrder", () => {
  // The backend is unique on (assessment, order), so the default must be one
  // past whatever is already present.
  const cases: ReadonlyArray<{ existing: number[]; expected: number }> = [
    { existing: [], expected: 1 },
    { existing: [1], expected: 2 },
    { existing: [1, 2], expected: 3 },
    { existing: [1, 2, 3], expected: 4 },
    // A gap must not produce a colliding default.
    { existing: [1, 5], expected: 6 },
    // Unordered input, highest wins.
    { existing: [3, 1, 2], expected: 4 },
  ]

  it.each(cases)(
    "existing [$existing] -> $expected",
    ({ existing, expected }) => {
      expect(nextQuestionOrder(existing.map((order) => ({ order })))).toBe(
        expected
      )
    }
  )
})

describe("assessment authoring", () => {
  it("offers only the two guidance-owned assessment types", async () => {
    renderPage()
    await screen.findByText("Wellness Check-In")

    fireEvent.click(screen.getByRole("button", { name: /new assessment/i }))
    const dialog = await screen.findByRole("dialog")

    await openSelect(within(dialog).getByRole("combobox", { name: "Type" }))
    expect(
      await screen.findByRole("option", { name: "Wellness" })
    ).toBeInTheDocument()
    expect(
      screen.getByRole("option", { name: "Behavioral" })
    ).toBeInTheDocument()
    // `academic` belongs to faculty and is refused by the serializer.
    expect(screen.queryByRole("option", { name: "Academic" })).toBeNull()
  })

  it("creates an assessment with only writable fields", async () => {
    mockedPost.mockResolvedValue({ data: {} } as never)

    renderPage()
    await screen.findByText("Wellness Check-In")

    fireEvent.click(screen.getByRole("button", { name: /new assessment/i }))
    const dialog = await screen.findByRole("dialog")

    fireEvent.change(within(dialog).getByLabelText(/^title$/i), {
      target: { value: "  Belonging Check  " },
    })
    fireEvent.change(within(dialog).getByLabelText(/time limit/i), {
      target: { value: "20" },
    })
    fireEvent.click(
      within(dialog).getByRole("button", { name: "Create assessment" })
    )

    await waitFor(() => {
      expect(mockedPost).toHaveBeenCalledWith("/assessments/assessments/", {
        title: "Belonging Check",
        assessment_type: "wellness",
        description: null,
        time_limit_minutes: 20,
        deadline: null,
        target_students: [],
      })
    })

    const payload = mockedPost.mock.calls[0]?.[1] as Record<string, unknown>
    // `created_by` is read-only and `creator_role` is inferred server-side.
    expect(payload).not.toHaveProperty("created_by")
    expect(payload).not.toHaveProperty("creator_role")
    expect(payload).not.toHaveProperty("is_published")
  })

  it("only offers students with guidance activity as targets", async () => {
    mockedFetchAllPages.mockImplementation(async (url: string) => {
      if (url.includes("/assessments/assessments/")) {
        return { count: assessments.length, results: assessments }
      }
      if (url.includes("/assessments/assessment-results/")) {
        return { count: 1, results: [results[0]] }
      }
      if (url.includes("/guidance/risk-alerts/")) {
        return {
          count: 1,
          results: [
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
              generated_at: "2025-02-01T00:00:00Z",
              last_updated: "2025-02-01T00:00:00Z",
              created_at: "2025-02-01T00:00:00Z",
              updated_at: "2025-02-01T00:00:00Z",
            },
          ],
        }
      }
      return { count: 0, results: [] }
    })

    renderPage()
    await screen.findByText("Wellness Check-In")

    fireEvent.click(screen.getByRole("button", { name: /new assessment/i }))
    const dialog = await screen.findByRole("dialog")

    expect(
      within(dialog).getByRole("button", { name: "Ana Reyes" })
    ).toBeInTheDocument()
    expect(
      within(dialog).getByText(/1 selected|0 selected/i)
    ).toBeInTheDocument()
  })

  it("lists a draft assessment's questions", async () => {
    renderPage()
    await screen.findByText("Wellness Check-In")

    expect(await screen.findByText("How are you feeling?")).toBeInTheDocument()
    expect(screen.getByText("Good · Okay · Low")).toBeInTheDocument()
  })

  it("offers the add-question form only for a draft", async () => {
    renderPage()
    await screen.findByText("Wellness Check-In")

    // a-1 is published, a-2 is a draft.
    const published = screen
      .getByText("Wellness Check-In")
      .closest("[data-assessment-id]") as HTMLElement
    expect(
      within(published).queryByRole("form", { name: "Add question" })
    ).toBeNull()

    const draft = screen
      .getByText("Behavior Review")
      .closest("[data-assessment-id]") as HTMLElement
    expect(
      within(draft).getByRole("form", { name: "Add question" })
    ).toBeInTheDocument()
  })

  it("creates a question at the questions endpoint", async () => {
    mockedPost.mockResolvedValue({ data: {} } as never)

    renderPage()
    await screen.findByText("Behavior Review")

    const draft = screen
      .getByText("Behavior Review")
      .closest("[data-assessment-id]") as HTMLElement
    const form = within(draft).getByRole("form", { name: "Add question" })

    fireEvent.change(within(form).getByLabelText(/question text/i), {
      target: { value: "  Which support helps?  " },
    })
    await openSelect(
      within(form).getByRole("combobox", { name: /question type/i })
    )
    fireEvent.click(
      await screen.findByRole("option", { name: "Multiple choice" })
    )

    fireEvent.change(within(form).getByLabelText(/^options$/i), {
      target: { value: "Mentoring\nCheck-ins" },
    })
    fireEvent.click(within(form).getByRole("button", { name: "Add question" }))

    await waitFor(() => {
      expect(mockedPost).toHaveBeenCalledWith(
        "/assessments/assessment-questions/",
        {
          assessment: "a-2",
          question_text: "Which support helps?",
          question_type: "multiple_choice",
          order: 1,
          options: ["Mentoring", "Check-ins"],
          correct_answer: null,
        }
      )
    })
  })

  it("blocks an option-bearing question with a single option", async () => {
    // `AssessmentQuestion.clean()` requires at least 2 options for
    // multiple_choice and likert, and the model cannot report that as a field
    // error, so the server rejects the request without naming the cause. The
    // form blocks the submit instead of round-tripping a guaranteed failure.
    renderPage()
    await screen.findByText("Behavior Review")

    const draft = screen
      .getByText("Behavior Review")
      .closest("[data-assessment-id]") as HTMLElement
    const form = within(draft).getByRole("form", { name: "Add question" })

    fireEvent.change(within(form).getByLabelText(/question text/i), {
      target: { value: "Pick one" },
    })
    fireEvent.change(within(form).getByLabelText(/^options$/i), {
      target: { value: "Only one" },
    })

    expect(
      within(form).getByText(
        "Multiple choice questions must have at least 2 options."
      )
    ).toBeInTheDocument()
    expect(
      within(form).getByRole("button", { name: "Add question" })
    ).toBeDisabled()

    fireEvent.click(within(form).getByRole("button", { name: "Add question" }))
    expect(mockedPost).not.toHaveBeenCalled()
  })

  it("blocks an option-bearing question with no options typed", async () => {
    renderPage()
    await screen.findByText("Behavior Review")

    const draft = screen
      .getByText("Behavior Review")
      .closest("[data-assessment-id]") as HTMLElement
    const form = within(draft).getByRole("form", { name: "Add question" })

    fireEvent.change(within(form).getByLabelText(/question text/i), {
      target: { value: "Open question" },
    })

    expect(
      within(form).getByRole("button", { name: "Add question" })
    ).toBeDisabled()
    fireEvent.click(within(form).getByRole("button", { name: "Add question" }))
    expect(mockedPost).not.toHaveBeenCalled()
  })

  it("blocks a multiple choice answer that is not one of the options", async () => {
    renderPage()
    await screen.findByText("Behavior Review")

    const draft = screen
      .getByText("Behavior Review")
      .closest("[data-assessment-id]") as HTMLElement
    const form = within(draft).getByRole("form", { name: "Add question" })

    fireEvent.change(within(form).getByLabelText(/question text/i), {
      target: { value: "Which support helps?" },
    })
    fireEvent.change(within(form).getByLabelText(/^options$/i), {
      target: { value: "Mentoring\nCheck-ins" },
    })
    fireEvent.change(within(form).getByLabelText(/correct answer/i), {
      target: { value: "Excellent" },
    })

    expect(
      within(form).getByText(
        "Correct answer must be one of the provided options."
      )
    ).toBeInTheDocument()
    expect(
      within(form).getByRole("button", { name: "Add question" })
    ).toBeDisabled()
    expect(mockedPost).not.toHaveBeenCalled()
  })

  it("accepts a multiple choice answer that matches an option", async () => {
    mockedPost.mockResolvedValue({ data: {} } as never)

    renderPage()
    await screen.findByText("Behavior Review")

    const draft = screen
      .getByText("Behavior Review")
      .closest("[data-assessment-id]") as HTMLElement
    const form = within(draft).getByRole("form", { name: "Add question" })

    fireEvent.change(within(form).getByLabelText(/question text/i), {
      target: { value: "Which support helps?" },
    })
    fireEvent.change(within(form).getByLabelText(/^options$/i), {
      target: { value: "Mentoring\nCheck-ins" },
    })
    fireEvent.change(within(form).getByLabelText(/correct answer/i), {
      target: { value: "Mentoring" },
    })

    const submit = within(form).getByRole("button", { name: "Add question" })
    expect(submit).toBeEnabled()
    fireEvent.click(submit)

    await waitFor(() => {
      expect(mockedPost).toHaveBeenCalledWith(
        "/assessments/assessment-questions/",
        expect.objectContaining({ correct_answer: "Mentoring" })
      )
    })
  })

  it("blocks a true/false answer that is not exactly True or False", async () => {
    renderPage()
    await screen.findByText("Behavior Review")

    const draft = screen
      .getByText("Behavior Review")
      .closest("[data-assessment-id]") as HTMLElement
    const form = within(draft).getByRole("form", { name: "Add question" })

    fireEvent.change(within(form).getByLabelText(/question text/i), {
      target: { value: "The sky is blue." },
    })
    await openSelect(
      within(form).getByRole("combobox", { name: /question type/i })
    )
    fireEvent.click(await screen.findByRole("option", { name: "True / False" }))

    fireEvent.change(within(form).getByLabelText(/correct answer/i), {
      target: { value: "Yes" },
    })

    expect(
      within(form).getByText(
        'True/False correct answer must be "True" or "False".'
      )
    ).toBeInTheDocument()
    expect(
      within(form).getByRole("button", { name: "Add question" })
    ).toBeDisabled()
    expect(mockedPost).not.toHaveBeenCalled()
  })

  it("accepts a true/false answer of exactly True", async () => {
    mockedPost.mockResolvedValue({ data: {} } as never)

    renderPage()
    await screen.findByText("Behavior Review")

    const draft = screen
      .getByText("Behavior Review")
      .closest("[data-assessment-id]") as HTMLElement
    const form = within(draft).getByRole("form", { name: "Add question" })

    fireEvent.change(within(form).getByLabelText(/question text/i), {
      target: { value: "The sky is blue." },
    })
    await openSelect(
      within(form).getByRole("combobox", { name: /question type/i })
    )
    fireEvent.click(await screen.findByRole("option", { name: "True / False" }))

    fireEvent.change(within(form).getByLabelText(/correct answer/i), {
      target: { value: "True" },
    })

    const submit = within(form).getByRole("button", { name: "Add question" })
    expect(submit).toBeEnabled()
    fireEvent.click(submit)

    await waitFor(() => {
      expect(mockedPost).toHaveBeenCalledWith(
        "/assessments/assessment-questions/",
        expect.objectContaining({
          question_type: "true_false",
          options: null,
          correct_answer: "True",
        })
      )
    })
  })

  it("still reports the option count once the minimum is met", async () => {
    renderPage()
    await screen.findByText("Behavior Review")

    const draft = screen
      .getByText("Behavior Review")
      .closest("[data-assessment-id]") as HTMLElement
    const form = within(draft).getByRole("form", { name: "Add question" })

    fireEvent.change(within(form).getByLabelText(/^options$/i), {
      target: { value: "One\nTwo\nThree" },
    })
    expect(
      within(form).getByText("3 options; one per line.")
    ).toBeInTheDocument()
  })

  it("requires two scale options on a likert question", async () => {
    renderPage()
    await screen.findByText("Behavior Review")

    const draft = screen
      .getByText("Behavior Review")
      .closest("[data-assessment-id]") as HTMLElement
    const form = within(draft).getByRole("form", { name: "Add question" })

    fireEvent.change(within(form).getByLabelText(/question text/i), {
      target: { value: "How satisfied are you?" },
    })
    await openSelect(
      within(form).getByRole("combobox", { name: /question type/i })
    )
    fireEvent.click(await screen.findByRole("option", { name: "Likert scale" }))

    fireEvent.change(within(form).getByLabelText(/scale points/i), {
      target: { value: "Agree" },
    })

    expect(
      within(form).getByText(
        "Likert questions must have at least 2 scale options."
      )
    ).toBeInTheDocument()
    expect(
      within(form).getByRole("button", { name: "Add question" })
    ).toBeDisabled()
  })

  it("does not ask for options on an essay question", async () => {
    renderPage()
    await screen.findByText("Behavior Review")

    const draft = screen
      .getByText("Behavior Review")
      .closest("[data-assessment-id]") as HTMLElement
    const form = within(draft).getByRole("form", { name: "Add question" })

    await openSelect(
      within(form).getByRole("combobox", { name: /question type/i })
    )
    fireEvent.click(await screen.findByRole("option", { name: "Essay" }))

    expect(within(form).queryByLabelText(/^options$/i)).toBeNull()
  })

  it("deploys a draft through the real deploy action", async () => {
    mockedPost.mockResolvedValue({ data: {} } as never)

    renderPage()
    await screen.findByText("Behavior Review")

    const draft = screen
      .getByText("Behavior Review")
      .closest("[data-assessment-id]") as HTMLElement
    fireEvent.click(within(draft).getByRole("button", { name: "Deploy" }))

    await waitFor(() => {
      expect(mockedPost).toHaveBeenCalledWith(
        "/assessments/assessments/a-2/deploy/",
        undefined
      )
    })
  })

  it("does not offer deploy on a published assessment", async () => {
    renderPage()
    await screen.findByText("Wellness Check-In")

    const published = screen
      .getByText("Wellness Check-In")
      .closest("[data-assessment-id]") as HTMLElement
    expect(
      within(published).queryByRole("button", { name: "Deploy" })
    ).toBeNull()
    expect(
      within(published).getByText(/blocks a second deploy/i)
    ).toBeInTheDocument()
  })

  it("surfaces the server refusal when deploy has no questions", async () => {
    mockedPost.mockRejectedValue(
      new Error("Cannot publish assessment without questions.")
    )

    renderPage()
    await screen.findByText("Behavior Review")

    const draft = screen
      .getByText("Behavior Review")
      .closest("[data-assessment-id]") as HTMLElement
    fireEvent.click(within(draft).getByRole("button", { name: "Deploy" }))

    expect(
      await screen.findByText(/Cannot publish assessment without questions/i)
    ).toBeInTheDocument()
  })

  it("surfaces the server refusal when already published", async () => {
    mockedPost.mockRejectedValue(new Error("Assessment is already published."))

    renderPage()
    await screen.findByText("Behavior Review")

    const draft = screen
      .getByText("Behavior Review")
      .closest("[data-assessment-id]") as HTMLElement
    fireEvent.click(within(draft).getByRole("button", { name: "Deploy" }))

    expect(
      await screen.findByText(/Assessment is already published/i)
    ).toBeInTheDocument()
  })

  it("never calls an AI question-generation endpoint", async () => {
    renderPage()
    await screen.findByText("Wellness Check-In")

    fireEvent.click(screen.getByRole("button", { name: /new assessment/i }))
    await screen.findByRole("dialog")

    expect(screen.queryByText(/generat/i)).toBeNull()
    expect(screen.queryByText(/\bAI\b/i)).toBeNull()
  })
})

describe("question order defaults", () => {
  function question(order: number, assessment = "a-2"): AssessmentQuestion {
    return {
      id: `q-${order}`,
      assessment,
      question_text: `Question ${order}`,
      question_type: "essay",
      order,
      options: null,
      correct_answer: null,
      created_at: "2025-01-15T00:00:00Z",
      updated_at: "2025-01-15T00:00:00Z",
    }
  }

  function stubQuestions(orders: number[]) {
    const rows = orders.map((order) => question(order))
    mockedFetchAllPages.mockImplementation(async (url: string) => {
      if (url.includes("/assessments/assessments/")) {
        return { count: assessments.length, results: assessments }
      }
      if (url.includes("/assessments/assessment-results/")) {
        return { count: 0, results: [] }
      }
      if (url.includes("/assessments/assessment-questions/")) {
        return { count: rows.length, results: rows }
      }
      return { count: 0, results: [] }
    })
  }

  /**
   * Renders and returns the add-question form for the draft, once its question
   * list has actually settled. Without the wait the form is read while the
   * questions query is still loading, so the derived default has not arrived.
   */
  async function draftForm(orders: number[]) {
    renderPage()
    await screen.findByText("Behavior Review")
    const draft = screen
      .getByText("Behavior Review")
      .closest("[data-assessment-id]") as HTMLElement

    if (orders.length > 0) {
      await within(draft).findByText(`Question ${Math.max(...orders)}`)
    } else {
      await within(draft).findByText(/has no questions yet/i)
    }

    return within(draft).getByRole("form", { name: "Add question" })
  }

  /**
   * The form defaults to `multiple_choice`, and
   * `AssessmentQuestion.clean()` requires at least 2 options for that type.
   * Tests in this block are about the order value, not about options, so they
   * supply a valid option set and stay focused on their own subject.
   */
  function fillValidOptions(form: HTMLElement) {
    fireEvent.change(within(form).getByLabelText(/^options$/i), {
      target: { value: "Yes\nNo" },
    })
  }

  it("defaults to 1 for an assessment with no questions", async () => {
    stubQuestions([])
    const form = await draftForm([])

    expect(within(form).getByLabelText(/^order$/i)).toHaveValue(1)
    expect(
      within(form).getByText(/Defaults to 1, one past the highest existing/i)
    ).toBeInTheDocument()
  })

  it("defaults to 2 when order 1 already exists", async () => {
    stubQuestions([1])
    const form = await draftForm([1])

    expect(within(form).getByLabelText(/^order$/i)).toHaveValue(2)
  })

  it("defaults to 3 when orders 1 and 2 already exist", async () => {
    stubQuestions([1, 2])
    const form = await draftForm([1, 2])

    expect(within(form).getByLabelText(/^order$/i)).toHaveValue(3)
  })

  it("defaults to 4 when orders 1, 2 and 3 already exist", async () => {
    stubQuestions([1, 2, 3])
    const form = await draftForm([1, 2, 3])

    expect(within(form).getByLabelText(/^order$/i)).toHaveValue(4)
  })

  it("never defaults onto an existing order, even with a gap", async () => {
    stubQuestions([1, 5])
    const form = await draftForm([1, 5])

    expect(within(form).getByLabelText(/^order$/i)).toHaveValue(6)
  })

  it("rejects a manual order that is already used", async () => {
    stubQuestions([1, 2, 3])
    const form = await draftForm([1, 2, 3])

    fireEvent.change(within(form).getByLabelText(/question text/i), {
      target: { value: "New question" },
    })
    fireEvent.change(within(form).getByLabelText(/^order$/i), {
      target: { value: "2" },
    })

    expect(
      await within(form).findByText(
        /Order 2 is already used by another question/i
      )
    ).toBeInTheDocument()
    expect(
      within(form).getByRole("button", { name: "Add question" })
    ).toBeDisabled()
    expect(mockedPost).not.toHaveBeenCalled()
  })

  it("allows a free manual order", async () => {
    mockedPost.mockResolvedValue({ data: {} } as never)
    stubQuestions([1, 2, 3])

    const form = await draftForm([1, 2, 3])
    fireEvent.change(within(form).getByLabelText(/question text/i), {
      target: { value: "Placed earlier" },
    })
    fireEvent.change(within(form).getByLabelText(/^order$/i), {
      target: { value: "10" },
    })
    fillValidOptions(form)

    expect(
      within(form).queryByText(/already used by another question/i)
    ).toBeNull()
    fireEvent.click(within(form).getByRole("button", { name: "Add question" }))

    await waitFor(() => {
      expect(mockedPost).toHaveBeenCalledWith(
        "/assessments/assessment-questions/",
        expect.objectContaining({ order: 10 })
      )
    })
  })

  it("sends the derived order in the payload for a reloaded draft", async () => {
    // The exact regression: a fresh form mounted against a draft that already
    // has a question at order 1 must not submit order 1 again.
    mockedPost.mockResolvedValue({ data: {} } as never)
    stubQuestions([1])

    const form = await draftForm([1])
    fireEvent.change(within(form).getByLabelText(/question text/i), {
      target: { value: "Second question" },
    })
    fillValidOptions(form)
    fireEvent.click(within(form).getByRole("button", { name: "Add question" }))

    await waitFor(() => {
      expect(mockedPost).toHaveBeenCalledWith(
        "/assessments/assessment-questions/",
        expect.objectContaining({ assessment: "a-2", order: 2 })
      )
    })
  })

  it("keeps the next order correct after a successful creation", async () => {
    // After the create succeeds the questions query is invalidated and
    // refetched. The mock grows its list when the POST lands, so the refetch
    // actually observes the new question rather than a pre-set array.
    let orders = [1]
    mockedPost.mockImplementation(async () => {
      orders = [1, 2]
      return { data: {} } as never
    })
    mockedFetchAllPages.mockImplementation(async (url: string) => {
      if (url.includes("/assessments/assessments/")) {
        return { count: assessments.length, results: assessments }
      }
      if (url.includes("/assessments/assessment-results/")) {
        return { count: 0, results: [] }
      }
      if (url.includes("/assessments/assessment-questions/")) {
        return {
          count: orders.length,
          results: orders.map((order) => question(order)),
        }
      }
      return { count: 0, results: [] }
    })

    renderPage()
    await screen.findByText("Behavior Review")
    const draft = screen
      .getByText("Behavior Review")
      .closest("[data-assessment-id]") as HTMLElement
    // Wait for the question list so the derived default has arrived.
    await within(draft).findByText("Question 1")
    const form = within(draft).getByRole("form", { name: "Add question" })

    expect(within(form).getByLabelText(/^order$/i)).toHaveValue(2)

    fireEvent.change(within(form).getByLabelText(/question text/i), {
      target: { value: "Second question" },
    })
    fillValidOptions(form)
    fireEvent.click(within(form).getByRole("button", { name: "Add question" }))

    // The server accepted order 2, the list refetched as [1, 2], and the cleared
    // override lets the field re-derive to 3.
    await within(draft).findByText("Question 2")
    expect(within(form).getByLabelText(/^order$/i)).toHaveValue(3)
  })

  it("leaves the create payload shape unchanged", async () => {
    mockedPost.mockResolvedValue({ data: {} } as never)
    stubQuestions([1])

    const form = await draftForm([1])
    fireEvent.change(within(form).getByLabelText(/question text/i), {
      target: { value: "  Second question  " },
    })
    fireEvent.change(within(form).getByLabelText(/^options$/i), {
      target: { value: "Yes\nNo" },
    })
    fireEvent.change(within(form).getByLabelText(/correct answer/i), {
      target: { value: "Yes" },
    })
    fireEvent.click(within(form).getByRole("button", { name: "Add question" }))

    await waitFor(() => {
      expect(mockedPost).toHaveBeenCalledWith(
        "/assessments/assessment-questions/",
        {
          assessment: "a-2",
          question_text: "Second question",
          question_type: "multiple_choice",
          order: 2,
          options: ["Yes", "No"],
          correct_answer: "Yes",
        }
      )
    })
  })

  it("still rejects an order below 1", async () => {
    stubQuestions([1])
    const form = await draftForm([1])

    fireEvent.change(within(form).getByLabelText(/question text/i), {
      target: { value: "Bad order" },
    })
    fireEvent.change(within(form).getByLabelText(/^order$/i), {
      target: { value: "0" },
    })

    expect(
      await within(form).findByText(/Order must be 1 or greater/i)
    ).toBeInTheDocument()
    expect(
      within(form).getByRole("button", { name: "Add question" })
    ).toBeDisabled()
  })
})

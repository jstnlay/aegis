import { render, screen, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { StudentSupportPage } from "@/features/student/StudentSupportPage"
import type { StudentBehavioralNote } from "@/features/student/api"

const fetchAllPages = vi.hoisted(() =>
  vi.fn<
    (url: string) => Promise<{ results: StudentBehavioralNote[]; count: number }>
  >()
)

vi.mock("@/lib/pagination", () => ({
  fetchAllPages: fetchAllPages,
}))

function note(overrides: Partial<StudentBehavioralNote>): StudentBehavioralNote {
  return {
    id: `bn-${Math.random().toString(36).slice(2)}`,
    student: "stu-1",
    student_name: "Student E2E",
    student_id_code: "STU-E2E-001",
    recorded_by_name: "Dana Cruz",
    note_type: "positive",
    note_text: "Helped organise the class activity.",
    date_recorded: "2026-11-13T10:00:00+08:00",
    ...overrides,
  }
}

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <StudentSupportPage />
    </QueryClientProvider>
  )
}

beforeEach(() => {
  fetchAllPages.mockReset()
})

afterEach(() => {
  vi.restoreAllMocks()
})

/*
 * Objective 2.1.3: "Behavioral notes and class-related concerns." The backend
 * already scopes the list to the signed-in student, so these cases pin the
 * surface: the student-only endpoint, the readable type labels and dates, and
 * the three states kept distinct.
 */
describe("StudentSupportPage", () => {
  it("reads the student's own notes from the scoped endpoint", async () => {
    fetchAllPages.mockResolvedValue({ results: [], count: 0 })

    renderPage()

    await waitFor(() => expect(fetchAllPages).toHaveBeenCalled())
    expect(fetchAllPages).toHaveBeenCalledWith("/guidance/behavioral-notes/")
  })

  it("announces the load instead of sitting silent", () => {
    fetchAllPages.mockReturnValue(new Promise(() => {}))

    renderPage()

    expect(screen.getByRole("status")).toHaveTextContent(
      "Loading behavioral notes"
    )
  })

  it("renders each note with a readable type, date and author", async () => {
    fetchAllPages.mockResolvedValue({
      results: [
        note({
          id: "bn-warning",
          note_type: "warning",
          note_text: "Repeatedly late to class.",
          date_recorded: "2026-11-12T08:00:00+08:00",
          recorded_by_name: "Ben Santos",
        }),
        note({ id: "bn-positive" }),
      ],
      count: 2,
    })

    renderPage()

    expect(
      await screen.findByText("Repeatedly late to class.")
    ).toBeInTheDocument()
    expect(screen.getByText("Warning")).toBeInTheDocument()
    expect(screen.getByText("Positive")).toBeInTheDocument()
    expect(screen.getByText(/Ben Santos/)).toBeInTheDocument()
    // The raw note_type enum never reaches the reader.
    expect(screen.queryByText("warning")).toBeNull()
  })

  it("reports a failed request as an error, not as an empty list", async () => {
    fetchAllPages.mockRejectedValue(new Error("Notes service down."))

    renderPage()

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Notes service down."
    )
    expect(
      screen.queryByText(/No behavioral notes have been recorded for you/i)
    ).not.toBeInTheDocument()
  })

  it("calls an empty result a legitimate empty state", async () => {
    fetchAllPages.mockResolvedValue({ results: [], count: 0 })

    renderPage()

    expect(
      await screen.findByText(/No behavioral notes have been recorded for you/i)
    ).toBeInTheDocument()
    await waitFor(() =>
      expect(screen.queryByRole("alert")).not.toBeInTheDocument()
    )
  })
})

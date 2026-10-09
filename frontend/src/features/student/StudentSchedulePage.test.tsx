import { render, screen, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { StudentSchedulePage } from "@/features/student/StudentSchedulePage"
import type { ScheduleEntry } from "@/features/student/schedule-api"

const fetchAllPages = vi.hoisted(() =>
  vi.fn<(url: string) => Promise<{ results: ScheduleEntry[]; count: number }>>()
)

vi.mock("@/lib/pagination", () => ({
  fetchAllPages: fetchAllPages,
}))

function entry(overrides: Partial<ScheduleEntry>): ScheduleEntry {
  return {
    id: `sc-${Math.random().toString(36).slice(2)}`,
    day_of_week: "mon",
    start_time: "07:30:00",
    end_time: "08:30:00",
    room: "Room 101",
    subject_assignment_detail: {
      id: "sa-1",
      subject_name: "Mathematics",
      subject_code: "MATH-10",
      faculty_name: "Dana Cruz",
      section_name: "Grade 10 - Sampaguita",
      academic_year_name: "SY 2026-2027",
    },
    ...overrides,
  }
}

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <StudentSchedulePage />
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
 * TC-STU-04: "Class schedule is successfully displayed and matches the
 * student's actual enrollment." The endpoint is already scoped by
 * `ScheduleViewSet`, so these cases pin the surface: the day grouping, the
 * readable times, and the three states kept distinct.
 */
describe("StudentSchedulePage", () => {
  it("announces the load instead of sitting silent", () => {
    fetchAllPages.mockReturnValue(new Promise(() => {}))

    renderPage()

    expect(screen.getByRole("status")).toHaveTextContent(
      "Loading class schedule"
    )
  })

  it("groups the student's periods by weekday with readable times", async () => {
    fetchAllPages.mockResolvedValue({
      results: [
        entry({ id: "sc-mon-2", start_time: "10:00:00", end_time: "11:00:00" }),
        entry({
          id: "sc-mon-1",
          start_time: "07:30:00",
          end_time: "08:30:00",
          subject_assignment_detail: {
            id: "sa-2",
            subject_name: "Science",
            subject_code: "SCI-10",
            faculty_name: "Ben Santos",
            section_name: "Grade 10 - Sampaguita",
            academic_year_name: "SY 2026-2027",
          },
        }),
        entry({ id: "sc-wed", day_of_week: "wed" }),
      ],
      count: 3,
    })

    renderPage()

    expect(
      await screen.findByRole("heading", { name: "Monday" })
    ).toBeInTheDocument()
    expect(
      screen.getByRole("heading", { name: "Wednesday" })
    ).toBeInTheDocument()

    // Both Monday periods render, earlier start first.
    const monday = screen.getByRole("heading", { name: "Monday" }).parentElement
      ?.parentElement as HTMLElement
    const rows = monday.textContent ?? ""
    expect(rows).toContain("Science")
    expect(rows).toContain("Mathematics")
    expect(rows.indexOf("7:30 AM")).toBeLessThan(rows.indexOf("10:00 AM"))

    // Raw database clocks never reach the reader.
    expect(screen.queryByText("07:30:00")).toBeNull()
    expect(screen.getAllByText(/Dana Cruz/).length).toBeGreaterThan(0)
  })

  it("reports a failed request as an error, not as an empty schedule", async () => {
    fetchAllPages.mockRejectedValue(new Error("Schedule service down."))

    renderPage()

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Schedule service down."
    )
    expect(
      screen.queryByText(/No class periods are on record/i)
    ).not.toBeInTheDocument()
  })

  it("calls an empty result a legitimate empty state", async () => {
    fetchAllPages.mockResolvedValue({ results: [], count: 0 })

    renderPage()

    expect(
      await screen.findByText(/No class periods are on record/i)
    ).toBeInTheDocument()
    await waitFor(() =>
      expect(screen.queryByRole("alert")).not.toBeInTheDocument()
    )
  })
})

import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { MemoryRouter } from "react-router-dom"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { ParentDashboard } from "./ParentDashboard"
import { useLinkedStudents } from "@/features/parent/api"
import { useStudentDashboardData } from "@/features/student/api"
import type { User } from "@/types/auth"

vi.mock("@/features/auth/AuthContext", () => ({
  useAuth: () => ({
    status: "authenticated",
    user: {
      id: "u-parent",
      email: "parent@school.edu",
      username: "parent1",
      first_name: "Mara",
      last_name: "Cruz",
      role: "parent",
      phone_number: null,
      address: null,
      language_preference: null,
      is_active: true,
      created_at: "2025-01-01T00:00:00Z",
      updated_at: "2025-01-01T00:00:00Z",
    } satisfies User,
    mustChangePassword: false,
    isAuthenticated: true,
    login: vi.fn(),
    logout: vi.fn(),
    changePassword: vi.fn(),
  }),
}))

vi.mock("@/features/parent/api", () => ({
  useLinkedStudents: vi.fn(),
}))

vi.mock("@/features/student/api", () => ({
  useStudentDashboardData: vi.fn(),
}))

const mockedUseLinkedStudents = vi.mocked(useLinkedStudents)
const mockedUseStudentDashboardData = vi.mocked(useStudentDashboardData)

function renderWithClient(ui: React.ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  // The dashboard links to the support record, so it renders inside a
  // router like the real shell does.
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>
  )
}

const CHILD = {
  id: "sp-uuid-1",
  student_name: "Ana Cruz",
  student_id: "STU-001",
  section_name: "Grade 7 - Rizal",
}

function stubLoadedChild(
  overrides: Partial<ReturnType<typeof useStudentDashboardData>> = {}
) {
  mockedUseLinkedStudents.mockReturnValue({
    data: [CHILD],
    isLoading: false,
    isError: false,
  } as unknown as ReturnType<typeof useLinkedStudents>)

  mockedUseStudentDashboardData.mockReturnValue({
    attendance: {
      present_days: 40,
      late_days: 0,
      absent_days: 2,
      total_days: 42,
      attendance_rate: 95.2,
    },
    grades: [
      {
        subject_name: "Mathematics",
        subject_code: "MATH7",
        score: 95,
        letter_grade: "A",
        grading_period: "1st Quarter",
      },
      {
        subject_name: "Filipino",
        subject_code: "FIL7",
        score: 88,
        letter_grade: "B",
        grading_period: "1st Quarter",
      },
    ],
    allGrades: [
      {
        subject_name: "Mathematics",
        subject_code: "MATH7",
        score: 95,
        letter_grade: "A",
        grading_period: "1st Quarter",
      },
      {
        subject_name: "Filipino",
        subject_code: "FIL7",
        score: 88,
        letter_grade: "B",
        grading_period: "1st Quarter",
      },
    ],
    periods: [
      { period_name: "1st Quarter", average_grade: 91.5 },
      { period_name: "2nd Quarter", average_grade: 93 },
    ],
    selectedPeriod: "1st Quarter",
    setSelectedPeriod: vi.fn(),
    averageGrade: 91.5,
    totalSubjects: 8,
    loading: false,
    error: null,
    ...overrides,
  } as unknown as ReturnType<typeof useStudentDashboardData>)
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe("ParentDashboard", () => {
  it("renders loading state", () => {
    mockedUseLinkedStudents.mockReturnValue({
      data: undefined,
      isLoading: true,
      isError: false,
    } as unknown as ReturnType<typeof useLinkedStudents>)
    mockedUseStudentDashboardData.mockReturnValue({
      loading: true,
    } as unknown as ReturnType<typeof useStudentDashboardData>)

    renderWithClient(<ParentDashboard />)

    // PH11.12: scoped to the heading. The card now renders the phrase twice — its
    // `CardTitle` and the visually-hidden label inside the loading `role="status"`
    // region — so a bare `getByText` is ambiguous. Matching the heading is the
    // stronger claim: it pins that the card is labelled by a heading, which the
    // loose text match never checked, and it still fails if the label goes.
    expect(
      screen.getByRole("heading", { name: /Linked Students/i })
    ).toBeInTheDocument()
    // The placeholder announces itself rather than sitting silent.
    expect(screen.getAllByRole("status")[0]).toHaveAttribute(
      "aria-busy",
      "true"
    )
  })

  it("renders the Academic Progress section from the fetched grading-period data", async () => {
    stubLoadedChild()
    renderWithClient(<ParentDashboard />)

    fireEvent.click(await screen.findByRole("button", { name: /Ana Cruz/ }))

    expect(await screen.findByText("Academic Progress")).toBeInTheDocument()

    // The period selector is driven by the already-fetched grading-period
    // data - no extra request is invented.
    const selector = screen.getByLabelText(/grading period/i)
    expect(selector).toHaveValue("1st Quarter")
    expect(
      screen.getByRole("option", { name: /2nd Quarter — Average: 93\.00%/ })
    ).toBeInTheDocument()

    // Period-scoped subject grades (also listed again under Recent Grades).
    expect(screen.getAllByText("Mathematics").length).toBeGreaterThan(0)
    expect(screen.getAllByText("Filipino").length).toBeGreaterThan(0)
  })

  it("renders numeric scores with no letter-grade badges", async () => {
    stubLoadedChild()
    renderWithClient(<ParentDashboard />)

    fireEvent.click(await screen.findByRole("button", { name: /Ana Cruz/ }))

    await screen.findByText("Academic Progress")

    // Scores render numerically; the Philippine system uses no letters.
    expect(screen.queryByText("N/A")).not.toBeInTheDocument()
    expect(screen.queryByText("A")).not.toBeInTheDocument()
  })

  it("shows N/A instead of 0.00% when there is no grade or attendance data", async () => {
    stubLoadedChild({
      averageGrade: null,
      attendance: undefined,
      grades: [],
      allGrades: [],
      periods: [],
      totalSubjects: null,
    } as Partial<ReturnType<typeof useStudentDashboardData>>)

    renderWithClient(<ParentDashboard />)

    fireEvent.click(await screen.findByRole("button", { name: /Ana Cruz/ }))

    await waitFor(() => {
      expect(screen.getAllByText("N/A").length).toBeGreaterThanOrEqual(2)
    })
    expect(screen.queryByText("0.00%")).not.toBeInTheDocument()
    expect(screen.queryByText("0.0%")).not.toBeInTheDocument()
  })

  it("renders an honest error state instead of a fake zero", async () => {
    stubLoadedChild({
      averageGrade: null,
      error: new Error("network down"),
    } as Partial<ReturnType<typeof useStudentDashboardData>>)

    renderWithClient(<ParentDashboard />)

    fireEvent.click(await screen.findByRole("button", { name: /Ana Cruz/ }))

    expect(
      await screen.findAllByText(/Unable to load academic progress/i)
    ).not.toHaveLength(0)
    expect(screen.queryByText("0.00%")).not.toBeInTheDocument()
  })
})

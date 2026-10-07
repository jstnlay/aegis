import { render, screen } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { StudentDashboard } from "./StudentDashboard"
import {
  useStudentDashboardData,
  useStudentProfileId,
} from "@/features/student/api"
import type { User } from "@/types/auth"

vi.mock("@/features/auth/AuthContext", () => ({
  useAuth: () => ({
    status: "authenticated",
    user: {
      id: "u-student",
      email: "student@school.edu",
      username: "student1",
      first_name: "Ana",
      last_name: "Cruz",
      role: "student",
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

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: false,
    },
  },
})

function renderWithClient(ui: React.ReactElement) {
  return render(
    <QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>
  )
}

vi.mock("@/features/student/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/features/student/api")>()
  return {
    ...actual,
    useStudentProfileId: vi.fn(),
    useStudentDashboardData: vi.fn(),
  }
})

const mockedProfileId = vi.mocked(useStudentProfileId)
const mockedDashboardData = vi.mocked(useStudentDashboardData)

beforeEach(() => {
  vi.clearAllMocks()
  mockedProfileId.mockReturnValue({
    data: "sp-uuid-1",
    isLoading: false,
    isError: false,
  } as unknown as ReturnType<typeof useStudentProfileId>)
})

describe("StudentDashboard", () => {
  it("renders loading state", () => {
    mockedDashboardData.mockReturnValue({
      loading: true,
    } as unknown as ReturnType<typeof useStudentDashboardData>)

    renderWithClient(<StudentDashboard />)
    // PH11.11: scoped to the heading. The tile now renders the phrase twice — its
    // `CardTitle` and the visually-hidden label inside the loading `role="status"`
    // region — so a bare `getByText` is genuinely ambiguous. Matching the heading
    // is the stronger claim: it pins that the tile is labelled by a heading, which
    // the loose text match never checked, and it still fails if the label goes.
    expect(
      screen.getByRole("heading", { name: /Average Grade/i })
    ).toBeInTheDocument()
    // The skeleton announces itself rather than sitting silent.
    // `getAllByRole` because three tiles plus the progress section are all pending
    // at once, and each is its own live region — four separate announcements of
    // four separate things, which is the intent.
    const pending = screen.getAllByRole("status")
    expect(pending.length).toBeGreaterThan(0)
    for (const region of pending) {
      expect(region).toHaveAttribute("aria-busy", "true")
    }
    expect(pending[0]).toHaveTextContent(/Average Grade/i)
  })

  it("describes Total Subjects as subjects with finalized grades, not assessments", () => {
    mockedDashboardData.mockReturnValue({
      averageGrade: 91.5,
      totalSubjects: 8,
      attendance: {
        present_days: 40,
        late_days: 0,
        absent_days: 2,
        total_days: 42,
        attendance_rate: 95.2,
      },
      grades: [],
      periods: [],
      selectedPeriod: "",
      setSelectedPeriod: vi.fn(),
      loading: false,
      error: null,
    } as unknown as ReturnType<typeof useStudentDashboardData>)

    renderWithClient(<StudentDashboard />)

    expect(screen.getByText("Total Subjects")).toBeInTheDocument()
    expect(
      screen.getByText("Subjects with finalized grades")
    ).toBeInTheDocument()
    expect(screen.queryByText("Completed assessments")).not.toBeInTheDocument()
  })

  it("shows N/A rather than 0 when the metrics carry no data", () => {
    mockedDashboardData.mockReturnValue({
      averageGrade: null,
      totalSubjects: null,
      attendance: undefined,
      grades: [],
      periods: [],
      selectedPeriod: "",
      setSelectedPeriod: vi.fn(),
      loading: false,
      error: null,
    } as unknown as ReturnType<typeof useStudentDashboardData>)

    renderWithClient(<StudentDashboard />)

    expect(screen.getAllByText("N/A").length).toBeGreaterThanOrEqual(3)
    expect(screen.queryByText("0.00%")).not.toBeInTheDocument()
  })

  it("keeps a legitimate zero as a real measurement", () => {
    mockedDashboardData.mockReturnValue({
      averageGrade: 0,
      totalSubjects: 0,
      attendance: {
        present_days: 0,
        late_days: 0,
        absent_days: 12,
        total_days: 12,
        attendance_rate: 0,
      },
      grades: [],
      periods: [],
      selectedPeriod: "",
      setSelectedPeriod: vi.fn(),
      loading: false,
      error: null,
    } as unknown as ReturnType<typeof useStudentDashboardData>)

    renderWithClient(<StudentDashboard />)

    expect(screen.getByText("0.00%")).toBeInTheDocument()
    expect(screen.getByText("0.0%")).toBeInTheDocument()
    expect(screen.queryByText("N/A")).not.toBeInTheDocument()
  })
})

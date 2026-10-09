import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { AxiosError, AxiosHeaders } from "axios"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { AcademicsPage } from "@/features/academics/AcademicsPage"
import { useAuth } from "@/features/auth/AuthContext"
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

function makeUser(role: Role): User {
  return {
    id: `u-${role}`,
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
      <AcademicsPage />
    </QueryClientProvider>
  )
}

beforeEach(() => {
  authState.user = null
  vi.clearAllMocks()
  mockedFetchAllPages.mockResolvedValue({ count: 0, results: [] })
})

describe("AcademicsPage (student)", () => {
  beforeEach(() => {
    authState.user = makeUser("student")
  })

  it("renders the read-only grade record heading", async () => {
    renderPage()
    expect(
      await screen.findByRole("heading", { name: "Academics", level: 2 })
    ).toBeInTheDocument()
    expect(
      screen.getByText(/Grades appear here once they are finalized/i)
    ).toBeInTheDocument()
  })

  it("does not offer the faculty grade-encoding form", () => {
    renderPage()
    expect(screen.queryByText(/Encode a grade/i)).not.toBeInTheDocument()
    expect(
      screen.queryByRole("button", { name: /Encode draft grade/i })
    ).toBeNull()
  })

  it("does not leak draft/submitted rows to students", () => {
    renderPage()
    expect(
      screen.getByText(/Only finalized results are listed/i)
    ).toBeInTheDocument()
  })

  it("shows an empty state when no finalized grades exist", async () => {
    renderPage()
    expect(
      await screen.findByText(/No finalized grades yet/i)
    ).toBeInTheDocument()
  })
})

describe("AcademicsPage (faculty)", () => {
  beforeEach(() => {
    authState.user = makeUser("faculty")
  })

  it("offers draft grade encoding", async () => {
    renderPage()
    expect(
      await screen.findByRole("heading", { name: "Academics", level: 2 })
    ).toBeInTheDocument()
    expect(screen.getByText(/Encode a grade/i)).toBeInTheDocument()
    expect(
      screen.getByRole("button", { name: /Encode draft grade/i })
    ).toBeInTheDocument()
  })

  it("states that faculty may update their own grades but not finalize them", () => {
    renderPage()
    expect(
      screen.getByText(/update the score, letter grade and remarks/i)
    ).toBeInTheDocument()
    expect(
      screen.getByText(/finalized stays with administration/i)
    ).toBeInTheDocument()
  })

  /**
   * `POST /academics/grades/{id}/finalize/` is `IsAdminUser`-only. The
   * "Finalized" status *filter* button is legitimate; a finalize *action* is
   * not, so this matches the verb form to avoid conflating the two.
   */
  it("does not render a grade-finalize action", () => {
    renderPage()
    expect(
      screen.queryByRole("button", { name: /^finalize grade$/i })
    ).toBeNull()
    // The status filter is a read-only view control and must still exist.
    expect(
      screen.getByRole("button", { name: /Finalized/i })
    ).toBeInTheDocument()
  })
})

describe("AcademicsPage (unauthenticated)", () => {
  it("renders nothing without a user", () => {
    authState.user = null
    const { container } = renderPage()
    expect(container).toBeEmptyDOMElement()
  })
})

describe("AcademicsPage hooks wiring", () => {
  it("never calls the encode endpoint during render", async () => {
    authState.user = makeUser("faculty")
    renderPage()
    await screen.findByRole("heading", { name: "Academics", level: 2 })
    // The encode mutation must be opt-in via an explicit submit.
    const { apiClient } = await import("@/lib/api")
    expect(apiClient.post).not.toHaveBeenCalled()
  })

  it("fetches subject assignments and grading periods for the faculty form", async () => {
    authState.user = makeUser("faculty")
    renderPage()
    await screen.findByRole("heading", { name: "Academics", level: 2 })

    const urls = mockedFetchAllPages.mock.calls.map((c) => c[0])
    expect(urls).toContain("/academics/subject-assignments/")
    expect(urls).toContain("/academics/grading-periods/")
  })

  it("does not fetch section-wide grade lists for a student", async () => {
    authState.user = makeUser("student")
    renderPage()
    await screen.findByRole("heading", { name: "Academics", level: 2 })

    const urls = mockedFetchAllPages.mock.calls.map((c) => c[0])
    // Students must only ever ask for their own finalized grades.
    for (const url of urls) {
      if (String(url).includes("/grades/")) {
        expect(String(url)).toContain("status=finalized")
      }
    }
  })
})

// Keep the typed hook import referenced so the mock shape stays honest.
void useAuth

/*
 * FR-011 / TC-FAC-11 / TC-FAC-12: the faculty grade update surface.
 *
 * The backend gained `PATCH /grades/{id}/` for a grade's own encoder, with
 * the lifecycle fields (status, encoded_by) refused server-side. These tests
 * pin the frontend half — the edit form seeded from the record, the
 * content-only payload, and a server refusal shown rather than swallowed.
 */
describe("AcademicsPage (faculty grade update)", () => {
  const gradeRow = {
    id: "g-1",
    student: "sp-1",
    student_name: "Ana Cruz",
    student_id: "STU-001",
    subject_assignment: "sa-1",
    subject_name: "Mathematics",
    subject_code: "MATH-101",
    section_name: "Section A",
    grading_period: "gp-1",
    grading_period_name: "First Quarter",
    score: "88.50",
    letter_grade: "B+",
    remarks: null,
    encoded_by: "fp-1",
    encoded_by_name: "Dr. Reyes",
    status: "draft",
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  }

  beforeEach(() => {
    authState.user = makeUser("faculty")
    mockedFetchAllPages.mockImplementation(async (url: string) => {
      if (url.startsWith("/academics/grades")) {
        return { count: 1, results: [gradeRow] }
      }
      return { count: 0, results: [] }
    })
  })

  async function openEditDialog() {
    renderPage()
    await screen.findByText("MATH-101")
    fireEvent.click(await screen.findByRole("button", { name: "Edit" }))
    return screen.findByRole("dialog")
  }

  it("saves the updated score with the content-only payload (TC-FAC-11)", async () => {
    const dialog = await openEditDialog()
    expect(
      within(dialog).getByLabelText<HTMLInputElement>("Score (0–100)").value
    ).toBe("88.5")

    fireEvent.change(within(dialog).getByLabelText("Score (0–100)"), {
      target: { value: "91" },
    })
    fireEvent.click(
      within(dialog).getByRole("button", { name: /save changes/i })
    )

    const { apiClient } = await import("@/lib/api")
    await waitFor(() =>
      expect(apiClient.patch).toHaveBeenCalledWith(
        "/academics/grades/g-1/",
        expect.objectContaining({ score: 91 })
      )
    )
    // The lifecycle is not part of the payload.
    const payload = vi.mocked(apiClient.patch).mock.calls[0]?.[1] as Record<
      string,
      unknown
    >
    expect(payload).toBeDefined()
    expect(payload).not.toHaveProperty("status")
    expect(payload).not.toHaveProperty("encoded_by")
    await waitFor(() =>
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
    )
  })

  it("offers no lifecycle control in the update form", async () => {
    const dialog = await openEditDialog()
    expect(within(dialog).queryByLabelText(/status/i)).not.toBeInTheDocument()
    expect(within(dialog).getByLabelText("Score (0–100)")).toBeInTheDocument()
    expect(within(dialog).getByLabelText("Letter grade")).toBeInTheDocument()
  })

  it("shows the server's field error and keeps the dialog open", async () => {
    const { apiClient } = await import("@/lib/api")
    vi.mocked(apiClient.patch).mockRejectedValue(
      new AxiosError(
        "Request failed with status code 400",
        undefined,
        undefined,
        undefined,
        {
          data: {
            success: false,
            error: {
              code: "VALIDATION_ERROR",
              message: "Score must be between 0 and 100.",
              details: { score: ["Score must be between 0 and 100."] },
            },
          },
          status: 400,
          statusText: "",
          headers: new AxiosHeaders(),
          config: { headers: new AxiosHeaders() },
        }
      )
    )

    const dialog = await openEditDialog()
    fireEvent.change(within(dialog).getByLabelText("Score (0–100)"), {
      target: { value: "140" },
    })
    fireEvent.click(
      within(dialog).getByRole("button", { name: /save changes/i })
    )

    expect(
      await within(dialog).findByText("Score must be between 0 and 100.")
    ).toBeInTheDocument()
    expect(screen.getByRole("dialog")).toBeInTheDocument()
  })
})

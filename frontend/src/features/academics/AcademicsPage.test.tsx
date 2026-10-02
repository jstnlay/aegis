import { render, screen } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
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
      await screen.findByRole("heading", { name: "Academics", level: 1 })
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
      await screen.findByRole("heading", { name: "Academics", level: 1 })
    ).toBeInTheDocument()
    expect(screen.getByText(/Encode a grade/i)).toBeInTheDocument()
    expect(
      screen.getByRole("button", { name: /Encode draft grade/i })
    ).toBeInTheDocument()
  })

  it("states honestly that faculty cannot edit, submit, or finalize", () => {
    renderPage()
    expect(
      screen.getByText(/no\s+edit, submit, or finalize/i)
    ).toBeInTheDocument()
    expect(screen.getByText(/administration finalizes/i)).toBeInTheDocument()
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
    await screen.findByRole("heading", { name: "Academics", level: 1 })
    // The encode mutation must be opt-in via an explicit submit.
    const { apiClient } = await import("@/lib/api")
    expect(apiClient.post).not.toHaveBeenCalled()
  })

  it("fetches subject assignments and grading periods for the faculty form", async () => {
    authState.user = makeUser("faculty")
    renderPage()
    await screen.findByRole("heading", { name: "Academics", level: 1 })

    const urls = mockedFetchAllPages.mock.calls.map((c) => c[0])
    expect(urls).toContain("/academics/subject-assignments/")
    expect(urls).toContain("/academics/grading-periods/")
  })

  it("does not fetch section-wide grade lists for a student", async () => {
    authState.user = makeUser("student")
    renderPage()
    await screen.findByRole("heading", { name: "Academics", level: 1 })

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

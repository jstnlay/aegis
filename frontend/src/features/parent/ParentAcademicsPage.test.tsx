import { render, screen } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { ParentAcademicsPage } from "./ParentAcademicsPage"
import { apiClient } from "@/lib/api"
import { fetchAllPages } from "@/lib/pagination"
import type { User } from "@/types/auth"

vi.mock("@/features/auth/AuthContext", () => ({
  useAuth: () => ({
    status: "authenticated",
    user: {
      id: "u-parent",
      email: "parent@school.edu",
      username: "parent1",
      first_name: "Pa",
      last_name: "Rent",
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

vi.mock("@/lib/api", () => ({
  apiClient: { get: vi.fn() },
}))

vi.mock("@/lib/pagination", () => ({
  fetchAllPages: vi.fn(),
}))

const mockedGet = vi.mocked(apiClient.get)
const mockedFetchAllPages = vi.mocked(fetchAllPages)

/** The enrollment rows that resolve a parent's linked children. */
const ENROLLMENT_PAGE = {
  count: 1,
  results: [
    {
      id: "enr-1",
      student: "sp-child-1",
      student_name: "Ana Cruz",
      student_id: "STU-001",
      section_name: "Section A",
      is_active: true,
    },
  ],
}

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <ParentAcademicsPage />
    </QueryClientProvider>
  )
}

async function selectChild() {
  const trigger = await screen.findByRole("combobox", { name: /student/i })
  trigger.focus()
  trigger.click()
  const option = await screen.findByRole("option", { name: /Ana Cruz/ })
  option.click()
}

/**
 * PH11.10 regression.
 *
 * The attendance *record* table was handed `summaryQuery.isError`. A failed
 * record request therefore rendered the empty state, "No attendance has been
 * recorded yet." — an empty-success state asserting something the API never
 * said. These tests pin that a record failure is reported as a failure, and
 * that a record request which succeeded with no rows still shows the empty
 * state.
 */
describe("ParentAcademicsPage attendance records", () => {
  beforeEach(() => {
    vi.clearAllMocks()

    // Enrollments resolve the linked children. Attendance *records* also come
    // through fetchAllPages (a paginated envelope), while the summary is the
    // bare-array endpoint on apiClient — which is exactly the split that let
    // the record table be handed the summary's error.
    mockedFetchAllPages.mockImplementation(async (url: string) => {
      if (url.includes("/academics/enrollments/")) return ENROLLMENT_PAGE
      if (url.includes("/attendance/records/")) return { count: 0, results: [] }
      return { count: 0, results: [] }
    })

    mockedGet.mockImplementation(async () => ({ data: [] }))
  })

  it("reports a failed record request instead of an empty table", async () => {
    mockedFetchAllPages.mockImplementation(async (url: string) => {
      if (url.includes("/academics/enrollments/")) return ENROLLMENT_PAGE
      if (url.includes("/attendance/records/")) {
        throw Object.assign(new Error("boom"), {
          isAxiosError: true,
          response: {
            status: 500,
            data: {
              success: false,
              error: {
                code: "INTERNAL_SERVER_ERROR",
                message: "Unable to load attendance records.",
              },
            },
          },
        })
      }
      return { count: 0, results: [] }
    })

    renderPage()
    await selectChild()

    const alert = await screen.findByRole("alert")
    expect(alert).toHaveTextContent(/unable to load attendance records/i)
    // The empty state must not claim there is simply no attendance on record.
    expect(
      screen.queryByText(/No attendance has been recorded yet/i)
    ).not.toBeInTheDocument()
  })

  it("shows the empty state only when the record request succeeded with no rows", async () => {
    renderPage()
    await selectChild()

    expect(
      await screen.findByText(/No attendance has been recorded yet/i)
    ).toBeInTheDocument()
    expect(screen.queryByRole("alert")).not.toBeInTheDocument()
  })

  it("still reports a summary failure separately from the record list", async () => {
    // The records succeed; the summary fails. The record table must stay
    // truthful and only the summary card reports the failure.
    mockedGet.mockImplementation(async (url: string) => {
      if (String(url).includes("/attendance/summary/")) {
        throw Object.assign(new Error("boom"), {
          isAxiosError: true,
          response: {
            status: 500,
            data: {
              success: false,
              error: {
                code: "INTERNAL_SERVER_ERROR",
                message: "Unable to load the attendance summary.",
              },
            },
          },
        })
      }
      return { data: [] }
    })

    renderPage()
    await selectChild()

    expect(
      await screen.findByText(/No attendance has been recorded yet/i)
    ).toBeInTheDocument()
  })
})
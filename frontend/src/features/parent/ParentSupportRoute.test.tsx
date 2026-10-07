import { render, screen } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { ParentSupportRoute } from "./ParentSupportRoute"
import { useLinkedStudents } from "@/features/parent/api"
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
    sessionExpired: false,
    login: vi.fn(),
    logout: vi.fn(),
    changePassword: vi.fn(),
  }),
}))

vi.mock("@/features/parent/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/features/parent/api")>()),
  useLinkedStudents: vi.fn(),
}))

/**
 * PH11.11: the child picker had no loading, failure or empty state.
 *
 * `linked` fell back to `[]`, so the route rendered an empty select and then
 * "No student selected — Choose a linked student above" in all three cases. Two
 * of those are actively misleading: an instruction to operate a control with
 * nothing in it while the request is still running, and the identical page after
 * the request failed — which told a parent with a broken connection that they had
 * no linked children.
 *
 * These are the three states the fix separates, asserted by role because the
 * distinction is the roles, not the words.
 */
describe("ParentSupportRoute picker states", () => {
  function renderRoute() {
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })
    return render(
      <QueryClientProvider client={client}>
        <ParentSupportRoute />
      </QueryClientProvider>
    )
  }

  beforeEach(() => {
    vi.mocked(useLinkedStudents).mockReset()
  })

  it("announces the pending roster instead of offering an empty picker", () => {
    vi.mocked(useLinkedStudents).mockReturnValue({
      isLoading: true,
      isFetching: true,
      isError: false,
      data: undefined,
    } as never)

    renderRoute()

    expect(screen.getByRole("status")).toHaveTextContent(
      /loading linked students/i
    )
    expect(
      screen.queryByRole("combobox", { name: /student/i })
    ).not.toBeInTheDocument()
  })

  it("reports a failed roster as a failure, not as having no children", () => {
    vi.mocked(useLinkedStudents).mockReturnValue({
      isLoading: false,
      isFetching: false,
      isError: true,
      data: undefined,
    } as never)

    renderRoute()

    expect(screen.getByRole("alert")).toHaveTextContent(
      /unable to load linked students/i
    )
    // The claim that must not be made from a failed request.
    expect(
      screen.queryByText(/This account has no linked children/i)
    ).not.toBeInTheDocument()
  })

  it("states the empty case separately, and only for a request that succeeded", () => {
    vi.mocked(useLinkedStudents).mockReturnValue({
      isLoading: false,
      isFetching: false,
      isError: false,
      data: [],
    } as never)

    renderRoute()

    expect(
      screen.getByText(/This account has no linked children/i)
    ).toBeInTheDocument()
    expect(screen.queryByRole("alert")).not.toBeInTheDocument()
  })

  it("offers the picker once the roster resolves", () => {
    vi.mocked(useLinkedStudents).mockReturnValue({
      isLoading: false,
      isFetching: false,
      isError: false,
      data: [
        {
          id: "sp-1",
          student_name: "Ana Cruz",
          section_name: "Section A",
          student_id: "STU-001",
        },
      ],
    } as never)

    renderRoute()

    expect(
      screen.getByRole("combobox", { name: /student/i })
    ).toBeInTheDocument()
  })
})

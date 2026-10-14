import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { AdminSettingsPage } from "./AdminSettingsPage"
import { apiClient } from "@/lib/api"
import { fetchAllPages } from "@/lib/pagination"

/**
 * TC-ADM-11 / FR-034: the admin system-wide settings page.
 *
 * The properties worth pinning are the ones a form gets wrong by being
 * plausible rather than wrong by being broken:
 *
 * 1. Editing one row must not submit the others. A page holding every draft in
 *    one state object will PATCH the untouched settings too, and the audit
 *    trail will show an administrator "changing" values they never touched.
 * 2. Save stays disabled while nothing is dirty — a no-op PATCH is a lie in
 *    the audit log.
 * 3. An integer setting refuses a non-integer before the round-trip, and says
 *    why. The server remains the authority; this is the courtesy.
 * 4. The page states where each setting bites. "Applied across the system" is
 *    only checkable if the reader is told which system.
 */

vi.mock("@/lib/api", () => ({
  apiClient: { get: vi.fn(), post: vi.fn(), patch: vi.fn() },
}))

vi.mock("@/lib/pagination", () => ({
  fetchAllPages: vi.fn(),
}))

const mockedPatch = vi.mocked(apiClient.patch)
const mockedFetchAllPages = vi.mocked(fetchAllPages)

const SETTINGS = [
  {
    key: "attendance.absence_threshold",
    value: "3",
    description: "Absences before a parent attendance alert is raised.",
    value_type: "int",
    default: 3,
    updated_at: "2026-10-01T08:00:00Z",
    updated_by_email: "admin@test.com",
  },
  {
    key: "guidance.risk_score_threshold",
    value: "50",
    description: "Risk score at or above which a student counts as at-risk.",
    value_type: "int",
    default: 50,
    updated_at: "2026-10-01T08:00:00Z",
    updated_by_email: "admin@test.com",
  },
]

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <AdminSettingsPage />
    </QueryClientProvider>
  )
}

describe("AdminSettingsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockedFetchAllPages.mockResolvedValue({ results: SETTINGS } as never)
    mockedPatch.mockResolvedValue({ data: {} } as never)
  })

  it("renders each setting's description, key and where it applies", async () => {
    renderPage()

    expect(
      await screen.findByText(
        "Absences before a parent attendance alert is raised."
      )
    ).toBeInTheDocument()
    expect(
      screen.getByText("guidance.risk_score_threshold")
    ).toBeInTheDocument()

    // Where a setting bites, so "applied across the system" is checkable.
    expect(
      screen.getByText(/Read when an absence is recorded/)
    ).toBeInTheDocument()
  })

  it("keeps Save disabled until the value is actually edited", async () => {
    renderPage()

    // Scoped by the row's own current value — both rows are labelled "Value",
    // and a query matching both is not a query about either.
    const input = await screen.findByDisplayValue("3")
    const saves = await screen.findAllByRole("button", { name: "Save" })
    expect(saves[0]!).toBeDisabled()

    fireEvent.change(input, { target: { value: "9" } })

    const savesAfter = await screen.findAllByRole("button", { name: "Save" })
    expect(savesAfter[0]!).toBeEnabled()
    // Editing one row leaves the other row's Save untouched.
    expect(savesAfter[1]!).toBeDisabled()
  })

  it("PATCHes only the edited setting's own value", async () => {
    renderPage()

    fireEvent.change(await screen.findByDisplayValue("3"), {
      target: { value: "9" },
    })
    const saves = await screen.findAllByRole("button", { name: "Save" })
    fireEvent.click(saves[0]!)

    await waitFor(() => expect(mockedPatch).toHaveBeenCalledTimes(1))
    expect(mockedPatch).toHaveBeenCalledWith(
      "/cms/settings/attendance.absence_threshold/",
      { value: "9" }
    )
  })

  it("refuses a non-integer for an integer setting and explains why", async () => {
    renderPage()

    fireEvent.change(await screen.findByDisplayValue("3"), {
      target: { value: "twelve" },
    })

    expect(
      await screen.findByText("This setting holds a whole number.")
    ).toBeInTheDocument()
    expect(screen.getAllByRole("button", { name: "Save" })[0]!).toBeDisabled()
    expect(mockedPatch).not.toHaveBeenCalled()
  })

  it("surfaces a server rejection rather than silently reverting", async () => {
    mockedPatch.mockRejectedValueOnce(new Error("nope"))
    renderPage()

    fireEvent.change(await screen.findByDisplayValue("3"), {
      target: { value: "9" },
    })
    const saves = await screen.findAllByRole("button", { name: "Save" })
    fireEvent.click(saves[0]!)

    await waitFor(() => expect(mockedPatch).toHaveBeenCalled())
    // The draft stays so the administrator's input is not destroyed by a
    // failed save — losing typed input to a network error is data loss.
    expect(screen.getByDisplayValue("9")).toBeInTheDocument()
  })

  it("states the default when a value has never been saved", async () => {
    renderPage()

    expect(await screen.findByText(/Default 3/)).toBeInTheDocument()
  })
})

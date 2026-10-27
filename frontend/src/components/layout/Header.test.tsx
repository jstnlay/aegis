import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { MemoryRouter } from "react-router-dom"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { Header } from "@/components/layout/Header"
import type { Notification } from "@/features/notifications/api"
import { apiClient } from "@/lib/api"
import { fetchAllPages } from "@/lib/pagination"
import type { Role, User } from "@/types/auth"

/**
 * Cycle-3 TC-STU-08: a notification must be readable in full where it is
 * announced, and must be marked read at the same time.
 *
 * The bell used to be a plain link to the inbox, so the badge told the reader
 * something had arrived and then made them go somewhere else to find out what.
 * It is now a menu of the unread items: the title, the message and the
 * provenance are all on the surface that announced them, selecting one marks it
 * read, and the inbox is still one click away at the foot of the menu.
 */

vi.mock("@/features/auth/AuthContext", () => ({
  useAuth: () => ({
    status: "authenticated",
    user: currentUser,
    logout: vi.fn(),
  }),
}))

vi.mock("@/lib/api", () => ({
  apiClient: { post: vi.fn(), get: vi.fn() },
}))

vi.mock("@/lib/pagination", () => ({
  fetchAllPages: vi.fn(async () => ({ count: 0, results: [] })),
}))

const mockedFetchAllPages = vi.mocked(fetchAllPages)
const mockedPost = vi.mocked(apiClient.post)

let currentUser: User

function makeUser(role: Role): User {
  return {
    id: `u-${role}`,
    email: `${role}@school.edu`,
    username: role,
    first_name: "Ana",
    last_name: "Cruz",
    role,
    phone_number: null,
    address: null,
    language_preference: null,
    is_active: true,
    created_at: "2025-01-01T00:00:00Z",
    updated_at: "2025-01-01T00:00:00Z",
  }
}

function makeNotification(overrides: Partial<Notification> = {}): Notification {
  return {
    id: "n-1",
    notification_type: "GRADE_POSTED",
    title: "Grade posted",
    message: "Your Mathematics grade has been posted.",
    link: null,
    is_read: false,
    read_at: null,
    sender: null,
    sender_full_name: "Ms. Reyes",
    created_at: "2025-02-01T00:00:00Z",
    ...overrides,
  }
}

function renderHeader(role: Role = "student") {
  currentUser = makeUser(role)
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <MemoryRouter>
      <QueryClientProvider client={client}>
        <Header onMenuClick={() => {}} />
      </QueryClientProvider>
    </MemoryRouter>
  )
}

beforeEach(() => {
  mockedFetchAllPages.mockReset()
  mockedFetchAllPages.mockResolvedValue({ count: 0, results: [] })
  mockedPost.mockReset()
  mockedPost.mockResolvedValue({ data: { success: true } } as never)
})

describe("header bell (TC-STU-08)", () => {
  it("opens the unread notification in full, not just the inbox", async () => {
    mockedFetchAllPages.mockResolvedValue({
      count: 1,
      results: [makeNotification()],
    })

    renderHeader()
    // The unread count is the badge's own copy of the number.
    const bell = await screen.findByRole("button", {
      name: "Notifications, 1 unread",
    })

    fireEvent.click(bell)

    const menu = await screen.findByRole("menu", {
      name: /unread notifications/i,
    })
    // Title, body and provenance are all present without leaving the page.
    expect(within(menu).getByText("Grade posted")).toBeInTheDocument()
    expect(
      within(menu).getByText("Your Mathematics grade has been posted.")
    ).toBeInTheDocument()
    expect(within(menu).getByText(/from Ms\. Reyes/)).toBeInTheDocument()
  })

  it("marks the notification read when it is opened from the bell", async () => {
    mockedFetchAllPages.mockResolvedValue({
      count: 1,
      results: [makeNotification({ id: "n-42" })],
    })

    renderHeader()
    fireEvent.click(
      await screen.findByRole("button", { name: "Notifications, 1 unread" })
    )

    const menu = await screen.findByRole("menu", {
      name: /unread notifications/i,
    })
    fireEvent.click(within(menu).getByText("Grade posted"))

    await waitFor(() => {
      expect(mockedPost).toHaveBeenCalledWith("/notifications/n-42/read/")
    })
    // The panel closes on the selection, so the reader is not left under a
    // menu they have finished with.
    expect(
      screen.queryByRole("menu", { name: /unread notifications/i })
    ).toBeNull()
  })

  it("offers the related page only when the role can open it", async () => {
    mockedFetchAllPages.mockResolvedValue({
      count: 1,
      results: [makeNotification({ link: "/guidance/risk-alerts" })],
    })

    // A student cannot open the guidance risk-alert screen, so the notification
    // still reads in full but carries no link out of it.
    renderHeader("student")
    fireEvent.click(
      await screen.findByRole("button", { name: "Notifications, 1 unread" })
    )
    const menu = await screen.findByRole("menu", {
      name: /unread notifications/i,
    })
    expect(within(menu).queryByText(/open the related page/i)).toBeNull()
  })

  it("says so when nothing is unread instead of showing an empty panel", async () => {
    renderHeader()
    fireEvent.click(
      await screen.findByRole("button", { name: "Notifications" })
    )

    const menu = await screen.findByRole("menu", {
      name: /unread notifications/i,
    })
    expect(
      within(menu).getByText(/no unread notifications/i)
    ).toBeInTheDocument()
    // The inbox remains reachable from the badge even with nothing unread.
    expect(
      within(menu).getByRole("menuitem", { name: /open the inbox/i })
    ).toBeInTheDocument()
  })
})

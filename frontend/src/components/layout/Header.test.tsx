import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { MemoryRouter } from "react-router-dom"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { Header } from "@/components/layout/Header"
import { SidebarAccount } from "@/components/layout/SidebarAccount"
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

const mockLogout = vi.hoisted(() => vi.fn<() => Promise<void>>())

vi.mock("@/features/auth/AuthContext", () => ({
  useAuth: () => ({
    status: "authenticated",
    user: currentUser,
    logout: mockLogout,
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

function renderHeader(role: Role = "student", pathname = "/") {
  currentUser = makeUser(role)
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <MemoryRouter initialEntries={[pathname]}>
      <QueryClientProvider client={client}>
        <Header onMenuClick={() => {}} />
        <aside aria-label="Sidebar account">
          <SidebarAccount />
        </aside>
      </QueryClientProvider>
    </MemoryRouter>
  )
}

beforeEach(() => {
  mockLogout.mockReset()
  mockLogout.mockResolvedValue(undefined)
  mockedFetchAllPages.mockReset()
  mockedFetchAllPages.mockResolvedValue({ count: 0, results: [] })
  mockedPost.mockReset()
  mockedPost.mockResolvedValue({ data: { success: true } } as never)
})

afterEach(() => vi.restoreAllMocks())

it.each([
  ["student", "Welcome back, Ana!"],
  ["faculty", "Welcome back, Teacher A. Cruz!"],
  ["guidance", "Welcome back, Ana!"],
  ["parent", "Your family portal"],
  ["admin", "Administration overview"],
] as const)(
  "integrates the %s dashboard welcome into the top header",
  (role, title) => {
    renderHeader(role, `/app/dashboard/${role}`)
    const header = screen.getByRole("banner")
    expect(
      within(header).getByRole("heading", { level: 1, name: title })
    ).toBeInTheDocument()
    expect(
      within(header).queryByRole("heading", { name: "Dashboard" })
    ).not.toBeInTheDocument()
    expect(
      within(header).getByRole("button", { name: /^Notifications/ })
    ).toBeVisible()
    expect(header).toHaveAttribute("data-dashboard", "true")
    if (role === "student") {
      expect(
        within(header).getByText("One step at a time. Make today yours.")
      ).toBeInTheDocument()
    } else {
      expect(
        within(header).queryByText("One step at a time. Make today yours.")
      ).not.toBeInTheDocument()
    }
  }
)

describe.each(["admin", "guidance", "student", "parent", "faculty"] as const)(
  "%s header scrolling",
  (role) => {
    function controlScroll() {
      const scrollY = vi.spyOn(window, "scrollY", "get").mockReturnValue(0)
      return (y: number) => {
        scrollY.mockReturnValue(y)
        fireEvent.scroll(window)
      }
    }

    it("hides on downward scrolling, ignores jitter and reveals on upward scrolling or at the top", () => {
      const scroll = controlScroll()
      renderHeader(role)
      const header = screen.getByRole("banner")
      scroll(20)
      expect(header).toHaveAttribute("data-hidden", "false")
      scroll(150)
      expect(header).toHaveAttribute("data-hidden", "true")
      scroll(149)
      expect(header).toHaveAttribute("data-hidden", "true")
      scroll(130)
      expect(header).toHaveAttribute("data-hidden", "false")
      scroll(200)
      expect(header).toHaveAttribute("data-hidden", "true")
      scroll(0)
      expect(header).toHaveAttribute("data-hidden", "false")
    })

    it("keeps account controls in the sidebar and reveals the header for its notification menu", () => {
      const scroll = controlScroll()
      renderHeader(role)
      const header = screen.getByRole("banner")
      scroll(150)
      expect(header).toHaveAttribute("data-hidden", "true")
      const account = screen.getByRole("button", { name: "Account menu" })
      expect(header).not.toContainElement(account)
      const notifications = screen.getByRole("button", {
        name: /^Notifications/,
      })
      fireEvent.focus(notifications)
      expect(header).toHaveAttribute("data-hidden", "false")
      fireEvent.click(notifications)
      scroll(300)
      expect(header).toHaveAttribute("data-hidden", "false")
      expect(notifications).toHaveAttribute("aria-expanded", "true")
    })

    it("hides the faculty header like the other school roles", () => {
      const scroll = controlScroll()
      renderHeader("faculty")
      scroll(200)
      expect(screen.getByRole("banner")).toHaveAttribute("data-hidden", "true")
    })
  }
)

describe("sign-out confirmation", () => {
  async function openConfirmation() {
    fireEvent.pointerDown(
      screen.getByRole("button", { name: "Account menu" }),
      { button: 0, ctrlKey: false }
    )
    fireEvent.click(screen.getByRole("menuitem", { name: "Sign out" }))
    return screen.findByRole("alertdialog", { name: "Sign out of AEGIS?" })
  }

  it.each(["Cancel", "Escape"])(
    "keeps the session active when the user chooses %s",
    async (dismissal) => {
      renderHeader("admin")
      const dialog = await openConfirmation()
      const cancel = within(dialog).getByRole("button", { name: "Cancel" })
      await waitFor(() => expect(cancel).toHaveFocus())
      expect(mockLogout).not.toHaveBeenCalled()

      if (dismissal === "Cancel") fireEvent.click(cancel)
      else fireEvent.keyDown(dialog, { key: "Escape" })

      await waitFor(() => expect(screen.queryByRole("alertdialog")).toBeNull())
      expect(mockLogout).not.toHaveBeenCalled()
      await waitFor(() =>
        expect(
          screen.getByRole("button", { name: "Account menu" })
        ).toHaveFocus()
      )
    }
  )

  it("signs out only after confirmation and prevents repeated requests while pending", async () => {
    let finishLogout!: () => void
    mockLogout.mockReturnValueOnce(
      new Promise<void>((resolve) => {
        finishLogout = resolve
      })
    )
    renderHeader()
    const dialog = await openConfirmation()
    expect(mockLogout).not.toHaveBeenCalled()

    fireEvent.click(within(dialog).getByRole("button", { name: "Sign out" }))
    const pendingButton = within(dialog).getByRole("button", {
      name: "Signing out…",
    })
    expect(pendingButton).toBeDisabled()
    expect(
      within(dialog).getByRole("button", { name: "Cancel" })
    ).toBeDisabled()
    expect(mockLogout).toHaveBeenCalledTimes(1)
    fireEvent.click(pendingButton)
    fireEvent.keyDown(dialog, { key: "Escape" })
    expect(dialog).toBeInTheDocument()
    expect(mockLogout).toHaveBeenCalledTimes(1)

    await act(async () => finishLogout())
    await waitFor(() => expect(screen.queryByRole("alertdialog")).toBeNull())
  })
})

describe("header bell (TC-STU-08)", () => {
  it("keeps related-page links outside the read button and marks the notification read on navigation", async () => {
    mockedFetchAllPages.mockResolvedValue({
      count: 1,
      results: [makeNotification({ id: "n-related", link: "/academics" })],
    })
    renderHeader()
    const bell = await screen.findByRole("button", {
      name: "Notifications, 1 unread",
    })
    fireEvent.click(bell)
    const menu = screen.getByRole("menu", { name: "Notifications" })
    const link = within(menu).getByRole("menuitem", {
      name: "Open the related page",
    })
    expect(link.closest("button")).toBeNull()
    fireEvent.click(link)
    await waitFor(() =>
      expect(mockedPost).toHaveBeenCalledWith("/notifications/n-related/read/")
    )
    expect(
      screen.queryByRole("menu", { name: "Notifications" })
    ).not.toBeInTheDocument()
  })

  it("returns focus to the bell when the dropdown is dismissed with Escape", async () => {
    renderHeader()
    const bell = screen.getByRole("button", { name: "Notifications" })
    fireEvent.click(bell)
    fireEvent.keyDown(screen.getByRole("menu", { name: "Notifications" }), {
      key: "Escape",
    })
    expect(
      screen.queryByRole("menu", { name: "Notifications" })
    ).not.toBeInTheDocument()
    expect(bell).toHaveFocus()
  })
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
      name: /^notifications$/i,
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
      name: /^notifications$/i,
    })
    fireEvent.click(within(menu).getByText("Grade posted"))

    await waitFor(() => {
      expect(mockedPost).toHaveBeenCalledWith("/notifications/n-42/read/")
    })
    // The panel closes on the selection, so the reader is not left under a
    // menu they have finished with.
    expect(screen.queryByRole("menu", { name: /^notifications$/i })).toBeNull()
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
      name: /^notifications$/i,
    })
    expect(within(menu).queryByText(/open the related page/i)).toBeNull()
  })

  it("says so when nothing is unread instead of showing an empty panel", async () => {
    renderHeader()
    fireEvent.click(
      await screen.findByRole("button", { name: "Notifications" })
    )

    const menu = await screen.findByRole("menu", {
      name: /^notifications$/i,
    })
    expect(
      await within(menu).findByText(/no notifications yet/i)
    ).toBeInTheDocument()
    // The inbox remains reachable from the badge even with nothing unread.
    expect(
      within(menu).getByRole("menuitem", { name: /open the inbox/i })
    ).toBeInTheDocument()
  })
})

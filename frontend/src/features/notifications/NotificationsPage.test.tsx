import { render, screen, waitFor, within } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { MemoryRouter } from "react-router-dom"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { NotificationsPage } from "@/features/notifications/NotificationsPage"
import {
  resolveNotificationHref,
  sortNotifications,
  type Notification,
} from "@/features/notifications/api"
import { apiClient } from "@/lib/api"
import { fetchAllPages } from "@/lib/pagination"
import type { Role, User } from "@/types/auth"

vi.mock("@/features/auth/AuthContext", () => ({
  useAuth: () => ({ status: "authenticated", user: currentUser }),
}))

vi.mock("@/lib/api", () => ({
  apiClient: { post: vi.fn(), get: vi.fn(), put: vi.fn() },
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
    sender_full_name: null,
    created_at: "2025-02-01T00:00:00Z",
    ...overrides,
  }
}

function renderPage(role: Role = "student") {
  currentUser = makeUser(role)
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <MemoryRouter>
      <QueryClientProvider client={client}>
        <NotificationsPage />
      </QueryClientProvider>
    </MemoryRouter>
  )
}

/* -------------------------------------------------------------------------- */
/* resolveNotificationHref                                                     */
/* -------------------------------------------------------------------------- */

/**
 * `Notification.link` is filled by its producer with a **backend API path**,
 * not a SPA route — e.g. `/guidance/risk-alerts`, `/academics/grades/{id}`,
 * `/attendance/summary?student={id}`. These cases pin the mapping onto screens
 * that exist, and the refusal to link a screen the caller's role cannot open.
 */
describe("resolveNotificationHref", () => {
  it("maps the real backend link paths onto frontend routes", () => {
    expect(resolveNotificationHref("/guidance/risk-alerts", "guidance")).toBe(
      "/app/risk-alerts"
    )
    expect(
      resolveNotificationHref("/guidance/consultations/c-1", "guidance")
    ).toBe("/app/consultations")
    expect(
      resolveNotificationHref("/guidance/interventions/i-1", "guidance")
    ).toBe("/app/interventions")
    expect(resolveNotificationHref("/academics/grades/g-1", "faculty")).toBe(
      "/app/academics"
    )
    expect(resolveNotificationHref("/attendance", "student")).toBe(
      "/app/attendance"
    )
  })

  it("matches on the path and ignores the query string", () => {
    // `apps/attendance/views.py` produces this exact shape.
    expect(
      resolveNotificationHref("/attendance/summary?student=sp-1", "student")
    ).toBe("/app/attendance")
  })

  it("returns null when the target is not reachable by the caller's role", () => {
    // A parent must not be pointed at the counselor-only risk-alerts screen
    // just because the backend addressed the notification that way.
    expect(
      resolveNotificationHref("/guidance/risk-alerts", "parent")
    ).toBeNull()
    expect(
      resolveNotificationHref("/guidance/consultations", "student")
    ).toBeNull()
    expect(resolveNotificationHref("/assessments", "student")).toBeNull()
    expect(resolveNotificationHref("/academics/grades", "parent")).toBeNull()
  })

  it("returns null for a null, empty or unmapped link", () => {
    expect(resolveNotificationHref(null, "student")).toBeNull()
    expect(resolveNotificationHref(undefined, "student")).toBeNull()
    expect(resolveNotificationHref("", "student")).toBeNull()
    expect(resolveNotificationHref("/something/unknown", "student")).toBeNull()
  })

  it("refuses an absolute or protocol-relative link", () => {
    // `link` is free text on the model, so an off-site value must never be
    // rendered as an anchor.
    expect(
      resolveNotificationHref("https://evil.example/x", "student")
    ).toBeNull()
    expect(resolveNotificationHref("//evil.example/x", "student")).toBeNull()
    expect(resolveNotificationHref("/\\evil.example", "student")).toBeNull()
    expect(resolveNotificationHref("javascript:alert(1)", "student")).toBeNull()
  })

  it("does not match a longer unrelated path that merely starts similarly", () => {
    expect(resolveNotificationHref("/academicsx/grades", "faculty")).toBeNull()
  })
})

/* -------------------------------------------------------------------------- */
/* sortNotifications                                                          */
/* -------------------------------------------------------------------------- */

describe("sortNotifications", () => {
  it("orders newest first without mutating the input", () => {
    const input = [
      makeNotification({ id: "old", created_at: "2025-01-01T00:00:00Z" }),
      makeNotification({ id: "new", created_at: "2025-03-01T00:00:00Z" }),
    ]

    const sorted = sortNotifications(input)

    expect(sorted.map((n) => n.id)).toEqual(["new", "old"])
    expect(input.map((n) => n.id)).toEqual(["old", "new"])
  })
})

/* -------------------------------------------------------------------------- */
/* NotificationsPage                                                          */
/* -------------------------------------------------------------------------- */

beforeEach(() => {
  vi.clearAllMocks()
  currentUser = makeUser("student")
  mockedPost.mockResolvedValue({ data: { success: true } } as never)
})

describe("NotificationsPage", () => {
  it("lists notifications newest first with their type and sender", async () => {
    mockedFetchAllPages.mockImplementation(async (url: string) => {
      if (url.includes("is_read=false")) {
        return { count: 0, results: [] }
      }
      return {
        count: 2,
        results: [
          makeNotification({
            id: "n-old",
            title: "Older",
            created_at: "2025-01-01T00:00:00Z",
          }),
          makeNotification({
            id: "n-new",
            title: "Newer",
            notification_type: "RISK_ALERT_GENERATED",
            sender_full_name: "Robin Vega",
            created_at: "2025-03-01T00:00:00Z",
          }),
        ],
      }
    })

    const { container } = renderPage()

    await screen.findByText("Newer")
    const rows = within(container).getAllByRole("row")
    // Header row first, then newest-first data rows.
    expect(
      within(rows[1] as HTMLElement).getByText("Newer")
    ).toBeInTheDocument()
    expect(
      within(rows[2] as HTMLElement).getByText("Older")
    ).toBeInTheDocument()
    expect(container.textContent).toContain("Risk alert generated")
    expect(container.textContent).toContain("from Robin Vega")
  })

  it("shows an unread count and a Mark all read control", async () => {
    mockedFetchAllPages.mockImplementation(async (url: string) =>
      url.includes("is_read=false")
        ? {
            count: 2,
            results: [
              makeNotification({ id: "a" }),
              makeNotification({ id: "b" }),
            ],
          }
        : { count: 0, results: [] }
    )

    renderPage()

    expect(
      await screen.findByText(/2 unread notifications/i)
    ).toBeInTheDocument()
    expect(
      screen.getByRole("button", { name: /mark all read/i })
    ).toBeInTheDocument()
  })

  it("disables Mark all read when there is nothing unread", async () => {
    mockedFetchAllPages.mockResolvedValue({ count: 0, results: [] })

    renderPage()

    await screen.findByText(/You have no unread notifications/i)
    expect(
      screen.getByRole("button", { name: /mark all read/i })
    ).toBeDisabled()
  })

  it("marks one notification read and refetches", async () => {
    mockedFetchAllPages.mockImplementation(async (url: string) =>
      url.includes("is_read=false")
        ? { count: 1, results: [makeNotification({ id: "n-1" })] }
        : { count: 1, results: [makeNotification({ id: "n-1" })] }
    )

    renderPage()

    const button = await screen.findByRole("button", { name: /mark read/i })
    button.click()

    await waitFor(() => {
      expect(mockedPost).toHaveBeenCalledWith("/notifications/n-1/read/")
    })
    // The action returns only {success, message}, so the list must refetch.
    expect(mockedFetchAllPages.mock.calls.length).toBeGreaterThan(1)
  })

  it("marks every notification read", async () => {
    mockedFetchAllPages.mockImplementation(async (url: string) =>
      url.includes("is_read=false")
        ? { count: 1, results: [makeNotification({ id: "n-1" })] }
        : { count: 0, results: [] }
    )

    renderPage()

    const button = await screen.findByRole("button", { name: /mark all read/i })
    // The control is disabled while the unread count is still unknown (0), so
    // clicking it as soon as it appears is a no-op. Wait for it to be enabled.
    await waitFor(() => expect(button).toBeEnabled())
    button.click()

    await waitFor(() => {
      expect(mockedPost).toHaveBeenCalledWith("/notifications/read-all/")
    })
  })

  it("offers an Open link only for a link the role can reach", async () => {
    mockedFetchAllPages.mockImplementation(async (url: string) => {
      if (url.includes("is_read=false")) return { count: 0, results: [] }
      return {
        count: 2,
        results: [
          makeNotification({
            id: "n-ok",
            title: "Grade posted",
            link: "/academics/grades/g-1",
          }),
          makeNotification({
            id: "n-blocked",
            title: "Risk alert generated",
            notification_type: "RISK_ALERT_GENERATED",
            link: "/guidance/risk-alerts",
          }),
        ],
      }
    })

    renderPage("student")

    await screen.findByText("Grade posted")
    const links = screen.getAllByRole("link", { name: /open/i })
    expect(links).toHaveLength(1)
    expect(links[0]).toHaveAttribute("href", "/app/academics")
  })

  it("shows a loading state before the list resolves", async () => {
    type PageResult = { results: Notification[]; count: number }
    let resolve: (value: PageResult) => void = () => {}
    mockedFetchAllPages.mockImplementation(
      () =>
        new Promise<PageResult>((r) => {
          resolve = r
        })
    )

    renderPage()

    expect(
      await screen.findByTestId("notifications-loading")
    ).toBeInTheDocument()
    resolve({ count: 0, results: [] })
  })

  it("surfaces a fetch failure instead of an empty list", async () => {
    mockedFetchAllPages.mockRejectedValue(new Error("boom"))

    renderPage()

    const alert = await screen.findByRole("alert")
    expect(alert).toHaveTextContent("boom")
  })

  it("shows an empty state when there are no notifications", async () => {
    mockedFetchAllPages.mockResolvedValue({ count: 0, results: [] })

    renderPage()

    expect(
      await screen.findByText(/No notifications match the current filters/i)
    ).toBeInTheDocument()
  })

  it("requests the unread endpoint separately from the list", async () => {
    mockedFetchAllPages.mockResolvedValue({ count: 0, results: [] })

    renderPage()

    await screen.findByText(/You have no unread notifications/i)

    const urls = mockedFetchAllPages.mock.calls.map(([url]) => url)
    expect(urls).toContain("/notifications/?is_read=false")
    expect(urls).toContain("/notifications/")
  })

  it("marks a read notification as read in the status column", async () => {
    mockedFetchAllPages.mockImplementation(async (url: string) => {
      if (url.includes("is_read=false")) return { count: 0, results: [] }
      return {
        count: 1,
        results: [makeNotification({ id: "n-1", is_read: true })],
      }
    })

    renderPage()

    expect(await screen.findByText("Read")).toBeInTheDocument()
    // A read notification offers no "Mark read" action.
    expect(screen.queryByRole("button", { name: /mark read/i })).toBeNull()
  })
})

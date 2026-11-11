import { fireEvent, render, screen } from "@testing-library/react"
import { beforeEach, expect, it, vi } from "vitest"
import { NotificationPreviews } from "./NotificationPreviews"

const state = vi.hoisted(() => ({
  userId: "user-1",
  items: [] as Array<{
    id: string
    title: string
    message: string
    is_read: boolean
    created_at: string
  }>,
  markRead: vi.fn(),
  notifications: vi.fn(),
}))
vi.mock("@/features/auth/AuthContext", () => ({
  useAuth: () => ({ user: { id: state.userId } }),
}))
vi.mock("./api", () => ({
  useNotifications: (...args: unknown[]) => {
    state.notifications(...args)
    return { data: state.items }
  },
  useMarkNotificationRead: () => ({ mutate: state.markRead }),
  NOTIFICATION_TYPE_LABELS: {},
  sortNotifications: (items: typeof state.items) =>
    [...items].sort((a, b) => b.created_at.localeCompare(a.created_at)),
}))
vi.mock("./NotificationDetails", () => ({
  NotificationDetails: ({
    notification,
  }: {
    notification: { title: string } | null
  }) => (notification ? <div role="dialog">{notification.title}</div> : null),
}))

beforeEach(() => {
  vi.clearAllMocks()
  sessionStorage.clear()
  state.userId = "user-1"
  state.items = Array.from({ length: 4 }, (_, index) => ({
    id: `n-${index}`,
    title: `Update ${index}`,
    message: `Details ${index}`,
    is_read: false,
    created_at: `2026-11-10T10:0${index}:00Z`,
  }))
})

it("shows at most two previews and promotes the next queued update on dismiss", () => {
  render(<NotificationPreviews />)
  expect(screen.getAllByRole("article")).toHaveLength(2)
  expect(screen.getByText("Update 3")).toBeInTheDocument()
  expect(screen.queryByText("Update 1")).not.toBeInTheDocument()
  fireEvent.click(
    screen.getByRole("button", { name: "Dismiss preview: Update 3" })
  )
  expect(screen.queryByText("Update 3")).not.toBeInTheDocument()
  expect(screen.getByText("Update 1")).toBeInTheDocument()
  expect(screen.getAllByRole("article")).toHaveLength(2)
  expect(state.markRead).not.toHaveBeenCalled()
  expect(state.notifications).toHaveBeenCalledWith({}, 15_000)
})

it("clears the entire preview queue without marking read and still shows future updates", () => {
  const { rerender } = render(<NotificationPreviews />)
  fireEvent.click(screen.getByRole("button", { name: "Clear all" }))
  expect(screen.queryByRole("article")).not.toBeInTheDocument()
  expect(state.markRead).not.toHaveBeenCalled()
  expect(state.items).toHaveLength(4)
  state.items = [
    ...state.items,
    { ...state.items[0]!, id: "future", title: "Future update" },
  ]
  rerender(<NotificationPreviews />)
  expect(screen.getByText("Future update")).toBeInTheDocument()
  expect(screen.queryByText("Update 3")).not.toBeInTheDocument()
})

it("opens full details and marks read only when View is clicked", () => {
  render(<NotificationPreviews />)
  fireEvent.click(
    screen.getByRole("button", { name: "View notification: Update 3" })
  )
  expect(screen.getByRole("dialog")).toHaveTextContent("Update 3")
  expect(state.markRead).toHaveBeenCalledWith("n-3", expect.any(Object))
  expect(screen.getAllByRole("article")).toHaveLength(2)
})

it("remembers dismissals for this session without affecting another user's previews", () => {
  const { unmount } = render(<NotificationPreviews />)
  fireEvent.click(
    screen.getByRole("button", { name: "Dismiss preview: Update 3" })
  )
  unmount()
  const next = render(<NotificationPreviews />)
  expect(screen.queryByText("Update 3")).not.toBeInTheDocument()
  state.userId = "user-2"
  next.rerender(<NotificationPreviews />)
  expect(screen.getByText("Update 3")).toBeInTheDocument()
})

it("shows newly fetched unread updates and excludes already read notifications", () => {
  state.items = [{ ...state.items[0]!, is_read: true }]
  const { rerender } = render(<NotificationPreviews />)
  expect(screen.queryByRole("article")).not.toBeInTheDocument()
  state.items = [
    ...state.items,
    { ...state.items[0]!, id: "new", title: "New arrival", is_read: false },
  ]
  rerender(<NotificationPreviews />)
  expect(screen.getByText("New arrival")).toBeInTheDocument()
  expect(screen.queryByText("Update 0")).not.toBeInTheDocument()
})

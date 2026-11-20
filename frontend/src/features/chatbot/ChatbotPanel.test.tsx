import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { apiClient } from "@/lib/api"
import { ChatbotPanel } from "./ChatbotPanel"

vi.mock("@/features/auth/AuthContext", () => ({
  useAuth: () => ({ user: { first_name: "Ana", role: "student" } }),
}))
vi.mock("@/lib/api", () => ({
  apiClient: { get: vi.fn(), post: vi.fn(), delete: vi.fn() },
}))

const NOTICE = {
  version: "2026-01",
  text: "Your messages are stored and screened.",
  accepted: true,
  accepted_at: null,
}

const THREAD = {
  id: "t1",
  title: "Math help",
  created_at: "2026-11-01T09:00:00Z",
  updated_at: "2026-11-02T09:00:00Z",
  message_count: 1,
}

const THREAD_DETAIL = {
  ...THREAD,
  messages: [
    {
      id: "m1",
      thread_id: "t1",
      message: "What is my grade in Math?",
      reply: "You have 91.50%.",
      intent: "ask_grade",
      urgency: "normal",
      severity: "none",
      sensitive: false,
      manual_review: false,
      created_at: "2026-11-01T09:00:00Z",
    },
  ],
}

function renderPanel(onClose = vi.fn()) {
  return render(
    <QueryClientProvider
      client={
        new QueryClient({
          defaultOptions: {
            queries: { retry: false },
            mutations: { retry: false },
          },
        })
      }
    >
      <ChatbotPanel open onClose={onClose} />
    </QueryClientProvider>
  )
}

/**
 * Route GETs by URL. The notice and thread list load together on open, so a
 * single queue of resolved values would answer them in an unpredictable order.
 */
function mockGet(routes: Record<string, unknown> = {}) {
  vi.mocked(apiClient.get).mockImplementation(async (url: string) => {
    if (url in routes) return { data: routes[url] }
    if (url === "/chatbot/notice/") return { data: NOTICE }
    if (url === "/chatbot/threads/") return { data: { results: [] } }
    throw new Error(`unexpected GET ${url}`)
  })
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(apiClient.delete).mockResolvedValue({ data: {} })
  mockGet()
})

describe("ChatbotPanel", () => {
  it("sends a starter question and renders the returned record", async () => {
    vi.mocked(apiClient.post).mockResolvedValue({
      data: {
        reply: "Here is your grade summary.",
        intent: "ask_grade",
        urgency: "normal",
        data: { grade_summary: { average: 91.5, subject_count: 8 } },
      },
    })
    renderPanel()
    fireEvent.click(
      screen.getByRole("button", { name: "What is my grade in Math?" })
    )
    await waitFor(() =>
      expect(apiClient.post).toHaveBeenCalledWith("/chatbot/message/", {
        message: "What is my grade in Math?",
      })
    )
    expect(
      await screen.findByText("Here is your grade summary.")
    ).toBeInTheDocument()
    expect(screen.getByText(/91.50%/)).toBeInTheDocument()
  })

  it("shows the attendance counts the server actually sends", async () => {
    // The summary field names are specific: the chatbot sends `_days`, and
    // reading `_count` here rendered three dashes for a real answer.
    vi.mocked(apiClient.post).mockResolvedValue({
      data: {
        reply: "You have attended 18 of 20 recorded days.",
        intent: "ask_attendance",
        urgency: "normal",
        data: {
          attendance_summary: {
            present_days: 16,
            late_days: 2,
            absent_days: 2,
          },
        },
      },
    })
    renderPanel()
    fireEvent.click(
      screen.getByRole("button", { name: "What is my grade in Math?" })
    )
    expect(
      await screen.findByText(/Present: 16 · Late: 2 · Absent: 2/)
    ).toBeInTheDocument()
  })

  it("shows which school document grounded the answer", async () => {
    // The reply text names the source; this block is the link that lets the
    // student read the document themselves.
    vi.mocked(apiClient.post).mockResolvedValue({
      data: {
        reply: "From the handbook: a white polo is required.",
        intent: "unknown",
        urgency: "normal",
        data: {
          knowledge: [
            {
              chunk_id: "c1",
              title: "Student Handbook",
              source_label: "Student Handbook 2026, p. 12",
              source_url: "https://example.test/handbook",
            },
          ],
        },
      },
    })
    renderPanel()
    fireEvent.click(
      screen.getByRole("button", { name: "What is my grade in Math?" })
    )
    expect(await screen.findByText("Answered from:")).toBeInTheDocument()
    expect(
      screen.getByRole("link", { name: "Student Handbook 2026, p. 12" })
    ).toHaveAttribute("href", "https://example.test/handbook")
  })

  it("keeps Shift+Enter for new lines and sends with Enter", async () => {
    vi.mocked(apiClient.post).mockResolvedValue({
      data: { reply: "Hello Ana!", data: {} },
    })
    renderPanel()
    const input = screen.getByRole("textbox", { name: "Message" })
    expect(input).toHaveFocus()
    fireEvent.change(input, { target: { value: "Hello" } })
    fireEvent.keyDown(input, { key: "Enter", shiftKey: true })
    expect(apiClient.post).not.toHaveBeenCalled()
    fireEvent.keyDown(input, { key: "Enter" })
    expect(await screen.findByText("Hello Ana!")).toBeInTheDocument()
  })

  it("expands /grades into the record question", async () => {
    vi.mocked(apiClient.post).mockResolvedValue({
      data: { reply: "You have 91.50%.", data: {} },
    })
    renderPanel()
    const input = screen.getByRole("textbox", { name: "Message" })
    fireEvent.change(input, { target: { value: "/grades Math" } })
    fireEvent.keyDown(input, { key: "Enter" })

    await waitFor(() =>
      expect(apiClient.post).toHaveBeenCalledWith("/chatbot/message/", {
        message: "What is my grade in Math?",
      })
    )
    expect(
      await screen.findByText("What is my grade in Math?")
    ).toBeInTheDocument()
  })

  it("answers an unknown command locally without sending it", async () => {
    renderPanel()
    const input = screen.getByRole("textbox", { name: "Message" })
    fireEvent.change(input, { target: { value: "/nope" } })
    fireEvent.keyDown(input, { key: "Enter" })

    expect(await screen.findByText(/Unknown command/)).toBeInTheDocument()
    expect(apiClient.post).not.toHaveBeenCalled()
  })

  it("offers commands when the draft starts with a slash", async () => {
    vi.mocked(apiClient.post).mockResolvedValue({
      data: { reply: "You have 91.50%.", data: {} },
    })
    renderPanel()
    const input = screen.getByRole("textbox", { name: "Message" })
    fireEvent.change(input, { target: { value: "/" } })

    const menu = await screen.findByRole("group", { name: "Chat commands" })
    fireEvent.click(within(menu).getByRole("button", { name: /grades/ }))
    expect(input).toHaveValue("/grades ")

    fireEvent.change(input, { target: { value: "/grades Math" } })
    fireEvent.keyDown(input, { key: "Enter" })
    await waitFor(() =>
      expect(apiClient.post).toHaveBeenCalledWith("/chatbot/message/", {
        message: "What is my grade in Math?",
      })
    )
    expect(screen.queryByRole("group", { name: "Chat commands" })).toBeNull()
  })

  it("starts on a new chat instead of reopening the newest one", async () => {
    mockGet({
      "/chatbot/threads/": { results: [THREAD] },
      "/chatbot/threads/t1/": THREAD_DETAIL,
    })
    renderPanel()

    expect(await screen.findByText(/Hi, Ana!/)).toBeInTheDocument()
    expect(apiClient.get).not.toHaveBeenCalledWith("/chatbot/threads/t1/")
  })

  it("names the assistant Aegi", () => {
    renderPanel()
    expect(screen.getByRole("heading", { name: "Aegi" })).toBeInTheDocument()
    expect(screen.getByText(/Your AEGIS school assistant/)).toBeInTheDocument()
  })

  it("lists saved chats and opens one", async () => {
    mockGet({
      "/chatbot/threads/": {
        results: [{ ...THREAD, id: "t2", title: "Science help" }, THREAD],
      },
      "/chatbot/threads/t1/": THREAD_DETAIL,
    })
    renderPanel()

    fireEvent.click(screen.getByRole("button", { name: "Chat history" }))
    expect(await screen.findByText("Math help")).toBeInTheDocument()

    fireEvent.click(screen.getByText("Math help"))
    await waitFor(() =>
      expect(apiClient.get).toHaveBeenCalledWith("/chatbot/threads/t1/")
    )
    // The saved user turn repeats the starter-prompt text, so wait for the
    // reply, which exists only in the transcript.
    expect(await screen.findByText("You have 91.50%.")).toBeInTheDocument()
    expect(screen.getByText("What is my grade in Math?")).toBeInTheDocument()
  })

  it("asks before deleting a chat and says the safety record stays", async () => {
    mockGet({
      "/chatbot/threads/": { results: [THREAD] },
      "/chatbot/threads/t1/": THREAD_DETAIL,
    })
    renderPanel()

    fireEvent.click(screen.getByRole("button", { name: "Chat history" }))
    fireEvent.click(
      await screen.findByRole("button", { name: "Delete chat: Math help" })
    )
    expect(
      within(screen.getByRole("group", { name: "Delete Math help" })).getByText(
        /stays with Guidance/
      )
    ).toBeInTheDocument()

    fireEvent.click(screen.getByRole("button", { name: "Delete" }))
    await waitFor(() =>
      expect(apiClient.delete).toHaveBeenCalledWith("/chatbot/threads/t1/")
    )
  })

  it("deletes all saved chats after a second confirmation", async () => {
    mockGet({
      "/chatbot/threads/": { results: [THREAD] },
      "/chatbot/threads/t1/": THREAD_DETAIL,
    })
    renderPanel()

    fireEvent.click(screen.getByRole("button", { name: "Chat history" }))
    fireEvent.click(
      await screen.findByRole("button", { name: "Delete all chats" })
    )
    fireEvent.click(screen.getByRole("button", { name: "Delete all" }))
    await waitFor(() =>
      expect(apiClient.delete).toHaveBeenCalledWith("/chatbot/history/")
    )
  })

  it("states that chats are saved and closes with Escape", () => {
    const onClose = vi.fn()
    renderPanel(onClose)
    expect(screen.getByText(/Chats are saved in History/)).toBeInTheDocument()
    fireEvent.keyDown(screen.getByRole("textbox", { name: "Message" }), {
      key: "Escape",
    })
    expect(onClose).toHaveBeenCalledOnce()
  })
})

import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { apiClient } from "@/lib/api"
import { ChatbotPanel } from "./ChatbotPanel"

vi.mock("@/features/auth/AuthContext", () => ({
  useAuth: () => ({ user: { first_name: "Ana", role: "student" } }),
}))
vi.mock("@/lib/api", () => ({ apiClient: { post: vi.fn() } }))

function renderPanel(onClose = vi.fn()) {
  return render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { mutations: { retry: false } } })
      }
    >
      <ChatbotPanel open onClose={onClose} />
    </QueryClientProvider>
  )
}

beforeEach(() => vi.clearAllMocks())

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
          attendance_summary: { present_days: 16, late_days: 2, absent_days: 2 },
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

  it("offers the assistant limitations and closes with Escape", () => {
    const onClose = vi.fn()
    renderPanel(onClose)
    expect(
      screen.getByText(/does not remember earlier messages/)
    ).toBeInTheDocument()
    fireEvent.keyDown(screen.getByRole("textbox", { name: "Message" }), {
      key: "Escape",
    })
    expect(onClose).toHaveBeenCalledOnce()
  })
})

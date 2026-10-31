import { fireEvent, render, screen, within } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { LandingPage } from "./LandingPage"

const cms = vi.hoisted(() => ({ announcements: vi.fn(), resources: vi.fn() }))
vi.mock("@/features/cms/public-api", () => ({
  usePublicAnnouncements: cms.announcements,
  usePublicResources: cms.resources,
}))

const empty = () => ({
  data: [],
  isLoading: false,
  isError: false,
  isFetching: false,
  refetch: vi.fn(),
})
const page = () => (
  <MemoryRouter>
    <LandingPage />
  </MemoryRouter>
)

beforeEach(() => {
  cms.announcements.mockReturnValue(empty())
  cms.resources.mockReturnValue(empty())
})

describe("homepage interactions", () => {
  it("keeps the event and closing note visible when the announcement feed fails", () => {
    const announcements = {
      ...empty(),
      isError: true,
      error: new Error("private upstream traceback"),
    }
    const resources = {
      ...empty(),
      isError: true,
      error: new Error("private upstream traceback"),
    }
    cms.announcements.mockReturnValue(announcements)
    cms.resources.mockReturnValue(resources)
    render(page())
    const news = within(screen.getByRole("region", { name: "Announcements" }))
    const files = within(screen.getByRole("region", { name: "Resources" }))
    expect(
      news.getByRole("heading", { name: "Mister & Miss HIS CARE 2027!" })
    ).toBeInTheDocument()
    expect(news.getByRole("status")).toHaveTextContent(
      "That's all for now. Check back for more school announcements."
    )
    expect(
      news.queryByRole("button", { name: "Retry" })
    ).not.toBeInTheDocument()
    expect(news.queryByRole("alert")).not.toBeInTheDocument()
    fireEvent.click(files.getByRole("button", { name: "Retry" }))
    expect(resources.refetch).toHaveBeenCalledTimes(1)
    expect(announcements.refetch).not.toHaveBeenCalled()
    expect(screen.queryByText(/private upstream/)).not.toBeInTheDocument()
  })

  it("keeps the supplied event visible when the live feeds are empty", () => {
    render(page())
    expect(
      screen.getByRole("heading", { name: "Mister & Miss HIS CARE 2027!" })
    ).toBeInTheDocument()
    expect(screen.getByText("Ms. Anica Elain R. Banquil")).toBeInTheDocument()
    expect(
      screen.getByRole("img", {
        name: /Mister & Miss HIS CARE 2027 event poster/,
      })
    ).toHaveAttribute("src", "/announcement%20pic.png")
    expect(
      screen.queryByText("No announcements have been published yet.")
    ).not.toBeInTheDocument()
    expect(
      screen.getByText(
        "That's all for now. Check back for more school announcements."
      )
    ).toBeInTheDocument()
    expect(
      screen.getByText("No resources have been published yet.")
    ).toBeInTheDocument()
    expect(screen.queryByRole("alert")).not.toBeInTheDocument()
    expect(
      screen.queryByRole("button", { name: "Retry" })
    ).not.toBeInTheDocument()
  })

  it("labels loading states and prevents duplicate retries while fetching", () => {
    cms.announcements.mockReturnValue({ ...empty(), isLoading: true })
    cms.resources.mockReturnValue({
      ...empty(),
      isError: true,
      isFetching: true,
    })
    render(page())
    expect(
      screen.getByRole("status", { name: "Loading announcements" })
    ).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Retrying…" })).toBeDisabled()
  })

  it("renders the returned announcement and resource without truncating their text", () => {
    cms.announcements.mockReturnValue({
      ...empty(),
      data: [
        {
          document_id: "test-announcement",
          title: "API announcement title",
          content: "Complete announcement text from the API.",
          announcement_type: "academic",
          published_at: "2026-10-01T00:00:00Z",
        },
      ],
    })
    cms.resources.mockReturnValue({
      ...empty(),
      data: [
        {
          document_id: "test-resource",
          title: "API resource title",
          description: "Complete resource description from the API.",
          resource_type: "document",
        },
      ],
    })
    render(page())
    expect(
      screen.getByRole("heading", { name: "API announcement title" })
    ).toBeInTheDocument()
    expect(
      screen.getByText("Complete announcement text from the API.")
    ).toBeInTheDocument()
    expect(
      screen.getByRole("heading", { name: "API resource title" })
    ).toBeInTheDocument()
    expect(
      screen.getByText("Complete resource description from the API.")
    ).toBeInTheDocument()
    expect(screen.queryByRole("alert")).not.toBeInTheDocument()
  })

  it("exposes FAQ expansion state and closes the previous answer", () => {
    render(page())
    const first = screen.getByRole("button", { name: "How do I sign in?" })
    const second = screen.getByRole("button", {
      name: "Where do grades appear?",
    })
    expect(first).toHaveAttribute("aria-expanded", "false")
    first.focus()
    fireEvent.click(first)
    expect(first).toHaveFocus()
    expect(first).toHaveAttribute("aria-expanded", "true")
    expect(
      screen.getByRole("region", { name: "How do I sign in?" })
    ).toBeInTheDocument()
    fireEvent.click(second)
    expect(first).toHaveAttribute("aria-expanded", "false")
    expect(second).toHaveAttribute("aria-expanded", "true")
    fireEvent.click(second)
    expect(second).toHaveAttribute("aria-expanded", "false")
  })

  it("uses the current copyright year and preserves the legal links", () => {
    render(page())
    const footer = within(screen.getByRole("contentinfo"))
    expect(
      footer.getByText(new RegExp(`© ${new Date().getFullYear()} His Care`))
    ).toBeInTheDocument()
    expect(
      footer.getByRole("link", { name: "Privacy Policy" })
    ).toHaveAttribute("href", "/privacy")
  })
})

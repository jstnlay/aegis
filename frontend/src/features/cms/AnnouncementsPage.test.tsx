import { render, screen } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { AnnouncementsPage } from "@/features/cms/AnnouncementsPage"
import { useCmsAnnouncements, type CmsAnnouncement } from "@/features/admin/api"

vi.mock("@/features/admin/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/features/admin/api")>()
  return { ...actual, useCmsAnnouncements: vi.fn() }
})

const mockedUseCmsAnnouncements = vi.mocked(useCmsAnnouncements)

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <AnnouncementsPage />
    </QueryClientProvider>
  )
}

const announcement: CmsAnnouncement = {
  document_id: "doc-1",
  title: "Sports Fest",
  content: "The annual sports fest starts on Monday.",
  announcement_type: "news",
  priority: "normal",
  target_roles: ["all"],
  target_sections: [],
  published_at: "2026-08-22T01:00:00Z",
  expires_at: null,
  cover_image: null,
}

describe("AnnouncementsPage", () => {
  beforeEach(() => {
    mockedUseCmsAnnouncements.mockReturnValue({
      data: [announcement],
      isLoading: false,
      isError: false,
    } as unknown as ReturnType<typeof useCmsAnnouncements>)
  })

  it("lists the announcements the caller may see", () => {
    renderPage()

    expect(
      screen.getByRole("heading", { name: "Sports Fest" })
    ).toBeInTheDocument()
    expect(
      screen.getByText("The annual sports fest starts on Monday.")
    ).toBeInTheDocument()
  })

  it("says so when there is nothing to read", () => {
    mockedUseCmsAnnouncements.mockReturnValue({
      data: [],
      isLoading: false,
      isError: false,
    } as unknown as ReturnType<typeof useCmsAnnouncements>)

    renderPage()

    expect(screen.getByText(/No announcements yet/i)).toBeInTheDocument()
  })
})

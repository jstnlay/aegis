import type { ReactNode } from "react"
import { fireEvent, render, screen, within } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { describe, expect, it, vi } from "vitest"

import indexHtml from "../../../index.html?raw"

import {
  ABOUT_EXCERPT,
  CONTACT,
  MISSION_TEXT,
  SCHOOL_NAME,
} from "@/lib/school-content"
import { LandingPage } from "@/routes/pages/LandingPage"
import { SchoolPage } from "@/routes/pages/SchoolPage"

// The identity assertions below are static; the CMS feeds are covered by
// public-api.test.tsx and would only add network noise here.
vi.mock("@/features/cms/public-api", () => ({
  usePublicAnnouncements: () => ({
    isLoading: false,
    isError: false,
    data: [],
  }),
  usePublicResources: () => ({ isLoading: false, isError: false, data: [] }),
}))

function renderPage(page: ReactNode, path: string) {
  return render(<MemoryRouter initialEntries={[path]}>{page}</MemoryRouter>)
}

describe("landing school identity", () => {
  it("leads with the school name and seal over the cover-photo backdrop", () => {
    const { container } = renderPage(<LandingPage />, "/")

    const heading = screen.getByRole("heading", {
      level: 1,
      name: SCHOOL_NAME,
    })
    expect(heading).toBeInTheDocument()

    expect(
      screen.getByAltText("His Care Christian Institute seal")
    ).toBeInTheDocument()

    // The campus photo is the hero backdrop now; the old side-by-side
    // banner <img> is intentionally gone (blank slot).
    const hero = container.querySelector(
      'section[aria-labelledby="landing-hero"]'
    )
    expect(hero?.getAttribute("style")).toContain("/cover-photo.png")
    expect(
      screen.queryByRole("img", { name: /banner: DepEd authorization/ })
    ).not.toBeInTheDocument()
    // The campus line appears in both the header lockup and the hero.
    expect(
      screen.getAllByText("of Santa Maria, Sto. Tomas Batangas Inc.").length
    ).toBeGreaterThanOrEqual(2)
  })

  it("shows the school's own mission and vision copy verbatim", () => {
    renderPage(<LandingPage />, "/")

    expect(screen.getByRole("heading", { name: "Mission" })).toBeInTheDocument()
    expect(screen.getByRole("heading", { name: "Vision" })).toBeInTheDocument()
    // The numbered Mission breaks from the design are preserved as lines
    // (rendered with whitespace-pre-line); getByText only normalizes the DOM
    // side, so collapse the matcher the same way before comparing.
    expect(
      screen.getByText(MISSION_TEXT.replace(/\s+/g, " "))
    ).toBeInTheDocument()
    expect(screen.getByText(ABOUT_EXCERPT)).toBeInTheDocument()
  })

  it("points both Read more links at the school page", () => {
    renderPage(<LandingPage />, "/")

    const readMore = screen.getAllByRole("link", { name: /Read more/ })
    expect(readMore.length).toBeGreaterThanOrEqual(2)
    for (const link of readMore) {
      expect(link).toHaveAttribute("href", "/school")
    }
  })

  it("lists the draft contact details without inventing a phone number", () => {
    renderPage(<LandingPage />, "/")

    expect(screen.getByText(CONTACT.address)).toBeInTheDocument()
    expect(screen.getByText(CONTACT.schoolId)).toBeInTheDocument()
    const mail = screen.getByRole("link", { name: CONTACT.email })
    expect(mail).toHaveAttribute("href", `mailto:${CONTACT.email}`)
    expect(screen.queryByText(/phone/i)).not.toBeInTheDocument()
  })

  it("plays the hero entrance on the first visit of a session only", () => {
    sessionStorage.clear()

    const first = renderPage(<LandingPage />, "/")
    const firstCopy = screen.getByRole("heading", { level: 1 }).parentElement
    expect(firstCopy?.className).toContain("animate-in")
    first.unmount()

    renderPage(<LandingPage />, "/")
    const secondCopy = screen.getByRole("heading", { level: 1 }).parentElement
    expect(secondCopy?.className).not.toContain("animate-in")

    sessionStorage.clear()
  })
})

describe("school background page", () => {
  it("renders the full About, Mission and Vision", () => {
    renderPage(<SchoolPage />, "/school")

    expect(
      screen.getByRole("heading", { level: 1, name: "School background" })
    ).toBeInTheDocument()
    // Fragments that only exist in the full text, not the landing excerpt.
    expect(screen.getByText(/Ramonita Homes/)).toBeInTheDocument()
    expect(screen.getByText(/MATATAG Curiculum/)).toBeInTheDocument()
    expect(screen.getByRole("heading", { name: "Mission" })).toBeInTheDocument()
    expect(screen.getByRole("heading", { name: "Vision" })).toBeInTheDocument()
  })

  it("offers a way back to the landing page", () => {
    renderPage(<SchoolPage />, "/school")

    const back = screen.getByRole("link", { name: "Back to the landing page" })
    expect(back).toHaveAttribute("href", "/")

    const header = screen.getByRole("banner")
    expect(
      within(header).getByAltText("His Care Christian Institute seal")
    ).toBeInTheDocument()
  })
})

describe("landing navigation on a phone", () => {
  it("opens the section menu, follows a link and closes on Escape", () => {
    renderPage(<LandingPage />, "/")

    const toggle = screen.getByRole("button", { name: "Menu" })
    expect(toggle).toHaveAttribute("aria-expanded", "false")

    fireEvent.click(toggle)
    expect(toggle).toHaveAttribute("aria-expanded", "true")

    const panel = document.getElementById("public-nav-menu")
    expect(panel).not.toBeNull()
    expect(within(panel!).getByRole("link", { name: "About" })).toHaveAttribute(
      "href",
      "#about"
    )

    fireEvent.click(within(panel!).getByRole("link", { name: "About" }))
    expect(toggle).toHaveAttribute("aria-expanded", "false")

    fireEvent.click(toggle)
    fireEvent.keyDown(document, { key: "Escape" })
    expect(toggle).toHaveAttribute("aria-expanded", "false")
  })
})

describe("document identity", () => {
  it("ships the HCCI seal as favicon and names the school in the title", () => {
    expect(indexHtml).toContain('href="/hcci-logo.png"')
    expect(indexHtml).not.toContain("favicon.svg")
    expect(indexHtml).toContain(
      "<title>AEGIS — HIS CARE CHRISTIAN INSTITUTE</title>"
    )
  })
})

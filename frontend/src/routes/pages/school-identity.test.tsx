import type { ReactNode } from "react"
import { fireEvent, render, screen, within } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { describe, expect, it, vi } from "vitest"

import indexHtml from "../../../index.html?raw"

import { CONTACT, MISSION_TEXT, SCHOOL_NAME } from "@/lib/school-content"
import { LandingPage } from "@/routes/pages/LandingPage"
import { NotFoundPage } from "@/routes/pages/NotFoundPage"
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
  it("leads with the school name, seal and supplied campus photo", () => {
    const { container } = renderPage(<LandingPage />, "/")

    const heading = screen.getByRole("heading", {
      level: 1,
      name: SCHOOL_NAME,
    })
    expect(heading).toBeInTheDocument()

    expect(
      within(screen.getByRole("banner")).getByAltText(
        "His Care Christian Institute seal"
      )
    ).toBeInTheDocument()

    // Campus photography belongs in the responsive hero, rather than
    // displaying the entire information poster as an extra banner.
    const hero = container.querySelector(
      'section[aria-labelledby="landing-hero"]'
    )
    expect(hero?.querySelector('img[src="/front%20bg.png"]')).not.toBeNull()
    expect(hero).toHaveTextContent(
      "serving students from Nursery to Grade 12 (Senior High School) in Batangas."
    )
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
    // Number badges change the presentation while retaining every sentence.
    for (const line of MISSION_TEXT.split("\n")) {
      expect(
        screen.getByText(line.replace(/^\d+\.\s*/, ""))
      ).toBeInTheDocument()
    }
  })

  it("points the hero Read more link at the school page", () => {
    renderPage(<LandingPage />, "/")

    expect(screen.getByRole("link", { name: /Read more/ })).toHaveAttribute(
      "href",
      "/school"
    )
  })

  it("lists the supplied school contact channels with working links", () => {
    renderPage(<LandingPage />, "/")

    expect(screen.getByText(CONTACT.address)).toBeInTheDocument()
    expect(screen.getByText(CONTACT.schoolId)).toBeInTheDocument()
    const mail = screen.getByRole("link", { name: CONTACT.email })
    expect(mail).toHaveAttribute("href", `mailto:${CONTACT.email}`)
    expect(screen.getByRole("link", { name: CONTACT.phone })).toHaveAttribute(
      "href",
      "tel:09463781119"
    )
    expect(screen.getByText(CONTACT.messengerName)).toBeInTheDocument()
    const facebook = screen.getByRole("link", { name: "Facebook" })
    expect(facebook).toHaveAttribute("href", CONTACT.facebookUrl)
    expect(facebook).toHaveAttribute("target", "_blank")
    expect(facebook).toHaveAttribute("rel", "noopener noreferrer")
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
      "/school"
    )

    fireEvent.click(within(panel!).getByRole("link", { name: "About" }))
    expect(toggle).toHaveAttribute("aria-expanded", "false")

    fireEvent.click(toggle)
    fireEvent.keyDown(document, { key: "Escape" })
    expect(toggle).toHaveAttribute("aria-expanded", "false")
  })

  it("only links to sections the landing page actually has", () => {
    const { container } = renderPage(<LandingPage />, "/")

    const toggle = screen.getByRole("button", { name: "Menu" })
    fireEvent.click(toggle)
    const panel = document.getElementById("public-nav-menu")!
    const links = within(panel).getAllByRole("link")

    const anchors = links
      .map((link) => link.getAttribute("href"))
      .filter((href): href is string => !!href?.startsWith("#"))

    expect(anchors.length).toBeGreaterThanOrEqual(4)
    for (const href of anchors) {
      expect(
        container.querySelector(`[id="${href.slice(1)}"]`),
        href
      ).not.toBeNull()
    }
  })
})

describe("not-found page", () => {
  it("wears the public chrome, with a main landmark and the policy links", () => {
    renderPage(<NotFoundPage />, "/nowhere")

    expect(
      screen.getByRole("heading", { level: 1, name: "Page not found" })
    ).toBeInTheDocument()
    expect(screen.getByRole("main")).toBeInTheDocument()
    expect(screen.getByRole("banner")).toBeInTheDocument()
    expect(
      screen.getByRole("link", { name: "Privacy Policy" })
    ).toHaveAttribute("href", "/privacy")
    expect(screen.getByRole("link", { name: "Back to home" })).toHaveAttribute(
      "href",
      "/"
    )
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

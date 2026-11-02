import { render, screen } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { describe, expect, it } from "vitest"

import { PublicFooter } from "@/components/brand/PublicFooter"
import { appRoutes } from "@/routes/routes"
import { CookiePolicyPage } from "@/routes/pages/CookiePolicyPage"
import { PrivacyPolicyPage } from "@/routes/pages/PrivacyPolicyPage"
import { TermsOfUsePage } from "@/routes/pages/TermsOfUsePage"

function renderPage(page: React.ReactNode) {
  return render(<MemoryRouter initialEntries={["/"]}>{page}</MemoryRouter>)
}

/*
 * The three legal pages are public and reach no API, so they are rendered
 * directly rather than through `appRoutes`. The wiring is asserted separately
 * below against the real route table.
 */
describe("legal page routes", () => {
  it("registers a public route for each legal page", () => {
    const paths = appRoutes.map((route) => route.path)
    expect(paths).toContain("/privacy")
    expect(paths).toContain("/terms")
    expect(paths).toContain("/cookies")
  })
})

describe("Privacy Policy", () => {
  it("states the controller, the children's section and the statutory rights", () => {
    renderPage(<PrivacyPolicyPage />)

    expect(
      screen.getByRole("heading", { level: 1, name: "Privacy Policy" })
    ).toBeInTheDocument()
    expect(
      screen.getByRole("heading", { name: "Children's information" })
    ).toBeInTheDocument()
    expect(
      screen.getByRole("heading", { name: "Your rights" })
    ).toBeInTheDocument()
    expect(screen.getByText(/Data Privacy Act of 2012/)).toBeInTheDocument()
    expect(
      screen.getAllByText(
        /lodge a complaint with the National Privacy Commission/
      ).length
    ).toBeGreaterThan(0)
    // Breach notification window, as the law sets it.
    expect(screen.getByText(/within 72 hours/)).toBeInTheDocument()
  })
})

describe("Terms of Use", () => {
  it("covers accounts, acceptable use, fees and governing law", () => {
    renderPage(<TermsOfUsePage />)

    expect(
      screen.getByRole("heading", { level: 1, name: "Terms of Use" })
    ).toBeInTheDocument()
    expect(
      screen.getByRole("heading", { name: "Your account" })
    ).toBeInTheDocument()
    expect(screen.getByRole("heading", { name: "No fees" })).toBeInTheDocument()
    expect(
      screen.getByText(/takes no payment and processes no payment details/)
    ).toBeInTheDocument()
    expect(
      screen.getByText(
        /governed by the laws of the Republic of the Philippines/
      )
    ).toBeInTheDocument()
  })
})

describe("Cookie Policy", () => {
  it("names every item of browser storage the app actually uses", () => {
    renderPage(<CookiePolicyPage />)

    expect(
      screen.getByRole("heading", { level: 1, name: "Cookie Policy" })
    ).toBeInTheDocument()
    expect(
      screen.getByRole("heading", { name: /sets no cookies/i })
    ).toBeInTheDocument()

    // Exact keys, matching `@/lib/auth-storage`, the landing hero flag and the
    // guidance archive toggles.
    for (const key of [
      "aegis.access_token",
      "aegis.refresh_token",
      "aegis:hero-entrance-seen",
      "aegis:archive:consultations",
      "aegis:archive:interventions",
    ]) {
      expect(screen.getByText(key), key).toBeInTheDocument()
    }

    // No consent banner exists, and the page says why.
    expect(
      screen.getByRole("heading", { name: /Why there is no accept button/ })
    ).toBeInTheDocument()
  })
})

describe("public footer", () => {
  it("links to every legal page from the public pages", () => {
    renderPage(<PublicFooter />)

    expect(
      screen.getByRole("link", { name: "Privacy Policy" })
    ).toHaveAttribute("href", "/privacy")
    expect(screen.getByRole("link", { name: "Terms of Use" })).toHaveAttribute(
      "href",
      "/terms"
    )
    expect(screen.getByRole("link", { name: "Cookie Policy" })).toHaveAttribute(
      "href",
      "/cookies"
    )
  })
})

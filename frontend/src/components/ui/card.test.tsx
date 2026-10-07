import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"

/**
 * PH11.11: `CardTitle` heading semantics.
 *
 * `CardTitle` rendered a `<div>`, so every card title in the application was
 * absent from the heading outline. PH11.2 §16.4 requires `h1`–`h6` in
 * hierarchical order with no skipped levels, which a `div` cannot satisfy
 * however it is styled.
 *
 * These tests pin the element and the level, because either can regress
 * silently: the classes are unchanged from the `div`, so the visual result is
 * identical and only the DOM differs.
 */
describe("CardTitle", () => {
  function renderCard(title: React.ReactNode, description?: React.ReactNode) {
    return render(
      <Card>
        <CardHeader>
          <CardTitle>{title}</CardTitle>
          {description ? (
            <CardDescription>{description}</CardDescription>
          ) : null}
        </CardHeader>
        <CardContent>Body</CardContent>
      </Card>
    )
  }

  it("renders a heading rather than a div", () => {
    renderCard("Average grade")

    const heading = screen.getByRole("heading", { name: "Average grade" })
    expect(heading.tagName).toBe("H3")
  })

  it("defaults to h3, the level a titled region sits at inside a page", () => {
    renderCard("Risk alerts")

    expect(screen.getByRole("heading", { name: "Risk alerts" })).toHaveProperty(
      "tagName",
      "H3"
    )
  })

  it("honours an explicit level for a card at a different depth", () => {
    render(
      <Card>
        <CardHeader>
          <CardTitle as="h2">Profile</CardTitle>
        </CardHeader>
      </Card>
    )

    const heading = screen.getByRole("heading", { name: "Profile" })
    expect(heading.tagName).toBe("H2")
  })

  it("can opt out of the heading outline for a card that is not a section", () => {
    // A stat tile is a labelled value, not a section. Adding a heading there
    // would put noise in the outline, so `as="div"` is available rather than
    // forcing every caller to accept a heading.
    render(
      <Card>
        <CardHeader>
          <CardTitle as="div">Attendance rate</CardTitle>
        </CardHeader>
      </Card>
    )

    expect(
      screen.queryByRole("heading", { name: "Attendance rate" })
    ).not.toBeInTheDocument()
    expect(screen.getByText("Attendance rate").tagName).toBe("DIV")
  })

  it("keeps the card's visual treatment unchanged", () => {
    renderCard("Average grade", "Across all grading periods")

    const heading = screen.getByRole("heading", { name: "Average grade" })
    // The classes carried over from the div version, so nothing moved on screen.
    expect(heading).toHaveClass("font-heading", "text-base", "font-medium")
    expect(heading).toHaveAttribute("data-slot", "card-title")
  })
})

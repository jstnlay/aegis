import { render, screen, within } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import { SubjectGradeCard } from "./SubjectGradeCard"

describe("SubjectGradeCard", () => {
  it("keeps full subject names, codes, scores and written passing status readable", () => {
    render(
      <ul>
        <SubjectGradeCard
          name="Contemporary Philippine Arts from the Regions"
          code="CPAR-12"
          score={89.25}
        />
      </ul>
    )

    expect(
      screen.getByRole("heading", {
        name: "Contemporary Philippine Arts from the Regions",
        level: 4,
      })
    ).toBeInTheDocument()
    expect(screen.getByText("CPAR-12")).toBeInTheDocument()
    expect(screen.getByText("89.25%")).toBeInTheDocument()
    expect(screen.getByText("Passing")).toBeInTheDocument()
    // A read-only result should not advertise a button that does nothing.
    expect(screen.queryByRole("button")).not.toBeInTheDocument()
  })

  it("distinguishes an unrecorded grade from an actual zero", () => {
    render(
      <ul>
        <SubjectGradeCard name="English" code="ENG7" score={null} />
        <SubjectGradeCard name="Science" code="SCI7" score={0} />
      </ul>
    )

    const unrecorded = screen
      .getByRole("heading", { name: "English" })
      .closest("li")!
    const zero = screen.getByRole("heading", { name: "Science" }).closest("li")!
    expect(within(unrecorded).getByText("N/A")).toBeInTheDocument()
    expect(within(unrecorded).getByText("Not recorded")).toBeInTheDocument()
    expect(
      within(unrecorded).queryByText("Below passing")
    ).not.toBeInTheDocument()
    expect(within(zero).getByText("0.00%")).toBeInTheDocument()
    expect(within(zero).getByText("Below passing")).toBeInTheDocument()
  })
})

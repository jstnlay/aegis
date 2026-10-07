import { render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

import { ChoiceField, Field } from "@/components/ui/form-field"

/**
 * PH11.11: the shared labelled-field pattern.
 *
 * This is the contract PH11.2 §16.5 asks for, promoted out of
 * `AdminAcademicsPage` — the only place in the application that had met it. The
 * assertions are on the wiring rather than the appearance, because the wiring is
 * what was missing everywhere else: a control can look correctly labelled and
 * still leave a screen-reader user unable to tell which field an error belongs
 * to.
 */
describe("Field", () => {
  const base = {
    id: "new-name",
    value: "",
    onChange: vi.fn(),
  }

  it("binds the label to the control", () => {
    render(<Field {...base} label="Name" />)

    // The accessible name is exactly the field's name — no marker folded in.
    expect(screen.getByLabelText(/^Name$/)).toBeInTheDocument()
  })

  it("marks a required field visually and programmatically", () => {
    render(<Field {...base} label="Name" required />)

    const input = screen.getByLabelText(/^Name$/)
    // PH11.2 §16.5 asks for `aria-required`; `required` is the HTML equivalent
    // and is what stops the browser's own validation firing first.
    expect(input).toHaveAttribute("aria-required", "true")
    expect(input).toBeRequired()

    // The sighted cue, and it must stay out of the accessible name so the
    // requirement is not announced twice.
    expect(screen.getByText("*")).toHaveAttribute("aria-hidden", "true")
  })

  it("leaves an optional field unmarked", () => {
    render(<Field {...base} label="Name" />)

    const input = screen.getByLabelText(/^Name$/)
    expect(input).not.toBeRequired()
    expect(input).not.toHaveAttribute("aria-required")
    expect(screen.queryByText("*")).not.toBeInTheDocument()
  })

  it("links an error to its control by aria-describedby", () => {
    render(<Field {...base} label="Name" error="This field is required." />)

    const input = screen.getByLabelText(/^Name$/)
    const message = screen.getByText("This field is required.")

    // The pair that was missing app-wide: the message is announced, and the
    // control points at it so focusing the control reads it.
    expect(input).toHaveAttribute("aria-invalid", "true")
    expect(input.getAttribute("aria-describedby")).toBe(message.id)
  })

  it("does not point aria-describedby at an id that is not rendered", () => {
    render(<Field {...base} label="Name" />)

    // A dangling `aria-describedby` is announced as an empty string by some
    // screen readers and is an HTML validity error regardless. With no error and
    // no hint there is nothing to describe, so the attribute must be absent
    // rather than present-but-empty.
    expect(screen.getByLabelText(/^Name$/)).not.toHaveAttribute(
      "aria-describedby"
    )
  })

  it("describes the control by both the hint and the error when both exist", () => {
    render(
      <Field
        {...base}
        label="Name"
        hint="Up to 80 characters."
        error="Too long."
      />
    )

    const input = screen.getByLabelText(/^Name$/)
    const ids = input.getAttribute("aria-describedby")?.split(" ") ?? []

    expect(ids).toHaveLength(2)
    expect(ids).toContain(screen.getByText("Up to 80 characters.").id)
    expect(ids).toContain(screen.getByText("Too long.").id)
  })

  it("describes the control by the hint alone when there is no error", () => {
    render(<Field {...base} label="Name" hint="Up to 80 characters." />)

    const input = screen.getByLabelText(/^Name$/)
    expect(input.getAttribute("aria-describedby")).toBe(
      screen.getByText("Up to 80 characters.").id
    )
    expect(input).not.toHaveAttribute("aria-invalid")
  })
})

describe("ChoiceField", () => {
  const base = {
    id: "new-section",
    value: "",
    onChange: vi.fn(),
    options: [{ value: "a", label: "Bonifacio" }],
  }

  it("binds the label to the Radix trigger", () => {
    render(<ChoiceField {...base} label="Section" />)

    // The trigger is a real button, so `<label for>` targeting it is a valid
    // association.
    expect(screen.getByLabelText(/^Section$/)).toBeInTheDocument()
  })

  it("marks a required select programmatically", () => {
    render(<ChoiceField {...base} label="Section" required />)

    const trigger = screen.getByLabelText(/^Section$/)
    expect(trigger).toHaveAttribute("aria-required", "true")
    expect(screen.getByText("*")).toHaveAttribute("aria-hidden", "true")
  })

  it("links an error to the trigger by aria-describedby", () => {
    render(<ChoiceField {...base} label="Section" error="Select a section." />)

    const trigger = screen.getByLabelText(/^Section$/)
    expect(trigger).toHaveAttribute("aria-invalid", "true")
    expect(trigger.getAttribute("aria-describedby")).toBe(
      screen.getByText("Select a section.").id
    )
  })
})

import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import {
  EmptyState,
  ErrorNote,
  LoadingState,
  PendingMetric,
  PendingRegion,
  UnavailableMetric,
} from "@/components/feedback/Feedback"

/**
 * PH11.11: the three list states announce themselves, and stay distinct.
 *
 * This module exists so a page cannot collapse "the request failed" into
 * "there is nothing there" — two different claims, one of which is a failure the
 * reader has to be told about. PH11.11 closed the remaining hole in that set:
 * `LoadingState` and `ErrorNote` already announced themselves, but `EmptyState`
 * was silent, so the polite end of a request was the one outcome a screen reader
 * never heard about.
 *
 * The distinction between error and empty is the thing worth protecting, and it
 * is asserted by role rather than by text, because text can be reworded and the
 * role cannot be lost by accident.
 */
describe("Feedback states", () => {
  describe("ErrorNote", () => {
    it("announces assertively, because a failure interrupts", () => {
      render(<ErrorNote message="Request failed." />)

      expect(screen.getByRole("alert")).toHaveTextContent("Request failed.")
    })

    it("renders nothing when there is no message", () => {
      const { container } = render(<ErrorNote message="" />)

      expect(container).toBeEmptyDOMElement()
    })
  })

  describe("LoadingState", () => {
    it("announces politely and marks itself busy", () => {
      render(<LoadingState label="Loading students" />)

      const status = screen.getByRole("status")
      expect(status).toHaveAttribute("aria-busy", "true")
      expect(status).toHaveAttribute("aria-live", "polite")
      expect(status).toHaveTextContent("Loading students…")
    })

    it("falls back to a generic label", () => {
      render(<LoadingState />)

      expect(screen.getByRole("status")).toHaveTextContent("Loading…")
    })
  })

  describe("EmptyState", () => {
    it("announces politely, and never as an alert", () => {
      render(<EmptyState message="No students" />)

      // PH11.2 §16.7 requires dynamic content updates to be announced. The
      // empty state replaces a table the reader was waiting on.
      const status = screen.getByRole("status")
      expect(status).toHaveTextContent("No students")

      // Nothing failed, so it must not interrupt the way an error does. This is
      // the distinction the module is built around.
      expect(screen.queryByRole("alert")).not.toBeInTheDocument()
    })

    it("renders a caller's action alongside the message", () => {
      render(
        <EmptyState message="No students">
          <button type="button">Try again</button>
        </EmptyState>
      )

      expect(
        screen.getByRole("button", { name: "Try again" })
      ).toBeInTheDocument()
    })
  })

  it("keeps error and empty distinguishable by role, not only by colour", () => {
    const { unmount } = render(<ErrorNote message="Request failed." />)
    expect(screen.getByRole("alert")).toBeInTheDocument()
    expect(screen.queryByRole("status")).not.toBeInTheDocument()
    unmount()

    render(<EmptyState message="No students" />)
    expect(screen.getByRole("status")).toBeInTheDocument()
    expect(screen.queryByRole("alert")).not.toBeInTheDocument()
  })
})

/**
 * PH11.11: the metric-tile states.
 *
 * Every dashboard in the app drew an unresolved request as one or more bare
 * `Skeleton` bars — no role, no state, no text. A screen-reader user arriving on
 * a dashboard heard the page title and then nothing about the dozen figures still
 * arriving, and had no way to tell "still loading" from "a dashboard with no
 * content". `PendingRegion` wraps a skeleton in place so the visual language is
 * unchanged and the region announces itself.
 *
 * The second half of the change is the harder one: a tile whose request *failed*
 * used to fall back to `NO_DATA_TEXT` ("N/A"), which asserts the backend reported
 * no figure. A failed request asserts nothing of the sort. `UnavailableMetric` is
 * the third state, and these tests pin that it is neither a number nor "N/A".
 */
describe("metric-tile states", () => {
  it("announces a pending region without changing what it renders", () => {
    render(
      <PendingRegion label="Overall grade average">
        <div data-testid="skeleton" />
      </PendingRegion>
    )

    const region = screen.getByRole("status")
    expect(region).toHaveAttribute("aria-busy", "true")
    expect(region).toHaveAttribute("aria-live", "polite")
    expect(region).toHaveTextContent("Overall grade average…")
    // The caller's own placeholder is untouched — this owns semantics, not looks.
    expect(screen.getByTestId("skeleton")).toBeInTheDocument()
  })

  it("renders the metric placeholder as an announced skeleton", () => {
    render(<PendingMetric label="Total students" />)

    const region = screen.getByRole("status")
    expect(region).toHaveAttribute("aria-busy", "true")
    expect(region).toHaveTextContent("Total students…")
    expect(region.querySelector('[data-slot="skeleton"]')).not.toBeNull()
  })

  it("says a failed metric is unavailable, never N/A and never a number", () => {
    render(<UnavailableMetric />)

    expect(screen.getByText("Unavailable")).toBeInTheDocument()
    // The distinction this exists for: "N/A" claims the backend reported no
    // figure. A failure means nobody knows.
    expect(screen.queryByText("N/A")).not.toBeInTheDocument()
    expect(screen.queryByText("0")).not.toBeInTheDocument()
    // And it is not announced as an interruption — the accompanying ErrorNote is.
    expect(screen.queryByRole("alert")).not.toBeInTheDocument()
  })
})

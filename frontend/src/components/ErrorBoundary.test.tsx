import { act, fireEvent, render, screen } from "@testing-library/react"
import { useState } from "react"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { ErrorBoundary } from "@/components/ErrorBoundary"

/**
 * Throws on demand so a render failure can be produced deterministically.
 *
 * This is the class of failure PH11.9 had no defence against: a malformed
 * record reaching render (the object-shaped `risk_factors` bug was exactly
 * this) threw during render and unmounted the whole SPA.
 */
function Boom({ explode }: { explode: boolean }): React.ReactElement {
  if (explode) {
    throw new Error("Objects are not valid as a React child")
  }
  return <p>rendered fine</p>
}

function Subject({
  explode,
  extra,
}: {
  explode: boolean
  extra?: React.ReactNode
}): React.ReactElement {
  return (
    <div>
      <Boom explode={explode} />
      {extra}
    </div>
  )
}

beforeEach(() => {
  vi.restoreAllMocks()
  // The boundary always logs the real error; that is deliberate and asserted
  // separately. Silence it here so a passing run stays quiet.
  vi.spyOn(console, "error").mockImplementation(() => {})
})

describe("ErrorBoundary", () => {
  it("renders children when nothing throws", () => {
    render(
      <ErrorBoundary>
        <Subject explode={false} />
      </ErrorBoundary>
    )

    expect(screen.getByText("rendered fine")).toBeInTheDocument()
  })

  it("shows a recovery state instead of unmounting the tree", () => {
    render(
      <ErrorBoundary>
        <Subject explode />
      </ErrorBoundary>
    )

    expect(screen.getByRole("alert")).toBeInTheDocument()
    expect(
      screen.getByText("This page could not be displayed")
    ).toBeInTheDocument()
    // The real message is shown, not a generic apology.
    expect(
      screen.getByText("Objects are not valid as a React child")
    ).toBeInTheDocument()
    expect(
      screen.getByRole("button", { name: /try again/i })
    ).toBeInTheDocument()
  })

  it("logs the error and component stack so the cause is diagnosable", () => {
    const spy = vi.spyOn(console, "error").mockImplementation(() => {})

    render(
      <ErrorBoundary>
        <Subject explode />
      </ErrorBoundary>
    )

    expect(spy).toHaveBeenCalledWith(
      "[aegis] render error caught by ErrorBoundary",
      expect.any(Error),
      expect.stringContaining("Boom")
    )
  })

  it("recovers when resetKeys change", () => {
    function Harness(): React.ReactElement {
      const [route, setRoute] = useState("broken")
      return (
        <div>
          <button onClick={() => setRoute("healthy")}>navigate</button>
          <ErrorBoundary resetKeys={[route]}>
            <Subject explode={route === "broken"} />
          </ErrorBoundary>
        </div>
      )
    }

    render(<Harness />)
    expect(screen.getByRole("alert")).toBeInTheDocument()

    fireEvent.click(screen.getByRole("button", { name: "navigate" }))

    // Navigating away clears the error with no reload — the point of keying
    // the boundary on the route.
    expect(screen.queryByRole("alert")).not.toBeInTheDocument()
    expect(screen.getByText("rendered fine")).toBeInTheDocument()
  })

  it("does not reset when resetKeys are unchanged", () => {
    const { rerender } = render(
      <ErrorBoundary resetKeys={["same"]}>
        <Subject explode />
      </ErrorBoundary>
    )

    expect(screen.getByRole("alert")).toBeInTheDocument()

    rerender(
      <ErrorBoundary resetKeys={["same"]}>
        <Subject explode />
      </ErrorBoundary>
    )

    // Still showing the error: retrying the same broken route is the Retry
    // button's job, not a silent remount.
    expect(screen.getByRole("alert")).toBeInTheDocument()
  })

  it("Try again clears a boundary whose children stopped throwing", async () => {
    function Switch(): React.ReactElement {
      const [broken, setBroken] = useState(true)
      return (
        <div>
          <button onClick={() => setBroken(false)}>fix data</button>
          <ErrorBoundary>
            <Subject explode={broken} />
          </ErrorBoundary>
        </div>
      )
    }

    render(<Switch />)
    expect(screen.getByRole("alert")).toBeInTheDocument()

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "fix data" }))
    })
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /try again/i }))
    })

    expect(screen.queryByRole("alert")).not.toBeInTheDocument()
    expect(screen.getByText("rendered fine")).toBeInTheDocument()
  })

  it("renders a custom fallback when one is supplied", () => {
    render(
      <ErrorBoundary
        label="Student profile"
        fallback={(reset) => (
          <div>
            <p>custom recovery</p>
            <button onClick={reset}>retry</button>
          </div>
        )}
      >
        <Subject explode />
      </ErrorBoundary>
    )

    expect(screen.getByText("custom recovery")).toBeInTheDocument()
    expect(
      screen.queryByRole("button", { name: /reload the page/i })
    ).not.toBeInTheDocument()
  })

  it("uses the label to name the area that failed", () => {
    render(
      <ErrorBoundary label="Student profile">
        <Subject explode />
      </ErrorBoundary>
    )

    expect(
      screen.getByText("Student profile could not be displayed")
    ).toBeInTheDocument()
  })

  it("keeps a sibling alive so the rest of the page still works", () => {
    // The boundary is the safety net for one region, not the whole document.
    render(
      <div>
        <nav>sidebar navigation</nav>
        <ErrorBoundary>
          <Subject explode />
        </ErrorBoundary>
      </div>
    )

    expect(screen.getByText("sidebar navigation")).toBeInTheDocument()
    expect(screen.getByRole("alert")).toBeInTheDocument()
  })
})

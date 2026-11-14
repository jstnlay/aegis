import { act, render, screen } from "@testing-library/react"
import { afterEach, describe, expect, it } from "vitest"

import { OfflineGate } from "./OfflineGate"

function setOnline(value: boolean) {
  Object.defineProperty(window.navigator, "onLine", {
    configurable: true,
    get: () => value,
  })
}

afterEach(() => {
  setOnline(true)
})

describe("OfflineGate", () => {
  it("replaces the app with the offline page and recovers on `online`", () => {
    setOnline(false)

    render(
      <OfflineGate>
        <p>Signed-in workspace</p>
      </OfflineGate>
    )

    expect(screen.getByText("You are offline")).toBeInTheDocument()
    expect(screen.queryByText("Signed-in workspace")).not.toBeInTheDocument()

    act(() => {
      setOnline(true)
      window.dispatchEvent(new Event("online"))
    })

    expect(screen.getByText("Signed-in workspace")).toBeInTheDocument()
    expect(screen.queryByText("You are offline")).not.toBeInTheDocument()
  })

  it("renders the app while online", () => {
    setOnline(true)
    render(
      <OfflineGate>
        <p>Signed-in workspace</p>
      </OfflineGate>
    )
    expect(screen.getByText("Signed-in workspace")).toBeInTheDocument()
  })
})

import { act, cleanup, fireEvent, render, screen } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { PublicNav } from "./PublicNav"
import { SchoolHeader } from "./SchoolHeader"

function renderHeader() {
  return render(
    <MemoryRouter>
      <SchoolHeader>
        <PublicNav />
      </SchoolHeader>
    </MemoryRouter>
  )
}

function scrollTo(y: number) {
  vi.stubGlobal("scrollY", y)
  fireEvent.scroll(window)
}

function waitWithoutScrolling() {
  act(() => vi.advanceTimersByTime(5000))
}

beforeEach(() => {
  vi.useFakeTimers()
  vi.stubGlobal("scrollY", 0)
})

afterEach(() => {
  cleanup()
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

describe("public header visibility", () => {
  it("hides on scroll down and stays visible after scrolling up until scrolling down again", () => {
    renderHeader()
    const header = screen.getByRole("banner")
    waitWithoutScrolling()
    expect(header).toHaveAttribute("data-hidden", "false")

    scrollTo(300)
    expect(header).toHaveAttribute("data-scrolled", "true")
    expect(header).toHaveAttribute("data-hidden", "true")

    fireEvent.pointerMove(window)
    waitWithoutScrolling()
    expect(header).toHaveAttribute("data-hidden", "true")

    scrollTo(250)
    expect(header).toHaveAttribute("data-hidden", "false")
    waitWithoutScrolling()
    scrollTo(250)
    expect(header).toHaveAttribute("data-hidden", "false")

    scrollTo(350)
    expect(header).toHaveAttribute("data-hidden", "true")
    scrollTo(0)
    waitWithoutScrolling()
    expect(header).toHaveAttribute("data-hidden", "false")
    expect(header).toHaveAttribute("data-scrolled", "false")
  })

  it("keeps an open mobile menu visible until it is dismissed", () => {
    renderHeader()
    const header = screen.getByRole("banner")
    scrollTo(300)
    scrollTo(250)
    fireEvent.click(screen.getByRole("button", { name: "Menu" }))
    scrollTo(350)
    waitWithoutScrolling()
    expect(header).toHaveAttribute("data-hidden", "false")

    fireEvent.keyDown(document, { key: "Escape" })
    waitWithoutScrolling()
    expect(header).toHaveAttribute("data-hidden", "false")
    scrollTo(400)
    expect(header).toHaveAttribute("data-hidden", "true")
  })

  it("keeps keyboard-focused navigation visible", () => {
    renderHeader()
    scrollTo(300)
    act(() => screen.getByRole("link", { name: "Home" }).focus())
    waitWithoutScrolling()
    expect(screen.getByRole("banner")).toHaveAttribute("data-hidden", "false")
  })
})

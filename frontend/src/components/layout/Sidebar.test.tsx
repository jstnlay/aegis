import { act, fireEvent, render, screen } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { Sidebar } from "./Sidebar"

const state = vi.hoisted(() => ({ role: "admin" }))
vi.mock("@/features/auth/AuthContext", () => ({
  useAuth: () => ({ user: { role: state.role } }),
}))

function renderSidebar(
  wide = true,
  open = false,
  brandContainer: HTMLDivElement | null = null
) {
  vi.stubGlobal("matchMedia", () => ({
    matches: wide,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  }))
  render(
    <MemoryRouter initialEntries={["/app/dashboard"]}>
      <Sidebar
        open={open}
        onOpenChange={vi.fn()}
        brandContainer={brandContainer}
      />
    </MemoryRouter>
  )
  return screen.getByRole("complementary", { name: "Primary" })
}

function idle() {
  act(() => vi.advanceTimersByTime(2400))
}

function scrollPage(top: number) {
  vi.stubGlobal("scrollY", top)
  fireEvent.scroll(window)
}

beforeEach(() => {
  state.role = "admin"
  vi.stubGlobal("scrollY", 0)
  vi.useFakeTimers()
})

afterEach(() => {
  vi.clearAllTimers()
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

describe.each(["admin", "guidance", "student", "parent"])(
  "%s sidebar auto-minimize",
  (role) => {
    beforeEach(() => {
      state.role = role
    })
    it("keeps branding in the top header and synchronizes it with the sidebar", () => {
      const headerBrand = document.createElement("div")
      document.body.append(headerBrand)
      try {
        const sidebar = renderSidebar(true, false, headerBrand)
        expect(headerBrand.querySelector("img")).toBeInTheDocument()
        expect(sidebar.querySelector("img")).not.toBeInTheDocument()
        idle()
        expect(headerBrand.querySelector(".app-header-brand")).toHaveAttribute(
          "data-compact",
          "true"
        )
        fireEvent.pointerEnter(sidebar, { pointerType: "mouse" })
        expect(headerBrand.querySelector(".app-header-brand")).toHaveAttribute(
          "data-compact",
          "false"
        )
        fireEvent.click(
          screen.getByRole("button", { name: "Minimize navigation" })
        )
        expect(sidebar).toHaveAttribute("data-compact", "true")
        expect(headerBrand.querySelector(".app-header-brand")).toHaveAttribute(
          "data-compact",
          "true"
        )
      } finally {
        headerBrand.remove()
      }
    })

    it("allows manual minimizing while the pointer and focus are inside the panel", () => {
      const sidebar = renderSidebar()
      fireEvent.pointerEnter(sidebar, { pointerType: "mouse" })
      const toggle = screen.getByRole("button", { name: "Minimize navigation" })
      expect(toggle).toHaveAttribute("aria-controls", "primary-navigation")
      act(() => toggle.focus())
      fireEvent.click(toggle)
      idle()
      expect(sidebar).toHaveAttribute("data-compact", "true")
      expect(toggle).not.toBeInTheDocument()

      fireEvent.pointerLeave(sidebar)
      fireEvent.pointerEnter(sidebar, { pointerType: "mouse" })
      expect(sidebar).toHaveAttribute("data-compact", "false")
      expect(
        screen.getByRole("button", { name: "Minimize navigation" })
      ).toHaveAttribute("aria-expanded", "true")
    })

    it("hides the arrow while minimized and shows it again when keyboard focus expands navigation", () => {
      const sidebar = renderSidebar()
      idle()
      expect(
        screen.queryByRole("button", { name: /navigation/i })
      ).not.toBeInTheDocument()
      expect(sidebar).toHaveAttribute("data-compact", "true")
      act(() => screen.getByRole("link", { name: "Dashboard" }).focus())
      expect(sidebar).toHaveAttribute("data-compact", "false")
      expect(
        screen.getByRole("button", { name: "Minimize navigation" })
      ).toBeInTheDocument()
    })

    it("collapses after idle and preserves accessible link names", () => {
      const sidebar = renderSidebar()
      expect(sidebar).toHaveAttribute("data-compact", "false")
      idle()
      expect(sidebar).toHaveAttribute("data-compact", "true")
      expect(screen.getByRole("link", { name: "Dashboard" })).toHaveAttribute(
        "title",
        "Dashboard"
      )
    })

    it("expands on hover and waits until the pointer leaves before collapsing", () => {
      const sidebar = renderSidebar()
      idle()
      fireEvent.pointerEnter(sidebar, { pointerType: "mouse" })
      idle()
      expect(sidebar).toHaveAttribute("data-compact", "false")
      fireEvent.pointerLeave(sidebar)
      expect(sidebar).toHaveAttribute("data-compact", "false")
      idle()
      expect(sidebar).toHaveAttribute("data-compact", "true")
    })

    it("stays expanded while keyboard focus is inside navigation", () => {
      const sidebar = renderSidebar()
      idle()
      const link = screen.getByRole("link", { name: "Dashboard" })
      act(() => link.focus())
      idle()
      expect(sidebar).toHaveAttribute("data-compact", "false")
      act(() => link.blur())
      idle()
      expect(sidebar).toHaveAttribute("data-compact", "true")
    })

    it("minimizes immediately when the page scrolls down, including after using a navigation link", () => {
      const sidebar = renderSidebar()
      const link = screen.getByRole("link", { name: "Dashboard" })
      act(() => link.focus())
      scrollPage(100)
      expect(sidebar).toHaveAttribute("data-compact", "true")
      expect(link).toHaveFocus()

      fireEvent.pointerEnter(sidebar, { pointerType: "mouse" })
      expect(sidebar).toHaveAttribute("data-compact", "false")
      scrollPage(60)
      expect(sidebar).toHaveAttribute("data-compact", "false")
      scrollPage(140)
      expect(sidebar).toHaveAttribute("data-compact", "true")
    })

    it("keeps the panel expanded when scrolling through its navigation", () => {
      const sidebar = renderSidebar()
      fireEvent.pointerEnter(sidebar, { pointerType: "mouse" })
      const navigation = screen.getByRole("navigation", { name: "Main" })
      navigation.scrollTop = 120
      fireEvent.scroll(navigation)
      idle()
      expect(sidebar).toHaveAttribute("data-compact", "false")
    })

    it("keeps the mobile drawer full-width while open", () => {
      const sidebar = renderSidebar(false, true)
      scrollPage(100)
      idle()
      expect(sidebar).toHaveAttribute("data-compact", "false")
      expect(
        screen.getByRole("button", {
          name: "Minimize navigation",
        })
      ).toHaveAttribute("aria-expanded", "true")
      expect(
        screen.getByRole("navigation", { name: "Main" })
      ).not.toHaveAttribute("inert")
    })

    it("auto-minimizes for faculty like the other school roles", () => {
      state.role = "faculty"
      const sidebar = renderSidebar()
      scrollPage(100)
      idle()
      expect(sidebar).toHaveAttribute("data-compact", "true")
    })
  }
)

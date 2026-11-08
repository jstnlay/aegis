import { fireEvent, render, screen } from "@testing-library/react"
import { beforeEach, afterEach, expect, it, vi } from "vitest"
import { LEGAL_LAST_UPDATED } from "@/routes/pages/LegalPageLayout"
import { PolicyWelcome } from "./PolicyWelcome"
import { POLICY_ACKNOWLEDGMENT_KEY } from "@/lib/policy-acknowledgment"

const auth = vi.hoisted(() => ({ status: "unauthenticated" }))
vi.mock("@/features/auth/AuthContext", () => ({ useAuth: () => auth }))

beforeEach(() => {
  localStorage.clear()
  auth.status = "unauthenticated"
})
afterEach(() => {
  vi.restoreAllMocks()
})

it("stays hidden until sign-in requests it", () => {
  const view = render(<PolicyWelcome />)
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
  view.rerender(<PolicyWelcome open />)
  expect(
    screen.getByRole("dialog", { name: "Before you begin" })
  ).toBeInTheDocument()
})

it("requires explicit acknowledgment and remembers the current policy version", () => {
  const view = render(<PolicyWelcome open />)
  const proceed = screen.getByRole("button", { name: "Agree and continue" })
  expect(proceed).toBeDisabled()
  fireEvent.click(screen.getByRole("checkbox"))
  fireEvent.click(proceed)
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
  expect(localStorage.getItem(POLICY_ACKNOWLEDGMENT_KEY)).toBe(
    LEGAL_LAST_UPDATED
  )
  view.unmount()
  render(<PolicyWelcome open />)
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
})

it("shows the notice again for a previous policy version", () => {
  localStorage.setItem(POLICY_ACKNOWLEDGMENT_KEY, "previous-version")
  render(<PolicyWelcome open />)
  expect(screen.getByRole("dialog")).toBeInTheDocument()
})

it.each(["Terms of Use", "Privacy Policy"])(
  "opens the existing %s and returns without accepting",
  (name) => {
    render(<PolicyWelcome open />)
    fireEvent.click(screen.getByRole("button", { name: new RegExp(name) }))
    expect(screen.getByRole("dialog", { name })).toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "Close policy" }))
    expect(
      screen.getByRole("dialog", { name: "Before you begin" })
    ).toBeInTheDocument()
    expect(
      screen.getByRole("button", { name: "Agree and continue" })
    ).toBeDisabled()
    expect(localStorage.getItem(POLICY_ACKNOWLEDGMENT_KEY)).toBeNull()
  }
)

it("does not silently accept when Escape is pressed", () => {
  render(<PolicyWelcome open />)
  fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape" })
  expect(screen.getByRole("dialog")).toBeInTheDocument()
  expect(localStorage.getItem(POLICY_ACKNOWLEDGMENT_KEY)).toBeNull()
})

it("can continue when browser storage is unavailable", () => {
  vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
    throw new Error("Storage blocked")
  })
  vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
    throw new Error("Storage blocked")
  })
  render(<PolicyWelcome open />)
  fireEvent.click(screen.getByRole("checkbox"))
  fireEvent.click(screen.getByRole("button", { name: "Agree and continue" }))
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
})

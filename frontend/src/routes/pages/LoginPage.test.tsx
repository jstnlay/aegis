import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { LoginPage } from "./LoginPage"

const login = vi.fn(async () => {})

vi.mock("@/features/auth/AuthContext", () => ({
  useAuth: () => ({
    status: "unauthenticated",
    user: null,
    mustChangePassword: false,
    isAuthenticated: false,
    sessionExpired: false,
    sessionEndedBy: null,
    login,
    logout: vi.fn(),
    changePassword: vi.fn(),
  }),
}))

function renderPage() {
  return render(
    <MemoryRouter>
      <LoginPage />
    </MemoryRouter>
  )
}

async function fillAndSubmit() {
  fireEvent.change(screen.getByLabelText("Email"), {
    target: { value: "student@school.edu" },
  })
  fireEvent.change(screen.getByLabelText("Password"), {
    target: { value: "pass12345" },
  })
  fireEvent.click(screen.getByRole("button", { name: "Sign in" }))
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe("LoginPage", () => {
  it("carries the sign-in elements the system documentation names", () => {
    renderPage()

    // Document elements 1, 2, 3 and 5.
    expect(screen.getByLabelText("Email")).toBeInTheDocument()
    expect(screen.getByLabelText("Password")).toBeInTheDocument()
    expect(screen.getByLabelText("Remember me")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Sign in" })).toBeInTheDocument()
  })

  it("links to password recovery and to student registration", () => {
    renderPage()

    // Document elements 4 and 6.
    expect(
      screen.getByRole("link", { name: "Forgot password?" })
    ).toHaveAttribute("href", "/forgot-password")
    expect(
      screen.getByRole("link", { name: "Request an account" })
    ).toHaveAttribute("href", "/register")
  })

  it("signs in with an idle session when the box is left unticked", async () => {
    renderPage()

    await fillAndSubmit()

    await waitFor(() => expect(login).toHaveBeenCalledTimes(1))
    expect(login).toHaveBeenCalledWith(
      "student@school.edu",
      "pass12345",
      false
    )
  })

  it("asks for a remembered session when the box is ticked", async () => {
    renderPage()

    fireEvent.click(screen.getByLabelText("Remember me"))
    await fillAndSubmit()

    await waitFor(() => expect(login).toHaveBeenCalledTimes(1))
    expect(login).toHaveBeenCalledWith(
      "student@school.edu",
      "pass12345",
      true
    )
  })
})

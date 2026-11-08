import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react"
import {
  createMemoryRouter,
  MemoryRouter,
  RouterProvider,
} from "react-router-dom"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { LoginPage } from "./LoginPage"
import { POLICY_ACKNOWLEDGMENT_KEY } from "@/lib/policy-acknowledgment"
import { LEGAL_LAST_UPDATED } from "./LegalPageLayout"

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
  localStorage.setItem(POLICY_ACKNOWLEDGMENT_KEY, LEGAL_LAST_UPDATED)
})

describe("LoginPage", () => {
  it("shows policies over the login interface before the first sign-in", async () => {
    localStorage.removeItem(POLICY_ACKNOWLEDGMENT_KEY)
    renderPage()
    const dialog = screen.getByRole("dialog", { name: "Before you begin" })
    expect(document.querySelector(".school-login-page")).toBeInTheDocument()
    expect(login).not.toHaveBeenCalled()
    fireEvent.click(within(dialog).getByRole("checkbox"))
    fireEvent.click(
      within(dialog).getByRole("button", { name: "Agree and continue" })
    )
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
    expect(login).not.toHaveBeenCalled()
    await fillAndSubmit()
    await waitFor(() =>
      expect(login).toHaveBeenCalledExactlyOnceWith(
        "student@school.edu",
        "pass12345",
        false
      )
    )
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
  })

  it("does not reopen policies when the current version was already accepted", () => {
    renderPage()
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
    expect(screen.getByLabelText("Email")).toBeVisible()
  })

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

    // Password recovery stays available; account requests are no longer shown.
    expect(
      screen.getByRole("link", { name: "Forgot password?" })
    ).toHaveAttribute("href", "/forgot-password")
    expect(
      screen.queryByRole("link", { name: "Request an account" })
    ).not.toBeInTheDocument()
  })

  it("returns directly to the landing page even when login was opened directly", async () => {
    const router = createMemoryRouter(
      [
        { path: "/", element: <h1>School homepage</h1> },
        { path: "/login", element: <LoginPage /> },
      ],
      { initialEntries: ["/login"] }
    )
    render(<RouterProvider router={router} />)
    fireEvent.change(screen.getByLabelText("Email"), {
      target: { value: "student@school.edu" },
    })
    fireEvent.change(screen.getByLabelText("Password"), {
      target: { value: "pass12345" },
    })
    fireEvent.click(screen.getByRole("link", { name: "Back to landing page" }))
    await screen.findByRole("heading", { name: "School homepage" })
    expect(router.state.location.pathname).toBe("/")
    expect(login).not.toHaveBeenCalled()
  })

  it("shows and hides the entered password without submitting or changing it", async () => {
    renderPage()
    const password = screen.getByLabelText("Password")
    fireEvent.change(password, { target: { value: "pass12345" } })
    expect(password).toHaveAttribute("type", "password")

    fireEvent.click(screen.getByRole("button", { name: "Show password" }))
    expect(password).toHaveAttribute("type", "text")
    expect(password).toHaveValue("pass12345")
    expect(login).not.toHaveBeenCalled()

    fireEvent.click(screen.getByRole("button", { name: "Hide password" }))
    expect(password).toHaveAttribute("type", "password")
    expect(password).toHaveValue("pass12345")
    expect(login).not.toHaveBeenCalled()

    fireEvent.click(screen.getByRole("button", { name: "Show password" }))
    fireEvent.change(screen.getByLabelText("Email"), {
      target: { value: "student@school.edu" },
    })
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }))
    await waitFor(() => expect(login).toHaveBeenCalledTimes(1))
    expect(login).toHaveBeenCalledWith("student@school.edu", "pass12345", false)
  })

  it.each(["Terms of Use", "Privacy Policy"])(
    "opens %s over the login form and keeps the entered email when closed",
    async (title) => {
      renderPage()
      fireEvent.change(screen.getByLabelText("Email"), {
        target: { value: "student@school.edu" },
      })
      const trigger = screen.getByRole("button", { name: title })
      fireEvent.click(trigger)

      const dialog = await screen.findByRole("dialog", { name: title })
      expect(within(dialog).getByRole("heading", { name: title })).toBeVisible()
      expect(
        within(dialog).getByRole("region", { name: `${title} document` })
      ).toBeInTheDocument()
      expect(
        within(dialog).queryByRole("link", {
          name: /back to the landing page/i,
        })
      ).not.toBeInTheDocument()

      fireEvent.click(
        within(dialog).getByRole("button", { name: "Back to sign in" })
      )
      await waitFor(() =>
        expect(screen.queryByRole("dialog")).not.toBeInTheDocument()
      )
      expect(screen.getByLabelText("Email")).toHaveValue("student@school.edu")
      await waitFor(() => expect(trigger).toHaveFocus())
      expect(login).not.toHaveBeenCalled()
    }
  )

  it("signs in with an idle session when the box is left unticked", async () => {
    renderPage()

    await fillAndSubmit()

    await waitFor(() => expect(login).toHaveBeenCalledTimes(1))
    expect(login).toHaveBeenCalledWith("student@school.edu", "pass12345", false)
  })

  it("asks for a remembered session when the box is ticked", async () => {
    renderPage()

    fireEvent.click(screen.getByLabelText("Remember me"))
    await fillAndSubmit()

    await waitFor(() => expect(login).toHaveBeenCalledTimes(1))
    expect(login).toHaveBeenCalledWith("student@school.edu", "pass12345", true)
  })
})

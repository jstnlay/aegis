import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { ForgotPasswordPage } from "./ForgotPasswordPage"
import { ResetPasswordPage } from "./ResetPasswordPage"

/*
 * `vi.mock` factories are hoisted above every other statement, so the
 * mocked functions have to be created inside the factory (or hoisted with
 * `vi.hoisted`) — a plain top-level `const` would not exist yet when the
 * factory runs.
 */
const { forgotPasswordRequest, resetPasswordRequest } = vi.hoisted(() => ({
  forgotPasswordRequest: vi.fn(async () => {}),
  resetPasswordRequest: vi.fn(async () => {}),
}))

vi.mock("@/features/auth/api", () => ({
  forgotPasswordRequest,
  resetPasswordRequest,
}))

function renderPage(element: React.ReactElement, path = "/") {
  return render(<MemoryRouter initialEntries={[path]}>{element}</MemoryRouter>)
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe("ForgotPasswordPage", () => {
  it("asks for a reset link with the address that was typed", async () => {
    renderPage(<ForgotPasswordPage />)

    fireEvent.change(screen.getByLabelText("Email"), {
      target: { value: "parent@school.edu" },
    })
    fireEvent.click(screen.getByRole("button", { name: "Send reset link" }))

    await waitFor(() => expect(forgotPasswordRequest).toHaveBeenCalledTimes(1))
    expect(forgotPasswordRequest).toHaveBeenCalledWith("parent@school.edu")
  })

  it("answers the same way whether or not the account exists", async () => {
    renderPage(<ForgotPasswordPage />)

    fireEvent.change(screen.getByLabelText("Email"), {
      target: { value: "nobody@example.com" },
    })
    fireEvent.click(screen.getByRole("button", { name: "Send reset link" }))

    // The page cannot say "no such account", because the server does not
    // say it either. The message covers both cases.
    expect(
      await screen.findByText(/If an account exists for that address/i)
    ).toBeInTheDocument()
    expect(
      screen
        .getByText("Check your inbox", { selector: "li span" })
        .closest("li")
    ).toHaveAttribute("aria-current", "step")
  })
})

describe("ResetPasswordPage", () => {
  it("redeems the token from the link with the new password", async () => {
    renderPage(<ResetPasswordPage />, "/reset-password?token=abc123")

    fireEvent.change(screen.getByLabelText("New password"), {
      target: { value: "brandnewpass1" },
    })
    fireEvent.change(screen.getByLabelText("Confirm new password"), {
      target: { value: "brandnewpass1" },
    })
    fireEvent.click(screen.getByRole("button", { name: "Set new password" }))

    await waitFor(() => expect(resetPasswordRequest).toHaveBeenCalledTimes(1))
    expect(resetPasswordRequest).toHaveBeenCalledWith({
      token: "abc123",
      new_password: "brandnewpass1",
      confirm_password: "brandnewpass1",
    })
    expect(
      await screen.findByRole("heading", { name: "Password reset" })
    ).toBeInTheDocument()
    expect(screen.getByRole("link", { name: "Sign in" })).toHaveAttribute(
      "href",
      "/login"
    )
  })

  it("shows each password independently without changing values or submitting", () => {
    renderPage(<ResetPasswordPage />, "/reset-password?token=abc123")
    const password = screen.getByLabelText("New password")
    const confirmation = screen.getByLabelText("Confirm new password")
    fireEvent.change(password, { target: { value: "brandnewpass1" } })
    fireEvent.change(confirmation, { target: { value: "brandnewpass1" } })

    fireEvent.click(screen.getByRole("button", { name: "Show new password" }))
    expect(password).toHaveAttribute("type", "text")
    expect(confirmation).toHaveAttribute("type", "password")
    expect(password).toHaveValue("brandnewpass1")
    fireEvent.click(screen.getByRole("button", { name: "Hide new password" }))
    expect(password).toHaveAttribute("type", "password")
    fireEvent.click(
      screen.getByRole("button", { name: "Show password confirmation" })
    )
    expect(confirmation).toHaveAttribute("type", "text")
    expect(confirmation).toHaveValue("brandnewpass1")
    expect(resetPasswordRequest).not.toHaveBeenCalled()
  })

  it("keeps mismatched passwords on the form instead of sending them", async () => {
    renderPage(<ResetPasswordPage />, "/reset-password?token=abc123")
    fireEvent.change(screen.getByLabelText("New password"), {
      target: { value: "brandnewpass1" },
    })
    fireEvent.change(screen.getByLabelText("Confirm new password"), {
      target: { value: "differentpass1" },
    })
    fireEvent.click(screen.getByRole("button", { name: "Set new password" }))
    expect(
      await screen.findByText("Passwords do not match.")
    ).toBeInTheDocument()
    expect(resetPasswordRequest).not.toHaveBeenCalled()
  })

  it("refuses a link with no token", () => {
    renderPage(<ResetPasswordPage />, "/reset-password")

    expect(screen.getByText(/missing its token/i)).toBeInTheDocument()
    expect(
      screen.queryByRole("button", { name: "Set new password" })
    ).not.toBeInTheDocument()
  })
})

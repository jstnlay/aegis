import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { RegisterPage } from "./RegisterPage"

/*
 * `vi.mock` factories are hoisted above every other statement, so the mocked
 * functions have to be created inside the factory (or hoisted with
 * `vi.hoisted`) — a plain top-level `const` would not exist yet when the
 * factory runs.
 */
const { submitRegistrationRequest, verifyRegistrationRequest } = vi.hoisted(
  () => ({
    submitRegistrationRequest: vi.fn(async () => {}),
    verifyRegistrationRequest: vi.fn(async () => {}),
  })
)

vi.mock("@/features/auth/api", () => ({
  submitRegistrationRequest,
  verifyRegistrationRequest,
}))

function renderPage(path = "/register") {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <RegisterPage />
    </MemoryRouter>
  )
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe("RegisterPage", () => {
  it("sends the request with the fields the student typed", async () => {
    renderPage()

    fireEvent.change(screen.getByLabelText("Full name"), {
      target: { value: "Juan Dela Cruz" },
    })
    fireEvent.change(screen.getByLabelText("Email"), {
      target: { value: "juan@example.com" },
    })
    fireEvent.change(screen.getByLabelText(/Student number/), {
      target: { value: "AEGIS-QA-S0001" },
    })
    fireEvent.change(screen.getByLabelText("Password"), {
      target: { value: "brandnewpass1" },
    })
    fireEvent.change(screen.getByLabelText("Confirm password"), {
      target: { value: "brandnewpass1" },
    })
    fireEvent.click(
      screen.getByRole("button", { name: "Send verification link" })
    )

    await waitFor(() =>
      expect(submitRegistrationRequest).toHaveBeenCalledTimes(1)
    )
    expect(submitRegistrationRequest).toHaveBeenCalledWith({
      full_name: "Juan Dela Cruz",
      email: "juan@example.com",
      student_code: "AEGIS-QA-S0001",
      password: "brandnewpass1",
      confirm_password: "brandnewpass1",
    })
  })

  it("says a request is not an account", async () => {
    renderPage()

    fireEvent.change(screen.getByLabelText("Full name"), {
      target: { value: "Juan Dela Cruz" },
    })
    fireEvent.change(screen.getByLabelText("Email"), {
      target: { value: "juan@example.com" },
    })
    fireEvent.change(screen.getByLabelText("Password"), {
      target: { value: "brandnewpass1" },
    })
    fireEvent.change(screen.getByLabelText("Confirm password"), {
      target: { value: "brandnewpass1" },
    })
    fireEvent.click(
      screen.getByRole("button", { name: "Send verification link" })
    )

    expect(
      await screen.findByText(/An administrator reviews the request/i)
    ).toBeInTheDocument()
  })

  it("verifies a request that arrives with a token", async () => {
    renderPage("/register?token=abc123")

    await waitFor(() =>
      expect(verifyRegistrationRequest).toHaveBeenCalledWith("abc123")
    )
    expect(await screen.findByText(/Request verified/i)).toBeInTheDocument()
  })

  it("refuses a token that does not verify", async () => {
    verifyRegistrationRequest.mockRejectedValueOnce(
      new Error("invalid") as Error
    )
    renderPage("/register?token=stale")

    expect(
      await screen.findByText(/This link has expired/i)
    ).toBeInTheDocument()
  })
})

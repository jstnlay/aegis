import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { AcceptInvitationPage } from "./AcceptInvitationPage"

const { acceptParentInvitationRequest } = vi.hoisted(() => ({
  acceptParentInvitationRequest: vi.fn(async () => {}),
}))

vi.mock("@/features/auth/api", () => ({
  acceptParentInvitationRequest,
}))

function renderPage(path = "/accept-invitation?token=abc123") {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AcceptInvitationPage />
    </MemoryRouter>
  )
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe("AcceptInvitationPage", () => {
  it("redeems the invitation with the password the parent chose", async () => {
    renderPage()

    fireEvent.change(screen.getByLabelText("Password"), {
      target: { value: "brandnewpass1" },
    })
    fireEvent.change(screen.getByLabelText("Confirm password"), {
      target: { value: "brandnewpass1" },
    })
    fireEvent.click(
      screen.getByRole("button", { name: "Create my account" })
    )

    await waitFor(() =>
      expect(acceptParentInvitationRequest).toHaveBeenCalledTimes(1)
    )
    expect(acceptParentInvitationRequest).toHaveBeenCalledWith({
      token: "abc123",
      password: "brandnewpass1",
      confirm_password: "brandnewpass1",
    })
  })

  it("says the account is ready once the invitation is accepted", async () => {
    renderPage()

    fireEvent.change(screen.getByLabelText("Password"), {
      target: { value: "brandnewpass1" },
    })
    fireEvent.change(screen.getByLabelText("Confirm password"), {
      target: { value: "brandnewpass1" },
    })
    fireEvent.click(
      screen.getByRole("button", { name: "Create my account" })
    )

    expect(
      await screen.findByText(/Your parent account is ready/i)
    ).toBeInTheDocument()
  })

  it("refuses a link with no token", () => {
    renderPage("/accept-invitation")

    expect(
      screen.getByText(/missing its token/i)
    ).toBeInTheDocument()
    expect(
      screen.queryByRole("button", { name: "Create my account" })
    ).not.toBeInTheDocument()
  })
})

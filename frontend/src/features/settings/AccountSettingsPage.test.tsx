import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { MemoryRouter } from "react-router-dom"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { apiClient } from "@/lib/api"

import { AccountSettingsPage } from "./AccountSettingsPage"
import { optionalText } from "./api"

vi.mock("@/lib/api", () => ({
  API_BASE_URL: "http://localhost:8000/api/v1",
  onSessionExpired: vi.fn(() => () => {}),
  apiClient: {
    get: vi.fn(),
    post: vi.fn(async () => ({ data: {} })),
    put: vi.fn(async () => ({ data: {} })),
    patch: vi.fn(async () => ({ data: {} })),
    delete: vi.fn(async () => ({ data: undefined })),
  },
}))

const mockedGet = vi.mocked(apiClient.get)
const mockedPost = vi.mocked(apiClient.post)
const mockedPut = vi.mocked(apiClient.put)
const mockedPatch = vi.mocked(apiClient.patch)

const user = {
  id: "u-1",
  email: "robin.vega@aegis.edu",
  username: "rvega",
  first_name: "Robin",
  last_name: "Vega",
  role: "guidance",
  phone_number: "+1-555-0100",
  address: "12 Willow Lane",
  language_preference: "en",
  is_active: true,
  created_at: "2024-08-01T00:00:00Z",
  updated_at: "2024-08-01T00:00:00Z",
}

const preference = {
  id: "np-1",
  email_enabled: true,
  in_app_enabled: true,
  quiet_hours_start: null,
  quiet_hours_end: null,
}

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  // `MemoryRouter` because the page's "Your data" card links to the legal
  // pages, and `Link` requires a router above it.
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <AccountSettingsPage />
      </MemoryRouter>
    </QueryClientProvider>
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  mockedGet.mockImplementation(async (url: string) => {
    if (String(url).startsWith("/notifications/preferences/")) {
      return { data: preference } as never
    }
    return { data: user } as never
  })
  mockedPatch.mockResolvedValue({ data: user } as never)
  mockedPut.mockResolvedValue({ data: preference } as never)
  mockedPost.mockResolvedValue({
    data: { detail: "Password changed." },
  } as never)
})

describe("optionalText", () => {
  it("trims, and maps blank to null for nullable CharFields", () => {
    expect(optionalText("  +1-555-0100  ")).toBe("+1-555-0100")
    expect(optionalText("")).toBeNull()
    expect(optionalText("   ")).toBeNull()
  })
})

describe("AccountSettingsPage", () => {
  it("renders the heading and the read-only identity fields", async () => {
    renderPage()

    expect(
      await screen.findByRole("heading", { name: "Account settings", level: 2 })
    ).toBeInTheDocument()
    expect(mockedGet).toHaveBeenCalledWith("/accounts/me/")

    expect(await screen.findByText("robin.vega@aegis.edu")).toBeInTheDocument()
    expect(screen.getByText("rvega")).toBeInTheDocument()
    expect(screen.getByText("guidance")).toBeInTheDocument()
  })

  it("does not offer inputs for server-controlled fields", async () => {
    renderPage()
    await screen.findByText("robin.vega@aegis.edu")

    // email, username, role and is_active are read-only in the serializer.
    expect(screen.queryByLabelText(/email/i)).toBeNull()
    expect(screen.queryByLabelText(/username/i)).toBeNull()
    expect(screen.queryByLabelText(/^role$/i)).toBeNull()
  })

  it("seeds the editable fields from the loaded account", async () => {
    renderPage()

    await waitFor(() =>
      expect(screen.getByLabelText("First name")).toHaveValue("Robin")
    )
    expect(screen.getByLabelText("Last name")).toHaveValue("Vega")
    expect(screen.getByLabelText("Phone number")).toHaveValue("+1-555-0100")
    expect(screen.getByLabelText("Address")).toHaveValue("12 Willow Lane")
    expect(screen.getByLabelText("Language preference")).toHaveValue("en")
  })

  it("patches only the four writable fields", async () => {
    renderPage()
    await waitFor(() =>
      expect(screen.getByLabelText("First name")).toHaveValue("Robin")
    )

    fireEvent.change(screen.getByLabelText("First name"), {
      target: { value: "Robyn" },
    })
    fireEvent.click(screen.getByRole("button", { name: /save profile/i }))

    await waitFor(() => {
      expect(mockedPatch).toHaveBeenCalledWith("/accounts/me/", {
        first_name: "Robyn",
        last_name: "Vega",
        phone_number: "+1-555-0100",
        address: "12 Willow Lane",
        language_preference: "en",
      })
    })

    const payload = mockedPatch.mock.calls[0]?.[1] as Record<string, unknown>
    expect(payload).not.toHaveProperty("email")
    expect(payload).not.toHaveProperty("username")
    expect(payload).not.toHaveProperty("role")
    expect(payload).not.toHaveProperty("is_active")
  })

  it("sends null for optional fields the user clears", async () => {
    renderPage()
    await waitFor(() =>
      expect(screen.getByLabelText("First name")).toHaveValue("Robin")
    )

    fireEvent.change(screen.getByLabelText("Phone number"), {
      target: { value: "   " },
    })
    fireEvent.change(screen.getByLabelText("Address"), {
      target: { value: "" },
    })
    fireEvent.change(screen.getByLabelText("Language preference"), {
      target: { value: "" },
    })
    fireEvent.click(screen.getByRole("button", { name: /save profile/i }))

    await waitFor(() => {
      expect(mockedPatch).toHaveBeenCalledWith(
        "/accounts/me/",
        expect.objectContaining({
          phone_number: null,
          address: null,
          language_preference: null,
        })
      )
    })
  })

  it("confirms a successful profile save", async () => {
    renderPage()
    await waitFor(() =>
      expect(screen.getByLabelText("First name")).toHaveValue("Robin")
    )

    fireEvent.click(screen.getByRole("button", { name: /save profile/i }))

    expect(await screen.findByRole("status")).toHaveTextContent(
      "Profile saved."
    )
  })

  it("surfaces a failed save without losing the typed value", async () => {
    mockedPatch.mockRejectedValue(new Error("Server rejected the change."))

    renderPage()
    await waitFor(() =>
      expect(screen.getByLabelText("First name")).toHaveValue("Robin")
    )

    fireEvent.change(screen.getByLabelText("First name"), {
      target: { value: "Robyn" },
    })
    fireEvent.click(screen.getByRole("button", { name: /save profile/i }))

    const alert = await screen.findByRole("alert")
    expect(alert).toHaveTextContent("Server rejected the change.")
    expect(screen.getByLabelText("First name")).toHaveValue("Robyn")
  })

  it("surfaces a failure to load the account", async () => {
    mockedGet.mockRejectedValue(new Error("profile unavailable"))

    renderPage()

    const alerts = await screen.findAllByRole("alert")
    expect(alerts.length).toBeGreaterThan(0)
    expect(alerts[0]).toHaveTextContent("profile unavailable")
  })

  it("posts the password change to the nested endpoint", async () => {
    renderPage()
    await waitFor(() =>
      expect(screen.getByLabelText("First name")).toHaveValue("Robin")
    )

    fireEvent.change(screen.getByLabelText("Current password"), {
      target: { value: "old-password" },
    })
    fireEvent.change(screen.getByLabelText("New password"), {
      target: { value: "new-password" },
    })
    fireEvent.change(screen.getByLabelText("Confirm new password"), {
      target: { value: "new-password" },
    })
    fireEvent.click(screen.getByRole("button", { name: /change password/i }))

    await waitFor(() => {
      expect(mockedPost).toHaveBeenCalledWith("/accounts/password/change/", {
        current_password: "old-password",
        new_password: "new-password",
      })
    })
  })

  it("clears the password fields after a successful change", async () => {
    renderPage()
    await waitFor(() =>
      expect(screen.getByLabelText("First name")).toHaveValue("Robin")
    )

    fireEvent.change(screen.getByLabelText("Current password"), {
      target: { value: "old-password" },
    })
    fireEvent.change(screen.getByLabelText("New password"), {
      target: { value: "new-password" },
    })
    fireEvent.change(screen.getByLabelText("Confirm new password"), {
      target: { value: "new-password" },
    })
    fireEvent.click(screen.getByRole("button", { name: /change password/i }))

    expect(await screen.findByRole("status")).toHaveTextContent(
      "Password changed."
    )
    expect(screen.getByLabelText("Current password")).toHaveValue("")
    expect(screen.getByLabelText("New password")).toHaveValue("")
    expect(screen.getByLabelText("Confirm new password")).toHaveValue("")
  })

  it("blocks a new password shorter than the server minimum", async () => {
    renderPage()
    await waitFor(() =>
      expect(screen.getByLabelText("First name")).toHaveValue("Robin")
    )

    fireEvent.change(screen.getByLabelText("Current password"), {
      target: { value: "old-password" },
    })
    fireEvent.change(screen.getByLabelText("New password"), {
      target: { value: "short" },
    })
    fireEvent.change(screen.getByLabelText("Confirm new password"), {
      target: { value: "short" },
    })

    expect(
      await screen.findByText(/Use at least 8 characters/i)
    ).toBeInTheDocument()
    expect(
      screen.getByRole("button", { name: /change password/i })
    ).toBeDisabled()
    expect(mockedPost).not.toHaveBeenCalled()
  })

  it("blocks a mismatched confirmation", async () => {
    renderPage()
    await waitFor(() =>
      expect(screen.getByLabelText("First name")).toHaveValue("Robin")
    )

    fireEvent.change(screen.getByLabelText("Current password"), {
      target: { value: "old-password" },
    })
    fireEvent.change(screen.getByLabelText("New password"), {
      target: { value: "new-password" },
    })
    fireEvent.change(screen.getByLabelText("Confirm new password"), {
      target: { value: "different" },
    })

    expect(await screen.findByText(/do not match/i)).toBeInTheDocument()
    expect(
      screen.getByRole("button", { name: /change password/i })
    ).toBeDisabled()
    expect(mockedPost).not.toHaveBeenCalled()
  })

  it("requires the current password", async () => {
    renderPage()
    await waitFor(() =>
      expect(screen.getByLabelText("First name")).toHaveValue("Robin")
    )

    fireEvent.change(screen.getByLabelText("New password"), {
      target: { value: "new-password" },
    })
    fireEvent.change(screen.getByLabelText("Confirm new password"), {
      target: { value: "new-password" },
    })

    expect(
      screen.getByRole("button", { name: /change password/i })
    ).toBeDisabled()
  })

  it("surfaces an incorrect-current-password error", async () => {
    mockedPost.mockRejectedValue(
      new Error("The current password is incorrect.")
    )

    renderPage()
    await waitFor(() =>
      expect(screen.getByLabelText("First name")).toHaveValue("Robin")
    )

    fireEvent.change(screen.getByLabelText("Current password"), {
      target: { value: "wrong" },
    })
    fireEvent.change(screen.getByLabelText("New password"), {
      target: { value: "new-password" },
    })
    fireEvent.change(screen.getByLabelText("Confirm new password"), {
      target: { value: "new-password" },
    })
    fireEvent.click(screen.getByRole("button", { name: /change password/i }))

    const alert = await screen.findByRole("alert")
    expect(alert).toHaveTextContent("The current password is incorrect.")
  })

  it("caps the language field at the model's max_length", async () => {
    renderPage()
    await waitFor(() =>
      expect(screen.getByLabelText("First name")).toHaveValue("Robin")
    )

    expect(screen.getByLabelText("Language preference")).toHaveAttribute(
      "maxLength",
      "10"
    )
  })
})

describe("notification preferences", () => {
  it("reads the real preferences endpoint", async () => {
    renderPage()

    await screen.findByRole("switch", { name: /email notifications/i })
    expect(mockedGet).toHaveBeenCalledWith("/notifications/preferences/")
  })

  it("renders the two channel toggles with their stored state", async () => {
    renderPage()

    const email = await screen.findByRole("switch", {
      name: /email notifications/i,
    })
    const inApp = screen.getByRole("switch", { name: /in-app notifications/i })
    expect(email).toHaveAttribute("aria-checked", "true")
    expect(inApp).toHaveAttribute("aria-checked", "true")
  })

  it("reflects a stored false value", async () => {
    mockedGet.mockImplementation(async (url: string) => {
      if (String(url).startsWith("/notifications/preferences/")) {
        return {
          data: { ...preference, in_app_enabled: false },
        } as never
      }
      return { data: user } as never
    })

    renderPage()

    expect(
      await screen.findByRole("switch", { name: /in-app notifications/i })
    ).toHaveAttribute("aria-checked", "false")
  })

  it("renders the two quiet-hours time inputs", async () => {
    renderPage()

    expect(await screen.findByLabelText(/quiet hours start/i)).toHaveValue("")
    expect(screen.getByLabelText(/quiet hours end/i)).toHaveValue("")
  })

  it("seeds the quiet hours from the stored value", async () => {
    mockedGet.mockImplementation(async (url: string) => {
      if (String(url).startsWith("/notifications/preferences/")) {
        return {
          data: {
            ...preference,
            quiet_hours_start: "22:00:00",
            quiet_hours_end: "06:30:00",
          },
        } as never
      }
      return { data: user } as never
    })

    renderPage()

    expect(await screen.findByLabelText(/quiet hours start/i)).toHaveValue(
      "22:00"
    )
    expect(screen.getByLabelText(/quiet hours end/i)).toHaveValue("06:30")
  })

  it("PUTs exactly the four serializer fields", async () => {
    renderPage()
    await screen.findByRole("switch", { name: /email notifications/i })

    fireEvent.click(
      screen.getByRole("switch", { name: /in-app notifications/i })
    )
    fireEvent.change(screen.getByLabelText(/quiet hours start/i), {
      target: { value: "22:00" },
    })
    fireEvent.change(screen.getByLabelText(/quiet hours end/i), {
      target: { value: "06:30" },
    })
    fireEvent.click(screen.getByRole("button", { name: /save preferences/i }))

    await waitFor(() => {
      expect(mockedPut).toHaveBeenCalledWith("/notifications/preferences/", {
        email_enabled: true,
        in_app_enabled: false,
        quiet_hours_start: "22:00",
        quiet_hours_end: "06:30",
      })
    })

    const payload = mockedPut.mock.calls[0]?.[1] as Record<string, unknown>
    // `id` is the only read-only field, and nothing outside the four
    // writable preferences may be sent.
    expect(Object.keys(payload).sort()).toEqual([
      "email_enabled",
      "in_app_enabled",
      "quiet_hours_end",
      "quiet_hours_start",
    ])
  })

  it("sends null for blank quiet hours", async () => {
    renderPage()
    await screen.findByRole("switch", { name: /email notifications/i })

    fireEvent.click(screen.getByRole("button", { name: /save preferences/i }))

    await waitFor(() => {
      expect(mockedPut).toHaveBeenCalledWith(
        "/notifications/preferences/",
        expect.objectContaining({
          quiet_hours_start: null,
          quiet_hours_end: null,
        })
      )
    })
  })

  it("blocks an equal quiet-hours pair, matching the server validate()", async () => {
    renderPage()
    await screen.findByRole("switch", { name: /email notifications/i })

    fireEvent.change(screen.getByLabelText(/quiet hours start/i), {
      target: { value: "08:00" },
    })
    fireEvent.change(screen.getByLabelText(/quiet hours end/i), {
      target: { value: "08:00" },
    })

    expect(
      await screen.findByText(/Quiet hours start and end must differ/i)
    ).toBeInTheDocument()
    expect(
      screen.getByRole("button", { name: /save preferences/i })
    ).toBeDisabled()
    expect(mockedPut).not.toHaveBeenCalled()
  })

  it("re-enables saving once the pair differs", async () => {
    renderPage()
    await screen.findByRole("switch", { name: /email notifications/i })

    fireEvent.change(screen.getByLabelText(/quiet hours start/i), {
      target: { value: "08:00" },
    })
    fireEvent.change(screen.getByLabelText(/quiet hours end/i), {
      target: { value: "08:00" },
    })
    expect(
      screen.getByRole("button", { name: /save preferences/i })
    ).toBeDisabled()

    fireEvent.change(screen.getByLabelText(/quiet hours end/i), {
      target: { value: "09:00" },
    })
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: /save preferences/i })
      ).toBeEnabled()
    )
  })

  it("confirms a successful save", async () => {
    renderPage()
    await screen.findByRole("switch", { name: /email notifications/i })

    fireEvent.click(screen.getByRole("button", { name: /save preferences/i }))

    expect(
      await screen.findByText(/Notification preferences saved/i)
    ).toBeInTheDocument()
  })

  it("surfaces a server rejection of the quiet-hours pair", async () => {
    mockedPut.mockRejectedValue(
      new Error("quiet_hours_start and quiet_hours_end must differ.")
    )

    renderPage()
    await screen.findByRole("switch", { name: /email notifications/i })

    fireEvent.change(screen.getByLabelText(/quiet hours start/i), {
      target: { value: "22:00" },
    })
    fireEvent.change(screen.getByLabelText(/quiet hours end/i), {
      target: { value: "06:30" },
    })
    fireEvent.click(screen.getByRole("button", { name: /save preferences/i }))

    expect(await screen.findByText(/must differ/i)).toBeInTheDocument()
  })

  it("surfaces a failure to load the preferences", async () => {
    mockedGet.mockImplementation(async (url: string) => {
      if (String(url).startsWith("/notifications/preferences/")) {
        throw new Error("preferences unavailable")
      }
      return { data: user } as never
    })

    renderPage()

    const alerts = await screen.findAllByRole("alert")
    expect(
      alerts.some((a) => a.textContent?.includes("preferences unavailable"))
    ).toBe(true)
  })
})

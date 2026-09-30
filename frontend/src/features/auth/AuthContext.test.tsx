import { act, render, screen, waitFor } from "@testing-library/react"
import { useEffect } from "react"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { AuthProvider, useAuth } from "@/features/auth/AuthContext"
import {
  changePasswordRequest,
  fetchCurrentUser,
  loginRequest,
  logoutRequest,
  restorePersistedTokens,
} from "@/features/auth/api"
import { tokenStorage } from "@/lib/auth-storage"
import type { User } from "@/types/auth"

/* ---------- vi.hoisted: shared between vi.mock factory + test code --- */

const apiState = vi.hoisted(() => {
  const handlers = new Set<() => void>()
  return {
    emitSessionExpired: () => handlers.forEach((h) => h()),
    onSessionExpired: (handler: () => void) => {
      handlers.add(handler)
      return () => handlers.delete(handler)
    },
  }
})

vi.mock("@/lib/api", () => ({
  onSessionExpired: apiState.onSessionExpired,
}))

vi.mock("@/features/auth/api", () => ({
  loginRequest: vi.fn(),
  logoutRequest: vi.fn(),
  fetchCurrentUser: vi.fn(),
  changePasswordRequest: vi.fn(),
  restorePersistedTokens: vi.fn(),
}))

const mockedLogin = vi.mocked(loginRequest)
const mockedLogout = vi.mocked(logoutRequest)
const mockedMe = vi.mocked(fetchCurrentUser)
const mockedChangePassword = vi.mocked(changePasswordRequest)
const mockedRestore = vi.mocked(restorePersistedTokens)

/* ---------- Test fixtures --------------------------------------------- */

const user: User = {
  id: "u-1",
  email: "student@school.edu",
  username: "student1",
  first_name: "Ana",
  last_name: "Cruz",
  role: "student",
  phone_number: null,
  address: null,
  language_preference: null,
  is_active: true,
  created_at: "2025-01-01T00:00:00Z",
  updated_at: "2025-01-01T00:00:00Z",
}

const tokenPair = { access: "access-token", refresh: "refresh-token" }

/**
 * A NormalizedApiError-shaped object — `normalizeApiError()` is idempotent
 * (it short-circuits when `error.name === "ApiClientError"`), so passing a
 * pre-built object avoids needing a real AxiosError in the test context.
 */
function makeNormalizedError(
  overrides: Partial<{
    code: string
    message: string
    isPasswordChangeRequired: boolean
  }> = {}
) {
  return {
    name: "ApiClientError" as const,
    code: overrides.code ?? "ERROR",
    message: overrides.message ?? "An error occurred.",
    isNetworkError: false,
    isCancelled: false,
    isPasswordChangeRequired: overrides.isPasswordChangeRequired ?? false,
  }
}

/* ---------- Tiny probe / harness components --------------------------- */

function Probe() {
  const { status, user: currentUser, mustChangePassword } = useAuth()
  return (
    <div>
      <span data-testid="status">{status}</span>
      <span data-testid="must-change">{String(mustChangePassword)}</span>
      <span data-testid="user-email">{currentUser?.email ?? ""}</span>
    </div>
  )
}

/** Exposes the AuthContext action methods to the test via a module-level ref. */
let harnessRef: ReturnType<typeof useAuth> | null = null
function Harness() {
  const auth = useAuth()
  useEffect(() => {
    harnessRef = auth
  }, [auth])
  return <Probe />
}

function renderAuth(children?: React.ReactNode) {
  return render(<AuthProvider>{children ?? <Harness />}</AuthProvider>)
}

function unmountAll() {
  document.body.innerHTML = ""
}

beforeEach(() => {
  vi.clearAllMocks()
  localStorage.clear()
  unmountAll()
  harnessRef = null
})

/* =====================================================================
   1. valid login response
   ===================================================================== */
describe("valid login", () => {
  it("transitions from unauthenticated → authenticated and persists tokens", async () => {
    mockedRestore.mockReturnValue(null)
    mockedLogin.mockResolvedValue({
      ...tokenPair,
      must_change_password: false,
    })
    mockedMe.mockResolvedValue(user)

    renderAuth()

    await waitFor(() => {
      expect(screen.getByTestId("status")).toHaveTextContent("unauthenticated")
    })

    const harness = harnessRef as {
      login: (e: string, p: string) => Promise<void>
    }

    await act(async () => {
      await harness.login("student@school.edu", "secret")
    })

    expect(screen.getByTestId("status")).toHaveTextContent("authenticated")
    expect(screen.getByTestId("must-change")).toHaveTextContent("false")
    expect(screen.getByTestId("user-email")).toHaveTextContent(user.email)
    expect(tokenStorage.getAccessToken()).toBe(tokenPair.access)
    expect(tokenStorage.getRefreshToken()).toBe(tokenPair.refresh)
  })

  it("returns to unauthenticated without tokens when /me fails after login", async () => {
    mockedRestore.mockReturnValue(null)
    mockedLogin.mockResolvedValue({
      ...tokenPair,
      must_change_password: false,
    })
    mockedMe.mockRejectedValue(
      makeNormalizedError({
        code: "AUTHENTICATION_REQUIRED",
        message: "Token has expired.",
      })
    )

    renderAuth()

    await waitFor(() => {
      expect(screen.getByTestId("status")).toHaveTextContent("unauthenticated")
    })

    const harness = harnessRef as {
      login: (e: string, p: string) => Promise<void>
    }

    await act(async () => {
      await harness.login("student@school.edu", "secret")
    })

    expect(screen.getByTestId("status")).toHaveTextContent("unauthenticated")
    expect(screen.getByTestId("user-email")).toHaveTextContent("")
    expect(tokenStorage.getAccessToken()).toBeNull()
    expect(tokenStorage.getRefreshToken()).toBeNull()
  })
})

/* =====================================================================
   2. invalid credentials
   ===================================================================== */
describe("invalid credentials", () => {
  it("stays unauthenticated and does not persist tokens", async () => {
    mockedRestore.mockReturnValue(null)
    mockedLogin.mockRejectedValue(
      makeNormalizedError({
        code: "AUTHENTICATION_REQUIRED",
        message: "Incorrect email or password.",
      })
    )

    renderAuth()

    await waitFor(() => {
      expect(screen.getByTestId("status")).toHaveTextContent("unauthenticated")
    })

    const harness = harnessRef as {
      login: (e: string, p: string) => Promise<void>
    }

    await act(async () => {
      await expect(
        harness.login("student@school.edu", "wrong")
      ).rejects.toThrow()
    })

    expect(screen.getByTestId("status")).toHaveTextContent("unauthenticated")
    expect(tokenStorage.getAccessToken()).toBeNull()
  })
})

/* =====================================================================
   3. refresh success (session restore with valid tokens)
   ===================================================================== */
describe("refresh success", () => {
  it("restores an authenticated session from persisted tokens", async () => {
    tokenStorage.setTokens(tokenPair.access, tokenPair.refresh)
    mockedRestore.mockReturnValue(tokenPair)
    mockedMe.mockResolvedValue(user)

    renderAuth()

    await waitFor(() => {
      expect(screen.getByTestId("status")).toHaveTextContent("authenticated")
    })
    expect(screen.getByTestId("user-email")).toHaveTextContent(user.email)
  })
})

/* =====================================================================
   4. refresh failure (session restore with stale tokens)
   ===================================================================== */
describe("refresh failure", () => {
  it("clears persisted tokens and returns to unauthenticated", async () => {
    tokenStorage.setTokens(tokenPair.access, tokenPair.refresh)
    mockedRestore.mockReturnValue(tokenPair)
    mockedMe.mockRejectedValue(
      makeNormalizedError({
        code: "AUTHENTICATION_REQUIRED",
        message: "Token has expired.",
      })
    )

    renderAuth()

    await waitFor(() => {
      expect(screen.getByTestId("status")).toHaveTextContent("unauthenticated")
    })
    expect(screen.getByTestId("user-email")).toHaveTextContent("")
  })
})

/* =====================================================================
   5. password-change-required response
   ===================================================================== */
describe("password-change-required", () => {
  it("enters restricted state when login returns must_change_password", async () => {
    mockedRestore.mockReturnValue(null)
    mockedLogin.mockResolvedValue({
      ...tokenPair,
      must_change_password: true,
    })

    renderAuth()

    await waitFor(() => {
      expect(screen.getByTestId("status")).toHaveTextContent("unauthenticated")
    })

    const harness = harnessRef as {
      login: (e: string, p: string) => Promise<void>
    }

    await act(async () => {
      await harness.login("student@school.edu", "secret")
    })

    expect(screen.getByTestId("status")).toHaveTextContent("restricted")
    expect(screen.getByTestId("must-change")).toHaveTextContent("true")
    expect(tokenStorage.getAccessToken()).toBe(tokenPair.access)
  })

  it("enters restricted state when /me rejects with password-change-required", async () => {
    tokenStorage.setTokens(tokenPair.access, tokenPair.refresh)
    mockedRestore.mockReturnValue(tokenPair)
    mockedMe.mockRejectedValue(
      makeNormalizedError({
        code: "AUTHENTICATION_REQUIRED",
        message: "Password change required.",
        isPasswordChangeRequired: true,
      })
    )

    renderAuth()

    await waitFor(() => {
      expect(screen.getByTestId("status")).toHaveTextContent("restricted")
    })
    expect(screen.getByTestId("must-change")).toHaveTextContent("true")
  })
})

/* =====================================================================
   /me outcomes after a successful login (password-change-required)
   ===================================================================== */
describe("login then /me password-change-required", () => {
  it("enters restricted when /me rejects with password-change-required after a normal login", async () => {
    mockedRestore.mockReturnValue(null)
    mockedLogin.mockResolvedValue({
      ...tokenPair,
      must_change_password: false,
    })
    mockedMe.mockRejectedValue(
      makeNormalizedError({
        code: "AUTHENTICATION_REQUIRED",
        message: "Password change required.",
        isPasswordChangeRequired: true,
      })
    )

    renderAuth()

    await waitFor(() => {
      expect(screen.getByTestId("status")).toHaveTextContent("unauthenticated")
    })

    const harness = harnessRef as {
      login: (e: string, p: string) => Promise<void>
    }

    await act(async () => {
      await harness.login("student@school.edu", "secret")
    })

    expect(screen.getByTestId("status")).toHaveTextContent("restricted")
    expect(screen.getByTestId("must-change")).toHaveTextContent("true")
    expect(tokenStorage.getAccessToken()).toBe(tokenPair.access)
  })
})

/* =====================================================================
   6. logout
   ===================================================================== */
describe("logout", () => {
  it("clears local auth state even if the server request fails", async () => {
    tokenStorage.setTokens(tokenPair.access, tokenPair.refresh)
    mockedRestore.mockReturnValue(tokenPair)
    mockedMe.mockResolvedValue(user)

    renderAuth()

    await waitFor(() => {
      expect(screen.getByTestId("status")).toHaveTextContent("authenticated")
    })

    mockedLogout.mockRejectedValue(new Error("server unavailable"))

    const harness = harnessRef as {
      logout: () => Promise<void>
    }

    await act(async () => {
      await harness.logout()
    })

    expect(screen.getByTestId("status")).toHaveTextContent("unauthenticated")
    expect(tokenStorage.getAccessToken()).toBeNull()
    expect(tokenStorage.getRefreshToken()).toBeNull()
  })
})

/* =====================================================================
   7. auth state transitions (session expiration)
   ===================================================================== */
describe("session expiration", () => {
  it("returns to unauthenticated when a session-expired event fires", async () => {
    tokenStorage.setTokens(tokenPair.access, tokenPair.refresh)
    mockedRestore.mockReturnValue(tokenPair)
    mockedMe.mockResolvedValue(user)

    renderAuth()

    await waitFor(() => {
      expect(screen.getByTestId("status")).toHaveTextContent("authenticated")
    })

    await act(async () => {
      apiState.emitSessionExpired()
    })

    expect(screen.getByTestId("status")).toHaveTextContent("unauthenticated")
    expect(screen.getByTestId("user-email")).toHaveTextContent("")
  })

  it("clears restricted state and becomes authenticated after a successful password change", async () => {
    tokenStorage.setTokens(tokenPair.access, tokenPair.refresh)
    mockedRestore.mockReturnValue(tokenPair)
    mockedMe.mockRejectedValue(
      makeNormalizedError({
        code: "AUTHENTICATION_REQUIRED",
        message: "Password change required.",
        isPasswordChangeRequired: true,
      })
    )

    renderAuth()

    await waitFor(() => {
      expect(screen.getByTestId("status")).toHaveTextContent("restricted")
    })

    mockedChangePassword.mockResolvedValue()
    mockedMe.mockResolvedValue(user)

    const harness = harnessRef as {
      changePassword: (c: string, n: string) => Promise<void>
    }

    await act(async () => {
      await harness.changePassword("old-pw", "new-pw-ok")
    })

    expect(mockedChangePassword).toHaveBeenCalledWith({
      current_password: "old-pw",
      new_password: "new-pw-ok",
    })
    await waitFor(() => {
      expect(screen.getByTestId("status")).toHaveTextContent("authenticated")
    })
    expect(screen.getByTestId("must-change")).toHaveTextContent("false")
    expect(screen.getByTestId("user-email")).toHaveTextContent(user.email)
  })

  it("clears tokens and returns to unauthenticated when /me fails after password change", async () => {
    tokenStorage.setTokens(tokenPair.access, tokenPair.refresh)
    mockedRestore.mockReturnValue(tokenPair)
    mockedMe.mockRejectedValue(
      makeNormalizedError({
        code: "AUTHENTICATION_REQUIRED",
        message: "Password change required.",
        isPasswordChangeRequired: true,
      })
    )

    renderAuth()

    await waitFor(() => {
      expect(screen.getByTestId("status")).toHaveTextContent("restricted")
    })

    mockedChangePassword.mockResolvedValue()
    mockedMe.mockRejectedValue(
      makeNormalizedError({
        code: "AUTHENTICATION_REQUIRED",
        message: "Token has expired.",
      })
    )

    const harness = harnessRef as {
      changePassword: (c: string, n: string) => Promise<void>
    }

    await act(async () => {
      await harness.changePassword("old-pw", "new-pw-ok")
    })

    expect(screen.getByTestId("status")).toHaveTextContent("unauthenticated")
    expect(tokenStorage.getAccessToken()).toBeNull()
    expect(tokenStorage.getRefreshToken()).toBeNull()
  })

  it("stays restricted when /me still reports password-change-required after password change", async () => {
    tokenStorage.setTokens(tokenPair.access, tokenPair.refresh)
    mockedRestore.mockReturnValue(tokenPair)
    mockedMe.mockRejectedValue(
      makeNormalizedError({
        code: "AUTHENTICATION_REQUIRED",
        message: "Password change required.",
        isPasswordChangeRequired: true,
      })
    )

    renderAuth()

    await waitFor(() => {
      expect(screen.getByTestId("status")).toHaveTextContent("restricted")
    })

    mockedChangePassword.mockResolvedValue()

    const harness = harnessRef as {
      changePassword: (c: string, n: string) => Promise<void>
    }

    await act(async () => {
      await harness.changePassword("old-pw", "new-pw-ok")
    })

    expect(screen.getByTestId("status")).toHaveTextContent("restricted")
    expect(screen.getByTestId("must-change")).toHaveTextContent("true")
    expect(tokenStorage.getAccessToken()).toBe(tokenPair.access)
  })
})

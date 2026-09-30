import { apiClient } from "@/lib/api"
import { tokenStorage } from "@/lib/auth-storage"
import { normalizeApiError } from "@/lib/error"
import type {
  AuthTokens,
  LoginResponse,
  LogoutPayload,
  PasswordChangePayload,
  User,
} from "@/types/auth"

/**
 * Thin, typed wrappers around the frozen auth endpoints.
 * Only the confirmed contract is used — nothing is invented.
 */

/** POST /api/v1/auth/login/ -> { access, refresh, must_change_password } */
export async function loginRequest(
  email: string,
  password: string
): Promise<LoginResponse> {
  try {
    const { data } = await apiClient.post<LoginResponse>("/auth/login/", {
      email,
      password,
    })
    return data
  } catch (error) {
    throw normalizeApiError(error)
  }
}

/** POST /api/v1/auth/logout/ — revokes the given refresh token. */
export async function logoutRequest(refreshToken: string): Promise<void> {
  try {
    const payload: LogoutPayload = { refresh: refreshToken }
    await apiClient.post("/auth/logout/", payload)
  } catch {
    // Logout is best-effort: token state is cleared client-side regardless.
  }
}

/** POST /api/v1/auth/token/refresh/ — rotates the pair (PH10). */
export async function refreshRequest(
  refreshToken: string
): Promise<AuthTokens> {
  try {
    const { data } = await apiClient.post<AuthTokens>("/auth/token/refresh/", {
      refresh: refreshToken,
    })
    return data
  } catch (error) {
    throw normalizeApiError(error)
  }
}

/** GET /api/v1/accounts/me/ */
export async function fetchCurrentUser(): Promise<User> {
  try {
    const { data } = await apiClient.get<User>("/accounts/me/")
    return data
  } catch (error) {
    throw normalizeApiError(error)
  }
}

/** POST /api/v1/accounts/password/change/ */
export async function changePasswordRequest(
  payload: PasswordChangePayload
): Promise<void> {
  try {
    await apiClient.post("/accounts/password/change/", payload)
  } catch (error) {
    throw normalizeApiError(error)
  }
}

/** Restores persisted tokens into storage (used by the provider bootstrap). */
export function restorePersistedTokens(): AuthTokens | null {
  const access = tokenStorage.getAccessToken()
  const refresh = tokenStorage.getRefreshToken()
  if (!access || !refresh) return null
  return { access, refresh }
}

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
  password: string,
  rememberMe = false
): Promise<LoginResponse> {
  try {
    const { data } = await apiClient.post<LoginResponse>("/auth/login/", {
      email,
      password,
      // Session length only: ticked keeps the session for a day, unticked
      // leaves it idle-bounded at 15 minutes. It grants no permission.
      remember_me: rememberMe,
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

/**
 * POST /api/v1/accounts/password/forgot/ - asks for a reset link.
 *
 * The answer is the same whether or not the address belongs to an account,
 * so this call cannot be used to find out who has one.
 */
export async function forgotPasswordRequest(email: string): Promise<void> {
  try {
    await apiClient.post("/accounts/password/forgot/", { email })
  } catch (error) {
    throw normalizeApiError(error)
  }
}

/** POST /api/v1/accounts/password/reset/ - redeems a reset link. */
export async function resetPasswordRequest(payload: {
  token: string
  new_password: string
  confirm_password: string
}): Promise<void> {
  try {
    await apiClient.post("/accounts/password/reset/", payload)
  } catch (error) {
    throw normalizeApiError(error)
  }
}

/**
 * POST /api/v1/accounts/registrations/ - ask for a student account.
 *
 * The answer is the same whether or not the address is known, so this call
 * cannot be used to find out who has an account. A request is not an
 * account: an administrator approves it.
 */
export async function submitRegistrationRequest(payload: {
  full_name: string
  email: string
  student_code: string
  password: string
  confirm_password: string
}): Promise<void> {
  try {
    await apiClient.post("/accounts/registrations/", payload)
  } catch (error) {
    throw normalizeApiError(error)
  }
}

/**
 * GET /api/v1/accounts/registrations/verify/?token=...
 *
 * Confirms the applicant owns the address. After this the request waits for
 * an administrator.
 */
export async function verifyRegistrationRequest(token: string): Promise<void> {
  try {
    await apiClient.get("/accounts/registrations/verify/", {
      params: { token },
    })
  } catch (error) {
    throw normalizeApiError(error)
  }
}

/**
 * POST /api/v1/accounts/parent-invitations/ - nominate a parent.
 *
 * A nomination is a request. An administrator approves it and issues the
 * invitation; only then does the parent get a link.
 */
export async function submitParentInvitationRequest(payload: {
  full_name: string
  email: string
  relationship: string
}): Promise<void> {
  try {
    await apiClient.post("/accounts/parent-invitations/", payload)
  } catch (error) {
    throw normalizeApiError(error)
  }
}

/**
 * POST /api/v1/accounts/parent-invitations/accept/ - redeem an invitation.
 *
 * Accepting creates the parent account and the link to the child.
 */
export async function acceptParentInvitationRequest(payload: {
  token: string
  password: string
  confirm_password: string
}): Promise<void> {
  try {
    await apiClient.post("/accounts/parent-invitations/accept/", payload)
  } catch (error) {
    throw normalizeApiError(error)
  }
}

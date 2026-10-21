/**
 * Authentication / account models mirrored from the frozen backend
 * (apps/accounts/models.py + serializers.py).
 *
 * Fields deliberately match the backend exactly — no invented fields.
 */

/** The five AEGIS roles. */
export const ROLES = [
  "student",
  "parent",
  "faculty",
  "guidance",
  "admin",
] as const

export type Role = (typeof ROLES)[number]

/** /api/v1/accounts/me/ — UserProfileSerializer fields. */
export interface User {
  id: string
  email: string
  username: string
  first_name: string
  last_name: string
  role: Role
  phone_number: string | null
  address: string | null
  language_preference: string | null
  is_active: boolean
  created_at: string
  updated_at: string
}

/** JWT pair issued by SimpleJWT. */
export interface AuthTokens {
  access: string
  refresh: string
}

/** POST /api/v1/auth/login/ — standard pair + PH8.7 onboarding flag. */
export interface LoginResponse extends AuthTokens {
  must_change_password: boolean
  /**
   * The session length the server granted: true when the sign-in asked to be
   * remembered (refresh token for a day), false for an idle session (15
   * minutes).
   */
  remember_me: boolean
}

/** POST /api/v1/auth/token/refresh/ — rotates the refresh token (PH10). */
export type TokenRefreshResponse = AuthTokens

/** POST /api/v1/accounts/password/change/ request body. */
export interface PasswordChangePayload {
  current_password: string
  new_password: string
}

/** POST /api/v1/auth/logout/ request body. */
export interface LogoutPayload {
  refresh: string
}

/** POST /api/v1/accounts/password/forgot/ request body. */
export interface PasswordForgotPayload {
  email: string
}

/** POST /api/v1/accounts/password/reset/ request body. */
export interface PasswordResetPayload {
  token: string
  new_password: string
  confirm_password: string
}

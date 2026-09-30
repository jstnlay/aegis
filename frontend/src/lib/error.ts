import { AxiosError } from "axios"
import type { ApiErrorEnvelope } from "@/types/api"

/**
 * Error normalization for the frozen backend error envelope.
 *
 * The backend (core/exceptions.py) always fails with:
 *   { "success": false, "error": { "code", "message", "details" } }
 *
 * We preserve code/message/details instead of collapsing everything into
 * "Something went wrong" — future UI can surface them (form field maps,
 * toasts, retry affordances). See docs/BACKEND_SPECIFICATION.md.
 */

export interface NormalizedApiError {
  readonly name: "ApiClientError"
  readonly message: string
  readonly code: string
  readonly status?: number
  readonly details?: unknown
  readonly isNetworkError: boolean
  readonly isCancelled: boolean
  /**
   * The PH8.7 onboarding gate: authenticated, but the account still has
   * `must_change_password = true` and every endpoint except password
   * change / logout returns 401 "Password change required.".
   */
  readonly isPasswordChangeRequired: boolean
}

const PASSWORD_CHANGE_REQUIRED_MESSAGE = "Password change required."

function envelopeOf(payload: unknown): ApiErrorEnvelope | null {
  if (typeof payload !== "object" || payload === null) return null
  const body = payload as { success?: unknown; error?: unknown }
  if (
    body.success !== false ||
    typeof body.error !== "object" ||
    body.error === null
  ) {
    return null
  }
  const err = body.error as {
    code?: unknown
    message?: unknown
    details?: unknown
  }
  return {
    success: false,
    error: {
      code: typeof err.code === "string" ? err.code : "ERROR",
      message:
        typeof err.message === "string" ? err.message : "An error occurred.",
      details: err.details,
    },
  }
}

export function normalizeApiError(error: unknown): NormalizedApiError {
  if (
    error &&
    typeof error === "object" &&
    (error as NormalizedApiError).name === "ApiClientError"
  ) {
    return error as NormalizedApiError
  }

  if (error instanceof AxiosError) {
    const envelope = envelopeOf(error.response?.data)
    const status = error.response?.status
    const cancelled = error.code === AxiosError.ERR_CANCELED
    const network = !error.response

    const code =
      envelope?.error.code ??
      (cancelled
        ? "REQUEST_CANCELLED"
        : network
          ? "NETWORK_ERROR"
          : `HTTP_${status ?? "ERROR"}`)
    const message =
      envelope?.error.message ??
      (cancelled
        ? "Request cancelled."
        : network
          ? "Unable to reach the server."
          : `Request failed with status ${status ?? "unknown"}.`)

    return {
      name: "ApiClientError",
      code,
      message,
      status,
      details: envelope?.error.details,
      isNetworkError: network,
      isCancelled: cancelled,
      isPasswordChangeRequired:
        status === 401 && message === PASSWORD_CHANGE_REQUIRED_MESSAGE,
    }
  }

  if (error instanceof Error) {
    return {
      name: "ApiClientError",
      code: "UNKNOWN_ERROR",
      message: error.message || "An unexpected error occurred.",
      isNetworkError: false,
      isCancelled: false,
      isPasswordChangeRequired: false,
    }
  }

  return {
    name: "ApiClientError",
    code: "UNKNOWN_ERROR",
    message: "An unexpected error occurred.",
    isNetworkError: false,
    isCancelled: false,
    isPasswordChangeRequired: false,
  }
}

/** True when the failure is an HTTP error with the given status. */
export function isHttpError(error: unknown, status: number): boolean {
  return normalizeApiError(error).status === status
}

/**
 * Structured field errors from a 400 VALIDATION_ERROR envelope
 * (`details` is the DRF serializer error dict), for inline form display.
 */
export function getFieldErrors(
  error: unknown
): Record<string, string[]> | null {
  const normalized = normalizeApiError(error)
  if (typeof normalized.details !== "object" || normalized.details === null)
    return null
  const details = normalized.details as Record<string, unknown>
  const out: Record<string, string[]> = {}
  let found = false
  for (const [key, value] of Object.entries(details)) {
    if (Array.isArray(value) && value.every((v) => typeof v === "string")) {
      out[key] = value as string[]
      found = true
    }
  }
  return found ? out : null
}

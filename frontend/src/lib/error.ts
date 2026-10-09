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

/**
 * Messages that carry no information for a reader. The backend no longer emits
 * these for a body it can describe, but a 4xx can still arrive from a proxy or
 * an older deployment, and a silent fallback would show the user nothing
 * actionable. When one of these is seen we look in `details` before giving up.
 */
const GENERIC_MESSAGES = new Set([
  "an error occurred.",
  "error",
  "bad request",
  "the request could not be processed.",
])

/** DRF field names that are labels rather than something a reader can act on. */
const OPAQUE_FIELD_NAMES = new Set([
  "detail",
  "non_field_errors",
  "__all__",
  "root",
])

const MAX_SUMMARIZED_FIELDS = 3

/**
 * Collapses a detail node to a string.
 *
 * The frozen envelope declares `message` as a string, but a hand-rolled or
 * proxied error body may put an array there, so both are accepted rather than
 * discarding the text.
 */
function coerceMessage(value: unknown): string | null {
  if (typeof value === "string") return value
  if (Array.isArray(value)) {
    const parts = value.filter(
      (item): item is string => typeof item === "string"
    )
    const joined = parts.join(" ").trim()
    return joined || null
  }
  return null
}

/**
 * Builds a one-line summary from a serializer's field-keyed error map, so a
 * field error is legible even when it is not attached to a form input. Mirrors
 * the backend's `_summarize_field_errors` so both sides name a field the same
 * way.
 */
function summarizeFieldErrors(details: Record<string, unknown>): string | null {
  const named: string[] = []
  const opaque: string[] = []
  let overflow = 0

  for (const [field, value] of Object.entries(details)) {
    const message = coerceMessage(value)
    if (!message) continue
    if (OPAQUE_FIELD_NAMES.has(field)) {
      opaque.push(message)
    } else if (named.length < MAX_SUMMARIZED_FIELDS) {
      named.push(`${field}: ${message}`)
    } else {
      overflow += 1
    }
  }

  const fragments = [...named, ...opaque]
  if (fragments.length === 0) return null
  if (overflow > 0) fragments.push(`(+${overflow} more)`)
  return fragments.join("; ")
}

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

  const details =
    typeof err.details === "object" && err.details !== null
      ? (err.details as Record<string, unknown>)
      : null

  let message = coerceMessage(err.message)
  if (message === null || GENERIC_MESSAGES.has(message.toLowerCase())) {
    // Prefer the real text over a placeholder the backend could not improve.
    message = (details && summarizeFieldErrors(details)) ?? message
  }

  return {
    success: false,
    error: {
      code: typeof err.code === "string" ? err.code : "ERROR",
      message: message ?? "An error occurred.",
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
 * Reads a blob error body back into JSON before normalization.
 *
 * File downloads ask for `responseType: "blob"`, so a failed export arrives
 * as bytes rather than an object. Without this, normalizeApiError would
 * report "Request failed with status 400." for a body that names the real
 * cause (e.g. EXPORT_EMPTY's "No data is available for this export.").
 *
 * Mutates `error.response.data` in place when the body parses as the
 * backend envelope; leaves everything untouched otherwise.
 */
export async function hydrateBlobError(error: AxiosError): Promise<void> {
  const data = error.response?.data
  if (!(data instanceof Blob)) return

  let text: string
  try {
    text = await data.text()
  } catch {
    return
  }

  try {
    const parsed: unknown = JSON.parse(text)
    if (envelopeOf(parsed) && error.response) {
      error.response.data = parsed
    }
  } catch {
    // Not JSON (an HTML error page from a proxy, etc.): keep the blob.
  }
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
    } else if (typeof value === "string") {
      out[key] = [value]
      found = true
    }
  }
  return found ? out : null
}

/**
 * The first message for one form field, for attaching to an input.
 *
 * Returns `null` when the failure was not attributed to that field, so a
 * caller must treat `null` as "no field error" rather than as valid input.
 */
export function getFieldError(error: unknown, field: string): string | null {
  return getFieldErrors(error)?.[field]?.[0] ?? null
}

/**
 * Shared API contracts mirrored from the frozen backend
 * (docs/BACKEND_SPECIFICATION.md v2.1 + actual backend source).
 *
 * Error envelope — emitted by core/exceptions.py `custom_exception_handler`:
 *   { "success": false, "error": { "code", "message", "details" } }
 *
 * Success responses are NOT wrapped; DRF pagination is PageNumberPagination:
 *   { "count", "next", "previous", "results" }
 */

/** Backend error envelope (only present on non-2xx responses). */
export interface ApiErrorEnvelope {
  success: false
  error: {
    code: string
    message: string
    details?: unknown
  }
}

type EnvelopeCode =
  | "VALIDATION_ERROR"
  | "AUTHENTICATION_REQUIRED"
  | "PERMISSION_DENIED"
  | "NOT_FOUND"
  | "METHOD_NOT_ALLOWED"
  | "CONFLICT"
  | "FILE_TOO_LARGE"
  | "RATE_LIMIT_EXCEEDED"
  | "INTERNAL_SERVER_ERROR"
  | "ERROR"

/** A code returned by the backend envelope. */
export type ApiErrorCode = EnvelopeCode | (string & {})

/** DRF PageNumberPagination response envelope. */
export interface Page<T> {
  count: number
  next: string | null
  previous: string | null
  results: T[]
}

/** Request shape used by the backend paginator. */
export interface PageQuery {
  page?: number
  page_size?: number
}

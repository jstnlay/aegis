import { AxiosError, AxiosHeaders } from "axios"
import { describe, expect, it } from "vitest"

import { getFieldErrors, isHttpError, normalizeApiError } from "@/lib/error"
import type { ApiErrorEnvelope } from "@/types/api"

function envelopeBody(
  code: string,
  message: string,
  details?: unknown
): ApiErrorEnvelope {
  return {
    success: false,
    error: { code, message, details },
  }
}

function axiosError(status: number, data: unknown): AxiosError {
  return new AxiosError(
    "Request failed with status code " + status,
    undefined,
    {
      headers: new AxiosHeaders(),
    },
    undefined,
    {
      data,
      status,
      statusText: "",
      headers: new AxiosHeaders(),
      config: { headers: new AxiosHeaders() },
    }
  )
}

describe("normalizeApiError", () => {
  it("preserves code and message for a 401 invalid-credentials response", () => {
    const error = axiosError(
      401,
      envelopeBody("AUTHENTICATION_REQUIRED", "Incorrect email or password.")
    )

    const normalized = normalizeApiError(error)

    expect(normalized.name).toBe("ApiClientError")
    expect(normalized.code).toBe("AUTHENTICATION_REQUIRED")
    expect(normalized.message).toBe("Incorrect email or password.")
    expect(normalized.status).toBe(401)
    expect(normalized.isNetworkError).toBe(false)
    expect(normalized.isCancelled).toBe(false)
    expect(normalized.isPasswordChangeRequired).toBe(false)
  })

  it("flags the password-change-required onboarding 401", () => {
    const error = axiosError(
      401,
      envelopeBody("AUTHENTICATION_REQUIRED", "Password change required.")
    )

    const normalized = normalizeApiError(error)

    expect(normalized.isPasswordChangeRequired).toBe(true)
    expect(normalized.status).toBe(401)
  })

  it("detects network failures (no response)", () => {
    const error = new AxiosError("Network Error", "NETWORK_ERROR")

    const normalized = normalizeApiError(error)

    expect(normalized.isNetworkError).toBe(true)
    expect(normalized.code).toBe("NETWORK_ERROR")
    expect(normalized.message).toBe("Unable to reach the server.")
  })

  it("normalizes a 400 validation error with field details", () => {
    const error = axiosError(
      400,
      envelopeBody("VALIDATION_ERROR", "Invalid input.", {
        email: ["This field must be unique."],
        password: ["This password is too short."],
      })
    )

    const normalized = normalizeApiError(error)

    expect(normalized.code).toBe("VALIDATION_ERROR")
    expect(normalized.isPasswordChangeRequired).toBe(false)
    expect(getFieldErrors(error)?.["email"]?.[0]).toBeDefined()
  })

  it("is idempotent for already-normalized errors", () => {
    const first = normalizeApiError(
      axiosError(
        401,
        envelopeBody("AUTHENTICATION_REQUIRED", "Password change required.")
      )
    )

    const second = normalizeApiError(first)

    expect(second).toBe(first)
    expect(second.isPasswordChangeRequired).toBe(true)
  })

  it("isHttpError matches on status", () => {
    const error = axiosError(
      401,
      envelopeBody("AUTHENTICATION_REQUIRED", "Bad credentials.")
    )

    expect(isHttpError(error, 401)).toBe(true)
    expect(isHttpError(error, 400)).toBe(false)
  })
})

describe("getFieldErrors", () => {
  it("extracts DRF field errors from a validation envelope", () => {
    const error = axiosError(
      400,
      envelopeBody("VALIDATION_ERROR", "Validation failed.", {
        current_password: ["Incorrect password."],
        new_password: ["This password is too common."],
      })
    )

    const fields = getFieldErrors(error)

    expect(fields).not.toBeNull()
    expect(fields?.["current_password"]).toContain("Incorrect password.")
    expect(fields?.["new_password"]?.[0]).toContain("too common")
  })

  it("returns null when details are not a field map", () => {
    const error = axiosError(
      400,
      envelopeBody("VALIDATION_ERROR", "Bad payload.", "not-an-object")
    )

    expect(getFieldErrors(error)).toBeNull()
  })
})

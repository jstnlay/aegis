import { AxiosError, AxiosHeaders } from "axios"
import { describe, expect, it } from "vitest"

import {
  getFieldError,
  getFieldErrors,
  hydrateBlobError,
  isHttpError,
  normalizeApiError,
} from "@/lib/error"
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

describe("hydrateBlobError", () => {
  it("reads the envelope back out of a blob error body", async () => {
    // A failed export request asks for bytes, so the JSON envelope arrives
    // as a Blob: without hydration the real cause is lost.
    const error = axiosError(
      400,
      new Blob(
        [
          JSON.stringify(
            envelopeBody(
              "EXPORT_EMPTY",
              "No data is available for this export."
            )
          ),
        ],
        { type: "application/json" }
      )
    )

    await hydrateBlobError(error)

    const normalized = normalizeApiError(error)
    expect(normalized.code).toBe("EXPORT_EMPTY")
    expect(normalized.message).toBe("No data is available for this export.")
    expect(normalized.status).toBe(400)
  })

  it("leaves a non-JSON blob untouched and still reports the status", async () => {
    const blob = new Blob(["<html>bad gateway</html>"], {
      type: "text/html",
    })
    const error = axiosError(502, blob)

    await hydrateBlobError(error)

    expect(error.response?.data).toBe(blob)
    const normalized = normalizeApiError(error)
    expect(normalized.message).toContain("502")
  })

  it("does nothing for a non-blob body or a missing response", async () => {
    const plain = axiosError(400, envelopeBody("ERROR", "Nope."))
    await hydrateBlobError(plain)
    expect(plain.response?.data).toMatchObject({ success: false })

    const network = new AxiosError("Network Error", "NETWORK_ERROR")
    await expect(hydrateBlobError(network)).resolves.toBeUndefined()
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

/**
 * The backend derives `error.message` from every DRF response shape, so a
 * meaningful message reaches the UI. These cases pin the client-side half of
 * that contract: the same text must survive normalization, and a body that
 * still carries only a placeholder must not blank out the user's error.
 */
describe("action and field error messages", () => {
  it("shows an action error that DRF wrapped in a list", () => {
    // DRF leaves a list `exc.detail` un-wrapped, so the text lands in
    // details.detail as an array. The backend now flattens it, and the
    // client must not lose it if it ever sees the raw shape again.
    const error = axiosError(
      400,
      envelopeBody("VALIDATION_ERROR", "An error occurred.", {
        detail: ["Assessment is already published."],
      })
    )

    expect(normalizeApiError(error).message).toBe(
      "Assessment is already published."
    )
  })

  it("names the field and reason when only a placeholder message arrives", () => {
    const error = axiosError(
      400,
      envelopeBody("VALIDATION_ERROR", "An error occurred.", {
        student: ["This field is required."],
        score: ["Must be between 0 and 100."],
      })
    )

    const message = normalizeApiError(error).message

    expect(message).toContain("student")
    expect(message).toContain("This field is required.")
    expect(message).toContain("score")
  })

  it("does not echo an opaque DRF key back as a field name", () => {
    const error = axiosError(
      400,
      envelopeBody("VALIDATION_ERROR", "An error occurred.", {
        non_field_errors: ["Ordering is inconsistent."],
      })
    )

    const message = normalizeApiError(error).message

    expect(message).toBe("Ordering is inconsistent.")
    expect(message).not.toContain("non_field_errors")
  })

  it("keeps a placeholder only when details hold nothing nameable", () => {
    const error = axiosError(
      400,
      envelopeBody("VALIDATION_ERROR", "An error occurred.", {})
    )

    expect(normalizeApiError(error).message).toBe("An error occurred.")
  })

  it("joins an array message instead of discarding it", () => {
    const body = {
      success: false,
      error: {
        code: "VALIDATION_ERROR",
        message: ["First problem.", "Second problem."],
      },
    }
    const error = axiosError(400, body)

    expect(normalizeApiError(error).message).toBe(
      "First problem. Second problem."
    )
  })

  it("still reports a permission denial rather than a placeholder", () => {
    const error = axiosError(
      403,
      envelopeBody(
        "PERMISSION_DENIED",
        "You do not have permission to perform this action."
      )
    )

    const normalized = normalizeApiError(error)

    expect(normalized.status).toBe(403)
    expect(normalized.message).toContain("permission")
  })

  it("never leaves the message empty for a bodiless 4xx", () => {
    const error = axiosError(400, "")

    expect(normalizeApiError(error).message).not.toBe("")
  })
})

describe("getFieldError", () => {
  it("returns the first message for one field", () => {
    const error = axiosError(
      400,
      envelopeBody("VALIDATION_ERROR", "Invalid input.", {
        subject_assignment: [
          "This field is required.",
          "And a second problem.",
        ],
      })
    )

    expect(getFieldError(error, "subject_assignment")).toBe(
      "This field is required."
    )
  })

  it("returns null when the failure was not attributed to that field", () => {
    const error = axiosError(
      400,
      envelopeBody("VALIDATION_ERROR", "Invalid input.", {
        subject_assignment: ["This field is required."],
      })
    )

    expect(getFieldError(error, "student")).toBeNull()
    expect(getFieldError(new Error("boom"), "student")).toBeNull()
  })

  it("handles a non-field action error without inventing a field", () => {
    const error = axiosError(
      400,
      envelopeBody("VALIDATION_ERROR", "Invalid input.", {
        detail: ["Assessment is already published."],
      })
    )

    expect(getFieldError(error, "detail")).toBe(
      "Assessment is already published."
    )
    expect(getFieldError(error, "assessment")).toBeNull()
  })
})

import { describe, expect, it } from "vitest"

import {
  ACCESS_TOKEN_STORAGE_KEY,
  accessTokenAccountId,
  tokenStorage,
} from "@/lib/auth-storage"

/**
 * Reading the account out of a stored access token.
 *
 * PH11 QA cycle 2 (TC-GUI-05). AEGIS keeps one bearer pair per browser origin,
 * so a second sign-in replaces the first account's session silently. The only
 * way a tab can notice is the token's own `user_id` claim — the frozen API
 * contract offers nothing else to tell the two accounts apart.
 */

function tokenFor(accountId: string): string {
  const encode = (value: object) =>
    btoa(JSON.stringify(value))
      .replace(/\+/g, "-")
      .replace(/\//g, "_")
      .replace(/=+$/, "")

  return `${encode({ alg: "HS256", typ: "JWT" })}.${encode({
    user_id: accountId,
    token_type: "access",
  })}.not-a-signature`
}

describe("accessTokenAccountId", () => {
  it("reads the user_id claim out of a JWT payload", () => {
    const id = "11111111-2222-3333-4444-555555555555"
    expect(accessTokenAccountId(tokenFor(id))).toBe(id)
  })

  it("decodes base64url, which is the only form a JWT uses", () => {
    // `btoa` emits `/` for these bytes; base64url renders that as `_`, which
    // `atob` rejects outright. A decoder that skipped the translation would
    // throw here instead of reading the claim.
    const id = "\u00ff\u00ff\u00ff"
    expect(accessTokenAccountId(tokenFor(id))).toBe(id)
  })

  it("returns null for anything that is not a JWT with a subject", () => {
    // The opaque strings the rest of the auth tests use as stand-in tokens.
    expect(accessTokenAccountId("access-token")).toBeNull()
    expect(accessTokenAccountId("")).toBeNull()
    // Two segments, so it is shaped like a JWT, but the payload is not one.
    expect(accessTokenAccountId("header.not-json.sig")).toBeNull()
    // A JWT with no user_id claim names no account.
    const noSubject = btoa(JSON.stringify({ token_type: "access" }))
      .replace(/\+/g, "-")
      .replace(/\//g, "_")
      .replace(/=+$/, "")
    expect(accessTokenAccountId(`header.${noSubject}.sig`)).toBeNull()
  })

  it("never throws on a hand-crafted payload", () => {
    expect(() => accessTokenAccountId("a.b.c")).not.toThrow()
    expect(accessTokenAccountId("a.b.c")).toBeNull()
  })
})

describe("tokenStorage", () => {
  it("round-trips the pair under the key the cross-tab listener watches", () => {
    tokenStorage.setTokens("access", "refresh")

    expect(tokenStorage.getAccessToken()).toBe("access")
    expect(tokenStorage.getRefreshToken()).toBe("refresh")
    expect(localStorage.getItem(ACCESS_TOKEN_STORAGE_KEY)).toBe("access")
  })

  it("clears both halves, so no account is left behind in storage", () => {
    tokenStorage.setTokens("access", "refresh")
    tokenStorage.clear()

    expect(tokenStorage.getAccessToken()).toBeNull()
    expect(tokenStorage.getRefreshToken()).toBeNull()
  })
})

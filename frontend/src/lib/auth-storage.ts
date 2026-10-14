/**
 * Token storage abstraction over localStorage.
 *
 * Isomorphic-safe: guards against an absent `window` (SSR / node smoke
 * scripts) and against storage being unavailable (private browsing).
 */

/**
 * The storage key holding the access token.
 *
 * Exported because `AuthProvider` has to hear about *another tab* writing it:
 * the pair below is shared by every tab on the origin, and only the tab that
 * lost its session can tell that it was replaced underneath it.
 */
export const ACCESS_TOKEN_STORAGE_KEY = "aegis.access_token"

const REFRESH_TOKEN_KEY = "aegis.refresh_token"

/**
 * The account a JWT belongs to, read from its own `user_id` claim.
 *
 * AEGIS keeps one bearer pair per browser origin under a fixed key pair, so a
 * second sign-in on the same browser silently replaces the first. The API
 * contract is frozen, so nothing server-side can tell this browser that two
 * different accounts have now used the same slot — the client has to notice,
 * and it can, because a SimpleJWT access token names its own subject
 * (`USER_ID_CLAIM`).
 *
 * This authorises nothing. No signature is verified here — the server verifies
 * one on every request — and the result is only ever compared against the
 * account this tab is already signed in as. It can notice that the stored
 * subject changed; it cannot be used to assume an identity.
 *
 * Returns `null` for anything unreadable so a caller can treat "unknown" as
 * unknown rather than acting on a guess.
 */
export function accessTokenAccountId(token: string): string | null {
  const segment = token.split(".")[1]
  if (!segment) return null

  try {
    const base64 = segment.replace(/-/g, "+").replace(/_/g, "/")
    const padded = base64.padEnd(
      base64.length + ((4 - (base64.length % 4)) % 4),
      "="
    )
    if (typeof atob !== "function") return null

    const payload = JSON.parse(atob(padded)) as { user_id?: unknown }
    const subject = payload.user_id
    return typeof subject === "string" && subject.length > 0 ? subject : null
  } catch {
    return null
  }
}

function read(key: string): string | null {
  if (typeof window === "undefined") return null
  try {
    return window.localStorage.getItem(key)
  } catch {
    return null
  }
}

function write(key: string, value: string): void {
  if (typeof window === "undefined") return
  try {
    window.localStorage.setItem(key, value)
  } catch {
    // Storage may be disabled; auth just won't persist across reloads.
  }
}

function remove(key: string): void {
  if (typeof window === "undefined") return
  try {
    window.localStorage.removeItem(key)
  } catch {
    // noop
  }
}

/** Whether a stored token exists (used to skip the bootstrap /me call). */
function hasTokens(): boolean {
  return read(REFRESH_TOKEN_KEY) !== null
}

export const tokenStorage = {
  getAccessToken: () => read(ACCESS_TOKEN_STORAGE_KEY),
  getRefreshToken: () => read(REFRESH_TOKEN_KEY),
  hasTokens,
  setTokens(access: string, refresh: string): void {
    write(ACCESS_TOKEN_STORAGE_KEY, access)
    write(REFRESH_TOKEN_KEY, refresh)
  },
  setAccessToken(access: string): void {
    write(ACCESS_TOKEN_STORAGE_KEY, access)
  },
  clear(): void {
    remove(ACCESS_TOKEN_STORAGE_KEY)
    remove(REFRESH_TOKEN_KEY)
  },
}

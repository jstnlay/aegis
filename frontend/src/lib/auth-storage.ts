/**
 * Token storage abstraction over localStorage.
 *
 * Isomorphic-safe: guards against an absent `window` (SSR / node smoke
 * scripts) and against storage being unavailable (private browsing).
 */

const ACCESS_TOKEN_KEY = "aegis.access_token"
const REFRESH_TOKEN_KEY = "aegis.refresh_token"

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
  getAccessToken: () => read(ACCESS_TOKEN_KEY),
  getRefreshToken: () => read(REFRESH_TOKEN_KEY),
  hasTokens,
  setTokens(access: string, refresh: string): void {
    write(ACCESS_TOKEN_KEY, access)
    write(REFRESH_TOKEN_KEY, refresh)
  },
  setAccessToken(access: string): void {
    write(ACCESS_TOKEN_KEY, access)
  },
  clear(): void {
    remove(ACCESS_TOKEN_KEY)
    remove(REFRESH_TOKEN_KEY)
  },
}

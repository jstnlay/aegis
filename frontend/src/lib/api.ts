import axios, { AxiosError, type InternalAxiosRequestConfig } from "axios"

import { tokenStorage } from "@/lib/auth-storage"
import { normalizeApiError } from "@/lib/error"

/**
 * Centralized HTTP layer for the frozen AEGIS API contract.
 *
 * - baseURL: VITE_API_BASE_URL (defaults to the local Django API).
 * - Authorization: Bearer header added automatically.
 * - 401 handling: single-flight silent refresh (token ROTATION is enabled
 *   on the backend, so the response contains a new refresh token too),
 *   then the original request is retried once.
 * - PH8.7 onboarding 401s ("Password change required.") are NOT retried.
 *
 * Must not be modified to fit the backend — the API contract is frozen.
 * (docs/BACKEND_SPECIFICATION.md, PH10)
 */

declare module "axios" {
  export interface InternalAxiosRequestConfig {
    /** Internal retry marker for the silent-refresh flow. */
    _retry?: boolean
  }
}

const isServer = () => typeof window === "undefined"

function resolveBaseUrl(): string {
  if (!isServer() && import.meta.env.VITE_API_BASE_URL) {
    return import.meta.env.VITE_API_BASE_URL
  }
  return "http://localhost:8000/api/v1"
}

export const API_BASE_URL = resolveBaseUrl()

const PUBLIC_AUTH_PATHS = ["/auth/login/", "/auth/token/refresh/"]

const isPublicPath = (url?: string) =>
  typeof url === "string" && PUBLIC_AUTH_PATHS.some((p) => url.includes(p))

function authHeader(): Record<string, string> {
  const token = tokenStorage.getAccessToken()
  return token ? { Authorization: `Bearer ${token}` } : {}
}

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: 20_000,
  headers: { "Content-Type": "application/json" },
})

apiClient.interceptors.request.use((config) => {
  if (!isPublicPath(config.url)) {
    Object.assign(config.headers, authHeader())
  }
  return config
})

/**
 * A plain instance for the refresh request itself — it must never go
 * through the interceptors (no token to refresh with yet, and no
 * recursion into the 401 handler).
 */
const refreshClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: 15_000,
  headers: { "Content-Type": "application/json" },
})

let refreshPromise: Promise<boolean> | null = null

/** Single-flight silent refresh. Rotates access AND refresh tokens. */
async function ensureFreshAccessToken(): Promise<boolean> {
  if (!refreshPromise) {
    refreshPromise = doSilentRefresh().finally(() => {
      refreshPromise = null
    })
  }
  return refreshPromise
}

async function doSilentRefresh(): Promise<boolean> {
  const refresh = tokenStorage.getRefreshToken()
  if (!refresh) return false
  try {
    const { data } = await refreshClient.post("/auth/token/refresh/", {
      refresh,
    })
    const access: unknown = data?.access
    const nextRefresh: unknown = data?.refresh
    if (typeof access !== "string" || typeof nextRefresh !== "string") {
      tokenStorage.clear()
      runSessionExpiredHandlers()
      return false
    }
    tokenStorage.setTokens(access, nextRefresh)
    return true
  } catch {
    tokenStorage.clear()
    runSessionExpiredHandlers()
    return false
  }
}

type SessionExpiredHandler = () => void
const sessionExpiredHandlers = new Set<SessionExpiredHandler>()

/** Registers a handler invoked when a silent refresh ultimately fails. */
export function onSessionExpired(handler: SessionExpiredHandler): () => void {
  sessionExpiredHandlers.add(handler)
  return () => sessionExpiredHandlers.delete(handler)
}

function runSessionExpiredHandlers(): void {
  for (const handler of sessionExpiredHandlers) handler()
}

apiClient.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const original = error.config as
      (InternalAxiosRequestConfig & { _retry?: boolean }) | undefined
    if (!original) return Promise.reject(normalizeApiError(error))

    const status = error.response?.status
    const normalized = normalizeApiError(error)

    const shouldAttemptRefresh =
      status === 401 &&
      !original._retry &&
      !isPublicPath(original.url) &&
      !normalized.isPasswordChangeRequired

    if (shouldAttemptRefresh) {
      original._retry = true
      const ok = await ensureFreshAccessToken()
      if (ok) {
        const token = tokenStorage.getAccessToken()
        original.headers.set("Authorization", `Bearer ${token}`)
        return apiClient(original)
      }
    }

    return Promise.reject(normalized)
  }
)

/**
 * Request cancellation: pass an `AbortSignal` via the request config
 * (`signal`) or use `axios.CancelToken`. The interceptor chain is
 * signal-agnostic, so cancelling rejects with a normalizer-recognized
 * `ERR_CANCELED` error (code "REQUEST_CANCELLED").
 */

import { QueryClient } from "@tanstack/react-query"

/**
 * Query key convention:
 *   - Array, ordered from general to specific: ["domain", "resource", id, ...filters]
 *   - Example: ["academics", "subjects", subjectId, { term: "1" }]
 *   - Collocation: keep keys next to the query functions that consume them.
 */
export const queryKeys = {
  accounts: {
    me: ["accounts", "me"] as const,
  },
}

/** How often a live screen asks the server for changes. */
export const LIVE_POLL_INTERVAL_MS = 20_000

/**
 * Adaptive polling for screens that must show changes while watched.
 *
 * React Query suspends the interval while the tab is hidden, and `"always"`
 * makes focus refetch even when the existing data is still inside `staleTime`.
 * `staleTime: 0` is deliberate: the next poll is the source of freshness, not
 * the 60 s default that would let a focus event skip the fetch.
 */
export const liveQueryOptions = {
  staleTime: 0,
  refetchInterval: LIVE_POLL_INTERVAL_MS,
  refetchIntervalInBackground: false,
  refetchOnWindowFocus: "always",
} as const

/**
 * Sensible defaults for an institutional SPA.
 * Retries stay low (the backend already throttles), staleTime prevents
 * refetch storms on tab focuses, and the API client owns token refresh.
 */
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 60 * 1000,
      gcTime: 5 * 60 * 1000,
      retry: 1,
      refetchOnWindowFocus: false,
    },
    mutations: {
      retry: 0,
    },
  },
})

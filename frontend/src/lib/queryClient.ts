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

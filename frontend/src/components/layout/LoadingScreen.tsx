import { Skeleton } from "@/components/ui/skeleton"

/**
 * Full-screen loading state used while the auth session resolves.
 * Minimal and quiet — no decorative animation (PH11.2 $11.4).
 */
/**
 * Content-area fallback while a route chunk loads.
 *
 * Not `LoadingScreen`: the shell stays on screen, so a full-viewport skeleton
 * would replace navigation with a blank page on every first visit to a module.
 */
export function PageLoading() {
  return (
    <div
      role="status"
      aria-busy="true"
      aria-label="Loading page"
      className="space-y-4 py-4"
    >
      <div className="space-y-3" aria-hidden="true">
        <Skeleton className="h-8 w-56" />
        <Skeleton className="h-4 w-full max-w-xl" />
        <Skeleton className="h-64 w-full" />
      </div>
      <span className="sr-only">Loading page</span>
    </div>
  )
}

export function LoadingScreen() {
  return (
    <div
      role="status"
      aria-busy="true"
      aria-label="Loading"
      className="flex min-h-svh items-center justify-center bg-background"
    >
      <div className="w-64 space-y-3" aria-hidden="true">
        <Skeleton className="h-8 w-40" />
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-4 w-3/4" />
        <Skeleton className="h-9 w-32" />
      </div>
      <span className="sr-only">Loading</span>
    </div>
  )
}

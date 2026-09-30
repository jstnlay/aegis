import { Skeleton } from "@/components/ui/skeleton"

/**
 * Full-screen loading state used while the auth session resolves.
 * Minimal and quiet — no decorative animation (PH11.2 $11.4).
 */
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

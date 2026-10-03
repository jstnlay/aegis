import { AlertCircle } from "lucide-react"

/**
 * Inline error message for a failed request or a rejected form.
 *
 * Shared rather than re-declared per page: PH11.7 and PH11.8 each declared a
 * local `ErrorNote`, and they had already drifted. Every call site passes
 * `normalizeApiError(error).message`, which since PH11.9 carries the backend's
 * real text instead of "An error occurred.", so the same component renders
 * field summaries and action errors correctly without knowing which it has.
 *
 * `role="alert"` is deliberate — it announces the failure to a screen reader
 * when it appears after a user action.
 */
export function ErrorNote({ message }: { message: string }) {
  if (!message) return null

  return (
    <div
      role="alert"
      className="flex items-start gap-2 rounded-md border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive"
    >
      <AlertCircle className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
      <span>{message}</span>
    </div>
  )
}

/**
 * Placeholder for a list or section that is legitimately empty.
 *
 * Distinct from `ErrorNote`: an empty result set is not a failure, and must not
 * be rendered as one. `children` lets a caller add a primary action (e.g. a
 * retry) without re-implementing the layout.
 */
export function EmptyState({
  message,
  children,
}: {
  message: string
  children?: React.ReactNode
}) {
  return (
    <div className="space-y-3 py-6 text-center">
      <p className="text-sm text-muted-foreground">{message}</p>
      {children}
    </div>
  )
}

/**
 * Placeholder for a request that has not resolved yet.
 *
 * `aria-busy` plus a visually-hidden status keeps the loading state announced
 * without reading a skeleton aloud.
 */
export function LoadingState({ label = "Loading" }: { label?: string }) {
  return (
    <div
      role="status"
      aria-busy="true"
      aria-live="polite"
      className="py-6 text-center text-sm text-muted-foreground"
    >
      {label}…
    </div>
  )
}

import type { ReactNode } from "react"

import { AlertCircle } from "lucide-react"

import { Skeleton } from "@/components/ui/skeleton"

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
 *
 * `role="status"` (PH11.2 §16.7, "dynamic content updates announced via
 * aria-live") was added in PH11.11. An empty state replaces a table or a list
 * the reader was waiting on, so it is a change of content and has to be
 * announced — previously `LoadingState` announced itself and `EmptyState` did
 * not, which meant the polite end of a request was the one silent outcome.
 *
 * `status`, not `alert`: nothing failed, so it must not interrupt the way
 * `ErrorNote` does. The two stay deliberately distinguishable in both tone and
 * timing, which is the distinction this module exists to protect.
 */
export function EmptyState({
  message,
  children,
}: {
  message: string
  children?: React.ReactNode
}) {
  return (
    <div role="status" className="space-y-3 py-6 text-center">
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

/**
 * A placeholder region that announces itself while it stands in for data.
 *
 * PH11.11. Every dashboard in the app draws a request that has not resolved yet
 * as one or more `Skeleton` bars — grey rectangles carrying no text, no role and
 * no state. That is honest to the eye and silent to a screen reader: the reader
 * activates a page, hears the page title and nothing at all about the dozen
 * figures that are still arriving, and has no way to tell "still loading" from
 * "a dashboard with no content".
 *
 * `LoadingState` already solves this for a whole region, but it replaces the
 * content with a line of text, which is wrong for a metric tile whose height is
 * already fixed — swapping the layout out from under a card to announce a
 * transient state is worse than the silence. So this wraps the skeleton in
 * place instead: the visual language is unchanged, and the region gains
 * `role="status"`, `aria-busy` and a visually-hidden label.
 *
 * The label is required, not defaulted, because the generic "Loading…" names no
 * region and there is usually more than one on a page. A caller that cannot name
 * what it is waiting for is a caller that should use `LoadingState`.
 *
 * The children are the caller's existing skeletons, deliberately unchanged: this
 * owns the semantics, not the appearance.
 */
export function PendingRegion({
  label,
  children,
}: {
  /** What is being waited for, e.g. "Overall grade average". */
  label: string
  children: ReactNode
}) {
  return (
    <div role="status" aria-busy="true" aria-live="polite">
      <span className="sr-only">{label}…</span>
      {children}
    </div>
  )
}

/**
 * `PendingRegion` specialised for a metric tile, which is where it is used.
 *
 * The three states a metric tile can be in are kept strictly apart, because
 * conflating two of them is how a dashboard ends up lying:
 *
 * - in flight → this, an announced skeleton of the tile's own shape;
 * - failed → `UnavailableMetric`, which says the figure is unknown;
 * - resolved → the real value, which may legitimately still read "N/A" via
 *   `formatCount`/`formatPercent` when the backend reported no figure.
 *
 * "N/A" means "no data was reported". A failed request means nobody knows, and
 * rendering it as "N/A" would report a measurement that was never made.
 */
export function PendingMetric({
  label,
  className,
}: {
  label: string
  className?: string
}) {
  return (
    <PendingRegion label={label}>
      <Skeleton className={className ?? "h-8 w-20"} />
    </PendingRegion>
  )
}

/**
 * A metric whose request failed.
 *
 * Deliberately not `NO_DATA_TEXT`. `formatCount`/`formatPercent` render "N/A"
 * when the backend answered with no figure, which is a real answer; a failed
 * request produced no answer at all, and "N/A" would read as one. The
 * accompanying `ErrorNote` carries the reason — this carries only the state, so
 * a grid of four tiles does not repeat the same sentence four times to a screen
 * reader.
 */
export function UnavailableMetric() {
  return (
    <span className="text-base font-normal text-destructive">Unavailable</span>
  )
}

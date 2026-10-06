import { useId, type ReactNode } from "react"

import { ErrorNote, LoadingState } from "@/components/feedback/Feedback"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { normalizeApiError } from "@/lib/error"

/**
 * The three states every chart must keep distinct.
 *
 * A chart that renders "no data" for a failed request tells the reader there is
 * nothing there, which is a different claim from "the request failed". These
 * components exist so a chart cannot collapse one into the other: `ChartState`
 * takes the same three props every time and picks exactly one.
 */

interface ChartStateProps {
  /** Rendered while the request is in flight. */
  isLoading: boolean
  /** The failure, or null. An error must never render as an empty chart. */
  error: unknown
  /** Label for the loading state, announced to assistive technology. */
  loadingLabel: string
  /** True when the request succeeded and there is genuinely nothing to plot. */
  isEmpty: boolean
  /** Message for the empty case. */
  emptyMessage: string
}

/**
 * Renders exactly one of: loading, error, empty, or the children.
 *
 * An error wins over everything, including loading: if a request has already
 * failed there is nothing left to wait for.
 */
export function ChartState({
  isLoading,
  error,
  loadingLabel,
  isEmpty,
  emptyMessage,
  children,
}: ChartStateProps & { children: ReactNode }) {
  if (error) return <ErrorNote message={normalizeApiError(error).message} />
  if (isLoading) return <LoadingState label={loadingLabel} />
  if (isEmpty) return <ChartEmptyState message={emptyMessage} />
  return <>{children}</>
}

/**
 * The "nothing to plot" panel.
 *
 * Names the reason rather than showing a blank frame, because "no data" and a
 * chart that failed to render look identical otherwise.
 */
export function ChartEmptyState({ message }: { message: string }) {
  return (
    <div
      role="status"
      className="flex min-h-40 items-center justify-center rounded-md border border-dashed border-border p-6 text-center text-sm text-muted-foreground"
    >
      {message}
    </div>
  )
}

interface ChartCardProps {
  title: string
  /** What the chart shows and over what scope. */
  description: string
  /** Rendered under the plot — the "as of" line, a unit note, a total. */
  footer?: ReactNode
  children: ReactNode
}

/**
 * A chart inside the app's existing card, with an accessible title.
 *
 * The visual title is a heading, and the plot itself gets the same title via
 * `role="img"` + `aria-label` from the caller, so a screen reader announces what
 * the chart is rather than reading a series of numbers.
 */
export function ChartCard({
  title,
  description,
  footer,
  children,
}: ChartCardProps) {
  const headingId = useId()

  return (
    <Card>
      <CardHeader>
        <CardTitle id={headingId}>{title}</CardTitle>
        <CardDescription>{description}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <div aria-labelledby={headingId}>{children}</div>
        {footer ? (
          <p className="text-xs text-muted-foreground">{footer}</p>
        ) : null}
      </CardContent>
    </Card>
  )
}

/**
 * A fixed-height plot area.
 *
 * Recharts needs a parent with a definite height or it renders nothing, and a
 * fixed height is what keeps a dashboard from reflowing as charts load.
 */
export function ChartFrame({
  height = 280,
  label,
  children,
}: {
  height?: number
  /** What the plot shows, for a reader who cannot see it. */
  label: string
  children: ReactNode
}) {
  return (
    <div
      role="img"
      aria-label={label}
      style={{ height }}
      className="w-full"
    >
      {children}
    </div>
  )
}
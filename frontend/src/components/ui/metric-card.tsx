import type { LucideIcon } from "lucide-react"

import {
  PendingMetric,
  UnavailableMetric,
} from "@/components/feedback/Feedback"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { cn } from "@/lib/utils"

/**
 * The one metric tile every dashboard uses.
 *
 * It replaced six copies of the same component (admin, admin-analytics,
 * faculty, guidance, student, parent), which had already drifted apart: the
 * placeholders were keyed off `isFetching`, which stays true through a
 * background refetch, so a refresh replaced real figures with grey bars; and no
 * copy had a failure state, so a failed request rendered `formatCount(undefined)`
 * → "N/A", claiming a figure that was never reported.
 *
 * `isLoading` in react-query v5 is `isPending && isFetching`, so it is true
 * only before the first result and a background refetch leaves the figures on
 * screen alone.
 *
 * The tile's three states stay strictly apart: in flight → `PendingMetric`
 * (announced skeleton of the tile's own shape), failed → `UnavailableMetric`
 * ("nobody knows"), resolved → the real value. "N/A" is not reused for a
 * failure, because it means "the backend reported no figure".
 */
export function MetricCard({
  title,
  hint,
  icon: Icon,
  centered = false,
  isLoading,
  isError,
  className,
  children,
}: {
  title: string
  /** What the figure covers, under the number. Omitted when the title says it. */
  hint?: string
  /** Decorative tile icon. Not rendered on centered tiles, which have no slot. */
  icon?: LucideIcon
  /**
   * Center the tile, per the reference's stat cards. Left-aligned is the
   * default everywhere else; centered is opt-in so existing tiles do not move.
   */
  centered?: boolean
  isLoading: boolean
  isError: boolean
  className?: string
  /** The formatted figure. Rendered only once the request has resolved. */
  children: React.ReactNode
}) {
  return (
    <Card className={cn("h-full", className)}>
      <CardHeader
        className={cn(
          "flex flex-row items-center justify-between space-y-0 pb-2",
          centered && "justify-center text-center"
        )}
      >
        <CardTitle className="text-sm font-medium">{title}</CardTitle>
        {Icon && !centered ? (
          <Icon aria-hidden="true" className="size-4 text-muted-foreground" />
        ) : null}
      </CardHeader>
      <CardContent className={cn(centered && "text-center")}>
        <div className="text-2xl font-bold tabular-nums">
          {isLoading ? (
            <PendingMetric label={title} />
          ) : isError ? (
            <UnavailableMetric />
          ) : (
            children
          )}
        </div>
        {hint ? (
          <p className="mt-1 text-xs text-muted-foreground">{hint}</p>
        ) : null}
      </CardContent>
    </Card>
  )
}

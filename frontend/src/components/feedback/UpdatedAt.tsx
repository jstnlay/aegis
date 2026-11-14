/**
 * Freshness line for a screen that polls in the background.
 *
 * The value is the query's `dataUpdatedAt`, so it advances only when a request
 * actually succeeds; a failed poll leaves the previous time visible instead of
 * claiming the screen is current. It renders nothing before the first success.
 */
export function UpdatedAt({
  at,
  className,
}: {
  at: number
  className?: string
}) {
  if (!at) return null

  const date = new Date(at)
  return (
    <time
      dateTime={date.toISOString()}
      title={date.toLocaleString()}
      className={className ?? "text-xs text-muted-foreground"}
    >
      Updated{" "}
      {date.toLocaleTimeString(undefined, {
        hour: "numeric",
        minute: "2-digit",
      })}
    </time>
  )
}

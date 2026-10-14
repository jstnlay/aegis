import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts"

import { ChartFrame } from "@/components/charts/ChartCard"
import {
  formatCountValue,
  formatPercentValue,
} from "@/components/charts/chart-config"
import { statusSlices } from "@/lib/guidance-analytics"
import type { RiskAlert } from "@/features/guidance/api"

/**
 * Case Status Overview — the reference's donut with the total in the centre.
 *
 * A donut alone cannot carry exact figures — an arc has to be eyeballed — so
 * the centre carries the total, the legend beside it carries every status with
 * its count and share, and the tooltip spells out all three. No number depends
 * on judging an angle, and colour is never the only signal.
 *
 * Statuses come from the alerts themselves: three open risk levels plus
 * `Resolved`, the only terminal status the backend offers.
 */
export function RiskStatusDonut({ alerts }: { alerts: readonly RiskAlert[] }) {
  const total = alerts.length

  if (total === 0) {
    return (
      <p className="py-6 text-center text-sm text-muted-foreground">
        No cases to summarise.
      </p>
    )
  }

  const slices = statusSlices(alerts)
  const drawn = slices.filter((slice) => slice.count > 0)

  return (
    <div className="flex flex-col gap-4 sm:flex-row sm:items-center">
      <div className="relative sm:w-40">
        <ChartFrame
          height={150}
          label={`Donut chart of ${total} total cases. ${drawn
            .map(
              (slice) =>
                `${slice.label}: ${slice.count}, ${Math.round(
                  (slice.count / total) * 100
                )}%`
            )
            .join(". ")}`}
        >
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Tooltip
                content={({ active, payload }) => {
                  if (!active || !payload?.length) return null
                  const point = payload[0]!.payload as (typeof slices)[number]
                  return (
                    <div className="rounded-md border border-border bg-background p-2 text-sm shadow-sm">
                      <p className="font-medium">{point.label}</p>
                      <p className="text-muted-foreground">
                        {formatCountValue(point.count)} cases ·{" "}
                        {formatPercentValue((point.count / total) * 100)}
                      </p>
                    </div>
                  )
                }}
              />
              <Pie
                data={drawn}
                dataKey="count"
                nameKey="label"
                innerRadius="62%"
                outerRadius="86%"
                stroke="var(--background)"
                isAnimationActive={false}
              >
                {drawn.map((slice) => (
                  <Cell key={slice.key} fill={slice.color} />
                ))}
              </Pie>
            </PieChart>
          </ResponsiveContainer>
        </ChartFrame>

        {/* The total reads from the centre of the hole, where the eye lands
            first. Hidden from assistive tech: the frame's label already spells
            out every slice, and repeating it would only talk over the reader. */}
        <div
          aria-hidden="true"
          className="absolute inset-0 flex flex-col items-center justify-center text-center"
        >
          <p className="text-2xl font-bold tabular-nums leading-none">
            {formatCountValue(total)}
          </p>
          <p className="text-[11px] text-muted-foreground">Total Cases</p>
        </div>
      </div>

      <ul className="flex-1 space-y-1.5">
        {drawn.map((slice) => (
          <li
            key={slice.key}
            className="flex items-center gap-2 text-xs sm:text-sm"
          >
            <span
              aria-hidden="true"
              className="size-2.5 shrink-0 rounded-full"
              style={{ backgroundColor: slice.color }}
            />
            <span className="min-w-0 flex-1 truncate font-medium">
              {slice.label}
            </span>
            <span className="shrink-0 tabular-nums text-muted-foreground">
              {formatCountValue(slice.count)} ·{" "}
              {Math.round((slice.count / total) * 100)}%
            </span>
          </li>
        ))}
      </ul>
    </div>
  )
}

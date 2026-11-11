import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  LabelList,
} from "recharts"
import { useId } from "react"

import { ChartFrame } from "@/components/charts/ChartCard"
import {
  AXIS_COLOR,
  formatCountValue,
  GRID_COLOR,
} from "@/components/charts/chart-config"
import {
  hasRecentCaseHistory,
  newCasesPerMonth,
} from "@/lib/guidance-analytics"
import type { RiskAlert } from "@/features/guidance/api"

/**
 * Monthly Trend — new cases per month, counted from the alerts' `created_at`.
 *
 * The shape follows the reference; the numbers are the hard part. They come
 * from `newCasesPerMonth`, and when that cannot be supported the chart omits
 * itself rather than drawing six empty bars that would read as "zero new cases
 * every month". The caller decides which it gets via `hasRecentCaseHistory`.
 */
export function NewCasesTrendChart({
  alerts,
  height = 150,
}: {
  alerts: readonly RiskAlert[]
  height?: number | string
}) {
  const months = newCasesPerMonth(alerts)
  const gradientId = useId().replace(/:/g, "")
  const total = months.reduce((sum, month) => sum + month.count, 0)

  if (!hasRecentCaseHistory(alerts)) return null

  return (
    <ChartFrame
      height={height}
      label={`Bar chart of new cases per month over the last six months: ${months
        .map((month) => `${month.label} ${month.count}`)
        .join(", ")}.`}
    >
      <ResponsiveContainer width="100%" height="100%">
        <BarChart
          data={months}
          margin={{ top: 28, right: 12, bottom: 8, left: -12 }}
        >
          <defs>
            <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#dc7184" />
              <stop offset="100%" stopColor="#992b46" />
            </linearGradient>
          </defs>
          <CartesianGrid
            vertical={false}
            stroke={GRID_COLOR}
            strokeDasharray="2 5"
          />
          <XAxis
            dataKey="label"
            tickLine={false}
            axisLine={false}
            tick={{ fill: AXIS_COLOR, fontSize: 11 }}
          />
          <YAxis
            allowDecimals={false}
            tickLine={false}
            axisLine={false}
            width={44}
            tick={{ fill: AXIS_COLOR, fontSize: 11 }}
          />
          <Tooltip
            cursor={{ fill: "var(--muted)" }}
            content={({ active, payload }) => {
              if (!active || !payload?.length) return null
              const point = payload[0]!.payload as (typeof months)[number]
              return (
                <div className="rounded-md border border-border bg-background p-2 text-sm shadow-sm">
                  <p className="font-medium">{point.label}</p>
                  <p className="text-muted-foreground">
                    {formatCountValue(point.count)} new case
                    {point.count === 1 ? "" : "s"}
                  </p>
                </div>
              )
            }}
          />
          <Bar
            dataKey="count"
            fill={`url(#${gradientId})`}
            radius={[7, 7, 0, 0]}
            maxBarSize={38}
            isAnimationActive={false}
          >
            <LabelList
              dataKey="count"
              position="top"
              formatter={(value: unknown) =>
                Number(value) > 0 ? formatCountValue(Number(value)) : ""
              }
              className="fill-foreground text-xs font-semibold"
            />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
      {/* Spoken once for the whole plot: the bars carry no per-point text. */}
      <p className="sr-only">
        {total} new case{total === 1 ? "" : "s"} in the last six months.
      </p>
    </ChartFrame>
  )
}

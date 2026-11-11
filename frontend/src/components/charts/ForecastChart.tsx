import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts"

import {
  ChartCard,
  ChartFrame,
  ChartState,
} from "@/components/charts/ChartCard"
import {
  AXIS_COLOR,
  GRID_COLOR,
  formatCountValue,
  formatPercentValue,
} from "@/components/charts/chart-config"
import type { ForecastResult } from "@/features/admin/api"

/**
 * Recorded month series with the projected point drawn as a dashed segment.
 *
 * The projection is an extension of the recorded line, not a second series
 * with equal standing: the first `Recorded` segment is solid, the segment that
 * reaches the estimate is dashed, and the tooltip names the projected month.
 * Months the backend did not record are not invented; the x-axis is exactly
 * the coverage the response reported plus the single projected point.
 */

/** `2026-01` + 3 → `2026-04`, in UTC so a local timezone cannot shift the month. */
function addMonths(month: string, offset: number): string {
  const [year, index] = month.split("-").map(Number)
  if (!year || !index) return month
  const date = new Date(Date.UTC(year, index - 1 + offset, 1))
  return `${date.getUTCFullYear()}-${String(date.getUTCMonth() + 1).padStart(
    2,
    "0"
  )}`
}

export function ForecastChart({
  data,
  isLoading,
  error,
}: {
  data: ForecastResult | undefined
  isLoading: boolean
  error: unknown
}) {
  const series = data?.series ?? []
  const last = series[series.length - 1]
  const estimate = data?.estimate ?? null
  const unit = data?.unit ?? "count"

  const points: {
    month: string
    recorded: number | null
    projected: number | null
  }[] = series.map((point, index) => ({
    month: point.month,
    // The projected key repeats the final recorded value so the dashed line
    // starts where the solid line ends; nothing earlier is duplicated.
    recorded: point.value,
    projected: index === series.length - 1 ? point.value : null,
  }))
  const projectedMonth =
    last && estimate !== null ? addMonths(last.month, data?.months ?? 0) : null
  const hasProjection = projectedMonth !== null && estimate !== null
  if (projectedMonth !== null && estimate !== null) {
    points.push({
      month: projectedMonth,
      recorded: null,
      projected: estimate,
    })
  }

  const formatValue = (value: number | null | undefined) =>
    unit === "percent" ? formatPercentValue(value) : formatCountValue(value)

  return (
    <ChartCard
      title={
        hasProjection
          ? "Recorded months and the projected point"
          : "Recorded months"
      }
      description={
        data
          ? `${series.length} recorded month${
              series.length === 1 ? "" : "s"
            } from ${data.coverage.from ?? "—"} to ${data.coverage.to ?? "—"}.${
              hasProjection
                ? ` Extended ${data.months} month${
                    data.months === 1 ? "" : "s"
                  } ahead.`
                : " No projection is offered for this series."
            }`
          : "A monthly series and its projection."
      }
      footer={
        data?.trend === "up"
          ? "The fitted line rises across the recorded months."
          : data?.trend === "down"
            ? "The fitted line falls across the recorded months."
            : data?.trend === "flat"
              ? "The fitted line is flat across the recorded months."
              : undefined
      }
    >
      <ChartState
        isLoading={isLoading}
        error={error}
        loadingLabel="Loading forecast chart"
        isEmpty={points.length === 0}
        emptyMessage="No monthly points are recorded for this metric yet."
      >
        <ChartFrame
          height={260}
          label={`Line chart of ${data?.metric ?? "the metric"} per month. ${series
            .map((point) => `${point.month}: ${formatValue(point.value)}`)
            .join(", ")}.${
            hasProjection
              ? ` Projected ${projectedMonth} (${
                  data?.months ?? 0
                } months ahead): ${formatValue(estimate)}.`
              : " No projection is offered."
          }`}
        >
          <ResponsiveContainer width="100%" height="100%">
            <LineChart
              data={points}
              margin={{ top: 8, right: 8, bottom: 8, left: 0 }}
            >
              <CartesianGrid
                vertical={false}
                stroke={GRID_COLOR}
                strokeDasharray="3 3"
              />
              <XAxis
                dataKey="month"
                tick={{ fill: AXIS_COLOR, fontSize: 12 }}
                tickLine={false}
                axisLine={{ stroke: GRID_COLOR }}
                minTickGap={16}
              />
              <YAxis
                domain={unit === "percent" ? [0, 100] : undefined}
                tick={{ fill: AXIS_COLOR, fontSize: 12 }}
                tickLine={false}
                axisLine={false}
                width={48}
                tickFormatter={(value: number) =>
                  unit === "percent" ? `${value}%` : String(value)
                }
              />
              <Tooltip
                content={({ active, payload, label }) => {
                  if (!active || !payload?.length) return null
                  const point = payload[0]!.payload as (typeof points)[number]
                  return (
                    <div className="rounded-md border border-border bg-background p-2 text-sm shadow-sm">
                      <p className="font-medium">{label}</p>
                      {point.recorded !== null ? (
                        <p className="text-muted-foreground">
                          Recorded {formatValue(point.recorded)}
                        </p>
                      ) : null}
                      {point.recorded === null && point.projected !== null ? (
                        <p className="text-muted-foreground">
                          Projected {formatValue(point.projected)}
                        </p>
                      ) : null}
                    </div>
                  )
                }}
              />
              {hasProjection ? (
                <Legend wrapperStyle={{ fontSize: 12 }} />
              ) : null}
              <Line
                type="monotone"
                dataKey="recorded"
                name="Recorded"
                stroke="var(--primary)"
                strokeWidth={2}
                dot={{ r: 4 }}
                connectNulls={false}
                isAnimationActive={false}
              />
              {hasProjection ? (
                <Line
                  type="monotone"
                  dataKey="projected"
                  name="Projected"
                  stroke="var(--chart-2)"
                  strokeWidth={2}
                  strokeDasharray="6 4"
                  dot={{ r: 3 }}
                  connectNulls={false}
                  isAnimationActive={false}
                />
              ) : null}
            </LineChart>
          </ResponsiveContainer>
        </ChartFrame>
      </ChartState>
    </ChartCard>
  )
}

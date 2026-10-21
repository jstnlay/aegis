import {
  CartesianGrid,
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
} from "@/components/charts/chart-config"
import type { AlertTrendPoint } from "@/features/admin/api"

/**
 * Risk alerts opened per day over the last 30 days.
 *
 * The reference dashboard asks for "Trend Overview (Last 30 Days)". Counts come
 * from `/analytics/risk-distribution/`; no student is named, so the card stays
 * inside NFR-010's anonymisation rule.
 *
 * Zero days stay in the series: a day with no alerts is a measured zero, not a
 * missing record, so dropping it would misstate the gap between alerts.
 */
export function RiskAlertTrendChart({
  points,
  isLoading,
  error,
}: {
  points: readonly AlertTrendPoint[]
  isLoading: boolean
  error: unknown
}) {
  const hasAny = points.some((point) => point.count > 0)

  return (
    <ChartCard
      title="Trend overview (last 30 days)"
      description="Risk alerts opened per day across the school."
    >
      <ChartState
        isLoading={isLoading}
        error={error}
        loadingLabel="Loading risk alert trend"
        isEmpty={!hasAny}
        emptyMessage="No risk alerts have been opened in the last 30 days."
      >
        <ChartFrame
          height={280}
          label={`Line chart of risk alerts opened per day for the last 30 days. ${points
            .map((point) => `${point.date}: ${formatCountValue(point.count)}`)
            .join(", ")}.`}
        >
          <ResponsiveContainer width="100%" height="100%">
            <LineChart
              data={points.map((point) => ({ ...point }))}
              margin={{ top: 8, right: 18, bottom: 8, left: 0 }}
            >
              <CartesianGrid
                vertical={false}
                stroke={GRID_COLOR}
                strokeDasharray="3 3"
              />
              <XAxis
                dataKey="date"
                tick={{ fill: AXIS_COLOR, fontSize: 11 }}
                tickLine={false}
                axisLine={{ stroke: GRID_COLOR }}
                tickFormatter={(date: string) => date.slice(5)}
                minTickGap={24}
              />
              <YAxis
                allowDecimals={false}
                tick={{ fill: AXIS_COLOR, fontSize: 11 }}
                tickLine={false}
                axisLine={false}
                width={32}
              />
              <Tooltip
                content={({ active, payload, label }) => {
                  if (!active || !payload?.length) return null
                  return (
                    <div className="rounded-md border border-border bg-background p-2 text-sm shadow-sm">
                      <p className="font-medium">{label}</p>
                      <p className="text-muted-foreground">
                        {formatCountValue(payload[0]?.value as number)} alert
                        {payload[0]?.value === 1 ? "" : "s"}
                      </p>
                    </div>
                  )
                }}
              />
              <Line
                type="monotone"
                dataKey="count"
                name="Alerts opened"
                stroke="var(--risk-high)"
                strokeWidth={2}
                dot={false}
                isAnimationActive={false}
              />
            </LineChart>
          </ResponsiveContainer>
        </ChartFrame>
      </ChartState>
    </ChartCard>
  )
}

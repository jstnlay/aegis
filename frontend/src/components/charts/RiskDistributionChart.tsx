import {
  Cell,
  Legend,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
} from "recharts"

import {
  ChartCard,
  ChartFrame,
  ChartState,
} from "@/components/charts/ChartCard"
import {
  AXIS_COLOR,
  formatCountValue,
  formatPercentValue,
} from "@/components/charts/chart-config"
import { useRiskDistribution } from "@/features/admin/api"

/**
 * Risk-level distribution, from `/analytics/risk-distribution/`.
 *
 * Four categories, because the endpoint returns four: `low`, `moderate`, `high`
 * and `insufficient_data`. PH11.2 §15.5 predates the `insufficient_data` case
 * and describes three segments, but a student whose computation could not run
 * is neither low nor moderate nor high, and dropping the bucket would make the
 * donut's total disagree with the "students with scores" figure shown beneath
 * it. The contract is the source of truth, so the fourth segment stays.
 *
 * Severity colours come from the same tokens the risk badges use, so a colour
 * in the donut means the same thing as the same colour in the alert list.
 */

interface DonutSlice {
  name: string
  value: number
  color: string
}

const SLICES: readonly {
  key: "low" | "moderate" | "high" | "insufficient_data"
  label: string
  color: string
}[] = [
  { key: "low", label: "Low", color: "var(--chart-2)" },
  { key: "moderate", label: "Moderate", color: "var(--chart-4)" },
  { key: "high", label: "High", color: "var(--destructive)" },
  { key: "insufficient_data", label: "Insufficient data", color: "var(--muted-foreground)" },
]

function toSlices(distribution: {
  low: number
  moderate: number
  high: number
  insufficient_data: number
}): DonutSlice[] {
  // A zero segment is dropped rather than drawn as a hairline: it would imply a
  // category exists when the count is simply zero.
  return SLICES.flatMap((slice) => {
    const value = distribution[slice.key]
    if (!value) return []
    return [{ name: slice.label, value, color: slice.color }]
  })
}

export function RiskDistributionChart() {
  const query = useRiskDistribution()
  const data = query.data
  const slices = data ? toSlices(data.distribution) : []
  const total = slices.reduce((sum, slice) => sum + slice.value, 0)

  return (
    <ChartCard
      title="Risk distribution"
      description="Students by their latest computed risk level."
      footer={
        total > 0
          ? `${formatCountValue(data?.total_with_scores)} student${
              data?.total_with_scores === 1 ? "" : "s"
            } have a computed risk score. Students without enough data are shown separately, not as low risk.`
          : undefined
      }
    >
      <ChartState
        isLoading={query.isLoading}
        error={query.isError ? query.error : null}
        loadingLabel="Loading risk distribution"
        isEmpty={slices.length === 0}
        emptyMessage="The risk engine has not produced any scores yet, so there is no distribution to show."
      >
        <ChartFrame
          label={`Donut chart of student risk levels: ${slices
            .map((slice) => `${slice.name} ${slice.value}`)
            .join(", ")}.`}
        >
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Tooltip
                content={({ active, payload }) => {
                  if (!active || !payload?.length) return null
                  const point = payload[0]!.payload as DonutSlice
                  const share = total > 0 ? (point.value / total) * 100 : null
                  return (
                    <div className="rounded-md border border-border bg-background p-2 text-sm shadow-sm">
                      <p className="font-medium">{point.name}</p>
                      <p className="text-muted-foreground">
                        {formatCountValue(point.value)}{" "}
                        {point.value === 1 ? "student" : "students"}
                      </p>
                      {share !== null ? (
                        <p className="text-muted-foreground">
                          {formatPercentValue(share)} of scored students
                        </p>
                      ) : null}
                    </div>
                  )
                }}
              />
              <Pie
                data={slices}
                dataKey="value"
                nameKey="name"
                innerRadius="55%"
                outerRadius="80%"
                paddingAngle={1}
                stroke="var(--background)"
                isAnimationActive={false}
              >
                {slices.map((slice) => (
                  <Cell key={slice.name} fill={slice.color} />
                ))}
              </Pie>
              <Legend
                verticalAlign="bottom"
                iconType="circle"
                formatter={(value) => (
                  <span style={{ color: AXIS_COLOR, fontSize: 12 }}>
                    {value}
                  </span>
                )}
              />
            </PieChart>
          </ResponsiveContainer>
        </ChartFrame>
      </ChartState>
    </ChartCard>
  )
}
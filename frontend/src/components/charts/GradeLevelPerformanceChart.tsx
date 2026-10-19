import {
  Bar,
  BarChart,
  CartesianGrid,
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
  SCORE_DOMAIN,
  SCORE_TICKS,
  chartColor,
  formatScoreValue,
  toChartValue,
} from "@/components/charts/chart-config"
import {
  useGradeLevelComparison,
  type GradeLevelComparison,
} from "@/features/admin/api"

/**
 * Grade-level performance, from `/analytics/grade-levels/comparison/`.
 *
 * The endpoint returns one average per grade level. A grade level with no
 * finalized grades carries `average: null`; that row is dropped rather than
 * plotted as zero, because zero would read as "every student in this level
 * scored nothing".
 */
interface BarDatum {
  gradeLevel: string
  average: number
  gradesCounted: number
}

function toBars(rows: readonly GradeLevelComparison[]): BarDatum[] {
  return rows.flatMap((row) => {
    const average = toChartValue(row.average)
    if (average === null) return []
    return [
      {
        gradeLevel: row.grade_level_name,
        average,
        gradesCounted: row.grade_count,
      },
    ]
  })
}

export function GradeLevelPerformanceChart() {
  const query = useGradeLevelComparison()
  const bars = toBars(query.data ?? [])

  return (
    <ChartCard
      title="Grade-level performance"
      description="Average of finalized grades, by grade level."
      footer={
        bars.length > 0
          ? `${bars.reduce((sum, bar) => sum + bar.gradesCounted, 0)} finalized grades counted.`
          : undefined
      }
    >
      <ChartState
        isLoading={query.isLoading}
        error={query.isError ? query.error : null}
        loadingLabel="Loading grade-level performance"
        isEmpty={bars.length === 0}
        emptyMessage="No finalized grades are available to compare yet."
      >
        <ChartFrame
          label={`Bar chart of average finalized grade by grade level, on a scale of 0 to 100. ${bars
            .map((bar) => `${bar.gradeLevel}: ${formatScoreValue(bar.average)}`)
            .join(", ")}.`}
        >
          <ResponsiveContainer width="100%" height="100%">
            <BarChart
              data={bars}
              margin={{ top: 8, right: 8, bottom: 8, left: 0 }}
            >
              <CartesianGrid
                vertical={false}
                stroke={GRID_COLOR}
                strokeDasharray="3 3"
              />
              <XAxis
                dataKey="gradeLevel"
                tick={{ fill: AXIS_COLOR, fontSize: 12 }}
                tickLine={false}
                axisLine={{ stroke: GRID_COLOR }}
                /*
                  PH11.11. Grade-level names are unbounded free text — "Senior High
                  School - Accountancy" is a realistic one — so on a phone's width
                  Recharts was drawing every tick on top of its neighbours into an
                  unreadable band. `minTickGap` makes it drop ticks that cannot be
                  spaced rather than overlapping them. Nothing is lost: every level
                  remains in the tooltip, and the full set is named in the frame's
                  `aria-label`, which is what a non-sighted reader gets.
                */
                minTickGap={8}
              />
              <YAxis
                domain={SCORE_DOMAIN}
                ticks={SCORE_TICKS}
                tick={{ fill: AXIS_COLOR, fontSize: 12 }}
                tickLine={false}
                axisLine={false}
                width={40}
              />
              <Tooltip
                cursor={{ fill: "var(--muted)", opacity: 0.4 }}
                content={({ active, payload }) => {
                  if (!active || !payload?.length) return null
                  const point = payload[0]!.payload as BarDatum
                  return (
                    <div className="rounded-md border border-border bg-background p-2 text-sm shadow-sm">
                      <p className="font-medium">{point.gradeLevel}</p>
                      <p className="text-muted-foreground">
                        Average {formatScoreValue(point.average)}
                      </p>
                      <p className="text-muted-foreground">
                        {point.gradesCounted} finalized grades counted
                      </p>
                    </div>
                  )
                }}
              />
              <Bar
                dataKey="average"
                name="Average score"
                fill={chartColor(0)}
                radius={[4, 4, 0, 0]}
                isAnimationActive={false}
              />
            </BarChart>
          </ResponsiveContainer>
        </ChartFrame>
      </ChartState>
    </ChartCard>
  )
}

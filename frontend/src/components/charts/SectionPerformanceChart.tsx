import {
  Bar,
  BarChart,
  CartesianGrid,
  LabelList,
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
  formatCountValue,
  formatScoreValue,
  toChartValue,
} from "@/components/charts/chart-config"
import type { SectionPerformance } from "@/features/admin/api"
import { formatCount, formatPercent } from "@/lib/metric-format"

/**
 * One section's aggregate, from `/analytics/sections/{id}/performance/`.
 *
 * The endpoint returns one figure per section, so there is no series to plot
 * across a shared axis — a single-value bar chart of one section against the
 * 0–100 scale is the honest presentation. It is worth drawing rather than
 * showing only a number because it shows where the section sits relative to
 * the possible range, which a bare figure does not.
 *
 * A section with no finalized grades reports `grade_average: null`. That is
 * rendered as the empty state rather than a zero-height bar, because a zero bar
 * would read as "every student scored nothing".
 */
export function SectionPerformanceChart({
  sectionId,
  data,
  isLoading,
  error,
}: {
  /** Null until a section is chosen; the panel is not shown then. */
  sectionId: string | null
  data: SectionPerformance | undefined
  isLoading: boolean
  error: unknown
}) {
  const average = toChartValue(data?.grade_average)
  const bars =
    data && average !== null
      ? [
          {
            name: data.section_name,
            average,
            totalStudents: data.total_students,
            totalGrades: data.total_grades,
          },
        ]
      : []

  return (
    <ChartCard
      title={data ? `${data.section_name} performance` : "Section performance"}
      description={
        data
          ? `${data.grade_level} · average of finalized grades, as points out of 100.`
          : "Average of finalized grades for the selected section."
      }
      footer={
        data
          ? `${formatCount(data.total_students)} enrolled · ${formatCount(
              data.total_grades
            )} finalized grades counted.`
          : undefined
      }
    >
      <ChartState
        isLoading={isLoading}
        error={error}
        loadingLabel="Loading section performance"
        isEmpty={bars.length === 0}
        emptyMessage={
          sectionId
            ? "No finalized grades are recorded for this section yet."
            : "Select a section to see its performance."
        }
      >
        <ChartFrame
          height={200}
          label={`Bar chart of ${data?.section_name ?? "section"} average finalized grade, ${formatScoreValue(average)}.`}
        >
          <ResponsiveContainer width="100%" height="100%">
            <BarChart
              data={bars}
              margin={{ top: 24, right: 8, bottom: 8, left: 0 }}
            >
              <CartesianGrid
                vertical={false}
                stroke={GRID_COLOR}
                strokeDasharray="3 3"
              />
              <XAxis
                dataKey="name"
                tick={{ fill: AXIS_COLOR, fontSize: 12 }}
                tickLine={false}
                axisLine={{ stroke: GRID_COLOR }}
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
                  const point = payload[0]!.payload as (typeof bars)[number]
                  return (
                    <div className="rounded-md border border-border bg-background p-2 text-sm shadow-sm">
                      <p className="font-medium">{point.name}</p>
                      <p className="text-muted-foreground">
                        Average {formatScoreValue(point.average)}
                      </p>
                      <p className="text-muted-foreground">
                        {formatCountValue(point.totalGrades)} finalized grades ·{" "}
                        {formatCountValue(point.totalStudents)} enrolled
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
              >
                {/*
                  A single bar with no axis grid to read its height against is
                  ambiguous, so the value is written on it. One data point is
                  under the ten-point threshold PH11.2 §15.4 sets for labels.
                */}
                <LabelList
                  dataKey="average"
                  position="top"
                  formatter={(value: unknown) =>
                    formatPercent(Number(value), 1)
                  }
                  style={{ fill: AXIS_COLOR, fontSize: 12 }}
                />
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </ChartFrame>
      </ChartState>
    </ChartCard>
  )
}

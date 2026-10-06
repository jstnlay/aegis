import { Legend, Line, LineChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts"

import {
  ChartCard,
  ChartFrame,
  ChartState,
} from "@/components/charts/ChartCard"
import {
  AXIS_COLOR,
  CHART_COLORS,
  GRID_COLOR,
  SCORE_DOMAIN,
  SCORE_TICKS,
  formatScoreValue,
} from "@/components/charts/chart-config"
import { useSubjectTrends, type GradingPeriodRef } from "@/features/admin/api"

/**
 * Subject performance across grading periods, from
 * `/analytics/subjects/trends/`.
 *
 * Period order
 * ------------
 * The endpoint keys periods by *name* (`subject_trends[subject][period]`), so
 * the order they arrive in is not the academic order. Sorting those names
 * alphabetically would give "Second Term" before "Third Term" and "First
 * Semester" in the wrong place. This chart therefore orders periods using
 * `GradingPeriod.order` fetched from the academic API — the same field the rest
 * of the app sorts periods by — and appends any period the endpoint returned
 * that has no matching record, rather than dropping it or inventing a position.
 *
 * The palette holds five distinguishable colours, so a chart with more than
 * five subjects plots the first five and states plainly how many were not
 * plotted. Silently truncating to five lines and calling it the trend would
 * misstate the data.
 */

const MAX_SERIES = CHART_COLORS.length

interface TrendPoint {
  period: string
  [subjectCode: string]: string | number | null
}

function toPoints(
  trends: Record<string, Record<string, number>>,
  periodOrder: readonly GradingPeriodRef[],
  subjects: readonly string[]
): TrendPoint[] {
  // Academic order first, then any period the trends mention that the academic
  // API does not list, ordered by name so the result is still deterministic.
  const known = new Set(periodOrder.map((period) => period.name))
  const extra = new Set<string>()
  for (const byPeriod of Object.values(trends)) {
    for (const periodName of Object.keys(byPeriod)) {
      if (!known.has(periodName)) extra.add(periodName)
    }
  }
  const order = [
    ...periodOrder.map((period) => period.name),
    ...Array.from(extra).sort(),
  ]

  return order.map((periodName) => {
    const point: TrendPoint = { period: periodName }
    for (const subject of subjects) {
      // A subject with no grades in a period is left null, not zero: the gap is
      // meaningful, and a zero would read as a failing score.
      point[subject] = trends[subject]?.[periodName] ?? null
    }
    return point
  })
}

export function SubjectTrendChart({
  periodOrder,
}: {
  periodOrder: readonly GradingPeriodRef[]
}) {
  const query = useSubjectTrends()
  const trends = query.data ?? {}

  const allSubjects = Object.keys(trends).sort()
  const subjects = allSubjects.slice(0, MAX_SERIES)
  const omitted = allSubjects.length - subjects.length

  const points = toPoints(trends, periodOrder, subjects)
  const hasAnyValue = points.some((point) =>
    subjects.some((subject) => point[subject] !== null)
  )

  return (
    <ChartCard
      title="Subject performance across periods"
      description="Average finalized grade per subject, by grading period, in academic order."
      footer={
        omitted > 0
          ? `Showing ${subjects.length} of ${allSubjects.length} subjects — ${omitted} more are not plotted, because only ${MAX_SERIES} series can be told apart by colour alone.`
          : undefined
      }
    >
      <ChartState
        isLoading={query.isLoading}
        error={query.isError ? query.error : null}
        loadingLabel="Loading subject trends"
        isEmpty={!hasAnyValue}
        emptyMessage="No finalized grades are recorded across any subject and period yet."
      >
        <ChartFrame
          label={`Line chart of average grade per subject across grading periods. ${subjects
            .map((subject) => {
              const values = points
                .map(
                  (point) =>
                    `${point.period}: ${formatScoreValue(point[subject] as number | null)}`
                )
                .join(", ")
              return `${subject} — ${values}`
            })
            .join(". ")}`}
        >
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={points} margin={{ top: 8, right: 8, bottom: 8, left: 0 }}>
              <CartesianGrid
                vertical={false}
                stroke={GRID_COLOR}
                strokeDasharray="3 3"
              />
              <XAxis
                dataKey="period"
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
                content={({ active, label, payload }) => {
                  if (!active || !payload?.length) return null
                  return (
                    <div className="rounded-md border border-border bg-background p-2 text-sm shadow-sm">
                      <p className="font-medium">{label}</p>
                      {payload.map((entry) => (
                        <p
                          key={String(entry.dataKey)}
                          className="text-muted-foreground"
                        >
                          {String(entry.name)}:{" "}
                          {formatScoreValue(entry.value as number | null)}
                        </p>
                      ))}
                    </div>
                  )
                }}
              />
              <Legend
                verticalAlign="bottom"
                iconType="plainline"
                formatter={(value) => (
                  <span style={{ color: AXIS_COLOR, fontSize: 12 }}>
                    {value}
                  </span>
                )}
              />
              {subjects.map((subject, index) => (
                <Line
                  key={subject}
                  type="monotone"
                  dataKey={subject}
                  name={subject}
                  stroke={CHART_COLORS[index]}
                  strokeWidth={2}
                  dot={{ r: 3 }}
                  // A gap stays a gap: connectNulls would draw a straight line
                  // across a period with no grades and imply data that is not
                  // there.
                  connectNulls={false}
                  isAnimationActive={false}
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </ChartFrame>
      </ChartState>
    </ChartCard>
  )
}
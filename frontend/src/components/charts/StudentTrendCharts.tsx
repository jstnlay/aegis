import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts"

import { ChartFrame } from "@/components/charts/ChartCard"
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
import {
  useStudentAcademicTrend,
  useStudentAttendanceTrend,
} from "@/features/admin/api"

/**
 * Per-student academic and attendance trends.
 *
 * Shared by the student and parent dashboards, because they read the same
 * record and the brief is explicit that a parent's view of a child's grades
 * must not look like a different feature from the student's own. Both hooks
 * are the existing student-scoped analytics views, whose authorization ladder
 * (`_StudentScopedAnalyticsView`) already resolves student → own record,
 * parent → linked child, faculty → assigned scope, guidance/admin → any
 * student, so neither chart widens access.
 */

/** Bare list shape the two charts need; `ResolvedGrade` etc. are not exposed. */
interface TrendPeriod {
  period: string
  order: number
  average: number | null
  grade_count: number
}

/**
 * One student's average per grading period.
 *
 * A period whose grades carry no score reports `average: null` and is drawn as
 * a gap rather than a zero: a zero would assert a failing average the database
 * does not contain.
 */
export function StudentAcademicTrendChart({
  studentId,
}: {
  studentId: string | null
}) {
  const query = useStudentAcademicTrend(studentId)
  const periods = (query.data?.periods ?? []) as TrendPeriod[]

  const points = [...periods]
    .sort((a, b) => a.order - b.order)
    .map((period) => ({
      period: period.period,
      average: toChartValue(period.average),
      gradesCounted: period.grade_count,
    }))

  const hasAnyValue = points.some((point) => point.average !== null)

  if (!studentId || query.isError) {
    return (
      <p className="text-sm text-muted-foreground">
        Unable to load your academic trend.
      </p>
    )
  }

  if (query.isLoading) {
    return (
      <p className="py-6 text-center text-sm text-muted-foreground">
        Loading academic trend…
      </p>
    )
  }

  if (!hasAnyValue) {
    return (
      <p className="py-6 text-center text-sm text-muted-foreground">
        No finalized grades are recorded for any grading period yet.
      </p>
    )
  }

  return (
    <ChartFrame
      height={240}
      label={`Line chart of your average grade per grading period. ${points
        .map(
          (point) =>
            `${point.period}: ${formatScoreValue(point.average)}, ${formatCountValue(point.gradesCounted)} grades counted`
        )
        .join(". ")}.`}
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
            dataKey="period"
            tick={{ fill: AXIS_COLOR, fontSize: 12 }}
            tickLine={false}
            axisLine={{ stroke: GRID_COLOR }}
            // Period names are free text, so they overlap at narrow widths
            // unless Recharts is told which ones it can drop.
            minTickGap={16}
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
            content={({ active, payload, label }) => {
              if (!active || !payload?.length) return null
              const point = payload[0]!.payload as (typeof points)[number]
              return (
                <div className="rounded-md border border-border bg-background p-2 text-sm shadow-sm">
                  <p className="font-medium">{label}</p>
                  <p className="text-muted-foreground">
                    Average {formatScoreValue(point.average)}
                  </p>
                  <p className="text-muted-foreground">
                    {formatCountValue(point.gradesCounted)} grades counted
                  </p>
                </div>
              )
            }}
          />
          <Line
            type="monotone"
            dataKey="average"
            name="Average score"
            stroke={chartColor(0)}
            strokeWidth={2}
            dot={{ r: 4 }}
            // A period with no scores stays a gap.
            connectNulls={false}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </ChartFrame>
  )
}

/**
 * "2026-09-14" → "Sep 14".
 *
 * The axis has room for a short label, not an ISO date, and fifteen of those
 * overlap into an unreadable strip at dashboard width. Unparseable values pass
 * through rather than vanishing, so a bad date is visible instead of silently
 * dropped from the axis.
 */
function formatDayLabel(value: string): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(value)
  if (!match) return value
  const date = new Date(
    Number(match[1]),
    Number(match[2]) - 1,
    Number(match[3])
  )
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleDateString(undefined, { month: "short", day: "numeric" })
}

/**
 * One student's attendance per day, stacked by status.
 *
 * Only days with a recorded record appear in the series: a day with no record
 * is absent rather than plotted as three zeroes, which would read as a day
 * nobody attended.
 */
export function StudentAttendanceTrendChart({
  studentId,
}: {
  studentId: string | null
}) {
  const query = useStudentAttendanceTrend(studentId)
  const days = query.data?.days ?? []

  const points = days.map((day) => ({
    date: day.date,
    present: day.present,
    late: day.late,
    absent: day.absent,
  }))

  if (!studentId || query.isError) {
    return (
      <p className="text-sm text-muted-foreground">
        Unable to load your attendance trend.
      </p>
    )
  }

  if (query.isLoading) {
    return (
      <p className="py-6 text-center text-sm text-muted-foreground">
        Loading attendance trend…
      </p>
    )
  }

  if (points.length === 0) {
    return (
      <p className="py-6 text-center text-sm text-muted-foreground">
        No attendance has been recorded yet.
      </p>
    )
  }

  return (
    <ChartFrame
      height={240}
      label={`Stacked bar chart of daily attendance by status. ${points
        .map(
          (point) =>
            `${point.date}: ${point.present} present, ${point.late} late, ${point.absent} absent`
        )
        .join(". ")}.`}
    >
      <ResponsiveContainer width="100%" height="100%">
        <BarChart
          data={points}
          margin={{ top: 8, right: 8, bottom: 8, left: 0 }}
        >
          <CartesianGrid
            vertical={false}
            stroke={GRID_COLOR}
            strokeDasharray="3 3"
          />
          <XAxis
            dataKey="date"
            tick={{ fill: AXIS_COLOR, fontSize: 12 }}
            tickLine={false}
            axisLine={{ stroke: GRID_COLOR }}
            tickFormatter={formatDayLabel}
            minTickGap={16}
          />
          <YAxis
            tick={{ fill: AXIS_COLOR, fontSize: 12 }}
            tickLine={false}
            axisLine={false}
            width={40}
            allowDecimals={false}
          />
          <Tooltip
            content={({ active, payload, label }) => {
              if (!active || !payload?.length) return null
              return (
                <div className="rounded-md border border-border bg-background p-2 text-sm shadow-sm">
                  <p className="font-medium">{label}</p>
                  <p className="text-muted-foreground">
                    Present: {formatCountValue(payload[0]?.payload.present)}
                  </p>
                  <p className="text-muted-foreground">
                    Late: {formatCountValue(payload[0]?.payload.late)}
                  </p>
                  <p className="text-muted-foreground">
                    Absent: {formatCountValue(payload[0]?.payload.absent)}
                  </p>
                </div>
              )
            }}
          />
          {(
            [
              { key: "present", label: "Present", color: "var(--chart-2)" },
              { key: "late", label: "Late", color: "var(--chart-4)" },
              { key: "absent", label: "Absent", color: "var(--destructive)" },
            ] as const
          ).map((series) => (
            <Bar
              key={series.key}
              dataKey={series.key}
              name={series.label}
              stackId="attendance"
              fill={series.color}
              maxBarSize={28}
              isAnimationActive={false}
            />
          ))}
        </BarChart>
      </ResponsiveContainer>
    </ChartFrame>
  )
}

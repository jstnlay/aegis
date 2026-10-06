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
import { useSchoolWideAcademicTrend } from "@/features/admin/api"

/**
 * School-wide academic performance across grading periods, from
 * `GET /analytics/academic-trend/`.
 *
 * Why this is not `/analytics/subjects/trends/`
 * --------------------------------------------
 * That endpoint keys its periods by *name*, so the axis order is whatever the
 * dictionary happens to yield and "Second Term" lands before "First Term". This
 * endpoint aggregates the same finalized grades but returns `GradingPeriod.order`
 * with each entry, so the chart draws the real academic sequence. One series here
 * rather than one per subject: the requirement is the school-wide trend, and one
 * line is legible where ten are not.
 *
 * A period whose grades carry no score reports `average: null` and is plotted as
 * a gap rather than a zero — a zero would assert a failing average that the
 * database does not contain.
 */
export function AcademicTrendChart() {
  const query = useSchoolWideAcademicTrend()
  const periods = query.data?.periods ?? []

  const points = periods.map((period) => ({
    period: period.period,
    // Kept as the raw number (or null) so Recharts draws a gap, not a zero.
    average: toChartValue(period.average),
    gradesCounted: period.grade_count,
  }))

  const hasAnyValue = points.some((point) => point.average !== null)

  return (
    <ChartCard
      title="Academic performance across periods"
      description="School-wide average of finalized grades per grading period, in academic order. Scores are points out of 100."
      footer={
        points.length > 0
          ? `${formatCountValue(
              points.reduce((sum, point) => sum + point.gradesCounted, 0)
            )} finalized grades counted across ${
              points.length
            } period${points.length === 1 ? "" : "s"}.`
          : undefined
      }
    >
      <ChartState
        isLoading={query.isLoading}
        error={query.isError ? query.error : null}
        loadingLabel="Loading academic trend"
        isEmpty={!hasAnyValue}
        emptyMessage="No finalized grades are recorded for any grading period yet."
      >
        <ChartFrame
          label={`Line chart of the school-wide average grade per grading period. ${points
            .map(
              (point) => `${point.period}: ${formatScoreValue(point.average)}`
            )
            .join(", ")}.`}
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
                        {formatCountValue(point.gradesCounted)} finalized grades
                        counted
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
                // A period with no scores stays a gap; a straight line across it
                // would imply a measurement that does not exist.
                connectNulls={false}
                isAnimationActive={false}
              />
            </LineChart>
          </ResponsiveContainer>
        </ChartFrame>
      </ChartState>
    </ChartCard>
  )
}

/**
 * School-wide attendance across days, from
 * `GET /analytics/attendance-trend/`.
 *
 * Stacked bars of present / late / absent per day, the shape PH11.2 §15.5 asks
 * for. A day with no record is absent from the series rather than plotted as
 * three zeroes, which would read as a day nobody attended.
 */
export function AttendanceTrendChart({
  days,
}: {
  days: readonly AttendanceTrendRow[]
}) {
  const points = days.map((day) => ({
    date: day.date,
    present: day.present,
    late: day.late,
    absent: day.absent,
  }))

  return (
    <ChartCard
      title="Attendance across the school day"
      description="Records per day, by status. Only days with recorded attendance appear."
    >
      <ChartState
        isLoading={false}
        error={null}
        loadingLabel="Loading attendance trend"
        isEmpty={points.length === 0}
        emptyMessage="No attendance has been recorded yet."
      >
        <ChartFrame
          height={260}
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
                  {
                    key: "absent",
                    label: "Absent",
                    color: "var(--destructive)",
                  },
                ] as const
              ).map((series) => (
                <Bar
                  key={series.key}
                  dataKey={series.key}
                  name={series.label}
                  stackId="attendance"
                  fill={series.color}
                  isAnimationActive={false}
                />
              ))}
            </BarChart>
          </ResponsiveContainer>
        </ChartFrame>
      </ChartState>
    </ChartCard>
  )
}

/** The shape `AttendanceTrendChart` plots. */
interface AttendanceTrendRow {
  date: string
  present: number
  late: number
  absent: number
}

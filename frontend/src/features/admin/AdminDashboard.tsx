import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import {
  ErrorNote,
  PendingMetric,
  PendingRegion,
  UnavailableMetric,
} from "@/components/feedback/Feedback"
import { Skeleton } from "@/components/ui/skeleton"
import { ChartState } from "@/components/charts/ChartCard"
import { GradeLevelPerformanceChart } from "@/components/charts/GradeLevelPerformanceChart"
import { RiskDistributionChart } from "@/components/charts/RiskDistributionChart"
import { RoleDistributionChart } from "@/components/charts/RoleDistributionChart"
import { SubjectTrendChart } from "@/components/charts/SubjectTrendChart"
import {
  AcademicTrendChart,
  AttendanceTrendChart,
} from "@/components/charts/TrendCharts"
import { useAuth } from "@/features/auth/AuthContext"
import {
  useGradeLevelComparison,
  useGradingPeriodOrder,
  useRiskDistribution,
  useSchoolWideAttendanceTrend,
  useSchoolWideMetrics,
} from "@/features/admin/api"
import { DataTable, type DataTableColumn } from "@/components/ui/data-table"
import { formatCount, formatPercent } from "@/lib/metric-format"
import type { GradeLevelComparison } from "@/features/admin/api"

/**
 * Administrator overview.
 *
 * Every metric on this screen is an aggregate. NFR-010 requires administrators
 * to view student data in aggregated or anonymised form unless explicit consent
 * is given, and the endpoints used here honour that: `school-wide` returns
 * three scalars, `risk-distribution` returns four counts, and
 * `grade-levels/comparison` returns one average per grade level.
 *
 * PH11.9 removed the "Low-Performance Students" card this screen previously
 * carried. It called `/analytics/low-performance/`, which returns
 * `student_id` and `student_name` — named individual students. That endpoint
 * predates this screen and is neither extended nor changed here, but presenting
 * its output on an admin dashboard is exactly what NFR-010 rules out, so the
 * card is gone rather than relabelled. Nothing else in the admin surface calls
 * it. See `docs/PH11.9_NOTE.md` for the full finding.
 */
function AdminDashboard() {
  const { user } = useAuth()

  const metricsQuery = useSchoolWideMetrics()
  const riskDistQuery = useRiskDistribution()
  const comparisonQuery = useGradeLevelComparison()
  const attendanceTrendQuery = useSchoolWideAttendanceTrend()
  const periodOrder = useGradingPeriodOrder()

  // `null` means the backend reported no data for that metric; a real 0 is
  // passed through untouched and rendered as "0" / "0.00%".
  const overallGradeAvg = metricsQuery.data?.overall_grade_average ?? null
  const totalStudents = metricsQuery.data?.total_students ?? null
  const gradeLevels = metricsQuery.data?.grade_levels ?? null
  const risk = riskDistQuery.data ?? null

  if (!user) return null

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-2">
        <h2 className="text-2xl font-bold text-foreground">
          Administration Panel
        </h2>
        <Badge
          variant="outline"
          className="w-max max-w-full border-border bg-maroon-100 text-maroon-800"
        >
          <span className="truncate">{user.email}</span>
        </Badge>
        <p className="text-sm text-muted-foreground">
          School-wide aggregates only. Individual student records are not shown
          here.
        </p>
      </div>

      {/*
        PH11.11: one note for the whole metric row rather than one per tile.
        The three figures come from a single request, so a failure is a single
        event, and four identical alerts for one event would interrupt a screen
        reader four times.
      */}
      {metricsQuery.isError ? (
        <ErrorNote message="Unable to load the school-wide metrics. Please try again." />
      ) : null}

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        <MetricCard
          title="Overall Grade Average"
          hint="School-wide academic performance"
          isLoading={metricsQuery.isLoading}
          isError={metricsQuery.isError}
        >
          {formatPercent(overallGradeAvg, 2)}
        </MetricCard>

        <MetricCard
          title="Total Students"
          hint="Active student enrollments"
          isLoading={metricsQuery.isLoading}
          isError={metricsQuery.isError}
        >
          {formatCount(totalStudents)}
        </MetricCard>

        <MetricCard
          title="Grade Levels"
          hint="Active grade levels"
          isLoading={metricsQuery.isLoading}
          isError={metricsQuery.isError}
        >
          {formatCount(gradeLevels)}
        </MetricCard>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Risk Distribution</CardTitle>
        </CardHeader>
        <CardContent>
          {riskDistQuery.isLoading ? (
            <PendingRegion label="Risk distribution">
              <Skeleton className="h-8 w-3/4" />
            </PendingRegion>
          ) : risk ? (
            <>
              <div className="grid gap-4 md:grid-cols-3">
                <div className="rounded-md p-3 text-center">
                  <div className="text-lg font-bold text-success">
                    {formatCount(risk.distribution.low)}
                  </div>
                  <p className="text-xs text-success">Low Risk</p>
                </div>
                <div className="rounded-md p-3 text-center">
                  <div className="text-lg font-bold text-warning-foreground">
                    {formatCount(risk.distribution.moderate)}
                  </div>
                  <p className="text-xs text-warning-foreground">
                    Moderate Risk
                  </p>
                </div>
                <div className="rounded-md p-3 text-center">
                  <div className="text-lg font-bold text-destructive">
                    {formatCount(risk.distribution.high)}
                  </div>
                  <p className="text-xs text-destructive">High Risk</p>
                </div>
              </div>
              {/*
                RiskScore has no API surface, so `total_with_scores` is zero
                unless the risk engine has been run out of band. Showing all
                three buckets as 0 without saying so would read as "no student
                is at risk" rather than "the model has not been run".
              */}
              {risk.total_with_scores === 0 ? (
                <p className="mt-3 text-sm text-muted-foreground">
                  No computed risk scores are available. These counts come from
                  the risk-scoring engine, which has not been run for this
                  dataset. Recorded manual alerts are counted separately on the
                  Guidance risk-alerts page.
                </p>
              ) : null}
            </>
          ) : (
            /*
              PH11.11: the failure is reported as a failure, via `role="alert"`.
              It was a muted paragraph before, which is the one thing a failed
              request must not be: an unannounced muted line reads as "there is
              nothing here" rather than "the request failed", and it is
              indistinguishable from the genuine no-data case below it.
            */
            <ErrorNote
              message={
                riskDistQuery.isError
                  ? "Unable to load the risk distribution. Please try again."
                  : "No risk distribution data is available."
              }
            />
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Average by grade level</CardTitle>
        </CardHeader>
        <CardContent>
          <GradeLevelTable
            rows={comparisonQuery.data ?? []}
            isLoading={comparisonQuery.isLoading}
            error={
              comparisonQuery.isError
                ? "Unable to load the grade level comparison. Please try again."
                : null
            }
          />
        </CardContent>
      </Card>

      {/*
        Analytics folded into this dashboard: every chart below reads the same
        endpoints as the standalone Analytics page, so the two can never
        disagree. Kept in a compact two-column grid so the whole picture is
        visible without deep scrolling.
      */}
      <div className="grid gap-4 lg:grid-cols-2">
        <GradeLevelPerformanceChart />
        <AcademicTrendChart />
        <SubjectTrendChart periodOrder={periodOrder} />
        <ChartState
          isLoading={attendanceTrendQuery.isLoading}
          error={
            attendanceTrendQuery.isError ? attendanceTrendQuery.error : null
          }
          loadingLabel="Loading attendance trend"
          isEmpty={false}
          emptyMessage="No attendance has been recorded yet."
        >
          <AttendanceTrendChart days={attendanceTrendQuery.data?.days ?? []} />
        </ChartState>
        <RiskDistributionChart />
        <RoleDistributionChart />
      </div>
    </div>
  )
}

/**
 * One headline figure, with its three states kept distinct.
 *
 * PH11.11. The three tiles on this screen were hand-rolled and each had already
 * drifted: all three keyed the placeholder off `isFetching`, which stays true
 * during a *refetch*, so a background refresh replaced three real figures with
 * grey bars and then restored them — and neither state was announced. They also
 * had no failure state at all, so a failed request rendered `formatPercent(null)`
 * → "N/A", which claims the backend reported no figure rather than that nobody
 * knows.
 *
 * `isLoading` is `isPending && isFetching` in react-query v5, so it is true only
 * before the first result — a refetch over figures already on screen leaves them
 * alone, which is what a reader wants while reading them.
 */
function MetricCard({
  title,
  hint,
  isLoading,
  isError,
  children,
}: {
  title: string
  hint: string
  isLoading: boolean
  isError: boolean
  /** The formatted figure. Rendered only once the request has resolved. */
  children: React.ReactNode
}) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-sm font-medium">{title}</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="text-2xl font-bold">
          {isLoading ? (
            <PendingMetric label={title} />
          ) : isError ? (
            <UnavailableMetric />
          ) : (
            children
          )}
        </div>
        <p className="mt-1 text-xs text-muted-foreground">{hint}</p>
      </CardContent>
    </Card>
  )
}

function GradeLevelTable({
  rows,
  isLoading,
  error,
}: {
  rows: readonly GradeLevelComparison[]
  isLoading: boolean
  error: string | null
}) {
  const columns: readonly DataTableColumn<GradeLevelComparison>[] = [
    {
      key: "name",
      header: "Grade level",
      cell: (row) => (
        <span className="font-medium">{row.grade_level_name}</span>
      ),
    },
    {
      key: "average",
      header: "Average",
      cell: (row) => (
        <span className="font-bold">{formatPercent(row.average, 2)}</span>
      ),
    },
    {
      key: "count",
      header: "Grades counted",
      cell: (row) => (
        <span className="text-muted-foreground">
          {formatCount(row.grade_count)}
        </span>
      ),
    },
  ]

  return (
    <DataTable
      caption="Average grade by level"
      columns={columns}
      rows={rows}
      rowKey={(row) => row.grade_level_id}
      isLoading={isLoading}
      error={error}
      loadingLabel="Loading grade level comparison"
      emptyMessage="No finalized grades are available to compare yet."
    />
  )
}

export { AdminDashboard }

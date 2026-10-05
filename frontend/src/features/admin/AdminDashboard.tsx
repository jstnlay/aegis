import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { useAuth } from "@/features/auth/AuthContext"
import {
  useGradeLevelComparison,
  useRiskDistribution,
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
        <h1 className="text-2xl font-bold text-foreground">
          Administration Panel
        </h1>
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

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">
              Overall Grade Average
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {metricsQuery.isFetching ? (
                <Skeleton className="h-8 w-20" />
              ) : (
                formatPercent(overallGradeAvg, 2)
              )}
            </div>
            <p className="mt-1 text-xs text-muted-foreground">
              School-wide academic performance
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">
              Total Students
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {metricsQuery.isFetching ? (
                <Skeleton className="h-8 w-20" />
              ) : (
                formatCount(totalStudents)
              )}
            </div>
            <p className="mt-1 text-xs text-muted-foreground">
              Active student enrollments
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Grade Levels</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {metricsQuery.isFetching ? (
                <Skeleton className="h-8 w-20" />
              ) : (
                formatCount(gradeLevels)
              )}
            </div>
            <p className="mt-1 text-xs text-muted-foreground">
              Active grade levels
            </p>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Risk Distribution</CardTitle>
        </CardHeader>
        <CardContent>
          {riskDistQuery.isFetching ? (
            <div className="space-y-2">
              <Skeleton className="h-8 w-3/4" />
            </div>
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
            <p className="text-sm text-muted-foreground">
              {riskDistQuery.isError
                ? "Unable to load the risk distribution. Please try again."
                : "No risk distribution data available"}
            </p>
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
    </div>
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

import { BellRing, ShieldAlert, TriangleAlert, Users } from "lucide-react"

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { ErrorNote } from "@/components/feedback/Feedback"
import { MetricCard } from "@/components/ui/metric-card"
import { RiskDistributionChart } from "@/components/charts/RiskDistributionChart"
import { RiskAlertTrendChart } from "@/components/charts/RiskAlertTrend"
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
 * Risk first, following the Administration reference: four school-wide counts
 * (students, at-risk, high risk, unresolved alerts), the risk distribution, and
 * a 30-day alert trend. Every figure is an aggregate.
 *
 * NFR-010 requires administrators to view student data in aggregated or
 * anonymised form unless explicit consent is given. The reference's "Recent
 * Alerts" and "Top At-Risk Students" lists name individual students, so they
 * are deliberately not present; the counts above and the distribution carry the
 * same state without identifying anyone. `docs/PH11.9_NOTE.md` records the
 * earlier removal of a named low-performance card for the same reason.
 *
 * The grade-level table stays. It is the one academic aggregate not repeated on
 * the Analytics page, and the previous embedded chart grid was removed because
 * that page already renders all of it.
 */
function AdminDashboard() {
  const { user } = useAuth()

  const metricsQuery = useSchoolWideMetrics()
  const comparisonQuery = useGradeLevelComparison()
  const riskQuery = useRiskDistribution()

  // `null` means the backend reported no data for that metric; a real 0 is
  // passed through untouched and rendered as "0" / "0.00%".
  const totalStudents = metricsQuery.data?.total_students ?? null
  const distribution = riskQuery.data?.distribution
  const atRiskStudents = distribution
    ? distribution.moderate + distribution.high
    : null
  const highRiskStudents = distribution ? distribution.high : null

  if (!user) return null

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-1">
        <h2 className="text-2xl font-bold text-foreground">
          Administration Panel
        </h2>
        <p className="text-sm text-muted-foreground">
          School-wide aggregates only. Individual student records are not shown
          here.
        </p>
      </div>

      {metricsQuery.isError ? (
        <ErrorNote message="Unable to load the school-wide metrics. Please try again." />
      ) : null}
      {riskQuery.isError ? (
        <ErrorNote message="Unable to load the risk overview. Please try again." />
      ) : null}

      <div className="grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-4">
        <MetricCard
          title="Total Students"
          hint="Active student enrollments"
          icon={Users}
          isLoading={metricsQuery.isLoading}
          isError={metricsQuery.isError}
        >
          {formatCount(totalStudents)}
        </MetricCard>

        <MetricCard
          title="At-Risk Students"
          hint="Latest score moderate or high"
          icon={ShieldAlert}
          isLoading={riskQuery.isLoading}
          isError={riskQuery.isError}
        >
          {formatCount(atRiskStudents)}
        </MetricCard>

        <MetricCard
          title="High Risk Students"
          hint="Latest score at the high level"
          icon={TriangleAlert}
          isLoading={riskQuery.isLoading}
          isError={riskQuery.isError}
        >
          {formatCount(highRiskStudents)}
        </MetricCard>

        <MetricCard
          title="Active Alerts"
          hint="Alerts not yet resolved"
          icon={BellRing}
          isLoading={riskQuery.isLoading}
          isError={riskQuery.isError}
        >
          {formatCount(riskQuery.data?.active_alerts)}
        </MetricCard>
      </div>

      <div className="grid items-start gap-4 lg:grid-cols-2">
        <RiskDistributionChart />
        <RiskAlertTrendChart
          points={riskQuery.data?.alert_trend ?? []}
          isLoading={riskQuery.isLoading}
          error={riskQuery.isError ? riskQuery.error : null}
        />
      </div>

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

import {
  BellRing,
  BookOpen,
  GraduationCap,
  ShieldAlert,
  TriangleAlert,
  Users,
} from "lucide-react"

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
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
    <div className="admin-dashboard space-y-6">
      <div className="admin-dashboard-heading flex flex-col gap-1">
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

      <div className="admin-dashboard-metrics grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-4">
        <MetricCard
          title="Total Students"
          className="admin-metric-card admin-metric-card--featured"
          hint="Active student enrollments"
          icon={Users}
          isLoading={metricsQuery.isLoading}
          isError={metricsQuery.isError}
        >
          {formatCount(totalStudents)}
        </MetricCard>

        <MetricCard
          title="At-Risk Students"
          className="admin-metric-card"
          hint="Latest score moderate or high"
          icon={ShieldAlert}
          isLoading={riskQuery.isLoading}
          isError={riskQuery.isError}
        >
          {formatCount(atRiskStudents)}
        </MetricCard>

        <MetricCard
          title="High Risk Students"
          className="admin-metric-card"
          hint="Latest score at the high level"
          icon={TriangleAlert}
          isLoading={riskQuery.isLoading}
          isError={riskQuery.isError}
        >
          {formatCount(highRiskStudents)}
        </MetricCard>

        <MetricCard
          title="Active Alerts"
          className="admin-metric-card admin-metric-card--soft"
          hint="Alerts not yet resolved"
          icon={BellRing}
          isLoading={riskQuery.isLoading}
          isError={riskQuery.isError}
        >
          {formatCount(riskQuery.data?.active_alerts)}
        </MetricCard>
      </div>

      <div className="admin-dashboard-charts grid items-start gap-4 lg:grid-cols-2">
        <RiskDistributionChart />
        <RiskAlertTrendChart
          points={riskQuery.data?.alert_trend ?? []}
          isLoading={riskQuery.isLoading}
          error={riskQuery.isError ? riskQuery.error : null}
        />
      </div>

      <Card className="admin-dashboard-table">
        <CardHeader className="admin-grade-summary-header">
          <div className="admin-grade-summary-heading">
            <span className="admin-grade-summary-icon" aria-hidden="true">
              <BookOpen />
            </span>
            <div>
              <CardTitle>Average by grade level</CardTitle>
              <CardDescription>
                Compare grade averages and the number of grades included.
              </CardDescription>
            </div>
          </div>
          {comparisonQuery.isSuccess ? (
            <Badge variant="outline" className="admin-grade-level-count">
              {comparisonQuery.data.length} grade{" "}
              {comparisonQuery.data.length === 1 ? "level" : "levels"}
            </Badge>
          ) : null}
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
      headerClassName: "admin-grade-name-column",
      cell: (row) => (
        <div className="admin-grade-name">
          <span aria-hidden="true">
            <GraduationCap />
          </span>
          <span>{row.grade_level_name}</span>
        </div>
      ),
    },
    {
      key: "average",
      header: "Average",
      headerClassName: "admin-grade-average-column",
      cell: (row) => (
        <div className="admin-grade-average">
          <span>{formatPercent(row.average, 2)}</span>
          {row.average !== null && Number.isFinite(row.average) ? (
            <span className="admin-grade-average-track" aria-hidden="true">
              <span
                style={{ width: `${Math.min(100, Math.max(0, row.average))}%` }}
              />
            </span>
          ) : null}
        </div>
      ),
    },
    {
      key: "count",
      header: "Grades counted",
      headerClassName: "admin-grade-count-column",
      cellClassName: "admin-grade-count-cell",
      cell: (row) => (
        <span className="admin-grade-count">
          {formatCount(row.grade_count)}
        </span>
      ),
    },
  ]

  return (
    <DataTable
      className="admin-grade-comparison"
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

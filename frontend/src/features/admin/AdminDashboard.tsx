import { ChartNoAxesColumn, Layers, Users } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { ErrorNote } from "@/components/feedback/Feedback"
import { MetricCard } from "@/components/ui/metric-card"
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
  const comparisonQuery = useGradeLevelComparison()
  const attendanceTrendQuery = useSchoolWideAttendanceTrend()
  const periodOrder = useGradingPeriodOrder()

  // `null` means the backend reported no data for that metric; a real 0 is
  // passed through untouched and rendered as "0" / "0.00%".
  const overallGradeAvg = metricsQuery.data?.overall_grade_average ?? null
  const totalStudents = metricsQuery.data?.total_students ?? null
  const gradeLevels = metricsQuery.data?.grade_levels ?? null

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
          icon={ChartNoAxesColumn}
          isLoading={metricsQuery.isLoading}
          isError={metricsQuery.isError}
        >
          {formatPercent(overallGradeAvg, 2)}
        </MetricCard>

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
          title="Grade Levels"
          hint="Active grade levels"
          icon={Layers}
          isLoading={metricsQuery.isLoading}
          isError={metricsQuery.isError}
        >
          {formatCount(gradeLevels)}
        </MetricCard>
      </div>

      {/*
        The three-number "Risk Distribution" card that used to sit here showed
        the same `/analytics/risk-distribution/` response as the donut rendered
        below — two presentations of one payload on one screen, above the chart
        that supersedes it. It is removed rather than restyled; the donut keeps
        the low/moderate/high/insufficient-data breakdown, the scored-student
        count in its footer, and the "engine has not produced scores yet" empty
        state that the card's zero caveat used to carry by hand.
      */}
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
 * The shared metric tile. The hand-rolled copy that lived here is gone since
 * this batch: PH11.11 introduced it on this screen to stop three tiles drifting,
 * and having introduced one definition, a sixth private copy in the same
 * codebase was the drift it was written to prevent. See `MetricCard`.
 */

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

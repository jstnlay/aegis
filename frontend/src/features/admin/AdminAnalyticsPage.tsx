import {
  ChartNoAxesColumn,
  GraduationCap,
  Layers,
  LayoutDashboard,
} from "lucide-react"
import { useState } from "react"

import { ErrorNote } from "@/components/feedback/Feedback"
import { Card, CardContent } from "@/components/ui/card"
import { MetricCard } from "@/components/ui/metric-card"
import { SearchableSelect } from "@/components/ui/searchable-select"
import { ChartState } from "@/components/charts/ChartCard"
import { GradeLevelPerformanceChart } from "@/components/charts/GradeLevelPerformanceChart"
import { RiskDistributionChart } from "@/components/charts/RiskDistributionChart"
import { RoleDistributionChart } from "@/components/charts/RoleDistributionChart"
import { SectionPerformanceChart } from "@/components/charts/SectionPerformanceChart"
import { SubjectTrendChart } from "@/components/charts/SubjectTrendChart"
import {
  AcademicTrendChart,
  AttendanceTrendChart,
} from "@/components/charts/TrendCharts"
import { Label } from "@/components/ui/label"
import {
  useGradingPeriodOrder,
  useSchoolWideAttendanceTrend,
  useSchoolWideMetrics,
  useSectionPerformance,
  useSections,
} from "@/features/admin/api"
import { formatCount, formatPercent } from "@/lib/metric-format"

/**
 * Administrator analytics.
 *
 * Every figure here is an aggregate. NFR-010 requires administrators to view
 * student data in aggregated or anonymised form unless explicit consent is
 * given, and these endpoints honour that: three school-wide scalars, four risk
 * counts (rendered on the dashboard), one average per grade level, one aggregate
 * per section. Nothing on this page identifies a student.
 *
 * `/analytics/low-performance/` is deliberately unused. It returns
 * `student_id` and `student_name` — named individuals — and is the one endpoint
 * in the analytics app that would make a student-level admin table possible. The
 * endpoint itself is unchanged; no admin screen calls it.
 */
export function AdminAnalyticsPage() {
  const [sectionId, setSectionId] = useState("")

  const schoolWideQuery = useSchoolWideMetrics()
  const periodOrder = useGradingPeriodOrder()
  const { list: sectionsQuery } = useSections()
  const sectionQuery = useSectionPerformance(sectionId || null)
  const attendanceTrendQuery = useSchoolWideAttendanceTrend()

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-1">
        <div className="flex items-center gap-3">
          <LayoutDashboard
            className="size-5 text-muted-foreground"
            aria-hidden="true"
          />
          <h2 className="text-2xl font-bold text-foreground">Analytics</h2>
        </div>
        <p className="text-sm text-muted-foreground">
          School-wide and section-level aggregates. No individual student record
          is shown on this screen.
        </p>
      </div>

      {/*
        PH11.11: the three headline figures had no state handling at all. They read
        `…?.total_students ?? null`, and `formatCount(null)` is "N/A" — so while the
        request was in flight, and after it failed, the page asserted three
        measurements that were never made. "N/A" is the right answer when the
        backend reports no figure; it is the wrong answer when there is no answer.
      */}
      {schoolWideQuery.isError ? (
        <ErrorNote message="Unable to load the school-wide metrics. Please try again." />
      ) : null}

      <div className="grid gap-4 md:grid-cols-3">
        <MetricCard
          title="Active students"
          hint="Enrolled students with an active record"
          icon={GraduationCap}
          isLoading={schoolWideQuery.isLoading}
          isError={schoolWideQuery.isError}
        >
          {formatCount(schoolWideQuery.data?.total_students ?? null)}
        </MetricCard>
        <MetricCard
          title="Overall grade average"
          hint="Mean of finalized grades"
          icon={ChartNoAxesColumn}
          isLoading={schoolWideQuery.isLoading}
          isError={schoolWideQuery.isError}
        >
          {formatPercent(
            schoolWideQuery.data?.overall_grade_average ?? null,
            2
          )}
        </MetricCard>
        <MetricCard
          title="Grade levels"
          hint="Distinct levels with records this school year"
          icon={Layers}
          isLoading={schoolWideQuery.isLoading}
          isError={schoolWideQuery.isError}
        >
          {formatCount(schoolWideQuery.data?.grade_levels ?? null)}
        </MetricCard>
      </div>

      {/*
        PH11.10. Each figure below also appears as a chart drawn from the same
        endpoint, so the number and the plot can never disagree: the chart reads
        the identical query result rather than fetching its own copy.
      */}
      <GradeLevelPerformanceChart />

      <AcademicTrendChart />

      <SubjectTrendChart periodOrder={periodOrder} />

      {/*
        The attendance trend is administrator-only, so it carries its own query
        state rather than being folded into a shared fetch. Loading and failure
        are handled here because the chart component is handed finished rows.
      */}
      <ChartState
        isLoading={attendanceTrendQuery.isLoading}
        error={attendanceTrendQuery.isError ? attendanceTrendQuery.error : null}
        loadingLabel="Loading attendance trend"
        isEmpty={false}
        emptyMessage="No attendance has been recorded yet."
      >
        <AttendanceTrendChart days={attendanceTrendQuery.data?.days ?? []} />
      </ChartState>

      <RiskDistributionChart />

      <RoleDistributionChart />

      <Card>
        <CardContent className="space-y-4 pt-6">
          <div className="space-y-1.5">
            <Label htmlFor="admin-analytics-section">Section performance</Label>
            <SearchableSelect
              id="admin-analytics-section"
              label="Section performance"
              value={sectionId}
              onChange={setSectionId}
              options={(sectionsQuery.data ?? []).map((section) => ({
                value: section.id,
                label: `${section.name} — ${section.grade_level_name}`,
              }))}
              placeholder="Select a section"
              searchPlaceholder="Search sections"
            />
          </div>

          <SectionPerformanceChart
            sectionId={sectionId || null}
            data={sectionQuery.data}
            isLoading={sectionQuery.isLoading}
            error={sectionQuery.isError ? sectionQuery.error : null}
          />
        </CardContent>
      </Card>
    </div>
  )
}

/**
 * The shared metric tile. The private copy that lived here is gone since this
 * batch: its own note describes the three-state split the shared component
 * enforces in one place, so keeping a sixth variant was drift for no gain.
 */

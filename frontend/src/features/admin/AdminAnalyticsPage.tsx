import {
  ChartNoAxesColumn,
  GraduationCap,
  Layers,
  LayoutDashboard,
  RefreshCw,
} from "lucide-react"
import { useState } from "react"
import { Link } from "react-router-dom"

import { ErrorNote } from "@/components/feedback/Feedback"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { MetricCard } from "@/components/ui/metric-card"
import { SearchableSelect } from "@/components/ui/searchable-select"
import { Tabs } from "@/components/ui/tabs"
import { ChartState } from "@/components/charts/ChartCard"
import { ForecastChart } from "@/components/charts/ForecastChart"
import { GradeLevelPerformanceChart } from "@/components/charts/GradeLevelPerformanceChart"
import { RiskAlertTrendChart } from "@/components/charts/RiskAlertTrend"
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
  useForecast,
  useGradingPeriodOrder,
  useRiskDistribution,
  useSchoolWideAttendanceTrend,
  useSchoolWideMetrics,
  useSectionPerformance,
  useSections,
  type ForecastMetric,
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
 * The screen is arranged the way the livestock analytics dashboard the client
 * cited is arranged: category tabs across the top, an analysis mode switch
 * underneath it, and a forecast range that only appears in the predictive
 * mode.
 *
 * - Descriptive: what has happened (the historical charts).
 * - Predictive: the recorded monthly series plus a dashed straight-line
 *   projection, with the coverage it was drawn from. A thin series answers
 *   "no estimate yet" rather than a projection drawn from noise.
 * - Prescriptive: live risk counts and the alert trend, with the follow-up
 *   actions those numbers call for.
 * - Surveillance: the health of the school right now (risk distribution and
 *   open alerts).
 *
 * `/analytics/low-performance/` is deliberately unused. It returns
 * `student_id` and `student_name` — named individuals — and is the one endpoint
 * in the analytics app that would make a student-level admin table possible. The
 * endpoint itself is unchanged; no admin screen calls it.
 */

type AnalysisMode =
  "descriptive" | "predictive" | "prescriptive" | "surveillance"
type CategoryTab = "academics" | "attendance" | "risk" | "sections"

const MODES: readonly { id: AnalysisMode; label: string; hint: string }[] = [
  {
    id: "descriptive",
    label: "Descriptive",
    hint: "What has happened",
  },
  {
    id: "predictive",
    label: "Predictive",
    hint: "What may happen",
  },
  {
    id: "prescriptive",
    label: "Prescriptive",
    hint: "What actions to take",
  },
  {
    id: "surveillance",
    label: "Surveillance",
    hint: "Health and risk right now",
  },
]

const FORECAST_RANGES = [1, 3, 6, 12] as const

/** The metric each category tab projects. */
const METRIC_BY_TAB: Record<CategoryTab, ForecastMetric> = {
  academics: "grade_average",
  attendance: "attendance_rate",
  risk: "risk_alerts",
  sections: "grade_average",
}

const METRIC_LABEL: Record<ForecastMetric, string> = {
  grade_average: "Overall grade average",
  attendance_rate: "Attendance rate",
  risk_alerts: "Risk alerts opened",
}

export function AdminAnalyticsPage() {
  const [mode, setMode] = useState<AnalysisMode>("descriptive")
  const [tab, setTab] = useState<CategoryTab>("academics")
  const [sectionId, setSectionId] = useState("")
  const [months, setMonths] = useState<number>(6)

  const schoolWideQuery = useSchoolWideMetrics()
  const periodOrder = useGradingPeriodOrder()
  const { list: sectionsQuery } = useSections()
  const sectionQuery = useSectionPerformance(sectionId || null)
  const attendanceTrendQuery = useSchoolWideAttendanceTrend()
  const riskQuery = useRiskDistribution()
  const metric = METRIC_BY_TAB[tab]
  const forecastQuery = useForecast(metric, months)

  const academicsContent = (
    <div className="space-y-6">
      <GradeLevelPerformanceChart />
      <AcademicTrendChart />
      <SubjectTrendChart periodOrder={periodOrder} />
    </div>
  )

  const attendanceContent = (
    <ChartState
      isLoading={attendanceTrendQuery.isLoading}
      error={attendanceTrendQuery.isError ? attendanceTrendQuery.error : null}
      loadingLabel="Loading attendance trend"
      isEmpty={false}
      emptyMessage="No attendance has been recorded yet."
    >
      <AttendanceTrendChart days={attendanceTrendQuery.data?.days ?? []} />
    </ChartState>
  )

  const riskContent = (
    <div className="space-y-6">
      <RiskDistributionChart />
      <RoleDistributionChart />
    </div>
  )

  const sectionsContent = (
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
  )

  const descriptiveContent = (
    <Tabs
      label="Analytics categories"
      value={tab}
      onValueChange={setTab}
      items={[
        { id: "academics", label: "Academics", content: academicsContent },
        { id: "attendance", label: "Attendance", content: attendanceContent },
        { id: "risk", label: "Risk & well-being", content: riskContent },
        { id: "sections", label: "Sections", content: sectionsContent },
      ]}
    />
  )

  const predictiveContent = (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="space-y-1.5">
              <CardTitle>{METRIC_LABEL[metric]}</CardTitle>
              <CardDescription>
                A straight-line projection of the monthly series, {months} month
                {months === 1 ? "" : "s"} ahead. It is a projection of what has
                been recorded, not a promise.
              </CardDescription>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <div className="space-y-1.5">
                <Label htmlFor="admin-forecast-range">Forecast range</Label>
                <select
                  id="admin-forecast-range"
                  value={months}
                  onChange={(event) => setMonths(Number(event.target.value))}
                  className="rounded-md border border-input bg-background px-3 py-2 text-sm"
                >
                  {FORECAST_RANGES.map((range) => (
                    <option key={range} value={range}>
                      {range} month{range === 1 ? "" : "s"}
                    </option>
                  ))}
                </select>
              </div>
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={forecastQuery.isFetching}
                onClick={() => {
                  void forecastQuery.refetch()
                }}
              >
                <RefreshCw className="size-4" aria-hidden="true" />
                {forecastQuery.isFetching ? "Refreshing…" : "Refresh"}
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          {forecastQuery.isError ? (
            <ErrorNote message="Unable to load the forecast. Please try again." />
          ) : forecastQuery.isLoading ? (
            <p className="text-sm text-muted-foreground">Loading forecast…</p>
          ) : forecastQuery.data?.insufficient_data ? (
            <div className="space-y-1">
              <p className="text-sm font-medium">No estimate yet</p>
              <p className="text-sm text-muted-foreground">
                {forecastQuery.data.reason ??
                  "Not enough months on record to project from."}
              </p>
            </div>
          ) : (
            <>
              <div className="grid grid-cols-2 gap-3 sm:gap-4 md:grid-cols-3">
                <MetricCard
                  title={`${METRIC_LABEL[metric]} in ${months} month${months === 1 ? "" : "s"}`}
                  hint={
                    forecastQuery.data?.trend === "up"
                      ? "Trending up over the recorded months"
                      : forecastQuery.data?.trend === "down"
                        ? "Trending down over the recorded months"
                        : "Flat over the recorded months"
                  }
                  icon={ChartNoAxesColumn}
                  isLoading={forecastQuery.isLoading}
                  isError={forecastQuery.isError}
                >
                  {forecastQuery.data?.unit === "percent"
                    ? formatPercent(forecastQuery.data.estimate ?? null, 2)
                    : formatCount(forecastQuery.data?.estimate ?? null)}
                </MetricCard>
                <MetricCard
                  title="Months on record"
                  hint="Monthly points the projection was drawn from"
                  icon={Layers}
                  isLoading={forecastQuery.isLoading}
                  isError={forecastQuery.isError}
                >
                  {formatCount(forecastQuery.data?.coverage.points ?? null)}
                </MetricCard>
                <MetricCard
                  title="Coverage"
                  hint="First and last month in the series"
                  icon={GraduationCap}
                  isLoading={forecastQuery.isLoading}
                  isError={forecastQuery.isError}
                >
                  <span className="font-mono text-sm">
                    {forecastQuery.data?.coverage.from ?? "—"} →{" "}
                    {forecastQuery.data?.coverage.to ?? "—"}
                  </span>
                </MetricCard>
              </div>

              <ForecastChart
                data={forecastQuery.data}
                isLoading={forecastQuery.isLoading}
                // This branch only renders after the query succeeded; a later
                // refetch failure flips the branch above to its error note.
                error={null}
              />
            </>
          )}
        </CardContent>
      </Card>
    </div>
  )

  const distribution = riskQuery.data?.distribution
  const flagged = distribution
    ? distribution.high + distribution.moderate
    : null
  const alertsLast30 = (riskQuery.data?.alert_trend ?? []).reduce(
    (total, point) => total + point.count,
    0
  )

  const prescriptiveContent = (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-3 sm:gap-4 md:grid-cols-4">
        <MetricCard
          title="High-risk learners"
          hint="Latest computed score is high"
          icon={ChartNoAxesColumn}
          isLoading={riskQuery.isLoading}
          isError={riskQuery.isError}
        >
          {formatCount(distribution?.high ?? null)}
        </MetricCard>
        <MetricCard
          title="Moderate-risk learners"
          hint="Latest computed score is moderate"
          icon={GraduationCap}
          isLoading={riskQuery.isLoading}
          isError={riskQuery.isError}
        >
          {formatCount(distribution?.moderate ?? null)}
        </MetricCard>
        <MetricCard
          title="Active alerts"
          hint="Alerts active or under monitoring"
          icon={Layers}
          isLoading={riskQuery.isLoading}
          isError={riskQuery.isError}
        >
          {formatCount(riskQuery.data?.active_alerts ?? null)}
        </MetricCard>
        <MetricCard
          title="Awaiting a score"
          hint="Too little data to compute risk"
          icon={ChartNoAxesColumn}
          isLoading={riskQuery.isLoading}
          isError={riskQuery.isError}
        >
          {formatCount(distribution?.insufficient_data ?? null)}
        </MetricCard>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <RiskDistributionChart />

        <Card>
          <CardHeader>
            <CardTitle>Follow-up plan</CardTitle>
            <CardDescription>
              Each action is derived from the counts beside it. No learner is
              named here.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <ChartState
              isLoading={riskQuery.isLoading}
              error={riskQuery.isError ? riskQuery.error : null}
              loadingLabel="Loading follow-up priorities"
              isEmpty={!distribution}
              emptyMessage="No risk scores have been computed yet, so there is no follow-up list to rank."
            >
              <ol className="space-y-5 text-sm">
                <li className="space-y-2">
                  <p>
                    <span className="font-medium">
                      Review {formatCount(flagged)} flagged learner
                      {flagged === 1 ? "" : "s"}.
                    </span>{" "}
                    Check the finalized grades and attendance behind each risk
                    score before the Guidance Office case conference.
                  </p>
                  <div className="flex flex-wrap gap-2">
                    <Button asChild variant="outline" size="sm">
                      <Link to="/app/admin/grades">Open grades</Link>
                    </Button>
                    <Button asChild variant="outline" size="sm">
                      <Link to="/app/admin/attendance">Open attendance</Link>
                    </Button>
                  </div>
                </li>
                <li className="space-y-2">
                  <p>
                    <span className="font-medium">
                      Close the data gap for{" "}
                      {formatCount(distribution?.insufficient_data ?? null)}{" "}
                      learner
                      {(distribution?.insufficient_data ?? 0) === 1 ? "" : "s"}.
                    </span>{" "}
                    A learner without enough finalized grades or attendance
                    records cannot be scored.
                  </p>
                  <Button asChild variant="outline" size="sm">
                    <Link to="/app/admin/data">Open imports &amp; exports</Link>
                  </Button>
                </li>
                <li className="space-y-2">
                  <p>
                    <span className="font-medium">
                      Check {formatCount(alertsLast30)} alert
                      {alertsLast30 === 1 ? "" : "s"} opened in the last 30
                      days.
                    </span>{" "}
                    Confirm the record trail for each change before acting on
                    it.
                  </p>
                  <Button asChild variant="outline" size="sm">
                    <Link to="/app/admin/audit">Open audit logs</Link>
                  </Button>
                </li>
              </ol>
            </ChartState>
          </CardContent>
        </Card>
      </div>

      <RiskAlertTrendChart
        points={riskQuery.data?.alert_trend ?? []}
        isLoading={riskQuery.isLoading}
        error={riskQuery.isError ? riskQuery.error : null}
      />
    </div>
  )

  const surveillanceContent = (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-3 sm:gap-4 md:grid-cols-3">
        <MetricCard
          title="Open risk alerts"
          hint="Alerts that are active or under monitoring"
          icon={ChartNoAxesColumn}
          isLoading={riskQuery.isLoading}
          isError={riskQuery.isError}
        >
          {formatCount(riskQuery.data?.active_alerts ?? null)}
        </MetricCard>
        <MetricCard
          title="Students with a stored risk score"
          hint="Latest computed risk score per student"
          icon={GraduationCap}
          isLoading={riskQuery.isLoading}
          isError={riskQuery.isError}
        >
          {formatCount(riskQuery.data?.total_with_scores ?? null)}
        </MetricCard>
        <MetricCard
          title="Alerts in the last 30 days"
          hint="Daily alert trend"
          icon={Layers}
          isLoading={riskQuery.isLoading}
          isError={riskQuery.isError}
        >
          {formatCount(
            (riskQuery.data?.alert_trend ?? []).reduce(
              (total, point) => total + point.count,
              0
            )
          )}
        </MetricCard>
      </div>
      <RiskDistributionChart />
    </div>
  )

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

      {schoolWideQuery.isError ? (
        <ErrorNote message="Unable to load the school-wide metrics. Please try again." />
      ) : null}

      <div className="grid grid-cols-2 gap-3 sm:gap-4 md:grid-cols-3">
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
        Analysis modes, the way the livestock dashboard the client cited
        arranges them. The mode decides what the screen answers, so it sits
        above the category tabs rather than inside them.
      */}
      <div
        role="group"
        aria-label="Analysis mode"
        className="flex flex-wrap gap-2"
      >
        {MODES.map((entry) => (
          <Button
            key={entry.id}
            type="button"
            size="sm"
            variant={mode === entry.id ? "default" : "outline"}
            aria-pressed={mode === entry.id}
            onClick={() => setMode(entry.id)}
          >
            {entry.label}
          </Button>
        ))}
      </div>

      {mode === "descriptive" ? descriptiveContent : null}
      {mode === "predictive" ? predictiveContent : null}
      {mode === "prescriptive" ? prescriptiveContent : null}
      {mode === "surveillance" ? surveillanceContent : null}
    </div>
  )
}

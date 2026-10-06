import { LayoutDashboard } from "lucide-react"
import { useState } from "react"

import { Card, CardContent } from "@/components/ui/card"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { GradeLevelPerformanceChart } from "@/components/charts/GradeLevelPerformanceChart"
import { SectionPerformanceChart } from "@/components/charts/SectionPerformanceChart"
import { SubjectTrendChart } from "@/components/charts/SubjectTrendChart"
import { Label } from "@/components/ui/label"
import {
  useGradingPeriodOrder,
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

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-1">
        <div className="flex items-center gap-3">
          <LayoutDashboard
            className="size-5 text-muted-foreground"
            aria-hidden="true"
          />
          <h1 className="text-2xl font-bold text-foreground">Analytics</h1>
        </div>
        <p className="text-sm text-muted-foreground">
          School-wide and section-level aggregates. No individual student record
          is shown on this screen.
        </p>
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        <MetricCard
          label="Active students"
          value={formatCount(schoolWideQuery.data?.total_students ?? null)}
        />
        <MetricCard
          label="Overall grade average"
          value={formatPercent(
            schoolWideQuery.data?.overall_grade_average ?? null,
            2
          )}
        />
        <MetricCard
          label="Grade levels"
          value={formatCount(schoolWideQuery.data?.grade_levels ?? null)}
        />
      </div>

      {/*
        PH11.10. Each figure below also appears as a chart drawn from the same
        endpoint, so the number and the plot can never disagree: the chart reads
        the identical query result rather than fetching its own copy.
      */}
      <GradeLevelPerformanceChart />

      <SubjectTrendChart periodOrder={periodOrder} />

      <Card>
        <CardContent className="space-y-4 pt-6">
          <div className="space-y-1.5">
            <Label htmlFor="admin-analytics-section">Section performance</Label>
            <Select value={sectionId} onValueChange={setSectionId}>
              <SelectTrigger id="admin-analytics-section">
                <SelectValue placeholder="Select a section" />
              </SelectTrigger>
              <SelectContent>
                {(sectionsQuery.data ?? []).map((section) => (
                  <SelectItem key={section.id} value={section.id}>
                    {section.name} — {section.grade_level_name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
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

function MetricCard({ label, value }: { label: string; value: string }) {
  return (
    <Card>
      <CardContent className="pt-6">
        <p className="text-sm font-medium text-muted-foreground">{label}</p>
        <p className="text-2xl font-bold">{value}</p>
      </CardContent>
    </Card>
  )
}


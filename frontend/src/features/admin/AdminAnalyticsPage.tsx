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
import { DataTable, type DataTableColumn } from "@/components/ui/data-table"
import { ErrorNote } from "@/components/feedback/Feedback"
import { Label } from "@/components/ui/label"
import {
  useGradeLevelComparison,
  useSchoolWideMetrics,
  useSectionPerformance,
  useSections,
  type GradeLevelComparison,
  type SectionPerformance,
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
  const comparisonQuery = useGradeLevelComparison()
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

      <Card>
        <CardContent className="pt-6">
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

          {sectionId ? (
            <SectionPerformancePanel
              data={sectionQuery.data}
              isLoading={sectionQuery.isLoading}
              error={
                sectionQuery.isError
                  ? "Unable to load this section's performance. Please try again."
                  : null
              }
            />
          ) : (
            <p className="text-sm text-muted-foreground">
              Select a section to see its aggregate.
            </p>
          )}
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

function SectionPerformancePanel({
  data,
  isLoading,
  error,
}: {
  data: SectionPerformance | undefined
  isLoading: boolean
  error: string | null
}) {
  if (isLoading) {
    return (
      <p
        role="status"
        aria-busy="true"
        className="text-sm text-muted-foreground"
      >
        Loading section performance…
      </p>
    )
  }
  if (error) return <ErrorNote message={error} />
  if (!data) return null

  return (
    <div className="grid gap-4 sm:grid-cols-3">
      <MetricCard
        label={`${data.section_name} average`}
        value={formatPercent(data.grade_average, 2)}
      />
      <MetricCard
        label="Students enrolled"
        value={formatCount(data.total_students)}
      />
      <MetricCard
        label="Finalized grades"
        value={formatCount(data.total_grades)}
      />
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

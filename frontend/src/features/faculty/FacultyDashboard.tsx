import { useMemo } from "react"
import { ClipboardList, LayoutGrid, Users } from "lucide-react"
import { Link } from "react-router-dom"

import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts"

import { ChartFrame } from "@/components/charts/ChartCard"
import {
  AXIS_COLOR,
  chartColor,
  formatCountValue,
  GRID_COLOR,
} from "@/components/charts/chart-config"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { ErrorNote, PendingRegion } from "@/components/feedback/Feedback"
import { MetricCard } from "@/components/ui/metric-card"
import { Skeleton } from "@/components/ui/skeleton"
import { useAuth } from "@/features/auth/AuthContext"
import {
  useFacultyDashboardStats,
  useFacultySections,
  useFacultySubjectAssignments,
} from "@/features/faculty/api"
import { formatCount } from "@/lib/metric-format"

/**
 * The shared metric tile. The private copy that lived here is gone since this
 * batch, for the reason its own doc comment gives: one definition, so five
 * dashboards cannot drift into six treatments of the same figure. See
 * `MetricCard`.
 */

function FacultyDashboard() {
  const { user } = useAuth()

  const statsQuery = useFacultyDashboardStats()
  const assignmentsQuery = useFacultySubjectAssignments()
  const sectionsQuery = useFacultySections()

  // `null` means the aggregate could not be measured at all; a real 0
  // (no pending work, no sections) is preserved and rendered as "0".
  const pendingTotal = useMemo<number | null>(() => {
    if (!statsQuery.data) return null
    return statsQuery.data.pending_grades + statsQuery.data.pending_submissions
  }, [statsQuery.data])

  if (!user) return null

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-2">
        <h2 className="text-2xl font-bold text-foreground">
          Faculty Dashboard
        </h2>
        <Badge
          variant="outline"
          className="w-max max-w-full border-border bg-maroon-100 text-maroon-800"
        >
          <span className="truncate">{user.email}</span>
        </Badge>
      </div>

      {/*
        PH11.11: one note for the metric row, then announced placeholders and a
        real failure state. The three tiles previously keyed off `isFetching` —
        true through a background refetch, so a refresh greyed out figures the
        reader was looking at — and had no failure state at all, printing "N/A"
        after a failed request, which claims the backend reported no figure rather
        than that nobody knows.
      */}
      {statsQuery.isError ? (
        <ErrorNote message="Unable to load the faculty statistics. Please try again." />
      ) : null}

      <div className="grid gap-4 md:grid-cols-3">
        <MetricCard
          title="Total Students"
          hint="Active enrollments across all sections"
          icon={Users}
          isLoading={statsQuery.isLoading}
          isError={statsQuery.isError}
        >
          {formatCount(statsQuery.data?.total_students ?? null)}
        </MetricCard>

        <MetricCard
          title="Pending Grades"
          hint={
            statsQuery.data
              ? `${statsQuery.data.pending_grades} drafts + ${statsQuery.data.pending_submissions} submissions`
              : "No data"
          }
          icon={ClipboardList}
          isLoading={statsQuery.isLoading}
          isError={statsQuery.isError}
        >
          {formatCount(pendingTotal)}
        </MetricCard>

        <MetricCard
          title="Sections"
          hint="Assigned teaching sections"
          icon={LayoutGrid}
          isLoading={sectionsQuery.isLoading}
          isError={sectionsQuery.isError}
        >
          {formatCount(sectionsQuery.data?.length ?? null)}
        </MetricCard>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Pending Grades</CardTitle>
        </CardHeader>
        <CardContent>
          {statsQuery.isLoading ? (
            <PendingRegion label="Pending grades">
              <Skeleton className="h-10 w-full" />
            </PendingRegion>
          ) : statsQuery.isError ? (
            <ErrorNote message="Unable to load pending grades. Please try again." />
          ) : statsQuery.data &&
            statsQuery.data.pending_grades +
              statsQuery.data.pending_submissions >
              0 ? (
            <PendingGradesChart
              drafts={statsQuery.data.pending_grades}
              submissions={statsQuery.data.pending_submissions}
            />
          ) : (
            <p className="text-sm text-muted-foreground">
              No pending grades — everything is finalized.
            </p>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Quick actions</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex flex-wrap gap-2">
            <Button asChild variant="outline" size="sm">
              <Link to="/app/academics">Encode a grade</Link>
            </Button>
            <Button asChild variant="outline" size="sm">
              <Link to="/app/attendance">Take attendance</Link>
            </Button>
            <Button asChild variant="outline" size="sm">
              <Link to="/app/faculty/advisory">Advisory class</Link>
            </Button>
            <Button asChild variant="outline" size="sm">
              <Link to="/app/faculty/import">Imports & exports</Link>
            </Button>
            <Button asChild variant="outline" size="sm">
              <Link to="/app/reports">Reports</Link>
            </Button>
          </div>
        </CardContent>
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Subject Assignments</CardTitle>
          </CardHeader>
          <CardContent>
            {assignmentsQuery.isLoading ? (
              <PendingRegion label="Subject assignments">
                <Skeleton className="h-10 w-full" />
              </PendingRegion>
            ) : assignmentsQuery.isError ? (
              <ErrorNote message="Unable to load subject assignments. Please try again." />
            ) : assignmentsQuery.data && assignmentsQuery.data.length > 0 ? (
              <ul className="max-h-72 space-y-2 overflow-y-auto pr-1">
                {assignmentsQuery.data.map((assignment, idx) => (
                  <li
                    key={idx}
                    className="flex items-center justify-between gap-2 rounded-md border p-3"
                  >
                    <div className="min-w-0">
                      <p className="truncate font-medium">
                        {assignment.subject_name}
                      </p>
                      <p className="truncate text-xs text-muted-foreground">
                        {assignment.subject_code} • {assignment.section_name}
                      </p>
                    </div>
                    <Badge variant="secondary" className="shrink-0">
                      {assignment.section_name}
                    </Badge>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-muted-foreground">
                No subject assignments found
              </p>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Sections Overview</CardTitle>
          </CardHeader>
          <CardContent>
            {sectionsQuery.isLoading ? (
              <PendingRegion label="Sections overview">
                <Skeleton className="h-10 w-full" />
              </PendingRegion>
            ) : sectionsQuery.isError ? (
              <ErrorNote message="Unable to load sections. Please try again." />
            ) : sectionsQuery.data && sectionsQuery.data.length > 0 ? (
              <ul className="max-h-72 space-y-2 overflow-y-auto pr-1">
                {sectionsQuery.data.map((section, idx) => (
                  <li
                    key={idx}
                    className="flex items-center justify-between gap-2 rounded-md border p-3"
                  >
                    <p className="min-w-0 truncate font-medium">
                      {section.name}
                    </p>
                    <p className="shrink-0 text-xs text-muted-foreground">
                      {section.grade_level_name}
                    </p>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-muted-foreground">No sections found</p>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}

/**
 * Drafts vs submissions, as two columns with the count printed above each.
 *
 * Two categories do not warrant a donut — a two-slice pie is decoration, not a
 * comparison — so this is the bar treatment with an axis that starts at zero
 * and counts readable without hovering.
 *
 * The six-pixel rows it replaced measured both numbers as a share of one
 * combined total, which drew "3 drafts and 12 submissions" as a 20/80 split of
 * a single quantity. They are two separate counts of pending work, and on a
 * chart with its own axis each column now carries its own value.
 */
function PendingGradesChart({
  drafts,
  submissions,
}: {
  drafts: number
  submissions: number
}) {
  const data = [
    { name: "Drafts", count: drafts },
    { name: "Submissions", count: submissions },
  ]

  return (
    <ChartFrame
      height={150}
      label={`Bar chart of pending grade work: ${drafts} drafts and ${submissions} submissions.`}
    >
      <ResponsiveContainer width="100%" height="100%">
        <BarChart
          data={data}
          margin={{ top: 20, right: 8, bottom: 8, left: 0 }}
        >
          <CartesianGrid
            vertical={false}
            stroke={GRID_COLOR}
            strokeDasharray="3 3"
          />
          <XAxis
            dataKey="name"
            tick={{ fill: AXIS_COLOR, fontSize: 12 }}
            tickLine={false}
            axisLine={{ stroke: GRID_COLOR }}
            minTickGap={8}
          />
          <YAxis
            tick={{ fill: AXIS_COLOR, fontSize: 12 }}
            tickLine={false}
            axisLine={false}
            width={40}
            allowDecimals={false}
          />
          <Tooltip
            cursor={{ fill: "var(--muted)", opacity: 0.4 }}
            content={({ active, payload, label }) => {
              if (!active || !payload?.length) return null
              const point = payload[0]!.payload as (typeof data)[number]
              return (
                <div className="rounded-md border border-border bg-background p-2 text-sm shadow-sm">
                  <p className="font-medium">{label}</p>
                  <p className="text-muted-foreground">
                    {formatCountValue(point.count)} pending
                  </p>
                </div>
              )
            }}
          />
          <Bar
            dataKey="count"
            name="Pending"
            fill={chartColor(0)}
            radius={[4, 4, 0, 0]}
            // Two bars in a full-width frame would each sprawl across half the
            // card; capped, they read as two columns instead of two walls.
            maxBarSize={120}
            isAnimationActive={false}
            label={{ position: "top", fill: AXIS_COLOR, fontSize: 12 }}
          />
        </BarChart>
      </ResponsiveContainer>
    </ChartFrame>
  )
}

export { FacultyDashboard }

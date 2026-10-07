import { useMemo } from "react"

import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import {
  ErrorNote,
  PendingMetric,
  PendingRegion,
  UnavailableMetric,
} from "@/components/feedback/Feedback"
import { Skeleton } from "@/components/ui/skeleton"
import { useAuth } from "@/features/auth/AuthContext"
import {
  useFacultyDashboardStats,
  useFacultySections,
  useFacultySubjectAssignments,
} from "@/features/faculty/api"
import { formatCount } from "@/lib/metric-format"

/**
 * One headline figure, with its three states kept distinct.
 *
 * PH11.11. Built to the same shape as the student, guidance and admin tiles so
 * the pattern has one definition across the role dashboards. See the note on the
 * guidance copy for what the previous hand-rolled version got wrong.
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
        <p className="text-xs text-muted-foreground mt-1">{hint}</p>
      </CardContent>
    </Card>
  )
}

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
          isLoading={statsQuery.isLoading}
          isError={statsQuery.isError}
        >
          {formatCount(pendingTotal)}
        </MetricCard>

        <MetricCard
          title="Sections"
          hint="Assigned teaching sections"
          isLoading={sectionsQuery.isLoading}
          isError={sectionsQuery.isError}
        >
          {formatCount(sectionsQuery.data?.length ?? null)}
        </MetricCard>
      </div>

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
            <ul className="space-y-2">
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
            <ul className="space-y-2">
              {sectionsQuery.data.map((section, idx) => (
                <li
                  key={idx}
                  className="flex items-center justify-between gap-2 rounded-md border p-3"
                >
                  <p className="min-w-0 truncate font-medium">{section.name}</p>
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
  )
}

export { FacultyDashboard }

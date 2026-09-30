import { useMemo } from "react"

import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { useAuth } from "@/features/auth/AuthContext"
import {
  useFacultyDashboardStats,
  useFacultySections,
  useFacultySubjectAssignments,
} from "@/features/faculty/api"
import { formatCount } from "@/lib/metric-format"

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
        <h1 className="text-2xl font-bold text-foreground">
          Faculty Dashboard
        </h1>
        <Badge
          variant="outline"
          className="w-max max-w-full border-border bg-maroon-100 text-maroon-800"
        >
          <span className="truncate">{user.email}</span>
        </Badge>
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">
              Total Students
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {statsQuery.isFetching ? (
                <Skeleton className="h-8 w-20" />
              ) : (
                formatCount(statsQuery.data?.total_students ?? null)
              )}
            </div>
            <p className="text-xs text-muted-foreground mt-1">
              Active enrollments across all sections
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">
              Pending Grades
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {statsQuery.isFetching ? (
                <Skeleton className="h-8 w-20" />
              ) : (
                formatCount(pendingTotal)
              )}
            </div>
            <p className="text-xs text-muted-foreground mt-1">
              {statsQuery.data
                ? `${statsQuery.data.pending_grades} drafts + ${statsQuery.data.pending_submissions} submissions`
                : "No data"}
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Sections</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {sectionsQuery.isFetching ? (
                <Skeleton className="h-8 w-20" />
              ) : (
                formatCount(sectionsQuery.data?.length ?? null)
              )}
            </div>
            <p className="text-xs text-muted-foreground mt-1">
              Assigned teaching sections
            </p>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Subject Assignments</CardTitle>
        </CardHeader>
        <CardContent>
          {assignmentsQuery.isFetching ? (
            <div className="space-y-2">
              <Skeleton className="h-10 w-full" />
            </div>
          ) : assignmentsQuery.isError ? (
            <p className="text-sm text-muted-foreground">
              Unable to load subject assignments. Please try again.
            </p>
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
          {sectionsQuery.isFetching ? (
            <div className="space-y-2">
              <Skeleton className="h-10 w-full" />
            </div>
          ) : sectionsQuery.isError ? (
            <p className="text-sm text-muted-foreground">
              Unable to load sections. Please try again.
            </p>
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

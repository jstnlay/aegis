import { useMemo } from "react"

import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import {
  ErrorNote,
  PendingMetric,
  PendingRegion,
  UnavailableMetric,
} from "@/components/feedback/Feedback"
import { Label } from "@/components/ui/label"
import { Skeleton } from "@/components/ui/skeleton"
import { useAuth } from "@/features/auth/AuthContext"
import {
  useStudentDashboardData,
  useStudentProfileId,
} from "@/features/student/api"
import { RecommendationsCard } from "@/features/student/RecommendationsCard"
import { formatCount, formatPercent } from "@/lib/metric-format"

/**
 * One headline figure, with its three states kept distinct.
 *
 * PH11.11. Identical in shape to the admin and guidance tiles and deliberately
 * built the same way, so the pattern has one definition across the five role
 * dashboards instead of five hand-rolled variants that drift — which is exactly
 * how the student tiles ended up printing "N/A" after a failed request.
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

export function StudentDashboard() {
  const { user } = useAuth()
  const profileQuery = useStudentProfileId()
  const profileError = profileQuery.isError
  const studentId = profileQuery.data || ""

  const {
    attendance,
    grades,
    periods,
    selectedPeriod,
    setSelectedPeriod,
    averageGrade,
    totalSubjects,
    loading,
    error,
  } = useStudentDashboardData(studentId)
  const dataLoading = loading || profileQuery.isLoading
  // `error` is `Error | null` — the failure object, not a boolean — so the
  // boolean the `MetricCard` prop requires is derived here rather than at each of
  // the four call sites, where `profileError || error` would have type-checked as
  // `true | Error | null`.
  const dataError = profileError || Boolean(error)

  const displayGrades = useMemo(() => {
    if (dataLoading) return Array(5).fill(null) as (typeof grades)[number][]
    if (error || !grades.length) return []
    return grades.slice(0, 5)
  }, [grades, dataLoading, error])

  if (!user) return null

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-2">
        <h2 className="text-2xl font-bold text-foreground">
          Student Dashboard
        </h2>
        <Badge
          variant="outline"
          className="w-max max-w-full border-border bg-maroon-100 text-maroon-800"
        >
          <span className="truncate">{user.email}</span>
        </Badge>
      </div>

      {/*
        PH11.11: the placeholder is announced and the failure is distinct from
        "no data". Both tiles previously fell back to `formatPercent(undefined)` →
        "N/A" on a failed request, which claims the backend reported no grade when
        it reported nothing at all — and the skeletons were silent.
      */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        <MetricCard
          title="Average Grade"
          hint="Overall academic performance"
          isLoading={dataLoading}
          isError={dataError}
        >
          {formatPercent(averageGrade, 2)}
        </MetricCard>

        <MetricCard
          title="Attendance Rate"
          hint={
            attendance
              ? `${attendance.present_days} present, ${attendance.absent_days} absent`
              : "No attendance records"
          }
          isLoading={dataLoading}
          isError={dataError}
        >
          {formatPercent(attendance?.attendance_rate, 1)}
        </MetricCard>

        <MetricCard
          title="Total Subjects"
          hint="Subjects with finalized grades"
          isLoading={dataLoading}
          isError={dataError}
        >
          {formatCount(totalSubjects)}
        </MetricCard>

        <Card className="col-span-1 md:col-span-2 lg:col-span-3">
          <CardHeader>
            <CardTitle>Academic Progress</CardTitle>
          </CardHeader>
          <CardContent>
            {dataLoading ? (
              // PH11.11: announced placeholder — the two grey bars carried no
              // state at all, so nothing said the section was still arriving.
              <PendingRegion label="Academic progress">
                <div className="space-y-2">
                  <Skeleton className="h-10 w-full" />
                  <Skeleton className="h-10 w-full" />
                </div>
              </PendingRegion>
            ) : dataError ? (
              // `ErrorNote` rather than a muted paragraph: this is a failure, and
              // it must not look like the "no grading period data" line below it.
              <ErrorNote message="Unable to load academic progress. Please try again." />
            ) : periods.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                No grading period data available
              </p>
            ) : (
              <div className="space-y-3">
                <div className="space-y-1.5">
                  <Label htmlFor="student-grading-period">Grading period</Label>
                  <select
                    id="student-grading-period"
                    value={selectedPeriod}
                    onChange={(e) => setSelectedPeriod(e.target.value)}
                    className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                  >
                    {periods.map((p) => (
                      <option key={p.period_name} value={p.period_name}>
                        {p.period_name} — Average:{" "}
                        {formatPercent(p.average_grade, 2)}
                      </option>
                    ))}
                  </select>
                </div>
                {displayGrades.length === 0 ? (
                  <p className="text-sm text-muted-foreground">
                    No finalized grades for {selectedPeriod}
                  </p>
                ) : (
                  <div className="space-y-2">
                    <p className="text-sm font-medium">Grades by Subject</p>
                    <ul className="space-y-2">
                      {displayGrades.map((grade) => (
                        <li
                          key={grade.subject_code}
                          className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-border p-2"
                        >
                          <span className="min-w-0 truncate font-medium">
                            {grade.subject_name}
                          </span>
                          <span
                            className={`shrink-0 font-bold ${
                              grade.score === null
                                ? "text-muted-foreground"
                                : grade.score >= 90
                                  ? "text-success"
                                  : grade.score >= 75
                                    ? "text-warning-foreground"
                                    : "text-destructive"
                            }`}
                          >
                            {formatPercent(grade.score, 2)}
                          </span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            )}
          </CardContent>
        </Card>

        <RecommendationsCard studentId={profileQuery.data ?? null} />
      </div>
    </div>
  )
}

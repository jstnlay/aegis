import { useMemo } from "react"

import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Label } from "@/components/ui/label"
import { Skeleton } from "@/components/ui/skeleton"
import { useAuth } from "@/features/auth/AuthContext"
import {
  useStudentDashboardData,
  useStudentProfileId,
} from "@/features/student/api"
import { formatCount, formatPercent } from "@/lib/metric-format"

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

  const displayGrades = useMemo(() => {
    if (dataLoading) return Array(5).fill(null) as (typeof grades)[number][]
    if (error || !grades.length) return []
    return grades.slice(0, 5)
  }, [grades, dataLoading, error])

  if (!user) return null

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-2">
        <h1 className="text-2xl font-bold text-foreground">
          Student Dashboard
        </h1>
        <Badge
          variant="outline"
          className="w-max max-w-full border-border bg-maroon-100 text-maroon-800"
        >
          <span className="truncate">{user.email}</span>
        </Badge>
      </div>

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Average Grade</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {dataLoading ? (
                <Skeleton className="h-8 w-20" />
              ) : (
                formatPercent(averageGrade, 2)
              )}
            </div>
            <p className="text-xs text-muted-foreground mt-1">
              Overall academic performance
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">
              Attendance Rate
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {dataLoading ? (
                <Skeleton className="h-8 w-20" />
              ) : (
                formatPercent(attendance?.attendance_rate, 1)
              )}
            </div>
            <p className="text-xs text-muted-foreground mt-1">
              {attendance
                ? `${attendance.present_days} present, ${attendance.absent_days} absent`
                : "No attendance records"}
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">
              Total Subjects
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {dataLoading ? (
                <Skeleton className="h-8 w-20" />
              ) : (
                formatCount(totalSubjects)
              )}
            </div>
            <p className="text-xs text-muted-foreground mt-1">
              Subjects with finalized grades
            </p>
          </CardContent>
        </Card>

        <Card className="col-span-1 md:col-span-2 lg:col-span-3">
          <CardHeader>
            <CardTitle>Academic Progress</CardTitle>
          </CardHeader>
          <CardContent>
            {dataLoading ? (
              <div className="space-y-2">
                <Skeleton className="h-10 w-full" />
                <Skeleton className="h-10 w-full" />
              </div>
            ) : profileError || error ? (
              <p className="text-sm text-muted-foreground">
                Unable to load academic progress. Please try again.
              </p>
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
      </div>
    </div>
  )
}

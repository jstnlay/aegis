import { useMemo, useState } from "react"

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
import { useLinkedStudents } from "@/features/parent/api"
import { useStudentDashboardData } from "@/features/student/api"
import { letterGradeBadgeClass } from "@/lib/grade-badge"
import { formatPercent } from "@/lib/metric-format"

/**
 * One headline figure, with its three states kept distinct.
 *
 * PH11.12. This page reads the same `useStudentDashboardData` hook as
 * `StudentDashboard` and presents the same two figures, so it was the one place
 * left where the identical data was rendered with a different treatment: silent
 * skeletons, a muted failure line sitting beside the empty line, and `N/A` after a
 * failed request. Two views of one record must not look like two different
 * features.
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

function ParentDashboard() {
  const { user } = useAuth()
  const [selectedChildId, setSelectedChildId] = useState<string>("")

  const linkedStudentsQuery = useLinkedStudents()
  const linkedStudents = useMemo(
    () => linkedStudentsQuery.data || [],
    [linkedStudentsQuery.data]
  )
  const studentsLoading = linkedStudentsQuery.isLoading
  const linkedStudentsError = linkedStudentsQuery.isError

  const {
    attendance,
    grades,
    allGrades,
    periods,
    selectedPeriod,
    setSelectedPeriod,
    averageGrade,
    loading: dataLoading,
    error: dataError,
  } = useStudentDashboardData(selectedChildId)

  const selectedStudent = useMemo(
    () => linkedStudents.find((s: { id: string }) => s.id === selectedChildId),
    [linkedStudents, selectedChildId]
  )

  if (!user) return null

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-2">
        <h2 className="text-2xl font-bold text-foreground">Parent Portal</h2>
        <Badge
          variant="outline"
          className="w-max max-w-full border-border bg-maroon-100 text-maroon-800"
        >
          <span className="truncate">{user.email}</span>
        </Badge>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Linked Students</CardTitle>
        </CardHeader>
        <CardContent>
          {studentsLoading ? (
            <PendingRegion label="Linked students">
              <Skeleton className="h-10 w-full" />
            </PendingRegion>
          ) : linkedStudentsError ? (
            <ErrorNote message="Unable to load linked students. Please try again." />
          ) : linkedStudents.length > 0 ? (
            <div className="space-y-2">
              <p className="text-sm text-muted-foreground">
                Select a child to view their dashboard:
              </p>
              <div className="grid gap-2 md:grid-cols-2 lg:grid-cols-3">
                {linkedStudents.map((student) => (
                  <button
                    key={student.id}
                    onClick={() => setSelectedChildId(student.id)}
                    aria-pressed={selectedChildId === student.id}
                    className={`flex items-center justify-between gap-2 rounded-md border p-3 text-left transition-colors ${
                      selectedChildId === student.id
                        ? "border-maroon-500 bg-maroon-50"
                        : "border-border hover:bg-muted"
                    }`}
                  >
                    <div className="min-w-0">
                      <p className="truncate font-medium">
                        {student.student_name}
                      </p>
                      <p className="truncate text-xs text-muted-foreground">
                        {student.section_name}
                      </p>
                    </div>
                    {selectedChildId === student.id && (
                      <Badge
                        variant="secondary"
                        className="shrink-0 bg-maroon-200 text-maroon-800"
                      >
                        Active
                      </Badge>
                    )}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">
              No linked students found. Please contact the school
              administration.
            </p>
          )}
        </CardContent>
      </Card>

      {selectedChildId && (
        <div className="animate-in fade-in slide-in-from-bottom-4 duration-500">
          <div className="mb-4">
            <h3 className="text-xl font-bold">
              {selectedStudent?.student_name ?? "Student"}&apos;s Dashboard
            </h3>
            <p className="text-sm text-muted-foreground">
              {selectedStudent?.section_name}
            </p>
          </div>

          <div className="grid gap-4 md:grid-cols-2">
            <MetricCard
              title="Average Grade"
              hint="Overall academic performance"
              isLoading={dataLoading}
              isError={Boolean(dataError)}
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
              isError={Boolean(dataError)}
            >
              {formatPercent(attendance?.attendance_rate, 1)}
            </MetricCard>
          </div>

          <Card className="mt-4">
            <CardHeader>
              <CardTitle>Academic Progress</CardTitle>
            </CardHeader>
            <CardContent>
              {dataLoading ? (
                <PendingRegion label="Academic progress">
                  <div className="space-y-3">
                    <Skeleton className="h-9 w-full" />
                    <Skeleton className="h-10 w-full" />
                    <Skeleton className="h-10 w-full" />
                  </div>
                </PendingRegion>
              ) : dataError ? (
                <ErrorNote message="Unable to load academic progress. Please try again." />
              ) : periods.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  No grading period data available
                </p>
              ) : (
                <div className="space-y-3">
                  <div className="space-y-1.5">
                    <Label htmlFor="parent-grading-period">
                      Grading period
                    </Label>
                    <select
                      id="parent-grading-period"
                      value={selectedPeriod}
                      onChange={(e) => setSelectedPeriod(e.target.value)}
                      className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                    >
                      {periods.map((period) => (
                        <option
                          key={period.period_name}
                          value={period.period_name}
                        >
                          {period.period_name} — Average:{" "}
                          {formatPercent(period.average_grade, 2)}
                        </option>
                      ))}
                    </select>
                  </div>

                  {grades.length === 0 ? (
                    <p className="text-sm text-muted-foreground">
                      No finalized grades for {selectedPeriod}
                    </p>
                  ) : (
                    <div className="space-y-2">
                      <p className="text-sm font-medium">Grades by Subject</p>
                      <ul className="space-y-2">
                        {grades.map((grade, idx) => (
                          <li
                            key={`${grade.subject_code}-${idx}`}
                            className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-border p-3"
                          >
                            <div className="min-w-0">
                              <p className="truncate font-medium">
                                {grade.subject_name}
                              </p>
                              <p className="truncate text-xs text-muted-foreground">
                                {grade.subject_code}
                              </p>
                            </div>
                            <div className="flex shrink-0 items-center gap-2">
                              <span className="font-bold text-foreground">
                                {formatPercent(grade.score, 2)}
                              </span>
                              <Badge
                                variant="secondary"
                                className={letterGradeBadgeClass(
                                  grade.letter_grade
                                )}
                              >
                                {grade.letter_grade?.trim() || "N/A"}
                              </Badge>
                            </div>
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              )}
            </CardContent>
          </Card>

          <Card className="mt-4">
            <CardHeader>
              <CardTitle>Recent Grades</CardTitle>
            </CardHeader>
            <CardContent>
              {dataLoading ? (
                <PendingRegion label="Recent grades">
                  <Skeleton className="h-10 w-full" />
                </PendingRegion>
              ) : dataError ? (
                <ErrorNote message="Unable to load grades. Please try again." />
              ) : allGrades.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  No finalized grades available
                </p>
              ) : (
                <ul className="space-y-3">
                  {allGrades.slice(0, 5).map((grade, idx) => (
                    <li
                      key={`${grade.subject_code}-${idx}`}
                      className="flex flex-wrap items-center justify-between gap-2 rounded-md border p-3"
                    >
                      <div className="min-w-0">
                        <p className="truncate font-medium">
                          {grade.subject_name}
                        </p>
                        <p className="truncate text-xs text-muted-foreground">
                          {grade.subject_code}
                          {grade.grading_period
                            ? ` • ${grade.grading_period}`
                            : ""}
                        </p>
                      </div>
                      <div className="flex shrink-0 items-center gap-2">
                        <span className="font-bold text-foreground">
                          {formatPercent(grade.score, 2)}
                        </span>
                        <Badge
                          variant="secondary"
                          className={letterGradeBadgeClass(grade.letter_grade)}
                        >
                          {grade.letter_grade?.trim() || "N/A"}
                        </Badge>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  )
}

export { ParentDashboard }

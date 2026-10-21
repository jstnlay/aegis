import { useEffect, useMemo, useState } from "react"
import { Link } from "react-router-dom"

import {
  StudentAcademicTrendChart,
  StudentAttendanceTrendChart,
} from "@/components/charts/StudentTrendCharts"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import {
  EmptyState,
  ErrorNote,
  PendingRegion,
} from "@/components/feedback/Feedback"
import { Label } from "@/components/ui/label"
import { MetricCard } from "@/components/ui/metric-card"
import { Skeleton } from "@/components/ui/skeleton"
import { useAuth } from "@/features/auth/AuthContext"
import { useLinkedStudents } from "@/features/parent/api"
import { useStudentDashboardData } from "@/features/student/api"
import { formatPercent } from "@/lib/metric-format"
import { scoreStatus, scoreStatusLabel } from "@/lib/score-status"

/**
 * One headline figure, with its three states kept distinct.
 *
 * PH11.12. This page reads the same `useStudentDashboardData` hook as
 * `StudentDashboard` and presents the same two figures, so it was the one place
 * left where the identical data was rendered with a different treatment: silent
 * skeletons, a muted failure line sitting beside the empty line, and `N/A` after a
 * failed request. Two views of one record must not look like two different
 * features.
 * The tile itself is now the shared `MetricCard`, for the same reason the
 * student page stopped keeping a private copy: one definition, no drift.
 */

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

  // A parent with one child should land on that child's record, not on a
  // prompt asking them to pick the only option. Runs only while nothing is
  // selected, so a deliberate choice is never overwritten.
  useEffect(() => {
    const first = linkedStudents[0]
    if (!selectedChildId && first) {
      setSelectedChildId(first.id)
    }
  }, [linkedStudents, selectedChildId])

  if (!user) return null

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-1">
        <h2 className="text-2xl font-bold text-foreground">Parent Portal</h2>
        <p className="text-sm text-muted-foreground">
          Follow your child&apos;s academic record.
        </p>
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
            /*
             * Chips, not a stack of cards: a parent with one child gets one
             * chip naming the child and the section, and a parent with several
             * switches between them in place. The child's name and section are
             * not repeated in a heading below, so the record is named once.
             */
            <div className="flex flex-wrap gap-2">
              {linkedStudents.map((student) => (
                <button
                  key={student.id}
                  type="button"
                  onClick={() => setSelectedChildId(student.id)}
                  aria-pressed={selectedChildId === student.id}
                  className={`rounded-full border px-3 py-1.5 text-left text-sm transition-colors ${
                    selectedChildId === student.id
                      ? "border-maroon-500 bg-maroon-50 text-maroon-900"
                      : "border-border hover:bg-muted"
                  }`}
                >
                  <span className="font-medium">{student.student_name}</span>
                  <span className="ml-2 text-xs text-muted-foreground">
                    {student.section_name}
                  </span>
                </button>
              ))}
            </div>
          ) : (
            <EmptyState message="No linked students found. Please contact the school administration." />
          )}
        </CardContent>
      </Card>

      {selectedChildId && (
        <div className="animate-in fade-in slide-in-from-bottom-4 duration-500">
          {/*
            PH11.16 (TC-PAR-08): the hint is state-aware for the same reason the
            Attendance Rate one already was. "N/A" plus a static sentence tells a
            parent the average is unavailable but never that the child simply has
            no finalized grades yet.
          */}
          <div className="grid grid-cols-2 gap-3 sm:gap-4">
            <MetricCard
              title="Average Grade"
              hint={
                dataError
                  ? "Could not load finalized grades"
                  : averageGrade === null
                    ? "No finalized grades yet"
                    : "Overall academic performance"
              }
              isLoading={dataLoading}
              isError={Boolean(dataError)}
            >
              {formatPercent(averageGrade, 2)}
            </MetricCard>

            <MetricCard
              title="Attendance Rate"
              hint={
                dataError
                  ? "Could not load attendance records"
                  : attendance
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
                <EmptyState message="No grading period data available." />
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
                    <EmptyState
                      message={`No finalized grades for ${selectedPeriod}.`}
                    />
                  ) : (
                    <div className="space-y-2">
                      <p className="text-sm font-medium">Grades by Subject</p>
                      {/*
                       * Subject, score, and whether it passes. The six-pixel
                       * bar that sat under each row repeated the printed
                       * number as a length and read as an unfinished rule, so
                       * it is gone; the passing mark is now stated in words,
                       * which the number alone never said and which colour
                       * alone must not be left to say.
                       */}
                      <ul className="space-y-2">
                        {grades.map((grade, idx) => {
                          const status = scoreStatus(grade.score)
                          return (
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
                              <span className="flex shrink-0 items-center gap-2">
                                <span
                                  className={`font-bold tabular-nums ${
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
                                <Badge
                                  variant={
                                    status === "below-passing"
                                      ? "destructive"
                                      : status === "passing"
                                        ? "secondary"
                                        : "outline"
                                  }
                                >
                                  {scoreStatusLabel(status)}
                                </Badge>
                              </span>
                            </li>
                          )
                        })}
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
                <EmptyState message="No finalized grades available." />
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
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>

          <Card className="mt-4">
            <CardHeader>
              <CardTitle>Guidance & Support</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-sm text-muted-foreground">
                Counseling sessions, intervention plans and behavioral notes for{" "}
                {selectedStudent?.student_name ?? "your child"} live on the
                support record.
              </p>
              <Link
                to="/app/parent/support"
                className="mt-3 inline-flex items-center rounded-md border border-border px-3 py-1.5 text-sm font-medium hover:bg-accent"
              >
                Open support record
              </Link>
            </CardContent>
          </Card>

          {/*
            The same two charts the student dashboard draws, over the same
            hooks. A parent's view of a child's record must not look like a
            different feature, and the student-scoped analytics endpoint
            already authorises a linked parent for exactly this student.
          */}
          {selectedChildId ? (
            <>
              <Card className="mt-4">
                <CardHeader>
                  <CardTitle>Academic Trend</CardTitle>
                </CardHeader>
                <CardContent>
                  <StudentAcademicTrendChart studentId={selectedChildId} />
                </CardContent>
              </Card>

              <Card className="mt-4">
                <CardHeader>
                  <CardTitle>Attendance Trend</CardTitle>
                </CardHeader>
                <CardContent>
                  <StudentAttendanceTrendChart studentId={selectedChildId} />
                </CardContent>
              </Card>
            </>
          ) : null}
        </div>
      )}
    </div>
  )
}

export { ParentDashboard }

import { useMemo, useState } from "react"
import { Link } from "react-router-dom"
import {
  ArrowUpRight,
  BookOpen,
  CalendarCheck,
  Check,
  ChevronRight,
  ClipboardCheck,
  HeartHandshake,
  TrendingUp,
  UsersRound,
} from "lucide-react"

import {
  StudentAcademicTrendChart,
  StudentAttendanceTrendChart,
} from "@/components/charts/StudentTrendCharts"
import { Badge } from "@/components/ui/badge"
import { GradeMeter } from "@/components/ui/grade-meter"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import {
  EmptyState,
  ErrorNote,
  PendingRegion,
} from "@/components/feedback/Feedback"
import { Label } from "@/components/ui/label"
import { MetricCard } from "@/components/ui/metric-card"
import { Skeleton } from "@/components/ui/skeleton"
import { useAuth } from "@/features/auth/AuthContext"
import { useLinkedStudents, useSelectedChild } from "@/features/parent/api"
import { useStudentDashboardData } from "@/features/student/api"
import { formatPercent } from "@/lib/metric-format"
import { scoreStatus, scoreStatusLabel } from "@/lib/score-status"
import {
  ParentSelectionPrompt,
  ParentStudentContext,
} from "./ParentStudentContext"

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
  const [expandedGradesFor, setExpandedGradesFor] = useState<string | null>(
    null
  )

  const linkedStudentsQuery = useLinkedStudents()
  const linkedStudents = useMemo(
    () => linkedStudentsQuery.data || [],
    [linkedStudentsQuery.data]
  )
  const { selectedChildId, setSelectedChildId } =
    useSelectedChild(linkedStudents)

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
  const gradesContext = JSON.stringify([selectedChildId, selectedPeriod])
  const gradesExpanded = expandedGradesFor === gradesContext
  const visibleGrades = gradesExpanded
    ? (grades ?? [])
    : (grades?.slice(0, 3) ?? [])

  if (!user) return null

  return (
    <div className="parent-page parent-dashboard space-y-6">
      <header className="parent-welcome">
        <div>
          <p className="parent-eyebrow">Parent & guardian portal</p>
          <h2>Your family portal</h2>
          <p>
            Choose a student to follow their learning, attendance and school
            support.
          </p>
        </div>
        <span className="parent-welcome-art" aria-hidden="true">
          <HeartHandshake strokeWidth={1.4} />
        </span>
      </header>

      <Card data-panel="students" className="parent-linked-students">
        <CardHeader>
          <CardTitle className="parent-card-title">
            <UsersRound aria-hidden="true" />
            Choose a student
          </CardTitle>
          <CardDescription>
            {selectedStudent
              ? "Choose another name to switch the record shown below."
              : "Select a name to open that student's school record."}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {studentsLoading ? (
            <PendingRegion label="Linked students">
              <Skeleton className="h-10 w-full" />
            </PendingRegion>
          ) : linkedStudentsError ? (
            <ErrorNote message="Unable to load linked students. Please try again." />
          ) : linkedStudents.length > 0 ? (
            <div
              className="parent-child-options"
              role="group"
              aria-label="Choose a student"
            >
              {linkedStudents.map((student) => (
                <button
                  key={student.id}
                  type="button"
                  onClick={() => setSelectedChildId(student.id)}
                  aria-pressed={selectedChildId === student.id}
                  className="parent-child-option"
                >
                  <span className="parent-student-avatar" aria-hidden="true">
                    {student.student_name
                      .trim()
                      .split(/\s+/)
                      .filter(
                        (_, index, names) =>
                          index === 0 || index === names.length - 1
                      )
                      .map((name) => name.charAt(0))
                      .join("")}
                  </span>
                  <span className="parent-student-details">
                    <strong>{student.student_name}</strong>
                    <span>
                      Section · {student.section_name || "Not assigned"}
                    </span>
                  </span>
                  <span className="parent-student-action" aria-hidden="true">
                    {selectedChildId === student.id ? (
                      <Check />
                    ) : (
                      <ChevronRight />
                    )}
                  </span>
                </button>
              ))}
            </div>
          ) : (
            <EmptyState message="No linked students found. Please contact the school administration." />
          )}
        </CardContent>
      </Card>

      {!studentsLoading &&
      !linkedStudentsError &&
      linkedStudents.length > 0 &&
      !selectedStudent ? (
        <ParentSelectionPrompt />
      ) : null}

      {selectedStudent && !studentsLoading && !linkedStudentsError && (
        <section
          className="parent-record"
          aria-label={`School record for ${selectedStudent?.student_name ?? "your child"}`}
        >
          <ParentStudentContext child={selectedStudent} />
          <nav className="parent-shortcuts" aria-label="Parent quick links">
            {[
              {
                to: "/app/parent/academics",
                label: "Grades & attendance",
                icon: BookOpen,
              },
              {
                to: "/app/parent/assessments",
                label: "Assessments",
                icon: ClipboardCheck,
              },
              {
                to: "/app/parent/support",
                label: "Guidance & support",
                icon: HeartHandshake,
              },
            ].map(({ to, label, icon: Icon }) => (
              <Link key={to} to={to}>
                <Icon aria-hidden="true" />
                <span>{label}</span>
                <ArrowUpRight aria-hidden="true" />
              </Link>
            ))}
          </nav>
          {/*
            PH11.16 (TC-PAR-08): the hint is state-aware for the same reason the
            Attendance Rate one already was. "N/A" plus a static sentence tells a
            parent the average is unavailable but never that the child simply has
            no finalized grades yet.
          */}
          <div className="parent-metrics">
            <MetricCard
              className="parent-metric parent-metric--grade"
              icon={BookOpen}
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
              className="parent-metric parent-metric--attendance"
              icon={CalendarCheck}
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

          <div className="parent-dashboard-columns">
            <Card data-panel="records" className="parent-progress">
              <CardHeader>
                <CardTitle className="parent-card-title">
                  <BookOpen aria-hidden="true" />
                  Academic Progress
                </CardTitle>
                <CardDescription>
                  Finalized subject grades for the grading period you choose.
                </CardDescription>
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
                    <div className="parent-period-filter space-y-1.5">
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
                        <ul
                          id="parent-dashboard-subjects"
                          className="parent-subject-list"
                        >
                          {visibleGrades.map((grade, idx) => {
                            const status = scoreStatus(grade.score)
                            return (
                              <li
                                key={`${grade.subject_code}-${idx}`}
                                className="parent-subject-row"
                              >
                                <div className="min-w-0">
                                  <p className="font-medium">
                                    {grade.subject_name}
                                  </p>
                                  <p className="text-xs text-muted-foreground">
                                    {grade.subject_code}
                                  </p>
                                </div>
                                <span className="parent-subject-result">
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
                                    status={status}
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
                                <GradeMeter
                                  score={grade.score}
                                  label={grade.subject_name}
                                />
                              </li>
                            )
                          })}
                        </ul>
                        {grades.length > 3 ? (
                          <button
                            type="button"
                            className="parent-action-link parent-subject-toggle"
                            aria-expanded={gradesExpanded}
                            aria-controls="parent-dashboard-subjects"
                            onClick={() =>
                              setExpandedGradesFor(
                                gradesExpanded ? null : gradesContext
                              )
                            }
                          >
                            {gradesExpanded
                              ? "Show less"
                              : `View more subjects (${grades.length - visibleGrades.length})`}
                            <ChevronRight aria-hidden="true" />
                          </button>
                        ) : null}
                      </div>
                    )}
                  </div>
                )}
              </CardContent>
            </Card>

            <Card data-panel="records" className="parent-recent-grades">
              <CardHeader>
                <CardTitle>Grade records</CardTitle>
                <CardDescription>
                  Latest recorded entries across all grading periods.
                </CardDescription>
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
                  <ul className="parent-recent-list">
                    {allGrades.slice(0, 5).map((grade, idx) => (
                      <li
                        key={`${grade.subject_code}-${idx}`}
                        className="parent-recent-row"
                      >
                        <div className="min-w-0">
                          <p className="font-medium">{grade.subject_name}</p>
                          <p className="text-xs text-muted-foreground">
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

            {/*
            The same two charts the student dashboard draws, over the same
            hooks. A parent's view of a child's record must not look like a
            different feature, and the student-scoped analytics endpoint
            already authorises a linked parent for exactly this student.
          */}
            {selectedChildId ? (
              <>
                <Card
                  data-panel="records"
                  className="parent-trend parent-trend--academic"
                >
                  <CardHeader>
                    <CardTitle className="parent-card-title">
                      <TrendingUp aria-hidden="true" />
                      Academic Trend
                    </CardTitle>
                    <CardDescription>
                      How the average grade changes across grading periods.
                    </CardDescription>
                  </CardHeader>
                  <CardContent>
                    <StudentAcademicTrendChart studentId={selectedChildId} />
                  </CardContent>
                </Card>

                <Card
                  data-panel="attendance"
                  className="parent-trend parent-trend--attendance"
                >
                  <CardHeader>
                    <CardTitle className="parent-card-title">
                      <CalendarCheck aria-hidden="true" />
                      Attendance Trend
                    </CardTitle>
                    <CardDescription>
                      Recorded attendance over time.
                    </CardDescription>
                  </CardHeader>
                  <CardContent>
                    <StudentAttendanceTrendChart studentId={selectedChildId} />
                  </CardContent>
                </Card>
              </>
            ) : null}
            <Card data-panel="notes" className="parent-support-callout">
              <CardHeader>
                <CardTitle className="parent-card-title">
                  <HeartHandshake aria-hidden="true" />
                  Guidance & Support
                </CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-sm text-muted-foreground">
                  View counselling sessions, school-recorded alerts and teacher
                  notes for {selectedStudent?.student_name ?? "your child"}.
                </p>
                <Link to="/app/parent/support" className="parent-action-link">
                  Open support record
                  <ArrowUpRight aria-hidden="true" />
                </Link>
              </CardContent>
            </Card>
          </div>
        </section>
      )}
    </div>
  )
}

export { ParentDashboard }

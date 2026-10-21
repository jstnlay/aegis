import { useMemo, useState } from "react"

import {
  StudentAcademicTrendChart,
  StudentAttendanceTrendChart,
} from "@/components/charts/StudentTrendCharts"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
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
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { MetricCard } from "@/components/ui/metric-card"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Skeleton } from "@/components/ui/skeleton"
import { useAuth } from "@/features/auth/AuthContext"
import {
  useNominateParent,
  useStudentDashboardData,
  useStudentProfileId,
} from "@/features/student/api"
import { RecommendationsCard } from "@/features/student/RecommendationsCard"
import { formatCount, formatPercent } from "@/lib/metric-format"
import { scoreStatus, scoreStatusLabel } from "@/lib/score-status"

/**
 * One headline figure, with its three states kept distinct.
 *
 * PH11.11. Identical in shape to the admin and guidance tiles and deliberately
 * built the same way, so the pattern has one definition across the five role
 * dashboards instead of five hand-rolled variants that drift — which is exactly
 * how the student tiles ended up printing "N/A" after a failed request.
 *
 * Since this batch the definition is the shared `MetricCard` above rather than
 * a per-page copy: the sixth copy of the same tile was the drift PH11.11 was
 * guarding against, made literal.
 */

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
      <div className="flex flex-col gap-1">
        <h2 className="text-2xl font-bold text-foreground">
          Student Dashboard
        </h2>
        <p className="text-sm text-muted-foreground">
          Your academic record at a glance.
        </p>
      </div>

      {/*
        PH11.11: the placeholder is announced and the failure is distinct from
        "no data". Both tiles previously fell back to `formatPercent(undefined)` →
        "N/A" on a failed request, which claims the backend reported no grade when
        it reported nothing at all — and the skeletons were silent.

        PH11.16 (TC-STU-03): the two academic tiles also had *static* hints, so
        an empty record rendered "N/A / Overall academic performance" — correct,
        but with nothing to say why. A bare "N/A" is an answer nobody can act on;
        the hint now names the state, the way Attendance Rate already did.
      */}
      <div className="grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-3">
        <MetricCard
          className="col-span-2 lg:col-span-1"
          title="Average Grade"
          hint={
            dataError
              ? "Could not load finalized grades"
              : averageGrade === null
                ? "No finalized grades yet"
                : "Overall academic performance"
          }
          isLoading={dataLoading}
          isError={dataError}
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
          isError={dataError}
        >
          {formatPercent(attendance?.attendance_rate, 1)}
        </MetricCard>

        <MetricCard
          title="Total Subjects"
          hint={
            dataError
              ? "Could not load finalized grades"
              : totalSubjects === null
                ? "No finalized grades yet"
                : "Subjects with finalized grades"
          }
          isLoading={dataLoading}
          isError={dataError}
        >
          {formatCount(totalSubjects)}
        </MetricCard>

        <Card className="col-span-2 lg:col-span-3">
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
              <EmptyState message="No grading period data available." />
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
                  <EmptyState
                    message={`No finalized grades for ${selectedPeriod}.`}
                  />
                ) : (
                  <div className="space-y-2">
                    <p className="text-sm font-medium">Grades by Subject</p>
                    {/*
                     * Each row is the subject, its score, and whether that
                     * score passes. This card used to carry a six-pixel bar
                     * under every row: the number was already printed beside
                     * it, so the bar repeated the same value as a length and
                     * read as an unfinished rule rather than a chart. The one
                     * thing the number does not say on its own — passes or not
                     * — is now a word, which is also what stops the meaning
                     * resting on colour alone.
                     */}
                    <ul className="space-y-2">
                      {displayGrades.map((grade) => {
                        const status = scoreStatus(grade.score)
                        return (
                          <li
                            key={grade.subject_code}
                            className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-border p-3"
                          >
                            <span className="min-w-0 truncate font-medium">
                              {grade.subject_name}
                            </span>
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

        <RecommendationsCard studentId={profileQuery.data ?? null} />

        <FamilyAccessCard />

        <Card className="col-span-2 lg:col-span-3">
          <CardHeader>
            <CardTitle>Academic Trend</CardTitle>
          </CardHeader>
          <CardContent>
            <StudentAcademicTrendChart studentId={profileQuery.data ?? null} />
          </CardContent>
        </Card>

        <Card className="col-span-2 lg:col-span-3">
          <CardHeader>
            <CardTitle>Attendance Trend</CardTitle>
          </CardHeader>
          <CardContent>
            <StudentAttendanceTrendChart
              studentId={profileQuery.data ?? null}
            />
          </CardContent>
        </Card>
      </div>
    </div>
  )
}

/**
 * Ask for a parent or guardian to have family access.
 *
 * A nomination is a request. The school reviews it and issues the
 * invitation, and the parent sets their own password when they accept it.
 * Nothing here grants access — the wording says so, because a student
 * should not think a submitted form has already shared their record.
 */
function FamilyAccessCard() {
  const nominate = useNominateParent()
  const [name, setName] = useState("")
  const [email, setEmail] = useState("")
  const [relationship, setRelationship] = useState("mother")

  const canSubmit =
    name.trim().length > 0 && email.trim().length > 0 && !nominate.isPending

  return (
    <Card className="col-span-2 lg:col-span-3">
      <CardHeader>
        <CardTitle>Family access</CardTitle>
        <CardDescription>
          Ask for a parent or guardian to be able to follow your academic
          record. The school reviews every request, and your parent sets their
          own password when they accept the invitation.
        </CardDescription>
      </CardHeader>
      <CardContent>
        {nominate.isSuccess ? (
          <p className="text-sm text-muted-foreground">
            The request was received. The school will review it and contact your
            parent with an invitation.
          </p>
        ) : (
          <div className="grid gap-3 sm:grid-cols-3">
            <div className="space-y-1.5">
              <Label htmlFor="family-name">Parent or guardian name</Label>
              <Input
                id="family-name"
                value={name}
                onChange={(event) => setName(event.target.value)}
                placeholder="Maria Cruz"
                disabled={nominate.isPending}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="family-email">Their email address</Label>
              <Input
                id="family-email"
                type="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                placeholder="maria@example.com"
                disabled={nominate.isPending}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="family-relationship">Relationship</Label>
              <Select value={relationship} onValueChange={setRelationship}>
                <SelectTrigger id="family-relationship">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="mother">Mother</SelectItem>
                  <SelectItem value="father">Father</SelectItem>
                  <SelectItem value="guardian">Guardian</SelectItem>
                  <SelectItem value="other">Other</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="sm:col-span-3">
              <Button
                size="sm"
                disabled={!canSubmit}
                onClick={() =>
                  nominate.mutate({
                    full_name: name.trim(),
                    email: email.trim(),
                    relationship,
                  })
                }
              >
                {nominate.isPending ? "Sending…" : "Request family access"}
              </Button>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

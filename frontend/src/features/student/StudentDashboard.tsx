import { useState } from "react"
import { Link } from "react-router-dom"
import {
  ArrowUpRight,
  BookOpen,
  CalendarCheck,
  CalendarDays,
  ClipboardCheck,
  GraduationCap,
  HeartHandshake,
  Sparkles,
  TrendingUp,
  UserRound,
} from "lucide-react"

import {
  StudentAcademicTrendChart,
  StudentAttendanceTrendChart,
} from "@/components/charts/StudentTrendCharts"
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
  useStudentEnrollment,
  useStudentProfileId,
} from "@/features/student/api"
import { RecommendationsCard } from "@/features/student/RecommendationsCard"
import { SubjectGradeCard } from "@/features/student/SubjectGradeCard"
import { StudentJournalBackdrop } from "./StudentJournalArtwork"
import { formatCount, formatPercent } from "@/lib/metric-format"

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
  const enrollmentQuery = useStudentEnrollment()
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

  const [subjectSelection, setSubjectSelection] = useState({
    period: "",
    code: "",
  })
  const selectedSubject =
    subjectSelection.period === selectedPeriod ? subjectSelection.code : ""
  if (!user) return null

  return (
    <div className="student-dashboard space-y-6">
      <StudentJournalBackdrop />
      <header className="student-welcome">
        <div className="student-welcome-copy">
          <p className="student-eyebrow">
            <Sparkles aria-hidden="true" className="size-3.5" /> Your learning
            space
          </p>
          <h2 className="text-2xl font-bold text-foreground">
            Welcome back
            {user.first_name?.trim() ? `, ${user.first_name.trim()}` : ""}!
          </h2>
          <p className="student-welcome-message">
            Keep up with your grades, attendance, and next steps.
          </p>
        </div>
        <div className="student-welcome-art" aria-hidden="true">
          <GraduationCap strokeWidth={1.5} />
          <Sparkles />
        </div>
      </header>

      <Card data-panel="profile" className="student-identity">
        <CardHeader>
          <CardTitle className="student-card-title">
            <UserRound aria-hidden="true" />
            My information
          </CardTitle>
          <CardDescription>
            Your basic school record. Ask the office to correct a detail that is
            wrong.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {enrollmentQuery.isLoading ? (
            <PendingRegion label="My information">
              <Skeleton className="h-16 w-full" />
            </PendingRegion>
          ) : enrollmentQuery.isError ? (
            <ErrorNote message="Unable to load your information. Please try again." />
          ) : !enrollmentQuery.data ? (
            <EmptyState message="No enrollment record yet." />
          ) : (
            <dl className="grid gap-3 text-sm sm:grid-cols-2 lg:grid-cols-3">
              <div>
                <dt className="text-muted-foreground">Name</dt>
                <dd className="font-medium">
                  {[user.first_name, user.last_name]
                    .filter(Boolean)
                    .join(" ") || "—"}
                </dd>
              </div>
              <div>
                <dt className="text-muted-foreground">Student ID</dt>
                <dd className="font-mono">{enrollmentQuery.data.student_id}</dd>
              </div>
              <div>
                <dt className="text-muted-foreground">Year level</dt>
                <dd className="font-medium">
                  {enrollmentQuery.data.grade_level_name || "—"}
                </dd>
              </div>
              <div>
                <dt className="text-muted-foreground">Section</dt>
                <dd className="font-medium">
                  {enrollmentQuery.data.section_name || "—"}
                </dd>
              </div>
              <div>
                <dt className="text-muted-foreground">Age</dt>
                <dd className="font-medium">
                  {enrollmentQuery.data.age === null
                    ? "—"
                    : enrollmentQuery.data.age}
                </dd>
              </div>
              <div>
                <dt className="text-muted-foreground">School year</dt>
                <dd className="font-medium">
                  {enrollmentQuery.data.academic_year_name || "—"}
                </dd>
              </div>
            </dl>
          )}
          <Button asChild variant="outline" size="sm" className="mt-4">
            <Link to="/app/account-settings">Edit profile</Link>
          </Button>
        </CardContent>
      </Card>

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
      <div className="student-dashboard-grid">
        <section className="student-overview" aria-label="Learning overview">
          <MetricCard
            className="student-metric student-metric--average"
            icon={GraduationCap}
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
            className="student-metric student-metric--attendance"
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
            isError={dataError}
          >
            {formatPercent(attendance?.attendance_rate, 1)}
          </MetricCard>

          <MetricCard
            className="student-metric student-metric--subjects"
            icon={BookOpen}
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
        </section>
        <nav className="student-shortcuts" aria-label="Student quick links">
          {[
            { to: "/app/academics", label: "Your grades", icon: BookOpen },
            { to: "/app/attendance", label: "Attendance", icon: CalendarCheck },
            {
              to: "/app/schedule",
              label: "Class schedule",
              icon: CalendarDays,
            },
            {
              to: "/app/student/assessments",
              label: "Assessments",
              icon: ClipboardCheck,
            },
          ].map(({ to, label, icon: Icon }) => (
            <Link key={to} to={to} className="student-shortcut">
              <Icon aria-hidden="true" />
              <span>{label}</span>
              <ArrowUpRight aria-hidden="true" />
            </Link>
          ))}
        </nav>
        <Card data-panel="records" className="student-progress">
          <CardHeader>
            <div className="student-progress-heading">
              <CardTitle className="student-card-title">
                <BookOpen aria-hidden="true" />
                Academic Progress
              </CardTitle>
              <CardDescription>
                Your finalized grades for the selected grading period.
              </CardDescription>
            </div>
            {!dataLoading && !dataError && periods.length > 0 ? (
              <div className="student-progress-filter space-y-1.5">
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
            ) : null}
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
              <div className="student-grade-viewer space-y-4">
                <p className="text-sm text-muted-foreground">
                  Select a subject card to view its grade.
                </p>
                {grades.length === 0 ? (
                  <EmptyState
                    message={`No finalized grades for ${selectedPeriod}.`}
                  />
                ) : (
                  <ul className="student-subject-grid">
                    {grades.map((grade) => (
                      <SubjectGradeCard
                        key={grade.subject_code}
                        name={grade.subject_name}
                        code={grade.subject_code}
                        score={grade.score}
                        selected={selectedSubject === grade.subject_code}
                        onSelect={() =>
                          setSubjectSelection({
                            period: selectedPeriod,
                            code:
                              selectedSubject === grade.subject_code
                                ? ""
                                : grade.subject_code,
                          })
                        }
                      />
                    ))}
                  </ul>
                )}{" "}
                <Link to="/app/academics" className="student-full-record">
                  View full grade record <ArrowUpRight aria-hidden="true" />
                </Link>
              </div>
            )}
          </CardContent>
        </Card>

        <section
          className="student-trends-row"
          aria-label="Your progress over time"
        >
          <Card
            data-panel="records"
            className="student-trend student-trend--academic"
          >
            <CardHeader>
              <CardTitle className="student-card-title">
                <TrendingUp aria-hidden="true" />
                Academic Trend
              </CardTitle>
              <CardDescription>
                How your average changes across grading periods.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <StudentAcademicTrendChart
                studentId={profileQuery.data ?? null}
              />
            </CardContent>
          </Card>

          <Card
            data-panel="attendance"
            className="student-trend student-trend--attendance"
          >
            <CardHeader>
              <CardTitle className="student-card-title">
                <CalendarCheck aria-hidden="true" />
                Attendance Trend
              </CardTitle>
              <CardDescription>
                Your recorded attendance over time.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <StudentAttendanceTrendChart
                studentId={profileQuery.data ?? null}
              />
            </CardContent>
          </Card>
        </section>
        <section
          className="student-support-row"
          aria-label="Learning support and family access"
        >
          <RecommendationsCard studentId={profileQuery.data ?? null} />
          <FamilyAccessCard />
        </section>
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
    <Card data-panel="notes" className="student-family">
      <CardHeader>
        <CardTitle className="student-card-title">
          <HeartHandshake aria-hidden="true" />
          Family access
        </CardTitle>
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
          <div className="student-family-fields grid gap-3 sm:grid-cols-3">
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

import { useId, useMemo } from "react"
import {
  ArrowUpRight,
  BookOpen,
  CalendarCheck,
  ClipboardCheck,
  ClipboardList,
  Download,
  NotebookPen,
  Users,
} from "lucide-react"
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
  formatCountValue,
  GRID_COLOR,
} from "@/components/charts/chart-config"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import {
  EmptyState,
  ErrorNote,
  PendingRegion,
} from "@/components/feedback/Feedback"
import { MetricCard } from "@/components/ui/metric-card"
import { Skeleton } from "@/components/ui/skeleton"
import { useAuth } from "@/features/auth/AuthContext"
import {
  useFacultyAttendanceSummary,
  useFacultyBehavioralNotes,
  useFacultyDashboardStats,
  useFacultySections,
  useFacultySubjectAssignments,
} from "@/features/faculty/api"
import { formatCount, formatPercent } from "@/lib/metric-format"
import { SubjectArt } from "@/features/student/SubjectArt"
import { getSubjectTheme } from "@/features/student/subject-appearance"
import { FacultyDeskArt } from "./FacultyDeskArt"
import { FacultyAttendancePanel } from "./FacultyAttendancePanel"

const NOTE_TYPE_LABELS = {
  positive: "Positive",
  warning: "Warning",
  incident: "Incident",
} as const

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
  const attendanceQuery = useFacultyAttendanceSummary()
  const notesQuery = useFacultyBehavioralNotes()

  // `null` means the aggregate could not be measured at all; a real 0
  // (no pending work, no sections) is preserved and rendered as "0".
  const pendingTotal = useMemo<number | null>(() => {
    if (!statsQuery.data) return null
    return statsQuery.data.pending_grades + statsQuery.data.pending_submissions
  }, [statsQuery.data])

  if (!user) return null

  const initials = user.first_name
    .trim()
    .split(/\s+/)
    .filter(Boolean)
    .map((part) => `${Array.from(part)[0]?.toLocaleUpperCase() ?? ""}.`)
    .join(" ")
  const teacherName = [initials, user.last_name.trim()]
    .filter(Boolean)
    .join(" ")

  return (
    <div className="faculty-page faculty-dashboard space-y-6">
      <header className="faculty-welcome">
        <div>
          <p className="faculty-eyebrow">HCCI · Teaching & learning</p>
          <h2 className="text-2xl font-bold text-foreground">
            <span className="faculty-greeting-lead">Welcome back,</span>{" "}
            <span className="faculty-greeting-name">
              <span className="faculty-greeting-title">Teacher</span>
              {teacherName ? (
                <>
                  {" "}
                  <span className="faculty-greeting-person">{teacherName}</span>
                </>
              ) : null}
            </span>
          </h2>
          <p className="text-sm text-muted-foreground">
            Make room for meaningful learning. Your classes, teaching tasks, and
            student progress—all in one place.
          </p>
          <div className="faculty-welcome-signature">
            <span aria-hidden="true" />
            <span>Your teaching workspace</span>
            <span className="faculty-welcome-divider" aria-hidden="true" />
            <span>His Care Christian Institute</span>
          </div>
        </div>
        <FacultyDeskArt />
      </header>

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

      <div className="faculty-metrics grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-4">
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
          title="Attendance"
          hint={
            attendanceQuery.data?.records
              ? `${attendanceQuery.data.present} present, ${attendanceQuery.data.late} late, ${attendanceQuery.data.absent} absent`
              : "No attendance recorded yet"
          }
          icon={CalendarCheck}
          isLoading={attendanceQuery.isLoading}
          isError={attendanceQuery.isError}
        >
          {formatPercent(attendanceQuery.data?.attendance_rate, 1)}
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
          title="Behavior Notes"
          hint={
            notesQuery.data
              ? `${notesQuery.data.total} note${notesQuery.data.total === 1 ? "" : "s"} for your students`
              : "No notes recorded yet"
          }
          icon={NotebookPen}
          isLoading={notesQuery.isLoading}
          isError={notesQuery.isError}
        >
          {formatCount(notesQuery.data?.total ?? null)}
        </MetricCard>
      </div>

      <div className="faculty-workspace-grid">
        <div className="faculty-main-column">
          <Card data-panel="actions" className="faculty-actions">
            <CardHeader className="faculty-actions-heading">
              <CardTitle>
                <span className="faculty-panel-icon" aria-hidden="true">
                  <ClipboardList />
                </span>
                <span>Quick actions</span>
              </CardTitle>
              <div className="faculty-panel-tools">
                <Link to="/app/faculty/import" className="faculty-reports-link">
                  <Download aria-hidden="true" /> Import / export
                </Link>
                <Link to="/app/reports" className="faculty-reports-link">
                  Reports <ArrowUpRight aria-hidden="true" />
                </Link>
              </div>
            </CardHeader>
            <CardContent className="faculty-action-grid">
              {[
                {
                  to: "/app/academics",
                  label: "Encode a grade",
                  detail: "Enter and review draft grades",
                  icon: BookOpen,
                },
                {
                  to: "/app/attendance",
                  label: "Take attendance",
                  detail: "Record your class attendance",
                  icon: CalendarCheck,
                },
                {
                  to: "/app/faculty/advisory",
                  label: "Advisory class",
                  detail: "View students and class records",
                  icon: Users,
                },
                {
                  to: "/app/faculty/assessments",
                  label: "Assessments",
                  detail: "Prepare questions and review results",
                  icon: ClipboardCheck,
                },
              ].map(({ to, label, detail, icon: Icon }) => (
                <Link key={label} to={to} className="faculty-action">
                  <span className="faculty-action-icon">
                    <Icon aria-hidden="true" />
                  </span>
                  <span>
                    <strong>{label}</strong>
                    <small>{detail}</small>
                  </span>
                  <ArrowUpRight aria-hidden="true" />
                </Link>
              ))}
            </CardContent>
          </Card>
          <Card data-panel="classes" className="faculty-classroom-board">
            <CardHeader className="faculty-classroom-heading">
              <CardTitle>
                <span className="faculty-panel-icon" aria-hidden="true">
                  <BookOpen />
                </span>
                <span>Subject Assignments</span>
              </CardTitle>
              <p className="text-sm text-muted-foreground">
                Your classrooms, ready for the next lesson.
              </p>
              {assignmentsQuery.data ? (
                <span className="faculty-class-count">
                  {assignmentsQuery.data.length} teaching assignment
                  {assignmentsQuery.data.length === 1 ? "" : "s"}
                </span>
              ) : null}
            </CardHeader>
            <CardContent>
              {assignmentsQuery.isLoading ? (
                <PendingRegion label="Subject assignments">
                  <Skeleton className="h-10 w-full" />
                </PendingRegion>
              ) : assignmentsQuery.isError ? (
                <ErrorNote message="Unable to load subject assignments. Please try again." />
              ) : assignmentsQuery.data && assignmentsQuery.data.length > 0 ? (
                <ul className="faculty-classrooms">
                  {assignmentsQuery.data.map((assignment) => (
                    <li
                      key={assignment.id}
                      className="faculty-classroom"
                      data-subject-theme={getSubjectTheme(
                        assignment.subject_name,
                        assignment.subject_code
                      )}
                    >
                      <div className="faculty-classroom-cover">
                        <SubjectArt
                          theme={getSubjectTheme(
                            assignment.subject_name,
                            assignment.subject_code
                          )}
                        />
                        <span className="faculty-classroom-code">
                          {assignment.subject_code}
                        </span>
                        <h4>{assignment.subject_name}</h4>
                        <p>{assignment.section_name}</p>
                      </div>
                      <div className="faculty-classroom-footer">
                        <span>
                          <BookOpen aria-hidden="true" /> Class records
                        </span>
                        <Link
                          to="/app/academics"
                          aria-label={`Open grade records for ${assignment.subject_name}, ${assignment.section_name}`}
                        >
                          Open <ArrowUpRight aria-hidden="true" />
                        </Link>
                      </div>
                    </li>
                  ))}
                </ul>
              ) : (
                <EmptyState message="No subject assignments found." />
              )}
            </CardContent>
          </Card>
        </div>
        <aside
          className="faculty-side-column"
          aria-label="Class overview and follow-up"
        >
          <FacultyAttendancePanel
            data={attendanceQuery.data}
            loading={attendanceQuery.isLoading}
            error={attendanceQuery.isError}
          />
          <Card data-panel="sections" className="faculty-sections-board">
            <CardHeader>
              <CardTitle>
                <span className="faculty-panel-icon" aria-hidden="true">
                  <Users />
                </span>
                <span>Sections Overview</span>
              </CardTitle>
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
                      <p className="min-w-0 font-medium">{section.name}</p>
                      <p className="shrink-0 text-xs text-muted-foreground">
                        {section.grade_level_name}
                      </p>
                    </li>
                  ))}
                </ul>
              ) : (
                <EmptyState message="No sections found." />
              )}
            </CardContent>
          </Card>
          <Card data-panel="pending" className="faculty-pending">
            <CardHeader>
              <CardTitle>
                <span className="faculty-panel-icon" aria-hidden="true">
                  <ClipboardList />
                </span>
                <span>Pending Grades</span>
              </CardTitle>
              <p className="text-sm text-muted-foreground">
                Draft records and submissions awaiting completion.
              </p>
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
                <EmptyState message="No pending grades — everything is finalized." />
              )}
            </CardContent>
          </Card>
        </aside>
        <Card data-panel="notes" className="faculty-notes">
          <CardHeader>
            <CardTitle>
              <span className="faculty-panel-icon" aria-hidden="true">
                <NotebookPen />
              </span>
              <span>Recent Notes</span>
            </CardTitle>
          </CardHeader>
          <CardContent>
            {notesQuery.isLoading ? (
              <PendingRegion label="Recent behavior notes">
                <Skeleton className="h-24 w-full" />
              </PendingRegion>
            ) : notesQuery.isError ? (
              <ErrorNote message="Unable to load behavior notes. Please try again." />
            ) : notesQuery.data && notesQuery.data.recent.length > 0 ? (
              <ul
                className="faculty-notes-list"
                aria-label="Recent student notes"
                tabIndex={0}
              >
                {notesQuery.data.recent.map((note) => (
                  <li
                    key={note.id}
                    className="rounded-md border border-border p-3"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <p className="min-w-0 truncate text-sm font-medium">
                        {note.student_name}
                      </p>
                      <Badge
                        status={note.note_type}
                        variant="secondary"
                        className="shrink-0"
                      >
                        {NOTE_TYPE_LABELS[note.note_type]}
                      </Badge>
                    </div>
                    <p className="mt-1 line-clamp-2 text-xs text-muted-foreground">
                      {note.note_text}
                    </p>
                    <p className="mt-1 text-xs text-muted-foreground">
                      {note.date_recorded}
                    </p>
                  </li>
                ))}
              </ul>
            ) : (
              <EmptyState message="No behavior notes recorded yet." />
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
  const gradientId = `faculty-grades-${useId().replaceAll(":", "")}`
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
          <defs>
            <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#cf9c64" />
              <stop offset="100%" stopColor="var(--primary)" />
            </linearGradient>
          </defs>
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
            fill={`url(#${gradientId})`}
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

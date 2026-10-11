import { Calendar } from "lucide-react"
import { useMemo, useState, type FormEvent } from "react"
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
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { SearchableSelect } from "@/components/ui/searchable-select"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Skeleton } from "@/components/ui/skeleton"
import {
  Table,
  TableBody,
  TableCaption,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { useEnrollmentsInSection, useSections } from "@/features/academics/api"
import {
  ATTENDANCE_STATUS_LABELS,
  useAttendanceRecords,
  useAttendanceSummary,
  useCreateAttendance,
  type AttendanceRecord,
  type AttendanceStatus,
  type AttendanceSummaryEntry,
} from "@/features/attendance/api"
import { useAuth } from "@/features/auth/AuthContext"
import { useStudentProfileId } from "@/features/student/api"
import { normalizeApiError } from "@/lib/error"

function PageHeading({
  title,
  description,
}: {
  title: string
  description: string
}) {
  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center gap-3">
        <Calendar className="size-5 text-muted-foreground" aria-hidden="true" />
        <h2 className="text-2xl font-bold text-foreground">{title}</h2>
      </div>
      <p className="text-sm text-muted-foreground">{description}</p>
    </div>
  )
}

function ErrorNote({ message }: { message: string }) {
  return (
    <div
      role="alert"
      className="flex items-start gap-2 rounded-md border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive"
    >
      <span>{message}</span>
    </div>
  )
}

function EmptyState({ message }: { message: string }) {
  return (
    <p className="py-6 text-center text-sm text-muted-foreground">{message}</p>
  )
}

const STATUS_OPTIONS: ReadonlyArray<{
  value: AttendanceStatus
  label: string
}> = [
  { value: "present", label: "Present" },
  { value: "late", label: "Late" },
  { value: "absent", label: "Absent" },
]

function StudentAttendance() {
  const profileQuery = useStudentProfileId()
  const studentId = profileQuery.data
  const recordsQuery = useAttendanceRecords({ student: studentId ?? undefined })
  const summaryQuery = useAttendanceSummary(studentId)

  const loading = profileQuery.isLoading || recordsQuery.isLoading

  return (
    <div className="space-y-6">
      <PageHeading
        title="Attendance"
        description="Your attendance history and totals by section."
      />

      {profileQuery.isError ? (
        <ErrorNote message={normalizeApiError(profileQuery.error).message} />
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle>Summary</CardTitle>
          <CardDescription>
            Your attendance rate by section, first — day-by-day records follow
            below.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {summaryQuery.isLoading ? (
            <Skeleton className="h-10 w-full" />
          ) : summaryQuery.isError ? (
            <ErrorNote
              message={normalizeApiError(summaryQuery.error).message}
            />
          ) : (summaryQuery.data ?? []).length === 0 ? (
            <EmptyState message="No attendance summary data." />
          ) : (
            <div className="space-y-4">
              {/*
                This used to be a row per section: the section name, its rate
                as text, and a six-pixel bar repeating that same rate as a
                length. The bar added no information the line above it lacked,
                and three near-equal hairlines read as "roughly the same" — the
                one comparison a chart should make easy.
                Stacking present/late/absent instead shows *why* a section's
                rate is what it is. The exact counts and the rate itself stay
                readable in the table below, so nothing here is hover-only.
              */}
              <SectionAttendanceChart sections={summaryQuery.data ?? []} />
              <Table scrollLabel="Attendance summary">
                {/*
                PH11.11. This table had no caption at all, so it had no accessible
                name — and the record table above it, once it gained one, would
                have been the only thing on the page that announced what it held.
                `scope="col"` and `whitespace-nowrap` on the counts follow the same
                reasoning as the record table: the numbers read better on one line
                and the headings have to be headers for the cells beneath them.
              */}
                <TableCaption className="sr-only">
                  Attendance totals by section
                </TableCaption>
                <TableHeader>
                  <TableRow>
                    <TableHead scope="col">Section</TableHead>
                    <TableHead scope="col" className="text-right">
                      Rate
                    </TableHead>
                    <TableHead scope="col" className="text-right">
                      Present
                    </TableHead>
                    <TableHead scope="col" className="text-right">
                      Late
                    </TableHead>
                    <TableHead scope="col" className="text-right">
                      Absent
                    </TableHead>
                    <TableHead scope="col" className="text-right">
                      Total
                    </TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {(summaryQuery.data ?? []).map((s, idx) => (
                    <TableRow key={idx}>
                      <TableCell>{s.section_name}</TableCell>
                      {/*
                        The rate moved here when the per-section bars went.
                        It is the figure the card is named for, and it had
                        lived only in a text line above a bar that repeated it.
                      */}
                      <TableCell className="text-right tabular-nums">
                        {attendanceRate(s)}%
                      </TableCell>
                      <TableCell className="text-right tabular-nums">
                        {s.present_count}
                      </TableCell>
                      <TableCell className="text-right tabular-nums">
                        {s.late_count}
                      </TableCell>
                      <TableCell className="text-right tabular-nums">
                        {s.absent_count}
                      </TableCell>
                      <TableCell className="text-right tabular-nums">
                        {s.total_records}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Records</CardTitle>
          <CardDescription>
            Day-by-day attendance records tied to you.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="space-y-2">
              <Skeleton className="h-10 w-full" />
              <Skeleton className="h-10 w-full" />
            </div>
          ) : recordsQuery.isError ? (
            <ErrorNote
              message={normalizeApiError(recordsQuery.error).message}
            />
          ) : (recordsQuery.data ?? []).length === 0 ? (
            <EmptyState message="No attendance records found." />
          ) : (
            <Table scrollLabel="Attendance records">
              <TableCaption className="sr-only">
                One record per student and date
              </TableCaption>
              <TableHeader>
                <TableRow>
                  <TableHead scope="col">Date</TableHead>
                  <TableHead scope="col">Section</TableHead>
                  <TableHead scope="col">Status</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {(recordsQuery.data ?? []).map((r) => (
                  <TableRow key={r.id}>
                    <TableCell className="whitespace-nowrap">
                      {r.date}
                    </TableCell>
                    <TableCell>{r.section_name}</TableCell>
                    <TableCell>{ATTENDANCE_STATUS_LABELS[r.status]}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  )
}

/**
 * A section's attendance rate, as a whole-number percentage.
 *
 * Late counts toward the rate — the student attended — and the breakdown
 * beside it keeps the late count separately visible so the two are never
 * conflated. A section with no records at all reports 0, which is the figure
 * the previous rows showed for the same case.
 */
function attendanceRate(entry: AttendanceSummaryEntry): number {
  const total = entry.total_records || 0
  if (total === 0) return 0
  return Math.round(((entry.present_count + entry.late_count) / total) * 100)
}

/** The same three series, and the same colours, as the school-wide trend. */
const ATTENDANCE_SERIES = [
  { key: "present", label: "Present", color: "var(--chart-2)" },
  { key: "late", label: "Late", color: "var(--chart-4)" },
  { key: "absent", label: "Absent", color: "var(--destructive)" },
] as const

/**
 * Attendance records per section, stacked by status.
 *
 * One chart for all sections rather than a bar each: the card's question is
 * comparative ("which section is behind, and why"), and stacked counts answer
 * it where a row of independent filled lengths did not. This mirrors
 * `AttendanceTrendChart` on the administrator dashboard — same series, same
 * colours — so the two attendance views read as one system.
 */
function SectionAttendanceChart({
  sections,
}: {
  sections: readonly AttendanceSummaryEntry[]
}) {
  const points = sections.map((entry) => ({
    name: entry.section_name,
    present: entry.present_count,
    late: entry.late_count,
    absent: entry.absent_count,
    rate: attendanceRate(entry),
  }))

  return (
    <div className="space-y-2">
      <ChartFrame
        height={220}
        label={`Stacked bar chart of attendance records by section. ${points
          .map(
            (point) =>
              `${point.name}: ${point.present} present, ${point.late} late, ${point.absent} absent, ${point.rate}% rate`
          )
          .join(". ")}.`}
      >
        <ResponsiveContainer width="100%" height="100%">
          <BarChart
            data={points}
            margin={{ top: 8, right: 8, bottom: 8, left: 0 }}
          >
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
              minTickGap={16}
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
                const point = payload[0]!.payload as (typeof points)[number]
                return (
                  <div className="rounded-md border border-border bg-background p-2 text-sm shadow-sm">
                    <p className="font-medium">{label}</p>
                    <p className="text-muted-foreground">Rate: {point.rate}%</p>
                    <p className="text-muted-foreground">
                      Present: {formatCountValue(point.present)}
                    </p>
                    <p className="text-muted-foreground">
                      Late: {formatCountValue(point.late)}
                    </p>
                    <p className="text-muted-foreground">
                      Absent: {formatCountValue(point.absent)}
                    </p>
                  </div>
                )
              }}
            />
            {ATTENDANCE_SERIES.map((series) => (
              <Bar
                key={series.key}
                dataKey={series.key}
                name={series.label}
                stackId="attendance"
                fill={series.color}
                isAnimationActive={false}
              />
            ))}
          </BarChart>
        </ResponsiveContainer>
      </ChartFrame>

      {/*
        The three colours mean nothing on their own, so the series are named
        here rather than left to a tooltip a touch user has to discover.
      */}
      <ul className="flex flex-wrap gap-x-4 gap-y-1">
        {ATTENDANCE_SERIES.map((series) => (
          <li
            key={series.key}
            className="flex items-center gap-1.5 text-xs text-muted-foreground"
          >
            <span
              aria-hidden="true"
              className="size-2.5 rounded-full"
              style={{ backgroundColor: series.color }}
            />
            {series.label}
          </li>
        ))}
      </ul>
    </div>
  )
}

function AttendanceRecordRow({ record }: { record: AttendanceRecord }) {
  return (
    <TableRow>
      <TableCell>{record.date}</TableCell>
      <TableCell>{record.student_name}</TableCell>
      <TableCell>{record.student_id_code}</TableCell>
      <TableCell>{record.section_name}</TableCell>
      <TableCell>{ATTENDANCE_STATUS_LABELS[record.status]}</TableCell>
      <TableCell>{record.recorded_by_name}</TableCell>
    </TableRow>
  )
}

/** Today as `YYYY-MM-DD` in local time, matching the `<input type="date">` value format. */
function todayIso(): string {
  const now = new Date()
  const month = String(now.getMonth() + 1).padStart(2, "0")
  const day = String(now.getDate()).padStart(2, "0")
  return `${now.getFullYear()}-${month}-${day}`
}

function FacultyAttendance() {
  const recordsQuery = useAttendanceRecords()
  const sectionsQuery = useSections()
  const create = useCreateAttendance()
  const records = useMemo(() => recordsQuery.data ?? [], [recordsQuery.data])

  const [sectionId, setSectionId] = useState("")
  const [studentId, setStudentId] = useState("")
  const [date, setDate] = useState("")
  const [status, setStatus] = useState<AttendanceStatus>("present")

  const sections = useMemo(() => sectionsQuery.data ?? [], [sectionsQuery.data])
  const enrollmentsQuery = useEnrollmentsInSection(sectionId || null)
  const enrollments = useMemo(
    () => enrollmentsQuery.data ?? [],
    [enrollmentsQuery.data]
  )

  // Evaluated once per mount, not per render, so a re-render mid-form cannot
  // shift the ceiling under a date the user already picked.
  const [maxDate] = useState(todayIso)
  const [bulkState, setBulkState] = useState<{
    running: boolean
    done: number
    failed: number
  } | null>(null)

  async function handleCreate(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    if (!studentId || !sectionId || !date) return
    try {
      await create.mutateAsync({
        student: studentId,
        section: sectionId,
        date,
        status,
      })
      setStudentId("")
      setDate("")
    } catch {
      // The error is surfaced from `create.isError` below; a duplicate
      // student/date conflict must never silently overwrite the existing row.
    }
  }

  /**
   * Bulk shortcut: mark every enrolled student present for the chosen
   * section and date. One request per student (the API takes single
   * records); already-recorded students fail with a conflict and are
   * counted, never overwritten. Individual corrections still go through
   * the single-record form above.
   */
  async function handleMarkAllPresent() {
    if (!sectionId || !date || enrollments.length === 0) return
    setBulkState({ running: true, done: 0, failed: 0 })
    let done = 0
    let failed = 0
    for (const enrollment of enrollments) {
      try {
        await create.mutateAsync({
          student: enrollment.student,
          section: sectionId,
          date,
          status: "present",
        })
        done += 1
      } catch {
        failed += 1
      }
      setBulkState({ running: true, done, failed })
    }
    setBulkState({ running: false, done, failed })
  }

  return (
    <div className="space-y-6">
      <PageHeading
        title="Attendance"
        description="Record attendance in your authorized sections and review existing records."
      />

      <Card>
        <CardHeader>
          <CardTitle>Take attendance</CardTitle>
          <CardDescription>
            Creates one record per student per date. Future dates are rejected.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleCreate} className="space-y-4">
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-1.5">
                <Label htmlFor="attendance-section">Section</Label>
                <SearchableSelect
                  id="attendance-section"
                  label="Section"
                  value={sectionId}
                  onChange={(value) => {
                    setSectionId(value)
                    // The previous student may not be enrolled in this section.
                    setStudentId("")
                  }}
                  options={sections.map((s) => ({
                    value: s.id,
                    label: s.name,
                  }))}
                  placeholder={
                    sections.length === 0
                      ? "No sections assigned"
                      : "Select a section"
                  }
                  searchPlaceholder="Search sections"
                  disabled={sectionsQuery.isLoading || sections.length === 0}
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="attendance-student">Student</Label>
                <SearchableSelect
                  id="attendance-student"
                  label="Student"
                  value={studentId}
                  onChange={setStudentId}
                  options={enrollments.map((enrollment) => ({
                    value: enrollment.student,
                    label: `${enrollment.student_name} — ${enrollment.student_id}`,
                  }))}
                  placeholder={
                    !sectionId
                      ? "Select a section first"
                      : enrollmentsQuery.isLoading
                        ? "Loading enrolled students"
                        : enrollments.length === 0
                          ? "No actively enrolled students"
                          : "Select a student"
                  }
                  searchPlaceholder="Search students"
                  disabled={!sectionId || enrollmentsQuery.isLoading}
                />
              </div>
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-1.5">
                <Label htmlFor="attendance-date">Date</Label>
                <Input
                  id="attendance-date"
                  type="date"
                  max={maxDate}
                  value={date}
                  onChange={(e) => setDate(e.target.value)}
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="attendance-status">Status</Label>
                <Select
                  value={status}
                  onValueChange={(v) => setStatus(v as AttendanceStatus)}
                >
                  <SelectTrigger id="attendance-status">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {STATUS_OPTIONS.map((o) => (
                      <SelectItem key={o.value} value={o.value}>
                        {o.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
            {create.isError ? (
              <ErrorNote message={normalizeApiError(create.error).message} />
            ) : create.isSuccess ? (
              <p className="text-sm text-muted-foreground" role="status">
                Attendance recorded. The records table below has been refreshed.
              </p>
            ) : null}

            <Button
              type="submit"
              disabled={create.isPending || !sectionId || !studentId || !date}
            >
              {create.isPending ? "Recording…" : "Record attendance"}
            </Button>
          </form>

          <div className="mt-4 border-t border-border pt-4">
            <div className="flex flex-wrap items-center gap-2">
              <Button
                type="button"
                variant="outline"
                disabled={
                  !sectionId ||
                  !date ||
                  enrollments.length === 0 ||
                  bulkState?.running === true
                }
                onClick={() => void handleMarkAllPresent()}
              >
                {bulkState?.running
                  ? `Marking… ${bulkState.done}/${enrollments.length}`
                  : "Mark all present for this section & date"}
              </Button>
            </div>
            {bulkState && !bulkState.running ? (
              <p className="mt-2 text-sm text-muted-foreground" role="status">
                Marked {bulkState.done} present
                {bulkState.failed > 0
                  ? `, ${bulkState.failed} already recorded and left untouched`
                  : ""}
                . Correct individuals with the form above.
              </p>
            ) : null}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Attendance records</CardTitle>
          <CardDescription>
            Records in your authorized sections. Each row shows who recorded it.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {recordsQuery.isLoading ? (
            <Skeleton className="h-10 w-full" />
          ) : recordsQuery.isError ? (
            <ErrorNote
              message={normalizeApiError(recordsQuery.error).message}
            />
          ) : records.length === 0 ? (
            <EmptyState message="No attendance records in your sections yet." />
          ) : (
            <Table scrollLabel="Attendance records">
              {/*
                PH11.11. No caption, no `scope`, and no `scrollLabel`. The last of
                those matters most on this table: six columns of a faculty view is
                the one hand-rolled table here wide enough to overflow a phone, and
                `scrollLabel` is what makes the overflow reachable from the
                keyboard rather than only by dragging. `nowrap` keeps the date and
                the ID on one line; the recorder's name is free text and wraps.
              */}
              <TableCaption className="sr-only">
                Attendance records in your sections
              </TableCaption>
              <TableHeader>
                <TableRow>
                  <TableHead scope="col">Date</TableHead>
                  <TableHead scope="col">Student</TableHead>
                  <TableHead scope="col">ID</TableHead>
                  <TableHead scope="col">Section</TableHead>
                  <TableHead scope="col">Status</TableHead>
                  <TableHead scope="col">Recorded by</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {(recordsQuery.data ?? []).map((r) => (
                  <AttendanceRecordRow key={r.id} record={r} />
                ))}
              </TableBody>
            </Table>
          )}

          <p className="mt-4 text-xs text-muted-foreground">
            Editing and deleting a record is not available in this view:{" "}
            <code className="font-mono">/accounts/me/</code> does not return the
            caller&rsquo;s FacultyProfile identifier, so this page cannot verify
            which records are yours. The API still enforces that only the
            original recorder can update or delete a record.
          </p>
        </CardContent>
      </Card>
    </div>
  )
}

export function AttendancePage() {
  const { user } = useAuth()
  if (!user) return null
  if (user.role === "faculty") return <FacultyAttendance />
  return <StudentAttendance />
}

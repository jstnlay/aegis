import { Calendar } from "lucide-react"
import { useMemo, useState, type FormEvent } from "react"

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
              {(summaryQuery.data ?? []).map((s, idx) => {
                const total = s.total_records || 0
                const rate =
                  total === 0
                    ? 0
                    : Math.round(
                        ((s.present_count + s.late_count) / total) * 100
                      )
                return (
                  <div key={idx} className="space-y-1">
                    <div className="flex items-center justify-between gap-2 text-sm">
                      <span className="min-w-0 truncate font-medium">
                        {s.section_name}
                      </span>
                      <span className="shrink-0 tabular-nums text-muted-foreground">
                        {rate}% · {s.present_count} present, {s.late_count}{" "}
                        late, {s.absent_count} absent
                      </span>
                    </div>
                    <div
                      role="img"
                      aria-label={`${s.section_name} attendance rate ${rate} percent`}
                      className="h-2 w-full overflow-hidden rounded-full bg-muted"
                    >
                      <div
                        className="h-full rounded-full bg-primary"
                        style={{ width: `${rate}%` }}
                      />
                    </div>
                  </div>
                )
              })}
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

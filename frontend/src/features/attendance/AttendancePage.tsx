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
        <h1 className="text-2xl font-bold text-foreground">{title}</h1>
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
          <CardTitle>Records</CardTitle>
          <CardDescription>Attendance records tied to you.</CardDescription>
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
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Date</TableHead>
                  <TableHead>Section</TableHead>
                  <TableHead>Status</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {(recordsQuery.data ?? []).map((r) => (
                  <TableRow key={r.id}>
                    <TableCell>{r.date}</TableCell>
                    <TableCell>{r.section_name}</TableCell>
                    <TableCell>{ATTENDANCE_STATUS_LABELS[r.status]}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
              <TableCaption>One record per student/date.</TableCaption>
            </Table>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Summary</CardTitle>
          <CardDescription>
            Bare array (no pagination). Multi-section students appear in
            multiple rows.
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
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Section</TableHead>
                  <TableHead className="text-right">Present</TableHead>
                  <TableHead className="text-right">Late</TableHead>
                  <TableHead className="text-right">Absent</TableHead>
                  <TableHead className="text-right">Total</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {(summaryQuery.data ?? []).map((s, idx) => (
                  <TableRow key={idx}>
                    <TableCell>{s.section_name}</TableCell>
                    <TableCell className="text-right">
                      {s.present_count}
                    </TableCell>
                    <TableCell className="text-right">{s.late_count}</TableCell>
                    <TableCell className="text-right">
                      {s.absent_count}
                    </TableCell>
                    <TableCell className="text-right">
                      {s.total_records}
                    </TableCell>
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
 * Read-only record row.
 *
 * There is intentionally no per-row action here. `record.recorded_by` is a
 * `FacultyProfile` UUID while `user.id` is a `User` UUID, and `/accounts/me/`
 * does not expose the caller's `FacultyProfile` — so the frontend cannot
 * establish ownership from verified data. Name comparison would be inference,
 * not identity, so it is not used. The backend's self-scoped
 * `PATCH`/`DELETE` guards remain in force; only the control is withheld.
 */
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
                <Select
                  value={sectionId}
                  onValueChange={(value) => {
                    setSectionId(value)
                    // The previous student may not be enrolled in this section.
                    setStudentId("")
                  }}
                  disabled={sectionsQuery.isLoading || sections.length === 0}
                >
                  <SelectTrigger id="attendance-section">
                    <SelectValue
                      placeholder={
                        sections.length === 0
                          ? "No sections assigned"
                          : "Select a section"
                      }
                    />
                  </SelectTrigger>
                  <SelectContent>
                    {sections.map((s) => (
                      <SelectItem key={s.id} value={s.id}>
                        {s.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="attendance-student">Student</Label>
                <Select
                  value={studentId}
                  onValueChange={setStudentId}
                  disabled={!sectionId || enrollmentsQuery.isLoading}
                >
                  <SelectTrigger id="attendance-student">
                    <SelectValue
                      placeholder={
                        !sectionId
                          ? "Select a section first"
                          : enrollmentsQuery.isLoading
                            ? "Loading enrolled students"
                            : enrollments.length === 0
                              ? "No actively enrolled students"
                              : "Select a student"
                      }
                    />
                  </SelectTrigger>
                  <SelectContent>
                    {enrollments.map((enrollment) => (
                      <SelectItem
                        key={enrollment.id}
                        value={enrollment.student}
                      >
                        {enrollment.student_name} — {enrollment.student_id}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
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
                <Label>Status</Label>
                <Select
                  value={status}
                  onValueChange={(v) => setStatus(v as AttendanceStatus)}
                >
                  <SelectTrigger>
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
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Date</TableHead>
                  <TableHead>Student</TableHead>
                  <TableHead>ID</TableHead>
                  <TableHead>Section</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Recorded by</TableHead>
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

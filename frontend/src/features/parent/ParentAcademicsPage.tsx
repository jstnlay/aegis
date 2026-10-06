import { useState } from "react"

import { Badge } from "@/components/ui/badge"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { DataTable, type DataTableColumn } from "@/components/ui/data-table"
import { useDataTablePagination } from "@/components/ui/data-table-pagination"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { useAuth } from "@/features/auth/AuthContext"
import {
  useChildAttendance,
  useChildAttendanceSummary,
  useChildGrades,
  useLinkedStudents,
  type LinkedStudent,
  type ParentGrade,
} from "@/features/parent/api"
import { letterGradeBadgeClass } from "@/lib/grade-badge"
import { formatCount, formatPercent } from "@/lib/metric-format"

/**
 * Parent's view of a child's academic record.
 *
 * Grades come from `GradeViewSet`, which scopes a parent to their linked
 * children; the `?student=` filter narrows to the selected child rather than
 * widening access. Attendance counts come from the `summary` action, which
 * returns a **bare array** rather than the paginated envelope — see
 * `@/features/parent/api`.
 *
 * Only finalized grades are requested. Draft and submitted grades are not
 * reportable to a guardian.
 */

const ATTENDANCE_FILTERS = [
  { value: "all", label: "All statuses" },
  { value: "present", label: "Present" },
  { value: "late", label: "Late" },
  { value: "absent", label: "Absent" },
] as const

export function ParentAcademicsPage() {
  const { user } = useAuth()
  const [selectedChildId, setSelectedChildId] = useState<string>("")
  const [statusFilter, setStatusFilter] = useState<string>("all")
  const [search, setSearch] = useState("")

  const linkedQuery = useLinkedStudents()
  const linked = linkedQuery.data ?? []
  const child: LinkedStudent | undefined = linked.find(
    (c) => c.id === selectedChildId
  )

  const gradesQuery = useChildGrades(selectedChildId || null)
  const summaryQuery = useChildAttendanceSummary(selectedChildId || null)
  const recordsQuery = useChildAttendance(selectedChildId || null)

  if (!user) return null

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-1">
        <h1 className="text-2xl font-bold text-foreground">Academic Record</h1>
        <p className="text-sm text-muted-foreground">
          Finalized grades and attendance for each of your linked children.
        </p>
      </div>

      <ChildPicker
        linked={linked}
        selectedId={selectedChildId}
        onSelect={setSelectedChildId}
        isLoading={linkedQuery.isLoading}
        error={linkedQuery.isError}
      />

      {child ? (
        <AcademicRecord
          key={child.id}
          child={child}
          grades={gradesQuery.data ?? []}
          gradesLoading={gradesQuery.isLoading}
          gradesError={gradesQuery.isError}
          summaryRows={summaryQuery.data ?? []}
          summaryLoading={summaryQuery.isLoading}
          records={recordsQuery.data ?? []}
          recordsLoading={recordsQuery.isLoading}
          recordsError={recordsQuery.isError}
          statusFilter={statusFilter}
          onStatusFilterChange={setStatusFilter}
          search={search}
          onSearchChange={setSearch}
        />
      ) : null}
    </div>
  )
}

function ChildPicker({
  linked,
  selectedId,
  onSelect,
  isLoading,
  error,
}: {
  linked: readonly LinkedStudent[]
  selectedId: string
  onSelect: (id: string) => void
  isLoading: boolean
  error: boolean
}) {
  if (isLoading) {
    return (
      <p
        role="status"
        aria-busy="true"
        className="text-sm text-muted-foreground"
      >
        Loading linked students…
      </p>
    )
  }
  if (error) {
    return (
      <div
        role="alert"
        className="rounded-md border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive"
      >
        Unable to load linked students. Please try again.
      </div>
    )
  }
  if (linked.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        No linked students were found. Please contact the school office.
      </p>
    )
  }

  return (
    <div className="space-y-1.5">
      <Label htmlFor="parent-academics-child">Student</Label>
      <Select value={selectedId} onValueChange={onSelect}>
        <SelectTrigger id="parent-academics-child">
          <SelectValue placeholder="Select a student" />
        </SelectTrigger>
        <SelectContent>
          {linked.map((student) => (
            <SelectItem key={student.id} value={student.id}>
              {student.student_name} — {student.section_name}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      {selectedId ? null : (
        <p className="text-xs text-muted-foreground">
          Select a student to see their record.
        </p>
      )}
    </div>
  )
}

function AcademicRecord({
  child,
  grades,
  gradesLoading,
  gradesError,
  summaryRows,
  summaryLoading,
  records,
  recordsLoading,
  recordsError,
  statusFilter,
  onStatusFilterChange,
  search,
  onSearchChange,
}: {
  child: LinkedStudent
  grades: readonly ParentGrade[]
  gradesLoading: boolean
  gradesError: boolean
  summaryRows: ReadonlyArray<{
    present_count: number
    late_count: number
    absent_count: number
    total_records: number
  }>
  summaryLoading: boolean
  records: readonly {
    id: string
    date: string
    status: "present" | "late" | "absent"
    section_name: string
  }[]
  recordsLoading: boolean
  recordsError: boolean
  statusFilter: string
  onStatusFilterChange: (value: string) => void
  search: string
  onSearchChange: (value: string) => void
}) {
  const withScores = grades.filter((g) => g.score !== null)
  const average =
    withScores.length > 0
      ? withScores.reduce((sum, g) => sum + Number(g.score ?? 0), 0) /
        withScores.length
      : null

  /*
   * The summary query drives this card only. It is deliberately kept separate
   * from the record query: PH11.10 fixed a defect where the record table was
   * handed the *summary* error, so a failed record request rendered as
   * "No attendance has been recorded yet." — an empty-success state asserting
   * something the API never said.
   */
  const present = summaryRows.reduce((s, r) => s + r.present_count, 0)
  const late = summaryRows.reduce((s, r) => s + r.late_count, 0)
  const absent = summaryRows.reduce((s, r) => s + r.absent_count, 0)
  const totalRecords = summaryRows.reduce((s, r) => s + r.total_records, 0)
  const attendanceRate =
    totalRecords > 0 ? ((present + late) / totalRecords) * 100 : null

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="text-xl font-bold">{child.student_name}</h2>
        <Badge variant="secondary">{child.section_name}</Badge>
        <Badge variant="outline">{child.student_id}</Badge>
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">Average grade</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {gradesLoading ? "—" : formatPercent(average, 2)}
            </div>
            <p className="mt-1 text-xs text-muted-foreground">
              Across {formatCount(withScores.length)} finalized{" "}
              {withScores.length === 1 ? "grade" : "grades"}
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">Attendance</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {summaryLoading
                ? "—"
                : summaryRows.length === 0
                  ? "—"
                  : formatPercent(attendanceRate, 1)}
            </div>
            <p className="mt-1 text-xs text-muted-foreground">
              {summaryLoading
                ? "Loading…"
                : summaryRows.length === 0
                  ? "No attendance summary available"
                  : `${present} present · ${late} late · ${absent} absent`}
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">
              Subjects graded
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {gradesLoading ? "—" : formatCount(grades.length)}
            </div>
            <p className="mt-1 text-xs text-muted-foreground">
              Finalized grade records
            </p>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Grades</CardTitle>
          <CardDescription>
            Only finalized grades are shown. Draft and submitted grades are not
            reportable.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <GradeTable
            grades={grades}
            isLoading={gradesLoading}
            error={
              gradesError ? "Unable to load grades. Please try again." : null
            }
            search={search}
            onSearchChange={onSearchChange}
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Attendance record</CardTitle>
          <CardDescription>
            Day-by-day attendance recorded by the class teacher.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="space-y-4">
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="space-y-1.5">
                <Label htmlFor="parent-attendance-status">Status</Label>
                <Select
                  value={statusFilter}
                  onValueChange={onStatusFilterChange}
                >
                  <SelectTrigger id="parent-attendance-status">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {ATTENDANCE_FILTERS.map((filter) => (
                      <SelectItem key={filter.value} value={filter.value}>
                        {filter.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
            <AttendanceTable
              records={records}
              statusFilter={statusFilter}
              isLoading={recordsLoading}
              error={
                recordsError
                  ? "Unable to load attendance records. Please try again."
                  : null
              }
            />
          </div>
        </CardContent>
      </Card>
    </div>
  )
}

function GradeTable({
  grades,
  isLoading,
  error,
  search,
  onSearchChange,
}: {
  grades: readonly ParentGrade[]
  isLoading: boolean
  error: string | null
  search: string
  onSearchChange: (value: string) => void
}) {
  const term = search.trim().toLowerCase()
  const filtered = term
    ? grades.filter((grade) =>
        [
          grade.subject_name,
          grade.subject_code,
          grade.grading_period_name ?? "",
        ]
          .join(" ")
          .toLowerCase()
          .includes(term)
      )
    : grades

  const { pagination, pageRows } = useDataTablePagination(
    filtered,
    10,
    `grades:${term}`
  )

  const columns: readonly DataTableColumn<ParentGrade>[] = [
    {
      key: "subject",
      header: "Subject",
      cell: (grade) => (
        <div className="min-w-0">
          <div className="font-medium">{grade.subject_name}</div>
          <div className="text-xs text-muted-foreground">
            {grade.subject_code}
          </div>
        </div>
      ),
    },
    {
      key: "period",
      header: "Grading period",
      cell: (grade) => (
        <span className="text-sm">{grade.grading_period_name ?? "—"}</span>
      ),
    },
    {
      key: "score",
      header: "Score",
      cell: (grade) => (
        <span className="font-bold">
          {grade.score === null || grade.score === ""
            ? "—"
            : formatPercent(Number(grade.score), 2)}
        </span>
      ),
    },
    {
      key: "letter",
      header: "Remark",
      cell: (grade) => (
        <Badge
          variant="secondary"
          className={letterGradeBadgeClass(grade.letter_grade)}
        >
          {grade.letter_grade?.trim() || "—"}
        </Badge>
      ),
    },
    {
      key: "remarks",
      header: "Teacher remarks",
      cell: (grade) => (
        <span className="text-sm text-muted-foreground">
          {grade.remarks || "—"}
        </span>
      ),
    },
  ]

  return (
    <div className="space-y-4">
      <div className="space-y-1.5">
        <Label htmlFor="parent-grade-search">Search grades</Label>
        <Input
          id="parent-grade-search"
          type="search"
          value={search}
          placeholder="Subject or grading period"
          onChange={(event) => onSearchChange(event.target.value)}
        />
      </div>
      <DataTable
        caption="Finalized grades"
        columns={columns}
        rows={pageRows}
        rowKey={(grade) => grade.id}
        isLoading={isLoading}
        error={error}
        loadingLabel="Loading grades"
        emptyMessage={
          term
            ? "No grades match your search."
            : "No finalized grades have been recorded yet."
        }
        pagination={pagination}
      />
    </div>
  )
}

function AttendanceTable({
  records,
  statusFilter,
  isLoading,
  error,
}: {
  records: readonly {
    id: string
    date: string
    status: "present" | "late" | "absent"
    section_name: string
  }[]
  statusFilter: string
  isLoading: boolean
  error: string | null
}) {
  const filtered =
    statusFilter === "all"
      ? records
      : records.filter((record) => record.status === statusFilter)

  const { pagination, pageRows } = useDataTablePagination(
    filtered,
    10,
    `attendance:${statusFilter}`
  )

  const columns: readonly DataTableColumn<(typeof filtered)[number]>[] = [
    {
      key: "date",
      header: "Date",
      cell: (record) => (
        <span className="text-sm font-medium">{formatDate(record.date)}</span>
      ),
    },
    {
      key: "status",
      header: "Status",
      cell: (record) => (
        <Badge variant="outline" data-attendance-status={record.status}>
          {ATTENDANCE_STATUS_LABELS[record.status]}
        </Badge>
      ),
    },
    {
      key: "section",
      header: "Section",
      cell: (record) => (
        <span className="text-sm text-muted-foreground">
          {record.section_name}
        </span>
      ),
    },
  ]

  return (
    <DataTable
      caption="Attendance record"
      columns={columns}
      rows={pageRows}
      rowKey={(record) => record.id}
      isLoading={isLoading}
      error={error}
      loadingLabel="Loading attendance"
      emptyMessage={
        statusFilter === "all"
          ? "No attendance has been recorded yet."
          : "No records with that status."
      }
      pagination={pagination}
    />
  )
}

const ATTENDANCE_STATUS_LABELS: Record<string, string> = {
  present: "Present",
  late: "Late",
  absent: "Absent",
}

function formatDate(value: string): string {
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return value
  return parsed.toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  })
}

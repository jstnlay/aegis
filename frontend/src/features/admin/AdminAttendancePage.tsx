import { CalendarCheck } from "lucide-react"
import { useMemo, useState } from "react"

import { Badge } from "@/components/ui/badge"
import {
  PendingMetric,
  PendingRegion,
  UnavailableMetric,
} from "@/components/feedback/Feedback"
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
import { SearchableSelect } from "@/components/ui/searchable-select"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  useAdminAttendanceRecords,
  useAdminAttendanceSummary,
  useSections,
  type AdminAttendanceRecord,
  type AttendanceSummaryRow,
} from "@/features/admin/api"

/**
 * Attendance oversight.
 *
 * Read-only, and the screen says why. `AttendanceRecordViewSet.get_permissions()`
 * gates create, update, partial_update and destroy on `IsFacultyUser`, so an
 * administrator holding `role="admin"` receives 403 on every write. Recording
 * attendance is a faculty action; an administrator's job here is to see the
 * picture, not to enter it. No write hook is imported from the attendance
 * module for that reason.
 *
 * Two shapes, because the backend genuinely uses two: the records endpoint
 * returns the paginated envelope while `summary` returns a bare array.
 */

const STATUS_LABELS: Record<string, string> = {
  present: "Present",
  late: "Late",
  absent: "Absent",
}

const STATUS_FILTERS = [
  { value: "all", label: "All statuses" },
  { value: "present", label: "Present" },
  { value: "late", label: "Late" },
  { value: "absent", label: "Absent" },
] as const

/*
 * A stable empty-array identity. `query.data ?? []` allocates a new array on
 * every render, which would make the `useMemo` above re-run each time and
 * defeat its purpose.
 */
const EMPTY_SUMMARY: readonly AttendanceSummaryRow[] = []

export function AdminAttendancePage() {
  const [sectionId, setSectionId] = useState<string>("all")
  const [status, setStatus] = useState<string>("all")
  const [dateFrom, setDateFrom] = useState("")
  const [dateTo, setDateTo] = useState("")

  const { list: sectionsQuery } = useSections()
  const recordsQuery = useAdminAttendanceRecords({
    section: sectionId === "all" ? undefined : sectionId,
    dateFrom: dateFrom || undefined,
    dateTo: dateTo || undefined,
    status: status === "all" ? undefined : status,
  })
  const summaryQuery = useAdminAttendanceSummary(
    sectionId === "all" ? null : sectionId
  )

  const summary = useMemo(
    () => summaryQuery.data ?? EMPTY_SUMMARY,
    [summaryQuery.data]
  )
  const totals = useMemo(() => {
    const present = summary.reduce((s, r) => s + r.present_count, 0)
    const late = summary.reduce((s, r) => s + r.late_count, 0)
    const absent = summary.reduce((s, r) => s + r.absent_count, 0)
    const total = summary.reduce((s, r) => s + r.total_records, 0)
    return {
      present,
      late,
      absent,
      total,
      rate: total > 0 ? ((present + late) / total) * 100 : null,
    }
  }, [summary])

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-1">
        <div className="flex items-center gap-3">
          <CalendarCheck
            className="size-5 text-muted-foreground"
            aria-hidden="true"
          />
          <h2 className="text-2xl font-bold text-foreground">Attendance</h2>
        </div>
        <p className="text-sm text-muted-foreground">
          School-wide attendance oversight.
        </p>
      </div>

      {/*
        Stated rather than assumed. An administrator looking for a "record
        attendance" button here would otherwise have no way to tell whether the
        role lacks the capability or the screen is incomplete.
      */}
      <Card>
        <CardHeader>
          <CardTitle>Read-only view</CardTitle>
          <CardDescription>
            Administrators can read every attendance record and the per-student
            summary. Recording or editing a record is a faculty action — the
            backend rejects an administrator write with HTTP 403 — so this
            screen offers no way to enter one.
          </CardDescription>
        </CardHeader>
        <CardContent />
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Attendance totals</CardTitle>
          <CardDescription>
            {/*
              PH11.11: the scope line no longer counts while the summary is in
              flight or after it failed. `summary` falls back to an empty array, so
              "0 students in scope" was printed over a request that had not
              answered — a claim about the school, made from no data.
            */}
            {summaryQuery.isLoading
              ? "Counting students in scope."
              : summaryQuery.isError
                ? "The number of students in scope could not be loaded."
                : `${summary.length} student${summary.length === 1 ? "" : "s"} in scope.`}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {/*
            The four totals are derived from the summary rows, so they inherit its
            three states. Rendering `totals.present` while the request was in
            flight produced a real-looking `0`, and `N/A` after a failure, when
            the honest state was neither: the first is a measurement that was
            never taken and the second claims the backend reported no attendance
            at all.
          */}
          {summaryQuery.isLoading ? (
            <PendingRegion label="Attendance totals">
              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                {(
                  ["Present", "Late", "Absent", "Attendance rate"] as const
                ).map((label) => (
                  <TotalCard
                    key={label}
                    label={label}
                    value={<PendingMetric label={label} className="h-7 w-16" />}
                  />
                ))}
              </div>
            </PendingRegion>
          ) : summaryQuery.isError ? (
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              {(["Present", "Late", "Absent", "Attendance rate"] as const).map(
                (label) => (
                  <TotalCard
                    key={label}
                    label={label}
                    value={<UnavailableMetric />}
                  />
                )
              )}
            </div>
          ) : (
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <TotalCard label="Present" value={totals.present} />
              <TotalCard label="Late" value={totals.late} />
              <TotalCard label="Absent" value={totals.absent} />
              <TotalCard
                label="Attendance rate"
                value={
                  totals.rate === null ? "N/A" : `${totals.rate.toFixed(1)}%`
                }
              />
            </div>
          )}

          <SummaryTable
            rows={summary}
            isLoading={summaryQuery.isLoading}
            error={
              summaryQuery.isError
                ? "Unable to load the attendance summary. Please try again."
                : null
            }
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Records</CardTitle>
          <CardDescription>
            Every attendance record in scope, filterable by section, date range
            and status.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <div className="space-y-1.5">
              <Label htmlFor="admin-attendance-section">Section</Label>
              <SearchableSelect
                id="admin-attendance-section"
                label="Section"
                value={sectionId}
                onChange={setSectionId}
                options={[
                  { value: "all", label: "All sections" },
                  ...(sectionsQuery.data ?? []).map((section) => ({
                    value: section.id,
                    label: `${section.name} — ${section.grade_level_name}`,
                  })),
                ]}
                placeholder="Select a section"
                searchPlaceholder="Search sections"
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="admin-attendance-status">Status</Label>
              <Select value={status} onValueChange={setStatus}>
                <SelectTrigger id="admin-attendance-status">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {STATUS_FILTERS.map((filter) => (
                    <SelectItem key={filter.value} value={filter.value}>
                      {filter.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="admin-attendance-from">From</Label>
              <Input
                id="admin-attendance-from"
                type="date"
                value={dateFrom}
                onChange={(event) => setDateFrom(event.target.value)}
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="admin-attendance-to">To</Label>
              <Input
                id="admin-attendance-to"
                type="date"
                value={dateTo}
                onChange={(event) => setDateTo(event.target.value)}
              />
            </div>
          </div>

          <RecordsTable
            records={recordsQuery.data ?? []}
            isLoading={recordsQuery.isLoading}
            error={
              recordsQuery.isError
                ? "Unable to load attendance records. Please try again."
                : null
            }
          />
        </CardContent>
      </Card>
    </div>
  )
}

function TotalCard({
  label,
  value,
}: {
  label: string
  /**
   * The figure, or a state element when the request has not resolved or failed.
   * A `ReactNode` rather than `string | number` because "not yet known" and
   * "not available" are elements, not numbers — see the note at the call site.
   */
  value: React.ReactNode
}) {
  return (
    <div className="rounded-md border border-border p-3">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="text-xl font-bold">{value}</p>
    </div>
  )
}

function SummaryTable({
  rows,
  isLoading,
  error,
}: {
  rows: readonly AttendanceSummaryRow[]
  isLoading: boolean
  error: string | null
}) {
  const { pagination, pageRows } = useDataTablePagination(rows, 10)

  const columns: readonly DataTableColumn<AttendanceSummaryRow>[] = [
    {
      key: "student",
      header: "Student",
      cell: (row) => (
        <div className="min-w-0">
          <div className="font-medium whitespace-nowrap">
            {row.student_name}
          </div>
          <div className="text-xs whitespace-nowrap text-muted-foreground">
            {row.student_id_code}
          </div>
        </div>
      ),
    },
    {
      key: "section",
      header: "Section",
      cell: (row) => <span className="text-sm">{row.section_name}</span>,
    },
    {
      key: "present",
      header: "Present",
      cell: (row) => <span>{row.present_count}</span>,
    },
    {
      key: "late",
      header: "Late",
      cell: (row) => <span>{row.late_count}</span>,
    },
    {
      key: "absent",
      header: "Absent",
      cell: (row) => <span>{row.absent_count}</span>,
    },
    {
      key: "total",
      header: "Records",
      cell: (row) => (
        <span className="text-muted-foreground">{row.total_records}</span>
      ),
    },
  ]

  return (
    <DataTable
      caption="Attendance summary by student"
      columns={columns}
      rows={pageRows}
      rowKey={(row) => row.student}
      isLoading={isLoading}
      error={error}
      loadingLabel="Loading attendance summary"
      emptyMessage="No attendance records match the current filters."
      pagination={pagination}
    />
  )
}

function RecordsTable({
  records,
  isLoading,
  error,
}: {
  records: readonly AdminAttendanceRecord[]
  isLoading: boolean
  error: string | null
}) {
  const { pagination, pageRows } = useDataTablePagination(records, 15)

  const columns: readonly DataTableColumn<AdminAttendanceRecord>[] = [
    {
      key: "date",
      header: "Date",
      cell: (record) => (
        <span className="font-medium">{formatDate(record.date)}</span>
      ),
    },
    {
      key: "student",
      header: "Student",
      cell: (record) => (
        <div className="min-w-0">
          <div className="text-sm font-medium whitespace-nowrap">
            {record.student_name}
          </div>
          <div className="text-xs text-muted-foreground">
            {record.student_id_code}
          </div>
        </div>
      ),
    },
    {
      key: "section",
      header: "Section",
      cell: (record) => <span className="text-sm">{record.section_name}</span>,
    },
    {
      key: "status",
      header: "Status",
      cell: (record) => (
        <Badge variant="outline" data-attendance-status={record.status}>
          {STATUS_LABELS[record.status] ?? record.status}
        </Badge>
      ),
    },
    {
      key: "recorded_by",
      header: "Recorded by",
      cell: (record) => (
        <span className="text-sm text-muted-foreground">
          {record.recorded_by_name || "—"}
        </span>
      ),
    },
  ]

  return (
    <DataTable
      caption="Attendance records"
      columns={columns}
      rows={pageRows}
      rowKey={(record) => record.id}
      isLoading={isLoading}
      error={error}
      loadingLabel="Loading attendance records"
      emptyMessage="No attendance records match the current filters."
      pagination={pagination}
    />
  )
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

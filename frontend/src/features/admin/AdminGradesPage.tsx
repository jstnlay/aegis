import { ClipboardCheck } from "lucide-react"
import { useMemo, useState } from "react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { DataTable, type DataTableColumn } from "@/components/ui/data-table"
import { useDataTablePagination } from "@/components/ui/data-table-pagination"
import { ErrorNote } from "@/components/feedback/Feedback"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  GRADE_STATUS_LABELS,
  useAdminGrades,
  useFinalizeGrade,
  type AdminGrade,
} from "@/features/admin/api"
import { normalizeApiError } from "@/lib/error"
import { formatCount } from "@/lib/metric-format"

/**
 * Grade oversight and finalization.
 *
 * This is the one grade screen an administrator can act on.
 * `GradeViewSet.get_permissions()` grants `finalize` to `IsAdminUser`, and
 * `finalize` is the only grade write that role holds — `encode` and
 * `batch_import` are `IsFacultyUser`, so an administrator cannot create or edit
 * a score here and no such control is offered.
 *
 * The finalize action only accepts a grade whose status is `submitted`; it
 * rejects anything else with a 400. So the button is rendered only for
 * submitted rows rather than being shown disabled everywhere, and the table's
 * status filter makes it easy to find the rows that can actually be finalized.
 *
 * Finalizing dispatches GRADE_POSTED to the student and their linked parents,
 * which is why the operation is offered as a deliberate action rather than a
 * bulk one.
 */
/** A stable empty-array identity, so the `useMemo` below can depend on it. */
const EMPTY_GRADES: readonly AdminGrade[] = []

export function AdminGradesPage() {
  const [status, setStatus] = useState<AdminGrade["status"] | "all">("all")
  const [search, setSearch] = useState("")

  const gradesQuery = useAdminGrades()
  const finalize = useFinalizeGrade()

  const grades = useMemo(
    () => gradesQuery.data ?? EMPTY_GRADES,
    [gradesQuery.data]
  )
  const term = search.trim().toLowerCase()
  const filtered = useMemo(
    () =>
      grades.filter((grade) => {
        if (status !== "all" && grade.status !== status) return false
        if (!term) return true
        return [
          grade.student_name,
          grade.student_id,
          grade.subject_name,
          grade.subject_code,
        ]
          .join(" ")
          .toLowerCase()
          .includes(term)
      }),
    [grades, status, term]
  )

  const { pagination, pageRows } = useDataTablePagination(
    filtered,
    15,
    `grades:${status}:${term}`
  )

  const pendingCount = grades.filter((g) => g.status === "submitted").length

  const columns: readonly DataTableColumn<AdminGrade>[] = [
    {
      key: "student",
      header: "Student",
      cell: (grade) => (
        <div className="min-w-0">
          <div className="font-medium">{grade.student_name}</div>
          <div className="text-xs text-muted-foreground">
            {grade.student_id} · {grade.section_name}
          </div>
        </div>
      ),
    },
    {
      key: "subject",
      header: "Subject",
      cell: (grade) => (
        <div className="min-w-0">
          <div className="text-sm">{grade.subject_name}</div>
          <div className="text-xs text-muted-foreground">
            {grade.subject_code}
          </div>
        </div>
      ),
    },
    {
      key: "period",
      header: "Period",
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
      key: "status",
      header: "Status",
      cell: (grade) => (
        <Badge variant="outline" data-grade-status={grade.status}>
          {GRADE_STATUS_LABELS[grade.status] ?? grade.status}
        </Badge>
      ),
    },
    {
      key: "actions",
      header: "Actions",
      /*
       * Only a submitted grade can be finalized — the action returns 400 for
       * any other status — so the control appears only where it can succeed.
       */
      cell: (grade) =>
        grade.status === "submitted" ? (
          <Button
            type="button"
            size="xs"
            disabled={finalize.isPending}
            onClick={() => finalize.mutate(grade.id)}
          >
            {finalize.isPending && finalize.variables === grade.id
              ? "Finalizing…"
              : "Finalize"}
          </Button>
        ) : (
          <span className="text-xs text-muted-foreground">—</span>
        ),
    },
  ]

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-1">
        <div className="flex items-center gap-3">
          <ClipboardCheck
            className="size-5 text-muted-foreground"
            aria-hidden="true"
          />
          <h2 className="text-2xl font-bold text-foreground">Grades</h2>
        </div>
        <p className="text-sm text-muted-foreground">
          Every grade record across the school. {formatCount(pendingCount)}{" "}
          submitted {pendingCount === 1 ? "grade is" : "grades are"} awaiting
          finalization.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Grade records</CardTitle>
          <CardDescription>
            Showing {filtered.length} of {grades.length} records.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="admin-grades-status">Status</Label>
              <Select
                value={status}
                onValueChange={(value) =>
                  setStatus(value as AdminGrade["status"] | "all")
                }
              >
                <SelectTrigger id="admin-grades-status">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All statuses</SelectItem>
                  {(
                    Object.keys(GRADE_STATUS_LABELS) as AdminGrade["status"][]
                  ).map((value) => (
                    <SelectItem key={value} value={value}>
                      {GRADE_STATUS_LABELS[value]}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="admin-grades-search">Search</Label>
              <Input
                id="admin-grades-search"
                type="search"
                value={search}
                placeholder="Student or subject"
                onChange={(event) => setSearch(event.target.value)}
              />
            </div>
          </div>

          {finalize.isError ? (
            <ErrorNote message={normalizeApiError(finalize.error).message} />
          ) : null}

          <DataTable
            caption="Grade records"
            columns={columns}
            rows={pageRows}
            rowKey={(grade) => grade.id}
            isLoading={gradesQuery.isLoading}
            error={
              gradesQuery.isError
                ? normalizeApiError(gradesQuery.error).message
                : null
            }
            loadingLabel="Loading grades"
            emptyMessage={
              term || status !== "all"
                ? "No grades match the current filters."
                : "No grades have been recorded yet."
            }
            pagination={pagination}
          />
        </CardContent>
      </Card>
    </div>
  )
}

function formatPercent(value: number, digits: number): string {
  return `${value.toFixed(digits)}%`
}

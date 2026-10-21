import { Users } from "lucide-react"
import { useMemo, useState } from "react"
import { Link } from "react-router-dom"

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
import { orderRows, type DataTableSort } from "@/components/ui/data-table-sort"
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
  RISK_LEVEL_LABELS,
  filterGuidanceStudents,
  useGuidanceStudents,
  type GuidanceStudent,
  type GuidanceStudentFilters,
  type RiskLevel,
} from "@/features/guidance/api"
import { normalizeApiError } from "@/lib/error"
import { riskLevelBadgeClass } from "@/lib/status-badge"

type ActivityFilter = NonNullable<GuidanceStudentFilters["activity"]>

const NO_CODE = "—"

/** Rows per page for a list that can reach the size of a school cohort. */
const PAGE_SIZE = 25

/** Page sizes offered for this list. */
const PAGE_SIZE_OPTIONS = [25, 50, 100] as const

function PageHeading() {
  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center gap-3">
        <Users className="size-5 text-muted-foreground" aria-hidden="true" />
        <h2 className="text-2xl font-bold text-foreground">Students</h2>
      </div>
      <p className="text-sm text-muted-foreground">
        Students with guidance activity — risk alerts, your consultations, your
        intervention plans, and results on assessments you created.
      </p>
    </div>
  )
}

/**
 * The student's most severe **open** alert level, or nothing.
 *
 * `atRiskLevel` is already scoped to open moderate/high alerts by
 * `useGuidanceStudents`, so this only maps that level to its semantic colour:
 * `moderate` uses warning semantics and `high` uses destructive semantics. A
 * student with no open escalating alert renders nothing rather than a
 * misleading "low" pill.
 */
function AtRiskBadge({ level }: { level: RiskLevel | null }) {
  if (!level) return null
  return (
    <Badge
      variant="secondary"
      className={riskLevelBadgeClass(level)}
      data-at-risk-level={level}
    >
      {RISK_LEVEL_LABELS[level]}
    </Badge>
  )
}

export function StudentsPage() {
  const studentsQuery = useGuidanceStudents()

  const [activity, setActivity] = useState<ActivityFilter>("all")
  const [search, setSearch] = useState("")
  const [sort, setSort] = useState<DataTableSort | null>(null)

  const students = useMemo(
    () => studentsQuery.data?.students ?? [],
    [studentsQuery.data]
  )

  const visible = useMemo(
    () => filterGuidanceStudents(students, { activity, search }),
    [students, activity, search]
  )

  const atRiskCount = useMemo(
    () => students.filter((student) => student.atRiskLevel !== null).length,
    [students]
  )

  const isFiltered = activity !== "all" || search.trim().length > 0

  const columns = useMemo<readonly DataTableColumn<GuidanceStudent>[]>(
    () => [
      {
        key: "name",
        header: "Student",
        sortValue: (row) => row.name,
        sortTieBreak: (row) => row.code,
        cell: (row) => (
          /*
            The name and the risk badge stay on one line. Wrapped, the badge
            dropped onto its own line under the name and read as a stray
            label rather than as the student's risk level.
          */
          <div className="flex items-center gap-2 whitespace-nowrap">
            <span className="font-medium">{row.name}</span>
            <AtRiskBadge level={row.atRiskLevel} />
          </div>
        ),
      },
      {
        key: "code",
        header: "Code",
        sortValue: (row) => row.code,
        cell: (row) => (
          <span className="tabular-nums whitespace-nowrap text-sm text-muted-foreground">
            {row.code ?? NO_CODE}
          </span>
        ),
      },
      {
        key: "openAlerts",
        header: "Open alerts",
        sortValue: (row) => row.openAlertCount,
        cellClassName: "tabular-nums",
        cell: (row) => row.openAlertCount,
      },
      {
        key: "consultations",
        header: "Consultations",
        sortValue: (row) => row.consultationCount,
        cellClassName: "tabular-nums",
        cell: (row) => row.consultationCount,
      },
      {
        key: "interventions",
        header: "Interventions",
        sortValue: (row) => row.interventionCount,
        cellClassName: "tabular-nums",
        cell: (row) => row.interventionCount,
      },
      {
        key: "results",
        header: "Results",
        sortValue: (row) => row.resultCount,
        cellClassName: "tabular-nums",
        cell: (row) => row.resultCount,
      },
      {
        key: "lastActivity",
        header: "Last activity",
        sortValue: (row) => row.latestActivity,
        cellClassName: "text-sm text-muted-foreground",
        cell: (row) => row.latestActivity ?? NO_CODE,
      },
      {
        key: "actions",
        header: "Actions",
        cell: (row) => (
          <Button asChild size="xs" variant="outline">
            <Link to={`/app/students/${row.id}`}>View profile</Link>
          </Button>
        ),
      },
    ],
    []
  )

  /*
   * PH11.10: this directory had no pagination and rendered every matching
   * student. Sorting is client-side because `useGuidanceStudents` composes five
   * sibling queries that are each fetched whole — the viewsets declare no
   * `ordering` filter backend, so there is nothing to send. The chosen sort is
   * applied before slicing, so page 1 shows the top of the ordering rather than
   * an arbitrary slice of it.
   */
  const sorted = useMemo(
    () => orderRows(visible, sort, columns),
    [visible, sort, columns]
  )

  const { pagination, pageRows, setPageSize } = useDataTablePagination(
    sorted,
    PAGE_SIZE,
    `students:${activity}:${search}`
  )

  return (
    <div className="space-y-6">
      <PageHeading />

      <Card>
        <CardHeader>
          <div className="space-y-1">
            <CardTitle>Students with guidance activity</CardTitle>
            <CardDescription>
              Showing {visible.length} of {students.length} · {atRiskCount} at
              risk
            </CardDescription>
          </div>
        </CardHeader>

        <CardContent className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="students-activity">Activity type</Label>
              <Select
                value={activity}
                onValueChange={(value) => setActivity(value as ActivityFilter)}
              >
                <SelectTrigger id="students-activity">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">Any activity</SelectItem>
                  <SelectItem value="alerts">Open risk alerts</SelectItem>
                  <SelectItem value="consultations">Consultations</SelectItem>
                  <SelectItem value="interventions">Interventions</SelectItem>
                  <SelectItem value="results">Assessment results</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="students-search">Search</Label>
              <Input
                id="students-search"
                type="search"
                value={search}
                placeholder="Name or student code"
                onChange={(event) => setSearch(event.target.value)}
              />
            </div>
          </div>

          <DataTable
            caption="Students with guidance activity"
            columns={columns}
            rows={pageRows}
            rowKey={(row) => row.id}
            rowProps={(row) => ({
              "data-student-id": row.id,
              "data-at-risk": row.atRiskLevel ? "true" : "false",
            })}
            isLoading={studentsQuery.isLoading}
            error={
              studentsQuery.isError
                ? normalizeApiError(studentsQuery.error).message
                : null
            }
            loadingLabel="Loading students"
            emptyMessage={
              isFiltered
                ? "No students match the current filters."
                : "No students have guidance activity yet."
            }
            pagination={pagination}
            pageSizeOptions={PAGE_SIZE_OPTIONS}
            onPageSizeChange={setPageSize}
            sort={sort}
            onSortChange={setSort}
          />
        </CardContent>
      </Card>

      <p className="text-xs text-muted-foreground">
        This directory is built from guidance records only. Students with no
        risk alert, no consultation, no intervention plan, and no assessment
        result do not appear — the list is not a school enrollment roster. A
        student code is shown only when a guidance record carries one; otherwise
        the row shows an em-dash rather than an internal id.
      </p>
    </div>
  )
}

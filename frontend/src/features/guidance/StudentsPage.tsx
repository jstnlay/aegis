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
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import {
  RISK_LEVEL_LABELS,
  filterGuidanceStudents,
  useGuidanceStudents,
  type GuidanceStudentFilters,
  type RiskLevel,
} from "@/features/guidance/api"
import { normalizeApiError } from "@/lib/error"
import { riskLevelBadgeClass } from "@/lib/status-badge"

type ActivityFilter = NonNullable<GuidanceStudentFilters["activity"]>

const NO_CODE = "—"

function PageHeading() {
  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center gap-3">
        <Users className="size-5 text-muted-foreground" aria-hidden="true" />
        <h1 className="text-2xl font-bold text-foreground">Students</h1>
      </div>
      <p className="text-sm text-muted-foreground">
        Students with guidance activity — risk alerts, your consultations, your
        intervention plans, and results on assessments you created.
      </p>
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

          {studentsQuery.isLoading ? (
            <div className="space-y-2">
              <Skeleton className="h-10 w-full" />
              <Skeleton className="h-10 w-full" />
            </div>
          ) : studentsQuery.isError ? (
            <ErrorNote
              message={normalizeApiError(studentsQuery.error).message}
            />
          ) : visible.length === 0 ? (
            <p className="py-6 text-center text-sm text-muted-foreground">
              {isFiltered
                ? "No students match the current filters."
                : "No students have guidance activity yet."}
            </p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Student</TableHead>
                  <TableHead>Code</TableHead>
                  <TableHead>Open alerts</TableHead>
                  <TableHead>Consultations</TableHead>
                  <TableHead>Interventions</TableHead>
                  <TableHead>Results</TableHead>
                  <TableHead>Last activity</TableHead>
                  <TableHead>Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {visible.map((student) => (
                  <TableRow
                    key={student.id}
                    data-student-id={student.id}
                    data-at-risk={student.atRiskLevel ? "true" : "false"}
                  >
                    <TableCell>
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="font-medium">{student.name}</span>
                        <AtRiskBadge level={student.atRiskLevel} />
                      </div>
                    </TableCell>
                    <TableCell className="tabular-nums text-sm text-muted-foreground">
                      {student.code ?? NO_CODE}
                    </TableCell>
                    <TableCell className="tabular-nums">
                      {student.openAlertCount}
                    </TableCell>
                    <TableCell className="tabular-nums">
                      {student.consultationCount}
                    </TableCell>
                    <TableCell className="tabular-nums">
                      {student.interventionCount}
                    </TableCell>
                    <TableCell className="tabular-nums">
                      {student.resultCount}
                    </TableCell>
                    <TableCell className="text-sm text-muted-foreground">
                      {student.latestActivity ?? NO_CODE}
                    </TableCell>
                    <TableCell>
                      <Button asChild size="xs" variant="outline">
                        <Link to={`/app/students/${student.id}`}>
                          View profile
                        </Link>
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
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

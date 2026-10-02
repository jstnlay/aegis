import { AlertCircle, BookOpen, Info, Lock } from "lucide-react"
import { useMemo, useState, type FormEvent } from "react"

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
  TableCaption,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import {
  GRADE_STATUS_LABELS,
  countByStatus,
  useAssignmentLabel,
  useEncodeGrade,
  useEnrollmentsInSection,
  useFacultyGrades,
  useGradingPeriods,
  useStudentGrades,
  useSubjectAssignments,
  type Grade,
  type GradeStatus,
} from "@/features/academics/api"
import { useAuth } from "@/features/auth/AuthContext"
import { useStudentProfileId } from "@/features/student/api"
import { AcademicsLandingPage } from "@/routes/pages/AcademicsLandingPage"
import { normalizeApiError } from "@/lib/error"

/* -------------------------------------------------------------------------- */
/* Shared pieces                                                              */
/* -------------------------------------------------------------------------- */

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
        <BookOpen className="size-5 text-muted-foreground" aria-hidden="true" />
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
      <AlertCircle className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
      <span>{message}</span>
    </div>
  )
}

const STATUS_BADGE_VARIANT: Record<
  GradeStatus,
  "outline" | "secondary" | "default"
> = {
  draft: "outline",
  submitted: "secondary",
  finalized: "default",
}

function StatusBadge({ status }: { status: GradeStatus }) {
  return (
    <Badge variant={STATUS_BADGE_VARIANT[status]}>
      {GRADE_STATUS_LABELS[status]}
    </Badge>
  )
}

/**
 * Renders a score, or an explicit "not recorded" marker.
 *
 * `Grade.score` is a raw 0–100 value (`DecimalField(max_digits=5, decimal_places=2)`,
 * serializer-validated to `0 <= score <= 100`) — not a percentage ratio. The
 * table header carries the "out of 100" scale so the unit is never ambiguous.
 */
function ScoreCell({ score }: { score: number | null }) {
  if (score === null) {
    return <span className="text-muted-foreground">Not recorded</span>
  }
  return <span className="font-medium tabular-nums">{score.toFixed(2)}</span>
}

function GradeTable({
  grades,
  caption,
  showStudent = false,
}: {
  grades: Grade[]
  caption: string
  showStudent?: boolean
}) {
  return (
    <Table>
      <TableCaption className="text-xs text-muted-foreground">
        {caption}
      </TableCaption>
      <TableHeader>
        <TableRow>
          {showStudent ? <TableHead>Student</TableHead> : null}
          <TableHead>Subject</TableHead>
          {showStudent ? <TableHead>Section</TableHead> : null}
          <TableHead>Grading period</TableHead>
          <TableHead className="text-right">Score (0&ndash;100)</TableHead>
          <TableHead className="text-right">Letter</TableHead>
          <TableHead>Status</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {grades.map((grade) => (
          <TableRow key={grade.id}>
            {showStudent ? (
              <TableCell>
                <span className="font-medium">{grade.student_name}</span>
                <span className="ml-1.5 text-xs text-muted-foreground">
                  {grade.student_id}
                </span>
              </TableCell>
            ) : null}
            <TableCell>
              <span className="font-medium">{grade.subject_name}</span>
              <span className="ml-1.5 text-xs text-muted-foreground">
                {grade.subject_code}
              </span>
            </TableCell>
            {showStudent ? (
              <TableCell className="text-muted-foreground">
                {grade.section_name}
              </TableCell>
            ) : null}
            <TableCell className="text-muted-foreground">
              {grade.grading_period_name ?? "Unassigned"}
            </TableCell>
            <TableCell className="text-right">
              <ScoreCell score={grade.score} />
            </TableCell>
            <TableCell className="text-right">
              {grade.letter_grade ? (
                grade.letter_grade
              ) : (
                <span className="text-muted-foreground">&mdash;</span>
              )}
            </TableCell>
            <TableCell>
              <StatusBadge status={grade.status} />
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}

function EmptyState({ message }: { message: string }) {
  return (
    <p className="py-6 text-center text-sm text-muted-foreground">{message}</p>
  )
}

/* -------------------------------------------------------------------------- */
/* Student view                                                               */
/* -------------------------------------------------------------------------- */

/**
 * Read-only record of finalized grades.
 *
 * Only `status=finalized` rows are requested. The API's own documentation
 * (`BACKEND_SPECIFICATION.md` §G.2) proposes that faculty submit grades and
 * that the system then compute a GPA — neither the submit transition nor a
 * GPA field exists in the backend, so neither is displayed here.
 */
function StudentAcademics() {
  const profileQuery = useStudentProfileId()
  const studentId = profileQuery.data
  const gradesQuery = useStudentGrades(studentId)

  const grades = useMemo(() => gradesQuery.data ?? [], [gradesQuery.data])

  const average = useMemo(() => {
    const scored = grades
      .map((g) => g.score)
      .filter((s): s is number => s !== null)
    if (scored.length === 0) return null
    // Arithmetic happens on the normalized `number` values from `normalizeScore`,
    // never on the raw DRF decimal strings.
    return scored.reduce((sum, s) => sum + s, 0) / scored.length
  }, [grades])

  const loading = profileQuery.isLoading || gradesQuery.isLoading

  return (
    <div className="space-y-6">
      <PageHeading
        title="Academics"
        description="Your official grade record. Grades appear here once they are finalized."
      />

      {profileQuery.isError ? (
        <ErrorNote message={normalizeApiError(profileQuery.error).message} />
      ) : null}

      <div className="grid gap-4 sm:grid-cols-2">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">
              Average of recorded scores
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {loading ? (
                <Skeleton className="h-8 w-24" />
              ) : average === null ? (
                <span className="text-muted-foreground">Not recorded</span>
              ) : (
                average.toFixed(2)
              )}
            </div>
            <p className="mt-1 text-xs text-muted-foreground">
              Mean of your finalized grade scores (out of 100)
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">
              Finalized grades
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {loading ? (
                <Skeleton className="h-8 w-16" />
              ) : (
                String(grades.length)
              )}
            </div>
            <p className="mt-1 text-xs text-muted-foreground">
              Subjects with an official result
            </p>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Grade record</CardTitle>
          <CardDescription>
            Only finalized results are listed. Draft and submitted work is not
            released to students.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="space-y-2">
              <Skeleton className="h-10 w-full" />
              <Skeleton className="h-10 w-full" />
              <Skeleton className="h-10 w-full" />
            </div>
          ) : gradesQuery.isError ? (
            <ErrorNote message={normalizeApiError(gradesQuery.error).message} />
          ) : grades.length === 0 ? (
            <EmptyState message="No finalized grades yet." />
          ) : (
            <GradeTable
              grades={grades}
              caption="Finalized grades, most recent grading period last."
            />
          )}
        </CardContent>
      </Card>
    </div>
  )
}

/* -------------------------------------------------------------------------- */
/* Faculty view                                                               */
/* -------------------------------------------------------------------------- */

const STATUS_FILTERS: ReadonlyArray<{
  value: GradeStatus | "all"
  label: string
}> = [
  { value: "all", label: "All" },
  { value: "draft", label: "Draft" },
  { value: "submitted", label: "Submitted" },
  { value: "finalized", label: "Finalized" },
]

function GradeEncodeForm({ onEncoded }: { onEncoded?: () => void }) {
  const assignmentsQuery = useSubjectAssignments()
  const periodsQuery = useGradingPeriods()
  const encodeMutation = useEncodeGrade()

  const assignments = assignmentsQuery.data ?? []
  const periods = periodsQuery.data ?? []
  const assignmentLabel = useAssignmentLabel(assignmentsQuery.data)

  const [assignmentId, setAssignmentId] = useState("")
  const [studentId, setStudentId] = useState("")
  const [periodId, setPeriodId] = useState("")
  const [score, setScore] = useState("")

  const selectedAssignment = assignments.find((a) => a.id === assignmentId)
  const sectionId = selectedAssignment?.section ?? null
  const enrollmentsQuery = useEnrollmentsInSection(sectionId)

  const enrollments = enrollmentsQuery.data ?? []
  // A grade is unique per (student, subject assignment, grading period), so the
  // form must offer periods that have no grade yet for this pair. The existing
  // grades list is not consulted here; the backend is authoritative and returns
  // a 400/409 with a clear message if the triple already exists.

  function reset() {
    setStudentId("")
    setPeriodId("")
    setScore("")
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!assignmentId || !studentId || !periodId) return

    const trimmedScore = score.trim()
    await encodeMutation.mutateAsync({
      student: studentId,
      subject_assignment: assignmentId,
      grading_period: periodId,
      score: trimmedScore === "" ? null : Number(trimmedScore),
    })

    reset()
    onEncoded?.()
  }

  const loadingOptions = assignmentsQuery.isLoading || periodsQuery.isLoading
  const optionsError =
    assignmentsQuery.isError || periodsQuery.isError
      ? normalizeApiError(assignmentsQuery.error ?? periodsQuery.error).message
      : null

  return (
    <Card>
      <CardHeader>
        <CardTitle>Encode a grade</CardTitle>
        <CardDescription>
          Encodes a single grade as a <strong>draft</strong> for a student
          enrolled in the selected subject assignment.
        </CardDescription>
      </CardHeader>
      <CardContent>
        {optionsError ? <ErrorNote message={optionsError} /> : null}

        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="encode-assignment">Subject assignment</Label>
            <Select
              value={assignmentId}
              onValueChange={(value) => {
                setAssignmentId(value)
                // Section changed: the previous student may not be enrolled here.
                setStudentId("")
              }}
              disabled={loadingOptions || assignments.length === 0}
            >
              <SelectTrigger id="encode-assignment">
                <SelectValue
                  placeholder={
                    assignments.length === 0
                      ? "No subject assignments"
                      : "Select a subject assignment"
                  }
                />
              </SelectTrigger>
              <SelectContent>
                {assignments.map((assignment) => (
                  <SelectItem key={assignment.id} value={assignment.id}>
                    {assignmentLabel(assignment.id)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="encode-student">Student</Label>
            <Select
              value={studentId}
              onValueChange={setStudentId}
              disabled={!assignmentId || enrollmentsQuery.isLoading}
            >
              <SelectTrigger id="encode-student">
                <SelectValue
                  placeholder={
                    !assignmentId
                      ? "Select an assignment first"
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
                  <SelectItem key={enrollment.id} value={enrollment.student}>
                    {enrollment.student_name} — {enrollment.student_id}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="encode-period">Grading period</Label>
              <Select
                value={periodId}
                onValueChange={setPeriodId}
                disabled={!assignmentId || periods.length === 0}
              >
                <SelectTrigger id="encode-period">
                  <SelectValue
                    placeholder={
                      periods.length === 0
                        ? "No grading periods configured"
                        : "Select a grading period"
                    }
                  />
                </SelectTrigger>
                <SelectContent>
                  {periods.map((period) => (
                    <SelectItem key={period.id} value={period.id}>
                      {period.academic_year_name} — {period.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="encode-score">Score (0&ndash;100)</Label>
              <Input
                id="encode-score"
                type="number"
                inputMode="decimal"
                min={0}
                max={100}
                step="0.01"
                value={score}
                onChange={(e) => setScore(e.target.value)}
                placeholder="Optional"
              />
            </div>
          </div>

          {encodeMutation.isError ? (
            <ErrorNote
              message={normalizeApiError(encodeMutation.error).message}
            />
          ) : null}

          <Button
            type="submit"
            disabled={
              encodeMutation.isPending ||
              !assignmentId ||
              !studentId ||
              !periodId
            }
          >
            {encodeMutation.isPending ? "Encoding…" : "Encode draft grade"}
          </Button>
        </form>
      </CardContent>
    </Card>
  )
}

function FacultyAcademics() {
  const gradesQuery = useFacultyGrades()
  const [statusFilter, setStatusFilter] = useState<GradeStatus | "all">("all")

  const grades = useMemo(() => gradesQuery.data ?? [], [gradesQuery.data])
  const counts = useMemo(() => countByStatus(grades), [grades])

  const visibleGrades = useMemo(
    () =>
      statusFilter === "all"
        ? grades
        : grades.filter((g) => g.status === statusFilter),
    [grades, statusFilter]
  )

  return (
    <div className="space-y-6">
      <PageHeading
        title="Academics"
        description="Encode draft grades and review the results for your subject assignments."
      />

      <div
        className="flex items-start gap-2 rounded-md border border-border bg-muted/60 p-3 text-sm text-muted-foreground"
        role="note"
      >
        <Lock className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
        <p>
          Encoded grades are saved as <strong>draft</strong>. This API has no
          edit, submit, or finalize transition for faculty, so a draft cannot be
          changed or released from this page &mdash; administration finalizes
          submitted results.
        </p>
      </div>

      <GradeEncodeForm />

      <Card>
        <CardHeader>
          <CardTitle>Grade records</CardTitle>
          <CardDescription>
            Every grade for the subject assignments assigned to you.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div
            role="group"
            aria-label="Filter grades by status"
            className="flex flex-wrap gap-2"
          >
            {STATUS_FILTERS.map((filter) => {
              const isActive = statusFilter === filter.value
              const count = counts[filter.value]
              return (
                <Button
                  key={filter.value}
                  type="button"
                  size="sm"
                  variant={isActive ? "default" : "outline"}
                  aria-pressed={isActive}
                  onClick={() => setStatusFilter(filter.value)}
                >
                  {filter.label}
                  <span
                    className={
                      isActive ? "opacity-80" : "text-muted-foreground"
                    }
                  >
                    {count}
                  </span>
                </Button>
              )
            })}
          </div>

          {gradesQuery.isLoading ? (
            <div className="space-y-2">
              <Skeleton className="h-10 w-full" />
              <Skeleton className="h-10 w-full" />
              <Skeleton className="h-10 w-full" />
            </div>
          ) : gradesQuery.isError ? (
            <ErrorNote message={normalizeApiError(gradesQuery.error).message} />
          ) : visibleGrades.length === 0 ? (
            <EmptyState
              message={
                grades.length === 0
                  ? "No grade records for your subject assignments yet."
                  : `No ${statusFilter} grades.`
              }
            />
          ) : (
            <GradeTable
              grades={visibleGrades}
              showStudent
              caption={`${visibleGrades.length} of ${grades.length} grade records.`}
            />
          )}
        </CardContent>
      </Card>

      <div className="flex items-start gap-2 rounded-md border border-border bg-muted/60 p-3 text-sm text-muted-foreground">
        <Info className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
        <p>
          Score values are stored as decimals and arrive as text; they are
          normalized to numbers before display so averages stay accurate.
        </p>
      </div>
    </div>
  )
}

/* -------------------------------------------------------------------------- */
/* Page entry point                                                           */
/* -------------------------------------------------------------------------- */

/**
 * Academics (PH11.7).
 *
 * Student and faculty reach the same route and get a role-appropriate view:
 * the backend scopes every grade queryset to the caller, so the page never
 * has to filter by identity itself.
 */
export function AcademicsPage() {
  const { user } = useAuth()
  if (!user) return null

  if (user.role === "faculty") return <FacultyAcademics />
  // PH11.7 implements the student and faculty surfaces only. Admin keeps the
  // documented placeholder rather than being shown a student-shaped view that
  // would resolve no StudentProfile.
  if (user.role === "admin") return <AcademicsLandingPage />

  return <StudentAcademics />
}

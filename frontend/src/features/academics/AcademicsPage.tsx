import { BookOpen, Info, Lock } from "lucide-react"
import { useMemo, useState, type FormEvent } from "react"

import {
  EmptyState,
  ErrorNote,
  PendingMetric,
  PendingRegion,
  UnavailableMetric,
} from "@/components/feedback/Feedback"
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
  useUpdateGrade,
  type Grade,
  type GradeStatus,
} from "@/features/academics/api"
import { useAuth } from "@/features/auth/AuthContext"
import { useStudentProfileId } from "@/features/student/api"
import { StudentPortfolioCard } from "@/features/portfolio/PortfolioCard"
import { AcademicsLandingPage } from "@/routes/pages/AcademicsLandingPage"
import { getFieldError, normalizeApiError } from "@/lib/error"
import { Field } from "@/components/ui/form-field"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"

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
        <h2 className="text-2xl font-bold text-foreground">{title}</h2>
      </div>
      <p className="text-sm text-muted-foreground">{description}</p>
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
 * serializer-validated to `0 <= score <= 100`), so it is shown as a percentage:
 * 85 out of 100 is 85%. Entry still takes the raw number.
 */
/**
 * Activity types for an encoded grade (paperwork, term exam, recitation…).
 *
 * The backend `Grade` row is unique per (student, subject assignment, grading
 * period) and carries no activity column, so the type is stored as a
 * `"[Type] rest"` prefix on `remarks` (max 255 chars) — an interim convention
 * until a dedicated grade-activity model exists. `parseActivityRemarks`
 * reverses it; remarks without the prefix report no activity rather than a
 * guess.
 */
const GRADE_ACTIVITY_TYPES = [
  "Classwork",
  "Paperwork",
  "Quiz",
  "Recitation",
  "Term exam",
  "Project",
  "Performance task",
] as const

function formatActivityRemarks(
  activity: string,
  remarks: string
): string | null {
  const text = remarks.trim()
  const prefix = activity ? `[${activity}]` : ""
  if (!prefix && !text) return null
  if (!prefix) return text
  return text ? `${prefix} ${text}` : prefix
}

function parseActivityRemarks(remarks: string | null): {
  activity: string
  text: string
} {
  if (!remarks) return { activity: "", text: "" }
  const match = remarks.match(/^\[([^\]]+)\]\s*(.*)$/)
  if (!match) return { activity: "", text: remarks }
  return { activity: match[1] ?? "", text: (match[2] ?? "").trim() }
}

function ScoreCell({ score }: { score: number | null }) {
  if (score === null) {
    return <span className="text-muted-foreground">Not recorded</span>
  }
  return <span className="font-medium tabular-nums">{score.toFixed(2)}%</span>
}

function GradeTable({
  grades,
  caption,
  showStudent = false,
  onEditGrade,
}: {
  grades: Grade[]
  caption: string
  showStudent?: boolean
  /**
   * Omitted for every read-only surface (the student record). Present,
   * a faculty member can open the edit form for one of their own grades.
   */
  onEditGrade?: (grade: Grade) => void
}) {
  return (
    <Table scrollLabel={caption}>
      {/*
        PH11.11. `scrollLabel` added. This is a five-to-seven column table with a
        `Subject`, `Section` and `Grading period` column of free text, so it is the
        one hand-rolled table in this file that can exceed a phone's width — and
        with no focusable, named scroll container its overflow was reachable only
        by dragging. The caption was already first, which is the only valid
        position; it stays visible rather than `sr-only` because here it carries a
        count ("12 of 40 grade records") that is worth reading.
      */}
      <TableCaption className="text-xs text-muted-foreground">
        {caption}
      </TableCaption>
      <TableHeader>
        <TableRow>
          {showStudent ? <TableHead scope="col">Student</TableHead> : null}
          <TableHead scope="col">Subject</TableHead>
          {showStudent ? <TableHead scope="col">Section</TableHead> : null}
          <TableHead scope="col">Grading period</TableHead>
          <TableHead scope="col">Activity</TableHead>
          <TableHead scope="col" className="text-right">
            Score
          </TableHead>
          <TableHead scope="col">Status</TableHead>
          {onEditGrade ? <TableHead scope="col">Update</TableHead> : null}
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
            <TableCell className="text-sm">
              {(() => {
                const { activity } = parseActivityRemarks(grade.remarks)
                return activity ? (
                  <span className="rounded-md bg-muted px-2 py-0.5 text-xs font-medium">
                    {activity}
                  </span>
                ) : (
                  <span className="text-muted-foreground">&mdash;</span>
                )
              })()}
            </TableCell>
            {/*
              PH11.11. `tabular-nums` on the score so the decimal points line up
              down the column, and `whitespace-nowrap` because a score split across
              two lines reads as two numbers. The subject, section and period cells
              keep the new wrapping default — those are the free-text columns that
              made this table wider than the screen.
            */}
            <TableCell className="text-right whitespace-nowrap tabular-nums">
              <ScoreCell score={grade.score} />
            </TableCell>
            <TableCell>
              <StatusBadge status={grade.status} />
            </TableCell>
            {onEditGrade ? (
              <TableCell>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => onEditGrade(grade)}
                >
                  Edit
                </Button>
              </TableCell>
            ) : null}
          </TableRow>
        ))}
      </TableBody>
    </Table>
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
                // PH11.11: announced placeholder. This skeleton was grey, silent
                // and stateless — a reader heard the page title and nothing about
                // the figure still arriving.
                <PendingMetric
                  label="Average of recorded scores"
                  className="h-8 w-24"
                />
              ) : gradesQuery.isError ? (
                // PH11.11: a failure is not "Not recorded". The card previously
                // printed the same muted line for both, which told the student
                // they had no grades when the request had simply failed.
                <UnavailableMetric />
              ) : average === null ? (
                <span className="text-muted-foreground">Not recorded</span>
              ) : (
                `${average.toFixed(2)}%`
              )}
            </div>
            <p className="mt-1 text-xs text-muted-foreground">
              Mean of your finalized grade scores
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
                <PendingMetric label="Finalized grades" className="h-8 w-16" />
              ) : gradesQuery.isError ? (
                <UnavailableMetric />
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
            <PendingRegion label="Grade record">
              <div className="space-y-2">
                <Skeleton className="h-10 w-full" />
                <Skeleton className="h-10 w-full" />
                <Skeleton className="h-10 w-full" />
              </div>
            </PendingRegion>
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

      <StudentPortfolioCard />
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

/**
 * Label plus the visible required marker for a hand-rolled control.
 *
 * The marker is a *sibling* of the `<label>`, never a child. An element inside
 * the label is part of its text content, so the control's accessible name would
 * become "Student *" and every announcement would state the requirement twice —
 * once from the name, once from `aria-required`. `FieldLabel` in
 * `@/components/ui/form-field` takes the same position for the same reason.
 *
 * This form cannot use `ChoiceField` even though it is fully controlled state:
 * the student and period selects are `disabled` until an assignment is chosen,
 * and their placeholders explain *why* the list is unavailable ("Select an
 * assignment first", "Loading enrolled students"). `ChoiceField` has no
 * `disabled` and no placeholder prop, so adopting it would silently drop both
 * the keyboard gating and the explanation of it.
 */
function RequiredLabel({
  htmlFor,
  children,
}: {
  htmlFor: string
  children: string
}) {
  return (
    <div className="flex items-center gap-1">
      <Label htmlFor={htmlFor}>{children}</Label>
      <span aria-hidden="true" className="text-destructive">
        *
      </span>
    </div>
  )
}

/** `id` of the form-level error node the failing control points at. */
const ENCODE_ERROR_ID = "encode-grade-error"

function GradeEncodeForm({
  onEncoded,
}: {
  onEncoded?: (grade: Grade) => void
}) {
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
  const [activity, setActivity] = useState("")
  const [remarks, setRemarks] = useState("")

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
    setActivity("")
    setRemarks("")
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!assignmentId || !studentId || !periodId) return

    const trimmedScore = score.trim()
    const grade = await encodeMutation.mutateAsync({
      student: studentId,
      subject_assignment: assignmentId,
      grading_period: periodId,
      score: trimmedScore === "" ? null : Number(trimmedScore),
      remarks: formatActivityRemarks(activity, remarks),
    })

    reset()
    onEncoded?.(grade)
  }

  const loadingOptions = assignmentsQuery.isLoading || periodsQuery.isLoading
  const optionsError =
    assignmentsQuery.isError || periodsQuery.isError
      ? normalizeApiError(assignmentsQuery.error ?? periodsQuery.error).message
      : null

  /*
    `GradeEncodeSerializer` keys its validation errors by the request field
    names, so these are the four controls a 400 can actually name. A failure the
    view raises itself arrives as a bare `{"detail": ...}` body, which maps to
    none of them and correctly leaves every control untouched — the note below is
    still announced, it just is not attributed to a field that did nothing
    wrong.
  */
  const assignmentError = getFieldError(
    encodeMutation.error,
    "subject_assignment"
  )
  const studentError = getFieldError(encodeMutation.error, "student")
  const periodError = getFieldError(encodeMutation.error, "grading_period")
  const scoreError = getFieldError(encodeMutation.error, "score")

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
            <RequiredLabel htmlFor="encode-assignment">
              Subject assignment
            </RequiredLabel>
            <Select
              value={assignmentId}
              onValueChange={(value) => {
                setAssignmentId(value)
                // Section changed: the previous student may not be enrolled here.
                setStudentId("")
              }}
              disabled={loadingOptions || assignments.length === 0}
            >
              <SelectTrigger
                id="encode-assignment"
                aria-required="true"
                aria-invalid={assignmentError ? true : undefined}
                aria-describedby={assignmentError ? ENCODE_ERROR_ID : undefined}
              >
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
            <RequiredLabel htmlFor="encode-student">Student</RequiredLabel>
            <Select
              value={studentId}
              onValueChange={setStudentId}
              disabled={!assignmentId || enrollmentsQuery.isLoading}
            >
              <SelectTrigger
                id="encode-student"
                aria-required="true"
                aria-invalid={studentError ? true : undefined}
                aria-describedby={studentError ? ENCODE_ERROR_ID : undefined}
              >
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
              <RequiredLabel htmlFor="encode-period">
                Grading period
              </RequiredLabel>
              <Select
                value={periodId}
                onValueChange={setPeriodId}
                disabled={!assignmentId || periods.length === 0}
              >
                <SelectTrigger
                  id="encode-period"
                  aria-required="true"
                  aria-invalid={periodError ? true : undefined}
                  aria-describedby={periodError ? ENCODE_ERROR_ID : undefined}
                >
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

            {/*
              The score is optional on purpose: `Grade.score` is nullable and the
              backend accepts `null`, so marking it required would be a lie. It is
              still a control a 400 can name (`validate_score` rejects anything
              outside 0–100), so it carries the error wiring but no marker.
            */}
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
                aria-invalid={scoreError ? true : undefined}
                aria-describedby={scoreError ? ENCODE_ERROR_ID : undefined}
              />
            </div>
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="encode-activity">Activity type</Label>
              <Select value={activity} onValueChange={setActivity}>
                <SelectTrigger id="encode-activity">
                  <SelectValue placeholder="Whole grade (no activity)" />
                </SelectTrigger>
                <SelectContent>
                  {GRADE_ACTIVITY_TYPES.map((type) => (
                    <SelectItem key={type} value={type}>
                      {type}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="encode-remarks">Remarks</Label>
              <Input
                id="encode-remarks"
                value={remarks}
                onChange={(e) => setRemarks(e.target.value)}
                placeholder="Optional note"
              />
            </div>
          </div>

          {/*
            The wrapper carries the id rather than `ErrorNote` itself, which takes
            only a message. That is enough: `aria-describedby` resolves against
            the referenced element's subtree text, which is exactly the note's own
            message, so focusing the offending control re-states the failure
            against that control instead of only alerting it in general.

            `encodeMutation.isError` and `isSuccess` are mutually exclusive in
            react-query, so the confirmation below can never render beside a
            failure it would contradict.
          */}
          {encodeMutation.isError ? (
            <div id={ENCODE_ERROR_ID}>
              <ErrorNote
                message={normalizeApiError(encodeMutation.error).message}
              />
            </div>
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
  const [editingGrade, setEditingGrade] = useState<Grade | null>(null)

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
          Encoded grades are saved as <strong>draft</strong>. You can update the
          score and remarks of your own records; moving a grade to submitted or
          finalized stays with administration.
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
            <PendingRegion label="Grade records">
              <div className="space-y-2">
                <Skeleton className="h-10 w-full" />
                <Skeleton className="h-10 w-full" />
                <Skeleton className="h-10 w-full" />
              </div>
            </PendingRegion>
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
              onEditGrade={setEditingGrade}
            />
          )}
        </CardContent>
      </Card>

      <GradeEditDialog
        grade={editingGrade}
        onClose={() => setEditingGrade(null)}
      />

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
/* Grade update (FR-011, TC-FAC-11 / TC-FAC-12)                                */
/* -------------------------------------------------------------------------- */

/**
 * The content-only edit form for one encoded grade.
 *
 * The API's write surface for a faculty member is the grade's content —
 * score and remarks — so those are the only controls here. The
 * lifecycle (`draft → submitted → finalized`) and the encoder never move
 * through this form: the backend answers 403 to either, and a control that
 * can only ever be refused should not exist.
 */
function GradeEditDialog({
  grade,
  onClose,
}: {
  grade: Grade | null
  onClose: () => void
}) {
  const updateGrade = useUpdateGrade()

  const [score, setScore] = useState("")
  const [activity, setActivity] = useState("")
  const [remarks, setRemarks] = useState("")
  const [seededId, setSeededId] = useState<string | null>(null)

  if (grade && seededId !== grade.id) {
    // Re-seed whenever the dialog opens on a different grade.
    const parsed = parseActivityRemarks(grade.remarks ?? null)
    setSeededId(grade.id)
    setScore(grade.score === null ? "" : String(grade.score))
    setActivity(
      (GRADE_ACTIVITY_TYPES as readonly string[]).includes(parsed.activity)
        ? parsed.activity
        : ""
    )
    setRemarks(parsed.text)
  }

  const onSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!grade) return
    const trimmed = score.trim()
    updateGrade.mutate(
      {
        id: grade.id,
        payload: {
          score: trimmed === "" ? null : Number(trimmed),
          remarks: formatActivityRemarks(activity, remarks),
        },
      },
      { onSuccess: () => onClose() }
    )
  }

  const scoreError = getFieldError(updateGrade.error, "score")
  const remarksError = getFieldError(updateGrade.error, "remarks")
  const saving = updateGrade.isPending

  return (
    <Dialog
      open={grade !== null}
      onOpenChange={(next) => {
        if (!next) onClose()
      }}
    >
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Update grade</DialogTitle>
          <DialogDescription>
            {grade
              ? `${grade.student_name} (${grade.student_id}) — ${grade.subject_name} (${grade.subject_code})`
              : null}
          </DialogDescription>
        </DialogHeader>

        <form
          className="space-y-3"
          id="grade-edit-form"
          onSubmit={onSubmit}
          noValidate
        >
          <Field
            label="Score (0–100)"
            id="grade-edit-score"
            type="number"
            min={0}
            max={100}
            required
            value={score}
            onChange={setScore}
            error={scoreError}
          />
          <Field
            label="Remarks"
            id="grade-edit-remarks"
            value={remarks}
            onChange={setRemarks}
            error={remarksError}
          />
          <div className="space-y-1.5">
            <Label htmlFor="grade-edit-activity">Activity type</Label>
            <Select value={activity} onValueChange={setActivity}>
              <SelectTrigger id="grade-edit-activity">
                <SelectValue placeholder="Whole grade (no activity)" />
              </SelectTrigger>
              <SelectContent>
                {GRADE_ACTIVITY_TYPES.map((type) => (
                  <SelectItem key={type} value={type}>
                    {type}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {updateGrade.isError && !scoreError ? (
            <ErrorNote message={normalizeApiError(updateGrade.error).message} />
          ) : null}
        </form>

        <DialogFooter>
          <Button type="button" variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" form="grade-edit-form" disabled={saving}>
            {saving ? "Saving…" : "Save changes"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
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

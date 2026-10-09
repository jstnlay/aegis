import { ClipboardCheck } from "lucide-react"
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
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import { ErrorNote } from "@/components/feedback/Feedback"
import { Field } from "@/components/ui/form-field"
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
  ASSESSMENT_QUESTION_TYPES,
  ASSESSMENT_QUESTION_TYPE_LABELS,
  OPTIONS_BEARING_QUESTION_TYPES,
  nextQuestionOrder,
  useCreateFacultyAssessment,
  useCreateFacultyAssessmentQuestion,
  useDeployFacultyAssessment,
  useFacultyAssessments,
  useFacultyAssessmentQuestions,
  useFacultyAssessmentResults,
  useFacultyTargetStudents,
  type AssessmentQuestionType,
  type FacultyAssessment,
  type FacultyAssessmentQuestion,
  type FacultyAssessmentResult,
  type FacultyTargetStudent,
} from "@/features/faculty/assessments-api"
import { normalizeApiError } from "@/lib/error"

/**
 * Faculty assessments.
 *
 * Faculty author `academic` assessments only. `Assessment.clean()` requires an
 * academic assessment to have `creator_role="faculty"` and a faculty
 * `created_by`, and `AssessmentViewSet.get_queryset` returns only the caller's
 * own assessments — so this page is academic-only by server scope, not by a
 * client-side filter. Wellness and behavioral assessments stay on the guidance
 * page, which is unchanged.
 *
 * Everything shown here is real: the list, question counts and results all come
 * from the backend, and an absent value renders as an em dash rather than a
 * zero.
 */

type StatusFilter = "all" | "published" | "draft"

function PageHeading() {
  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center gap-3">
        <ClipboardCheck
          className="size-5 text-muted-foreground"
          aria-hidden="true"
        />
        <h2 className="text-2xl font-bold text-foreground">Assessments</h2>
      </div>
      <p className="text-sm text-muted-foreground">
        The academic assessments you created. Build a plan, add its questions,
        then deploy it to your students.
      </p>
    </div>
  )
}

function NewAssessmentDialog({
  students,
}: {
  students: FacultyTargetStudent[]
}) {
  const create = useCreateFacultyAssessment()

  const [open, setOpen] = useState(false)
  const [title, setTitle] = useState("")
  const [description, setDescription] = useState("")
  const [timeLimit, setTimeLimit] = useState("")
  const [deadline, setDeadline] = useState("")
  const [targetIds, setTargetIds] = useState<string[]>([])

  const titleBlank = title.trim().length === 0
  const parsedLimit = timeLimit.trim() === "" ? null : Number(timeLimit)
  const limitInvalid =
    parsedLimit !== null && (!Number.isInteger(parsedLimit) || parsedLimit <= 0)

  function toggleTarget(id: string) {
    setTargetIds((current) =>
      current.includes(id)
        ? current.filter((item) => item !== id)
        : [...current, id]
    )
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (titleBlank || limitInvalid) return
    try {
      await create.mutateAsync({
        title: title.trim(),
        // Academic is the only type faculty may author; the server infers
        // creator_role from it and rejects any other value.
        assessment_type: "academic",
        description: description.trim() || null,
        time_limit_minutes: parsedLimit,
        deadline: deadline || null,
        target_students: targetIds,
      })
      setTitle("")
      setDescription("")
      setTimeLimit("")
      setDeadline("")
      setTargetIds([])
      setOpen(false)
    } catch {
      // Surfaced from `create.isError`; the dialog stays open with the draft.
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button>New assessment</Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>New assessment</DialogTitle>
          <DialogDescription>
            Starts as a draft. Add questions before deploying.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4">
          <Field
            label="Title"
            id="faculty-assessment-title"
            required
            value={title}
            onChange={setTitle}
          />

          <div className="space-y-1.5">
            <Label htmlFor="faculty-assessment-type">Type</Label>
            <Input
              id="faculty-assessment-type"
              value="Academic"
              readOnly
              aria-describedby="faculty-assessment-type-hint"
            />
            <p
              id="faculty-assessment-type-hint"
              className="text-xs text-muted-foreground"
            >
              Faculty create academic assessments. Wellness and behavioral
              assessments belong to guidance.
            </p>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="faculty-assessment-description">Description</Label>
            <textarea
              id="faculty-assessment-description"
              rows={3}
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-xs outline-none focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring"
            />
          </div>

          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="faculty-assessment-time-limit">
                Time limit (minutes)
              </Label>
              <Input
                id="faculty-assessment-time-limit"
                type="number"
                min={1}
                aria-invalid={limitInvalid || undefined}
                aria-describedby={
                  limitInvalid
                    ? "faculty-assessment-time-limit-error"
                    : "faculty-assessment-time-limit-hint"
                }
                value={timeLimit}
                onChange={(event) => setTimeLimit(event.target.value)}
              />
              {limitInvalid ? (
                <p
                  id="faculty-assessment-time-limit-error"
                  role="alert"
                  className="text-xs text-destructive"
                >
                  Must be a whole number of minutes.
                </p>
              ) : (
                <p
                  id="faculty-assessment-time-limit-hint"
                  className="text-xs text-muted-foreground"
                >
                  Optional.
                </p>
              )}
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="faculty-assessment-deadline">Deadline</Label>
              <Input
                id="faculty-assessment-deadline"
                type="date"
                value={deadline}
                onChange={(event) => setDeadline(event.target.value)}
              />
              <p className="text-xs text-muted-foreground">Optional.</p>
            </div>
          </div>

          <fieldset className="space-y-1.5">
            <legend className="text-sm font-medium">Target students</legend>
            {students.length === 0 ? (
              <p className="text-xs text-muted-foreground">
                No students in your sections to target yet.
              </p>
            ) : (
              <>
                <div className="flex flex-wrap gap-1.5">
                  {students.map((student) => {
                    const selected = targetIds.includes(student.id)
                    return (
                      <Button
                        key={student.id}
                        type="button"
                        size="sm"
                        variant={selected ? "secondary" : "outline"}
                        aria-pressed={selected}
                        onClick={() => toggleTarget(student.id)}
                      >
                        {student.name}
                      </Button>
                    )
                  })}
                </div>
                <p className="text-xs text-muted-foreground">
                  {targetIds.length} selected. Only students in your own
                  sections are listed.
                </p>
              </>
            )}
          </fieldset>

          {create.isError ? (
            <ErrorNote message={normalizeApiError(create.error).message} />
          ) : null}

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => setOpen(false)}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              disabled={create.isPending || titleBlank || limitInvalid}
            >
              {create.isPending ? "Creating…" : "Create assessment"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

function AddQuestionForm({
  assessment,
  questions,
}: {
  assessment: FacultyAssessment
  questions: FacultyAssessmentQuestion[]
}) {
  const create = useCreateFacultyAssessmentQuestion()

  const [questionText, setQuestionText] = useState("")
  const [questionType, setQuestionType] =
    useState<AssessmentQuestionType>("multiple_choice")
  const [order, setOrder] = useState<string>("")
  const [options, setOptions] = useState<string>("")
  const [correctAnswer, setCorrectAnswer] = useState("")

  const derivedOrder = nextQuestionOrder(questions)
  const effectiveOrder = order.trim() === "" ? derivedOrder : Number(order)
  const orderInvalid = !Number.isInteger(effectiveOrder) || effectiveOrder <= 0

  const needsOptions = OPTIONS_BEARING_QUESTION_TYPES.includes(questionType)
  const optionsList = options
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
  const optionsInvalid = needsOptions && optionsList.length < 2

  const textBlank = questionText.trim().length === 0
  const canSubmit =
    !textBlank && !orderInvalid && !optionsInvalid && !create.isPending

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!canSubmit) return
    try {
      await create.mutateAsync({
        assessment: assessment.id,
        question_text: questionText.trim(),
        question_type: questionType,
        order: effectiveOrder,
        options: needsOptions ? optionsList : null,
        correct_answer: correctAnswer.trim() || null,
      })
      setQuestionText("")
      setCorrectAnswer("")
      setOptions("")
      setOrder("")
    } catch {
      // Surfaced from `create.isError`.
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-3">
      <Field
        label="Question text"
        id={`faculty-question-text-${assessment.id}`}
        required
        value={questionText}
        onChange={setQuestionText}
      />

      <div className="grid gap-3 sm:grid-cols-2">
        <div className="space-y-1.5">
          <Label htmlFor={`faculty-question-type-${assessment.id}`}>Type</Label>
          <Select
            value={questionType}
            onValueChange={(value) =>
              setQuestionType(value as AssessmentQuestionType)
            }
          >
            <SelectTrigger id={`faculty-question-type-${assessment.id}`}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {ASSESSMENT_QUESTION_TYPES.map((type) => (
                <SelectItem key={type} value={type}>
                  {ASSESSMENT_QUESTION_TYPE_LABELS[type]}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="space-y-1.5">
          <Label htmlFor={`faculty-question-order-${assessment.id}`}>
            Order
          </Label>
          <Input
            id={`faculty-question-order-${assessment.id}`}
            type="number"
            min={1}
            aria-invalid={orderInvalid || undefined}
            value={order}
            placeholder={String(derivedOrder)}
            onChange={(event) => setOrder(event.target.value)}
          />
          <p className="text-xs text-muted-foreground">
            Defaults to {derivedOrder}, the next free order.
          </p>
        </div>
      </div>

      {needsOptions ? (
        <div className="space-y-1.5">
          <Label htmlFor={`faculty-question-options-${assessment.id}`}>
            Options (one per line)
          </Label>
          <textarea
            id={`faculty-question-options-${assessment.id}`}
            rows={3}
            value={options}
            aria-invalid={optionsInvalid || undefined}
            onChange={(event) => setOptions(event.target.value)}
            className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-xs outline-none focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring"
          />
          {optionsInvalid ? (
            <p role="alert" className="text-xs text-destructive">
              This type needs at least two options.
            </p>
          ) : null}
        </div>
      ) : null}

      <div className="space-y-1.5">
        <Label htmlFor={`faculty-question-answer-${assessment.id}`}>
          Correct answer
        </Label>
        <Input
          id={`faculty-question-answer-${assessment.id}`}
          value={correctAnswer}
          onChange={(event) => setCorrectAnswer(event.target.value)}
        />
        <p className="text-xs text-muted-foreground">
          Only multiple-choice and true/false questions are auto-graded.
        </p>
      </div>

      {create.isError ? (
        <ErrorNote message={normalizeApiError(create.error).message} />
      ) : null}

      <Button type="submit" disabled={!canSubmit}>
        {create.isPending ? "Adding…" : "Add question"}
      </Button>
    </form>
  )
}

function QuestionsBlock({ assessment }: { assessment: FacultyAssessment }) {
  const questionsQuery = useFacultyAssessmentQuestions(assessment.id)

  if (questionsQuery.isLoading) {
    return <Skeleton className="h-16 w-full" aria-hidden="true" />
  }
  if (questionsQuery.isError) {
    return (
      <ErrorNote message={normalizeApiError(questionsQuery.error).message} />
    )
  }

  const questions = questionsQuery.data ?? []

  return (
    <div className="space-y-3">
      <h4 className="text-sm font-medium">Questions ({questions.length})</h4>

      {questions.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          No questions yet. An assessment cannot be deployed without at least
          one.
        </p>
      ) : (
        <ol className="space-y-2">
          {questions.map((question) => (
            <li
              key={question.id}
              className="rounded-md border border-border p-3 text-sm"
            >
              <p className="font-medium">
                {question.order}. {question.question_text}
              </p>
              <p className="text-xs text-muted-foreground">
                {ASSESSMENT_QUESTION_TYPE_LABELS[question.question_type]}
                {question.correct_answer
                  ? ` · answer: ${question.correct_answer}`
                  : ""}
              </p>
              {question.options?.length ? (
                <ul className="mt-1 list-inside list-disc text-xs text-muted-foreground">
                  {question.options.map((option) => (
                    <li key={option}>{option}</li>
                  ))}
                </ul>
              ) : null}
            </li>
          ))}
        </ol>
      )}

      {/* `perform_create` rejects a question on a published assessment, so the
          form is only offered while the assessment is still a draft. */}
      {!assessment.is_published ? (
        <AddQuestionForm assessment={assessment} questions={questions} />
      ) : null}
    </div>
  )
}

function ResultsForAssessment({
  assessment,
  results,
}: {
  assessment: FacultyAssessment
  results: FacultyAssessmentResult[]
}) {
  if (!assessment.is_published) {
    return (
      <p className="text-sm text-muted-foreground">
        Not deployed yet, so no results exist.
      </p>
    )
  }

  const byStudent = new Map<string, FacultyAssessmentResult[]>()
  for (const result of results) {
    const bucket = byStudent.get(result.student)
    if (bucket) bucket.push(result)
    else byStudent.set(result.student, [result])
  }

  if (byStudent.size === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        No student has started this assessment yet.
      </p>
    )
  }

  return (
    <div className="space-y-2">
      <h4 className="text-sm font-medium">Results</h4>
      <Table>
        <TableCaption>
          Scores for this assessment. Percentage is 0&ndash;100.
        </TableCaption>
        <TableHeader>
          <TableRow>
            <TableHead scope="col">Student</TableHead>
            <TableHead scope="col">Status</TableHead>
            <TableHead scope="col">Score</TableHead>
            <TableHead scope="col">Percentage</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {[...byStudent.entries()].flatMap(([studentId, rows]) => {
            // A student with several submissions shows the latest attempt.
            const row = rows[rows.length - 1]
            if (!row) return []
            return [
              <TableRow key={studentId}>
                <TableCell>{row.student_name}</TableCell>
                <TableCell>
                  <Badge variant="outline">{row.status}</Badge>
                </TableCell>
                {/* An ungraded or absent score renders as an em dash, never a
                    fabricated zero. */}
                <TableCell>
                  {row.score === null
                    ? "—"
                    : `${row.score}${
                        row.total_possible === null
                          ? ""
                          : ` / ${row.total_possible}`
                      }`}
                </TableCell>
                <TableCell>
                  {row.percentage === null ? "—" : `${row.percentage}%`}
                </TableCell>
              </TableRow>,
            ]
          })}
        </TableBody>
      </Table>
    </div>
  )
}

export function FacultyAssessmentsPage() {
  const assessmentsQuery = useFacultyAssessments()
  const resultsQuery = useFacultyAssessmentResults()
  const studentsQuery = useFacultyTargetStudents()
  const deploy = useDeployFacultyAssessment()

  const [status, setStatus] = useState<StatusFilter>("all")
  const [search, setSearch] = useState("")

  const assessments = useMemo(
    () => assessmentsQuery.data ?? [],
    [assessmentsQuery.data]
  )
  const results = useMemo(() => resultsQuery.data ?? [], [resultsQuery.data])
  const students = useMemo(() => studentsQuery.data ?? [], [studentsQuery.data])

  const visible = useMemo(() => {
    const needle = search.trim().toLowerCase()
    return assessments.filter((assessment) => {
      if (status === "published" && !assessment.is_published) return false
      if (status === "draft" && assessment.is_published) return false
      if (needle) {
        const haystack =
          `${assessment.title} ${assessment.description ?? ""}`.toLowerCase()
        if (!haystack.includes(needle)) return false
      }
      return true
    })
  }, [assessments, status, search])

  const resultsByAssessment = useMemo(() => {
    const map = new Map<string, FacultyAssessmentResult[]>()
    for (const result of results) {
      const bucket = map.get(result.assessment)
      if (bucket) bucket.push(result)
      else map.set(result.assessment, [result])
    }
    return map
  }, [results])

  const isFiltered = status !== "all" || search.trim().length > 0

  return (
    <div className="space-y-6">
      <PageHeading />

      <Card>
        <CardHeader>
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="space-y-1">
              <CardTitle>Your assessments</CardTitle>
              <CardDescription>
                Showing {visible.length} of {assessments.length}.
              </CardDescription>
            </div>
            <NewAssessmentDialog students={students} />
          </div>
        </CardHeader>

        <CardContent className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="faculty-assessment-filter-status">Status</Label>
              <Select
                value={status}
                onValueChange={(value) => setStatus(value as StatusFilter)}
              >
                <SelectTrigger id="faculty-assessment-filter-status">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All statuses</SelectItem>
                  <SelectItem value="published">Published</SelectItem>
                  <SelectItem value="draft">Draft</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="faculty-assessment-search">Search</Label>
              <Input
                id="faculty-assessment-search"
                type="search"
                value={search}
                placeholder="Title or description"
                onChange={(event) => setSearch(event.target.value)}
              />
            </div>
          </div>

          {deploy.isError ? (
            <ErrorNote message={normalizeApiError(deploy.error).message} />
          ) : null}

          {assessmentsQuery.isLoading ? (
            <div className="space-y-2">
              <Skeleton className="h-20 w-full" />
              <Skeleton className="h-20 w-full" />
            </div>
          ) : assessmentsQuery.isError ? (
            <ErrorNote
              message={normalizeApiError(assessmentsQuery.error).message}
            />
          ) : visible.length === 0 ? (
            <p className="py-6 text-center text-sm text-muted-foreground">
              {isFiltered
                ? "No assessments match the current filters."
                : "You have not created any assessments yet."}
            </p>
          ) : (
            <div className="space-y-4">
              {visible.map((assessment) => (
                <div
                  key={assessment.id}
                  data-assessment-id={assessment.id}
                  className="space-y-3 rounded-md border border-border p-4"
                >
                  <div className="space-y-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <h3 className="font-semibold">{assessment.title}</h3>
                      <Badge variant="secondary">Academic</Badge>
                      <Badge
                        variant="outline"
                        data-published={
                          assessment.is_published ? "true" : "false"
                        }
                      >
                        {assessment.is_published ? "Published" : "Draft"}
                      </Badge>
                    </div>
                    {assessment.description ? (
                      <p className="text-sm text-muted-foreground">
                        {assessment.description}
                      </p>
                    ) : null}
                    <p className="text-xs text-muted-foreground">
                      {assessment.question_count} question
                      {assessment.question_count === 1 ? "" : "s"}
                      {assessment.time_limit_minutes === null
                        ? " · no time limit"
                        : ` · ${assessment.time_limit_minutes} min limit`}
                      {assessment.deadline
                        ? ` · due ${assessment.deadline}`
                        : ""}
                    </p>
                  </div>

                  <div className="flex flex-wrap items-center gap-2">
                    {/* One button per card, so the bare verb gave them all the
                        same accessible name. The label names the assessment and
                        still contains the visible "Deploy" (WCAG 2.5.3). */}
                    {!assessment.is_published ? (
                      /*
                       * The server 400s a draft without questions, so the
                       * control is withheld until one exists and the reason is
                       * stated in text instead of left to a failed request.
                       */
                      <>
                        <Button
                          type="button"
                          size="sm"
                          disabled={
                            deploy.isPending || assessment.question_count === 0
                          }
                          aria-label={
                            deploy.isPending &&
                            deploy.variables?.id === assessment.id
                              ? `Deploying ${assessment.title}`
                              : `Deploy ${assessment.title}`
                          }
                          onClick={() => deploy.mutate({ id: assessment.id })}
                        >
                          {deploy.isPending &&
                          deploy.variables?.id === assessment.id
                            ? "Deploying…"
                            : "Deploy"}
                        </Button>
                        {assessment.question_count === 0 ? (
                          <p className="text-xs text-muted-foreground">
                            Add at least one question before deploying.
                          </p>
                        ) : null}
                      </>
                    ) : (
                      /* `role="status"`: a successful deploy was previously only
                         conveyed by the button turning into plain text, which is
                         not an announcement. */
                      <span
                        role="status"
                        className="text-xs text-muted-foreground"
                      >
                        Deployed. The server blocks a second deploy.
                      </span>
                    )}
                  </div>

                  <QuestionsBlock assessment={assessment} />

                  {resultsQuery.isLoading ? (
                    <Skeleton className="h-16 w-full" />
                  ) : resultsQuery.isError ? (
                    <ErrorNote
                      message={normalizeApiError(resultsQuery.error).message}
                    />
                  ) : (
                    <ResultsForAssessment
                      assessment={assessment}
                      results={resultsByAssessment.get(assessment.id) ?? []}
                    />
                  )}
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      <p className="text-xs text-muted-foreground">
        The server scopes this list to academic assessments you created. An
        assessment starts as a draft, cannot be deployed without at least one
        question, and cannot be edited or deleted once published. Percentages
        are 0&ndash;100, not a 0&ndash;1 ratio. Wellness and behavioral
        assessments remain on the guidance assessments page.
      </p>
    </div>
  )
}

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
  GUIDANCE_ASSESSMENT_TYPES,
  OPTIONS_BEARING_QUESTION_TYPES,
  filterAssessments,
  nextQuestionOrder,
  useAssessmentQuestions,
  useCreateAssessment,
  useCreateAssessmentQuestion,
  useDeployAssessment,
  useGuidanceAssessments,
  useGuidanceAssessmentResults,
  useGuidanceStudents,
  type AssessmentQuestion,
  type AssessmentQuestionType,
  type GuidanceAssessment,
  type GuidanceAssessmentResult,
  type GuidanceAssessmentType,
  type GuidanceStudent,
} from "@/features/guidance/api"
import { normalizeApiError } from "@/lib/error"

type StatusFilter = "all" | "published" | "draft"
type TypeFilter = "all" | "wellness" | "behavioral"

const ASSESSMENT_TYPE_LABELS: Record<GuidanceAssessmentType, string> = {
  wellness: "Wellness",
  behavioral: "Behavioral",
}

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
        The wellness and behavioral assessments you created. Build a plan, add
        its questions, then deploy it to your students.
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

/** `POST /assessments/assessments/` form. */
function NewAssessmentDialog({ students }: { students: GuidanceStudent[] }) {
  const create = useCreateAssessment()

  const [open, setOpen] = useState(false)
  const [title, setTitle] = useState("")
  const [assessmentType, setAssessmentType] =
    useState<GuidanceAssessmentType>("wellness")
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
        assessment_type: assessmentType,
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
            id="assessment-title"
            required
            value={title}
            onChange={setTitle}
          />

          <div className="space-y-1.5">
            <Label htmlFor="assessment-type">Type</Label>
            <Select
              value={assessmentType}
              onValueChange={(value) =>
                setAssessmentType(value as GuidanceAssessmentType)
              }
            >
              <SelectTrigger id="assessment-type">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {GUIDANCE_ASSESSMENT_TYPES.map((type) => (
                  <SelectItem key={type} value={type}>
                    {ASSESSMENT_TYPE_LABELS[type]}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <p className="text-xs text-muted-foreground">
              Academic assessments belong to faculty and are not offered here.
            </p>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="assessment-description">Description</Label>
            <textarea
              id="assessment-description"
              rows={3}
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-xs outline-none focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring"
            />
          </div>

          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="assessment-time-limit">
                Time limit (minutes)
              </Label>
              <Input
                id="assessment-time-limit"
                type="number"
                min={1}
                aria-invalid={limitInvalid || undefined}
                aria-describedby={
                  limitInvalid
                    ? "assessment-time-limit-error"
                    : "assessment-time-limit-hint"
                }
                value={timeLimit}
                onChange={(event) => setTimeLimit(event.target.value)}
              />
              {limitInvalid ? (
                <p
                  id="assessment-time-limit-error"
                  role="alert"
                  className="text-xs text-destructive"
                >
                  Must be a whole number of minutes.
                </p>
              ) : (
                <p
                  id="assessment-time-limit-hint"
                  className="text-xs text-muted-foreground"
                >
                  Optional.
                </p>
              )}
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="assessment-deadline">Deadline</Label>
              <Input
                id="assessment-deadline"
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
                No students with guidance activity to target yet.
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
                  {targetIds.length} selected. Only students with guidance
                  activity are listed.
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

/**
 * `POST /assessments/assessment-questions/` form, for a draft assessment.
 *
 * `questions` is the already-loaded list for this assessment, and it is what
 * drives the default order. `AssessmentQuestion` is unique on
 * `(assessment, order)`, so a hardcoded default of 1 collides on the first add
 * to any draft that already holds a question. The field stays editable; an
 * explicit override is cleared after a successful create so the form falls back
 * to the derived default and follows the refetched list.
 */
function AddQuestionForm({
  assessment,
  questions,
}: {
  assessment: GuidanceAssessment
  questions: AssessmentQuestion[]
}) {
  const create = useCreateAssessmentQuestion()

  const [questionText, setQuestionText] = useState("")
  const [questionType, setQuestionType] =
    useState<AssessmentQuestionType>("multiple_choice")
  // `null` means "no manual override" — show the derived next order.
  const [orderOverride, setOrderOverride] = useState<string | null>(null)
  const [optionsText, setOptionsText] = useState("")
  const [correctAnswer, setCorrectAnswer] = useState("")

  const nextOrder = nextQuestionOrder(questions)
  const order = orderOverride ?? String(nextOrder)

  const takesOptions = OPTIONS_BEARING_QUESTION_TYPES.includes(questionType)
  const textBlank = questionText.trim().length === 0

  const parsedOrder = Number.parseInt(order, 10)
  const orderInvalid = !Number.isInteger(parsedOrder) || parsedOrder < 1

  // `AssessmentQuestion` is unique on `(assessment, order)`, so an order already
  // used by a sibling question cannot be reused. Caught here rather than by
  // letting the request fail, because the server rejects the collision.
  const orderTaken = questions.some(
    (question) => question.order === parsedOrder
  )

  const options = useMemo(
    () =>
      optionsText
        .split("\n")
        .map((line) => line.trim())
        .filter((line) => line.length > 0),
    [optionsText]
  )

  const answer = correctAnswer.trim()

  // `AssessmentQuestion.clean()` enforces all three of these. The model cannot
  // report them as field errors — `save()` calls `full_clean()`, whose Django
  // ValidationError DRF does not handle — so the server rejects the request
  // without saying which field was wrong. Mirrored here so the form blocks the
  // submit and names the field instead.
  const optionsTooFew = takesOptions && options.length < 2

  const answerNotAnOption =
    questionType === "multiple_choice" &&
    answer.length > 0 &&
    !options.includes(answer)

  const answerNotBoolean =
    questionType === "true_false" &&
    answer.length > 0 &&
    answer !== "True" &&
    answer !== "False"

  const blocked =
    textBlank ||
    orderInvalid ||
    orderTaken ||
    optionsTooFew ||
    answerNotAnOption ||
    answerNotBoolean

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (blocked) return
    try {
      await create.mutateAsync({
        assessment: assessment.id,
        question_text: questionText.trim(),
        question_type: questionType,
        order: parsedOrder,
        options: takesOptions ? options : null,
        correct_answer: answer.length > 0 ? answer : null,
      })
      setQuestionText("")
      setOptionsText("")
      setCorrectAnswer("")
      // Drop the manual override so the field re-derives from the refetched
      // question list rather than continuing from the submitted value.
      setOrderOverride(null)
    } catch {
      // Surfaced from `create.isError` below.
    }
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="space-y-3 rounded-md border border-border p-3"
      aria-label="Add question"
    >
      <div className="space-y-1.5">
        {/*
          Every id in this form is suffixed with the assessment id. The form is
          rendered once per draft assessment from inside the page's `.map()`, so
          the previous static ids (`question-text`, `question-order`, …) existed
          two or more times as soon as a second draft was on screen, and every
          `<label for>` resolved to the first instance — a label pointing at
          somebody else's control, which is an HTML validity error and a WCAG
          4.1.1 / 3.3.2 failure. The sibling forms in this file already scope
          their ids per instance (`step-title-${step.id}`), so this matches.
        */}
        <div className="flex items-center gap-1">
          <Label htmlFor={`question-text-${assessment.id}`}>
            Question text
          </Label>
          <span aria-hidden="true" className="text-destructive">
            *
          </span>
        </div>
        <textarea
          id={`question-text-${assessment.id}`}
          rows={2}
          aria-required="true"
          value={questionText}
          onChange={(event) => setQuestionText(event.target.value)}
          className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-xs outline-none focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring"
        />
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        <div className="space-y-1.5">
          <Label htmlFor={`question-type-${assessment.id}`}>
            Question type
          </Label>
          <Select
            value={questionType}
            onValueChange={(value) => {
              setQuestionType(value as AssessmentQuestionType)
              if (
                !OPTIONS_BEARING_QUESTION_TYPES.includes(
                  value as AssessmentQuestionType
                )
              ) {
                setOptionsText("")
              }
            }}
          >
            <SelectTrigger id={`question-type-${assessment.id}`}>
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
          <div className="flex items-center gap-1">
            <Label htmlFor={`question-order-${assessment.id}`}>Order</Label>
            <span aria-hidden="true" className="text-destructive">
              *
            </span>
          </div>
          <Input
            id={`question-order-${assessment.id}`}
            type="number"
            min={1}
            aria-required="true"
            aria-invalid={orderInvalid || orderTaken || undefined}
            aria-describedby={
              orderInvalid || orderTaken
                ? `question-order-${assessment.id}-error`
                : `question-order-${assessment.id}-hint`
            }
            value={order}
            onChange={(event) => setOrderOverride(event.target.value)}
          />
          {/* Two messages, one id: they are mutually exclusive, so the id is
              never rendered twice and is only referenced while present. */}
          {orderInvalid ? (
            <p
              id={`question-order-${assessment.id}-error`}
              role="alert"
              className="text-xs text-destructive"
            >
              Order must be 1 or greater.
            </p>
          ) : orderTaken ? (
            <p
              id={`question-order-${assessment.id}-error`}
              role="alert"
              className="text-xs text-destructive"
            >
              Order {parsedOrder} is already used by another question in this
              assessment.
            </p>
          ) : (
            <p
              id={`question-order-${assessment.id}-hint`}
              className="text-xs text-muted-foreground"
            >
              Defaults to {nextOrder}, one past the highest existing order.
            </p>
          )}
        </div>
      </div>

      {takesOptions ? (
        <div className="space-y-1.5">
          <div className="flex items-center gap-1">
            <Label htmlFor={`question-options-${assessment.id}`}>
              {questionType === "likert" ? "Scale points" : "Options"}
            </Label>
            <span aria-hidden="true" className="text-destructive">
              *
            </span>
          </div>
          <textarea
            id={`question-options-${assessment.id}`}
            rows={3}
            aria-required="true"
            aria-invalid={optionsTooFew || undefined}
            aria-describedby={`question-options-${assessment.id}-${
              optionsTooFew ? "error" : "hint"
            }`}
            value={optionsText}
            onChange={(event) => setOptionsText(event.target.value)}
            placeholder={"One per line, e.g.\nStrongly agree\nAgree"}
            className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-xs outline-none focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring"
          />
          {/*
            Minimum option count and answer-key shape are real backend rules
            (`AssessmentQuestion.clean()`): multiple_choice and likert need at
            least 2 options, and a multiple_choice correct answer must be one of
            them. An earlier revision of this form asserted the opposite — that
            `options` was an unconstrained JSONField — and removed the client
            check on that basis. The constraint is enforced by the model's
            clean(), so the form blocks the submit and names the field.

            This paragraph is the error, not just a caption: it turns red and
            replaces the count when the field is short, so it carries
            `role="alert"` to be announced and an id for `aria-describedby` to
            point at. It previously had no role at all and was therefore only
            marked visually.
          */}
          <p
            id={`question-options-${assessment.id}-${
              optionsTooFew ? "error" : "hint"
            }`}
            role={optionsTooFew ? "alert" : undefined}
            className={
              optionsTooFew
                ? "text-xs text-destructive"
                : "text-xs text-muted-foreground"
            }
          >
            {optionsTooFew
              ? questionType === "likert"
                ? "Likert questions must have at least 2 scale options."
                : "Multiple choice questions must have at least 2 options."
              : `${options.length} option${options.length === 1 ? "" : "s"}; one per line.`}
          </p>
        </div>
      ) : null}

      <div className="space-y-1.5">
        {/*
          The correct answer is genuinely optional — an essay question has none,
          and the copy below says so — so it is not marked required. It still
          has two failure modes the server enforces (`multiple_choice` answers
          must name one of the options; `true_false` answers must be exactly
          "True" or "False"), and the same red paragraph covers both, so it is
          treated as the field's error and linked back to the control.
        */}
        <Label htmlFor={`question-answer-${assessment.id}`}>
          Correct answer
        </Label>
        <Input
          id={`question-answer-${assessment.id}`}
          aria-invalid={answerNotAnOption || answerNotBoolean || undefined}
          aria-describedby={`question-answer-${assessment.id}-${
            answerNotAnOption || answerNotBoolean ? "error" : "hint"
          }`}
          value={correctAnswer}
          onChange={(event) => setCorrectAnswer(event.target.value)}
        />
        <p
          id={`question-answer-${assessment.id}-${
            answerNotAnOption || answerNotBoolean ? "error" : "hint"
          }`}
          role={answerNotAnOption || answerNotBoolean ? "alert" : undefined}
          className={
            answerNotAnOption || answerNotBoolean
              ? "text-xs text-destructive"
              : "text-xs text-muted-foreground"
          }
        >
          {answerNotAnOption
            ? "Correct answer must be one of the provided options."
            : answerNotBoolean
              ? 'True/False correct answer must be "True" or "False".'
              : questionType === "true_false"
                ? 'Optional. Must be exactly "True" or "False" if given.'
                : "Optional. Stored as the answer text that matches one of the options."}
        </p>
      </div>

      {create.isError ? (
        <ErrorNote message={normalizeApiError(create.error).message} />
      ) : null}

      <Button type="submit" size="sm" disabled={create.isPending || blocked}>
        {create.isPending ? "Adding…" : "Add question"}
      </Button>
    </form>
  )
}

function QuestionsBlock({ assessment }: { assessment: GuidanceAssessment }) {
  const questionsQuery = useAssessmentQuestions(assessment.id)
  const questions = useMemo(
    () => questionsQuery.data ?? [],
    [questionsQuery.data]
  )

  // `perform_create` blocks new questions once an assessment is published, so
  // the form is not rendered for a live assessment.
  if (assessment.is_published) {
    return questions.length === 0 ? (
      <p className="text-sm text-muted-foreground">No questions on record.</p>
    ) : (
      <QuestionList questions={questions} />
    )
  }

  return (
    <div className="space-y-3">
      {questionsQuery.isLoading ? (
        <Skeleton className="h-16 w-full" />
      ) : questionsQuery.isError ? (
        <ErrorNote message={normalizeApiError(questionsQuery.error).message} />
      ) : questions.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          This assessment has no questions yet. The server refuses to deploy an
          assessment without at least one.
        </p>
      ) : (
        <QuestionList questions={questions} />
      )}
      <AddQuestionForm assessment={assessment} questions={questions} />
    </div>
  )
}

function QuestionList({ questions }: { questions: AssessmentQuestion[] }) {
  return (
    <ol className="space-y-2">
      {questions.map((question) => (
        <li
          key={question.id}
          data-question-id={question.id}
          className="rounded-md border border-border p-3"
        >
          <div className="flex flex-wrap items-center gap-2">
            <span className="tabular-nums text-xs text-muted-foreground">
              #{question.order}
            </span>
            <span className="text-sm font-medium">
              {question.question_text}
            </span>
            <Badge variant="outline">
              {ASSESSMENT_QUESTION_TYPE_LABELS[question.question_type]}
            </Badge>
          </div>
          {question.options && question.options.length > 0 ? (
            <p className="mt-1 text-xs text-muted-foreground">
              {question.options.join(" · ")}
            </p>
          ) : null}
          {question.correct_answer ? (
            <p className="mt-1 text-xs text-muted-foreground">
              Answer: {question.correct_answer}
            </p>
          ) : null}
        </li>
      ))}
    </ol>
  )
}

/**
 * Result monitoring for one assessment.
 *
 * `assessment` is needed for the caption. Several of these render on one page,
 * stacked inside the assessment cards, and they all carry the identical
 * "Student / Status / Score / Percentage" header — so without a caption a screen
 * reader announced several indistinguishable tables and the reader could not
 * tell whose results they were. The caption is the table's accessible name, and
 * it is screen-reader-only because the card heading above already says it
 * visually.
 */
function ResultsForAssessment({
  assessment,
  results,
}: {
  assessment: GuidanceAssessment
  results: GuidanceAssessmentResult[]
}) {
  if (results.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        No results recorded for this assessment yet.
      </p>
    )
  }

  const byStudent = new Map<string, GuidanceAssessmentResult[]>()
  for (const result of results) {
    const bucket = byStudent.get(result.student)
    if (bucket) bucket.push(result)
    else byStudent.set(result.student, [result])
  }
  const ordered = Array.from(byStudent.entries()).sort((a, b) => {
    const nameA = a[1].find((r) => r.student_name)?.student_name ?? ""
    const nameB = b[1].find((r) => r.student_name)?.student_name ?? ""
    return nameA.localeCompare(nameB)
  })

  return (
    <Table>
      {/* Must be the first child of `<table>`, which is where the HTML parser
          expects it. */}
      <TableCaption className="sr-only">
        Results for {assessment.title}
      </TableCaption>
      <TableHeader>
        <TableRow>
          {/* `scope="col"` so a screen reader announces the column as a header
              for the cells under it, rather than reading the header row as four
              unrelated labels. */}
          <TableHead scope="col">Student</TableHead>
          <TableHead scope="col">Status</TableHead>
          <TableHead scope="col">Score</TableHead>
          <TableHead scope="col">Percentage</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {ordered.flatMap(([, list]) =>
          list.map((result) => (
            <TableRow
              key={result.id}
              data-result-id={result.id}
              data-student-id={result.student}
            >
              <TableCell>
                <div className="font-medium">{result.student_name}</div>
                <div className="tabular-nums text-xs text-muted-foreground">
                  {result.student_id}
                </div>
              </TableCell>
              <TableCell>
                <Badge variant="outline" data-result-status={result.status}>
                  {result.status === "completed" ? "Completed" : "In progress"}
                </Badge>
              </TableCell>
              <TableCell className="tabular-nums text-sm text-muted-foreground">
                {result.score === null
                  ? "—"
                  : `${result.score} / ${result.total_possible ?? "—"}`}
              </TableCell>
              <TableCell className="tabular-nums">
                {result.percentage === null ? "—" : `${result.percentage}%`}
              </TableCell>
            </TableRow>
          ))
        )}
      </TableBody>
    </Table>
  )
}

export function AssessmentsPage() {
  const assessmentsQuery = useGuidanceAssessments()
  const resultsQuery = useGuidanceAssessmentResults()
  const studentsQuery = useGuidanceStudents()
  const deploy = useDeployAssessment()

  const [status, setStatus] = useState<StatusFilter>("all")
  const [assessmentType, setAssessmentType] = useState<TypeFilter>("all")
  const [search, setSearch] = useState("")

  const assessments = useMemo(
    () => assessmentsQuery.data ?? [],
    [assessmentsQuery.data]
  )
  const results = useMemo(() => resultsQuery.data ?? [], [resultsQuery.data])
  const students = useMemo(
    () => studentsQuery.data?.students ?? [],
    [studentsQuery.data]
  )

  const visible = useMemo(
    () => filterAssessments(assessments, { status, assessmentType, search }),
    [assessments, status, assessmentType, search]
  )

  const resultsByAssessment = useMemo(() => {
    const map = new Map<string, GuidanceAssessmentResult[]>()
    for (const result of results) {
      const bucket = map.get(result.assessment)
      if (bucket) bucket.push(result)
      else map.set(result.assessment, [result])
    }
    return map
  }, [results])

  const isFiltered =
    status !== "all" || assessmentType !== "all" || search.trim().length > 0

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
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            <div className="space-y-1.5">
              <Label htmlFor="assessment-filter-status">Status</Label>
              <Select
                value={status}
                onValueChange={(value) => setStatus(value as StatusFilter)}
              >
                <SelectTrigger id="assessment-filter-status">
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
              <Label htmlFor="assessment-filter-type">Type</Label>
              <Select
                value={assessmentType}
                onValueChange={(value) =>
                  setAssessmentType(value as TypeFilter)
                }
              >
                <SelectTrigger id="assessment-filter-type">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All types</SelectItem>
                  <SelectItem value="wellness">Wellness</SelectItem>
                  <SelectItem value="behavioral">Behavioral</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="assessment-search">Search</Label>
              <Input
                id="assessment-search"
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
                      <Badge variant="secondary">
                        {ASSESSMENT_TYPE_LABELS[
                          assessment.assessment_type as GuidanceAssessmentType
                        ] ?? assessment.assessment_type}
                      </Badge>
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
                    {/*
                      The deploy action is the real server endpoint. It 400s
                      when the assessment is already published, so the control
                      is only offered for a draft and the server message is
                      surfaced if it still refuses.
                    */}
                    {!assessment.is_published ? (
                      /*
                       * There is one of these per card and the bare verb gave
                       * them all the same accessible name. The label names the
                       * assessment and still contains the visible "Deploy"
                       * (WCAG 2.5.3); it follows the in-flight state too, since
                       * `aria-label` overrides the visible "Deploying…" text
                       * and that progress would otherwise be lost.
                       */
                      <Button
                        type="button"
                        size="sm"
                        disabled={deploy.isPending}
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
                    ) : (
                      /*
                       * `role="status"`: a successful deploy was previously
                       * conveyed only by this button quietly turning into plain
                       * text, which is not an announcement. The whole element is
                       * the confirmation, so it is the region.
                       */
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
        The server scopes this list to assessments you created, and only
        wellness and behavioral assessments are visible to guidance. An
        assessment starts as a draft, cannot be deployed without at least one
        question, and cannot be edited or deleted once published. Percentages
        are 0&ndash;100, not a 0&ndash;1 ratio.
      </p>
    </div>
  )
}

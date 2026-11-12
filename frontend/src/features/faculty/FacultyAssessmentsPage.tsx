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
  useAssessmentCompletion,
  useCreateFacultyAssessment,
  useCreateFacultyAssessmentQuestion,
  useDeployFacultyAssessment,
  useFacultyAssessments,
  useFacultyAssessmentQuestions,
  useFacultyAssessmentResults,
  useFacultyTargetStudents,
  useGenerateAssessmentDraft,
  useReviewAssessment,
  type AssessmentQuestionType,
  type FacultyAssessment,
  type FacultyAssessmentQuestion,
  type FacultyAssessmentResult,
  type FacultyTargetStudent,
} from "@/features/faculty/assessments-api"
import { useGenerateQuestionDrafts } from "@/features/guidance/api"
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

/**
 * The AI draft dialog.
 *
 * The assistant writes the questions; a teacher reads them. The server enforces
 * the second half: a generated assessment is created with
 * `review_status="pending"` and `deploy` refuses to publish it until a human
 * approves it. So this dialog promises exactly one thing — a draft nobody has
 * approved yet — and the approval control lives on the assessment card.
 */
function GenerateDraftDialog({ students }: { students: FacultyTargetStudent[] }) {
  const generate = useGenerateAssessmentDraft()

  const [open, setOpen] = useState(false)
  const [title, setTitle] = useState("")
  const [topic, setTopic] = useState("")
  const [questionType, setQuestionType] = useState<
    "multiple_choice" | "likert" | "essay"
  >("multiple_choice")
  const [count, setCount] = useState("5")
  const [targetIds, setTargetIds] = useState<string[]>([])

  const topicBlank = topic.trim().length === 0
  const parsedCount = Number(count)
  const countInvalid = !Number.isInteger(parsedCount) || parsedCount < 1 || parsedCount > 20

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (topicBlank || countInvalid) return
    try {
      await generate.mutateAsync({
        title: title.trim() || topic.trim(),
        topic: topic.trim(),
        question_type: questionType,
        count: parsedCount,
      })
      setTitle("")
      setTopic("")
      setTargetIds([])
      setOpen(false)
    } catch {
      // Surfaced from `generate.isError`.
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="outline">Generate AI draft</Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Generate an AI draft</DialogTitle>
          <DialogDescription>
            The assistant writes the questions. You read them before anything
            reaches a student — the server will not publish an unapproved
            draft.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4">
          <Field
            label="Title"
            id="faculty-draft-title"
            value={title}
            onChange={setTitle}
          />

          <Field
            label="Topic"
            id="faculty-draft-topic"
            required
            value={topic}
            onChange={setTopic}
          />

          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="faculty-draft-type">Question type</Label>
              <Select
                value={questionType}
                onValueChange={(value) =>
                  setQuestionType(value as "multiple_choice" | "likert" | "essay")
                }
              >
                <SelectTrigger id="faculty-draft-type">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="multiple_choice">Multiple choice</SelectItem>
                  <SelectItem value="likert">Likert scale</SelectItem>
                  <SelectItem value="essay">Essay</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="faculty-draft-count">Questions</Label>
              <Input
                id="faculty-draft-count"
                type="number"
                min={1}
                max={20}
                value={count}
                aria-invalid={countInvalid || undefined}
                onChange={(event) => setCount(event.target.value)}
              />
              {countInvalid ? (
                <p role="alert" className="text-xs text-destructive">
                  Between 1 and 20.
                </p>
              ) : null}
            </div>
          </div>

          <fieldset className="space-y-1.5">
            <legend className="text-sm font-medium">Target students</legend>
            {students.length === 0 ? (
              <p className="text-xs text-muted-foreground">
                No students in your sections to target yet.
              </p>
            ) : (
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
                      onClick={() =>
                        setTargetIds((current) =>
                          current.includes(student.id)
                            ? current.filter((item) => item !== student.id)
                            : [...current, student.id]
                        )
                      }
                    >
                      {student.name}
                    </Button>
                  )
                })}
              </div>
            )}
          </fieldset>

          {generate.isError ? (
            <ErrorNote message={normalizeApiError(generate.error).message} />
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
              disabled={generate.isPending || topicBlank || countInvalid}
            >
              {generate.isPending ? "Generating…" : "Generate draft"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

/**
 * The human review of an AI draft.
 *
 * Approve unlocks deployment. Request changes sends it back. There is no
 * "publish anyway": the server refuses an unapproved draft, and this control
 * is the only way out of that state.
 */
function ReviewControls({ assessment }: { assessment: FacultyAssessment }) {
  const review = useReviewAssessment()
  const [note, setNote] = useState("")

  return (
    <div className="space-y-2 rounded-md border border-dashed border-border p-3">
      <p className="text-sm font-medium">
        Human review required before this draft can be published
      </p>
      <p className="text-xs text-muted-foreground">
        Read every question. The assistant can write a plausible wrong answer,
        and only you can catch that.
      </p>
      <div className="space-y-1.5">
        <Label htmlFor={`review-note-${assessment.id}`}>Review note</Label>
        <Input
          id={`review-note-${assessment.id}`}
          value={note}
          placeholder="Optional — what you checked or what to change"
          onChange={(event) => setNote(event.target.value)}
        />
      </div>
      <div className="flex flex-wrap gap-2">
        <Button
          type="button"
          size="sm"
          disabled={review.isPending}
          onClick={() =>
            void review.mutate({
              id: assessment.id,
              decision: "approved",
              note,
            })
          }
        >
          Approve draft
        </Button>
        <Button
          type="button"
          size="sm"
          variant="outline"
          disabled={review.isPending}
          onClick={() =>
            void review.mutate({
              id: assessment.id,
              decision: "changes_requested",
              note,
            })
          }
        >
          Request changes
        </Button>
      </div>
      {review.isError ? (
        <ErrorNote message={normalizeApiError(review.error).message} />
      ) : null}
    </div>
  )
}

/**
 * Deployment and completion tracking for a published assessment.
 */
function CompletionBlock({ assessment }: { assessment: FacultyAssessment }) {
  const completion = useAssessmentCompletion(assessment.id)

  if (!assessment.is_published) {
    return (
      <p className="text-sm text-muted-foreground">
        Not deployed yet, so there is nothing to track.
      </p>
    )
  }
  if (completion.isLoading) {
    return <Skeleton className="h-12 w-full" aria-hidden="true" />
  }
  if (completion.isError) {
    return (
      <ErrorNote message={normalizeApiError(completion.error).message} />
    )
  }

  const data = completion.data
  if (!data) return null

  return (
    <div className="space-y-1 text-sm">
      <h4 className="font-medium">Completion</h4>
      <p className="text-muted-foreground">
        {data.targeted} targeted · {data.completed} completed ·{" "}
        {data.in_progress} in progress · {data.not_started} not started
      </p>
      {data.non_completers.length > 0 ? (
        <details className="text-xs text-muted-foreground">
          <summary className="cursor-pointer">
            {data.non_completers.length} student(s) have not completed it
          </summary>
          <ul className="mt-1 list-inside list-disc">
            {data.non_completers.map((student) => (
              <li key={student.id}>{student.name}</li>
            ))}
          </ul>
        </details>
      ) : null}
    </div>
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
  const generate = useGenerateQuestionDrafts()

  const [questionText, setQuestionText] = useState("")
  const [questionType, setQuestionType] =
    useState<AssessmentQuestionType>("multiple_choice")
  const [order, setOrder] = useState<string>("")
  const [options, setOptions] = useState<string>("")
  const [correctAnswer, setCorrectAnswer] = useState("")
  const [draftTopic, setDraftTopic] = useState("")

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

  async function handleGenerate() {
    const topic = draftTopic.trim()
    if (topic.length < 3) return
    try {
      const result = await generate.mutateAsync({
        topic,
        question_type: questionType,
        count: 1,
      })
      const draft = result.drafts[0]
      if (!draft) return
      setQuestionText(draft.question_text)
      setOptions(draft.options ? draft.options.join("\n") : "")
      setCorrectAnswer(draft.correct_answer ?? "")
    } catch {
      // Surfaced from `generate.isError`.
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

      {/*
        AI draft (FR-027, now in the faculty module). The generator fills the
        fields with one proposed item for the selected question type; it is
        still only a proposal, and nothing reaches the assessment until
        "Add question" has passed the item through `AssessmentQuestion.clean()`.
      */}
      <div className="space-y-1.5 rounded-md border border-dashed border-border p-3">
        <Label htmlFor={`faculty-draft-topic-${assessment.id}`}>AI draft</Label>
        <div className="flex flex-col gap-2 sm:flex-row">
          <Input
            id={`faculty-draft-topic-${assessment.id}`}
            value={draftTopic}
            placeholder="e.g. study habits for the unit test"
            onChange={(event) => setDraftTopic(event.target.value)}
          />
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={generate.isPending || draftTopic.trim().length < 3}
            onClick={() => {
              void handleGenerate()
            }}
          >
            {generate.isPending ? "Drafting…" : "Generate draft"}
          </Button>
        </div>
        <p className="text-xs text-muted-foreground">
          Fills the fields with one item for the selected question type. A
          teacher&rsquo;s drafts come from the academic item bank. Nothing is
          saved until you press Add question.
        </p>
        {generate.isError ? (
          <ErrorNote message={normalizeApiError(generate.error).message} />
        ) : null}
      </div>

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
                  <Badge status={row.status} variant="outline">
                    {row.status}
                  </Badge>
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
    <div className="faculty-page space-y-6">
      <PageHeading />

      <Card data-panel="assessments">
        <CardHeader>
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="space-y-1">
              <CardTitle>
                <span className="faculty-panel-icon" aria-hidden="true">
                  <ClipboardCheck />
                </span>
                <span>Your assessments</span>
              </CardTitle>
              <CardDescription>
                Showing {visible.length} of {assessments.length}.
              </CardDescription>
            </div>
            <div className="flex flex-wrap gap-2">
              <NewAssessmentDialog students={students} />
              <GenerateDraftDialog students={students} />
            </div>
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
              {visible.map((assessment) => {
                // The server refuses to deploy an AI draft that nobody has
                // approved. The button mirrors that rule rather than offering
                // a control that can only fail.
                const blockedByReview =
                  assessment.ai_generated &&
                  assessment.review_status !== "approved"
                return (
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
                        status={assessment.is_published ? "published" : "draft"}
                        variant="outline"
                        data-published={
                          assessment.is_published ? "true" : "false"
                        }
                      >
                        {assessment.is_published ? "Published" : "Draft"}
                      </Badge>
                      {assessment.ai_generated ? (
                        <Badge
                          variant={
                            assessment.review_status === "approved"
                              ? "default"
                              : "destructive"
                          }
                        >
                          {assessment.review_status === "approved"
                            ? "AI draft · approved"
                            : "AI draft · needs review"}
                        </Badge>
                      ) : null}
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
                       *
                       * The same is true of the review gate: `deploy` refuses
                       * an AI draft that nobody has approved, so the button is
                       * disabled and the reason is stated.
                       */
                      <>
                        <Button
                          type="button"
                          size="sm"
                          disabled={
                            deploy.isPending ||
                            assessment.question_count === 0 ||
                            blockedByReview
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
                        {blockedByReview ? (
                          <p className="text-xs text-muted-foreground">
                            This AI draft needs a human review and an approval
                            before it can be deployed.
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

                  {assessment.ai_generated &&
                  assessment.review_status !== "approved" &&
                  !assessment.is_published ? (
                    <ReviewControls assessment={assessment} />
                  ) : null}

                  <QuestionsBlock assessment={assessment} />

                  <CompletionBlock assessment={assessment} />

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
                )
              })}
            </div>
          )}
        </CardContent>
      </Card>

      <p className="text-xs text-muted-foreground">
        The server scopes this list to academic assessments you created. An
        assessment starts as a draft, cannot be deployed without at least one
        question, and cannot be edited or deleted once published. An
        AI-generated draft additionally needs a human approval before the server
        will publish it. Percentages are 0&ndash;100, not a 0&ndash;1 ratio.
        Wellness and behavioral assessments remain on the guidance assessments
        page.
      </p>
    </div>
  )
}

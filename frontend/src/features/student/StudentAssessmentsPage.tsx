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
import { ErrorNote } from "@/components/feedback/Feedback"
import { Label } from "@/components/ui/label"
import { Skeleton } from "@/components/ui/skeleton"
import {
  ASSESSMENT_QUESTION_TYPE_LABELS,
  useStudentAssessments,
  useStudentAssessment,
  useStudentAssessmentResult,
  useStudentAssessmentResults,
  useSubmitAssessment,
  type StudentAssessment,
} from "@/features/student/assessments-api"
import { normalizeApiError } from "@/lib/error"

/**
 * Assessments assigned to the signed-in student (objective 2.4).
 *
 * The list comes from `AssessmentViewSet`, which returns only published
 * assessments targeting this student or their section. Nothing here filters by
 * identity, and nothing here grades: `POST /assessments/assessment-results/`
 * auto-grades and marks the attempt completed in a single request.
 */

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
        Assessments your teachers have deployed to you. Open one to answer its
        questions.
      </p>
    </div>
  )
}

/**
 * An em dash for anything absent.
 *
 * A missing score or deadline is not a zero, and rendering it as one would
 * report a result that does not exist.
 */
function OrDash(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === "") return "—"
  return String(value)
}

function TakeAssessment({
  assessment,
  onSubmitted,
}: {
  assessment: StudentAssessment
  onSubmitted: () => void
}) {
  const detailQuery = useStudentAssessment(assessment.id)
  const submit = useSubmitAssessment()

  const [answers, setAnswers] = useState<Record<string, string>>({})

  const questions = useMemo(
    () =>
      [...(detailQuery.data?.questions ?? [])].sort(
        (a, b) => a.order - b.order
      ),
    [detailQuery.data]
  )

  const answeredCount = questions.filter((q) => {
    const value = answers[q.id]
    return typeof value === "string" && value.trim().length > 0
  }).length

  if (detailQuery.isLoading) {
    return <Skeleton className="h-24 w-full" aria-hidden="true" />
  }
  if (detailQuery.isError) {
    return <ErrorNote message={normalizeApiError(detailQuery.error).message} />
  }
  if (questions.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        This assessment has no questions yet.
      </p>
    )
  }

  const deadlinePassed =
    assessment.deadline !== null && new Date(assessment.deadline) < new Date()

  return (
    <form
      className="space-y-4"
      onSubmit={(event) => {
        event.preventDefault()
        submit.mutate(
          { assessment: assessment.id, answers },
          { onSuccess: onSubmitted }
        )
      }}
    >
      <p className="text-xs text-muted-foreground">
        {answeredCount} of {questions.length} answered.
        {assessment.time_limit_minutes === null
          ? " No time limit."
          : ` ${assessment.time_limit_minutes} minute limit.`}
      </p>

      {questions.map((question, index) => (
        <fieldset
          key={question.id}
          className="space-y-1.5 rounded-md border border-border p-3"
        >
          <legend className="text-sm font-medium">
            {index + 1}. {question.question_text}
          </legend>
          <p className="text-xs text-muted-foreground">
            {ASSESSMENT_QUESTION_TYPE_LABELS[question.question_type]}
          </p>

          {/*
            The answer key is stripped server-side for students, so no correct
            answer is ever available to render a hint from.
          */}
          {question.question_type === "multiple_choice" ||
          question.question_type === "true_false" ||
          question.question_type === "likert" ? (
            <div className="space-y-1.5">
              {(question.options ?? []).map((option) => {
                const inputId = `student-answer-${question.id}-${option}`
                return (
                  <div key={option} className="flex items-center gap-2">
                    <input
                      id={inputId}
                      /*
                       * Radio for every option-bearing type. `true_false` has a
                       * fixed True/False pair, and likert is an ordered scale,
                       * so all three carry exactly one answer per question —
                       * which is what `answers[questionId]` stores and what
                       * `auto_grade_assessment` compares.
                       */
                      type="radio"
                      name={`student-answer-${question.id}`}
                      value={option}
                      checked={answers[question.id] === option}
                      onChange={() =>
                        setAnswers((current) => ({
                          ...current,
                          [question.id]: option,
                        }))
                      }
                      className="size-4"
                    />
                    <Label htmlFor={inputId} className="font-normal">
                      {option}
                    </Label>
                  </div>
                )
              })}
            </div>
          ) : (
            <div className="space-y-1.5">
              <Label htmlFor={`student-answer-${question.id}`}>
                Your answer
              </Label>
              <textarea
                id={`student-answer-${question.id}`}
                rows={3}
                value={answers[question.id] ?? ""}
                onChange={(event) => {
                  const value = event.target.value
                  setAnswers((current) => ({
                    ...current,
                    [question.id]: value,
                  }))
                }}
                className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-xs outline-none focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring"
              />
              <p className="text-xs text-muted-foreground">
                Essay answers are not auto-graded, so they are not counted in
                the score.
              </p>
            </div>
          )}
        </fieldset>
      ))}

      {deadlinePassed ? (
        <ErrorNote message="The deadline for this assessment has passed." />
      ) : null}

      {submit.isError ? (
        <ErrorNote message={normalizeApiError(submit.error).message} />
      ) : null}

      <Button type="submit" disabled={submit.isPending || deadlinePassed}>
        {submit.isPending ? "Submitting…" : "Submit assessment"}
      </Button>
      <p className="text-xs text-muted-foreground">
        Submitting is final. The server blocks a second attempt for the same
        assessment.
      </p>
    </form>
  )
}

export function StudentAssessmentsPage() {
  const assessmentsQuery = useStudentAssessments()
  const submissionsQuery = useStudentAssessmentResults()
  const [openId, setOpenId] = useState<string | null>(null)

  const assessments = useMemo(
    () => assessmentsQuery.data ?? [],
    [assessmentsQuery.data]
  )

  const submittedIds = useMemo(() => {
    const ids = new Set<string>()
    for (const submission of submissionsQuery.data ?? []) {
      if (submission.completed) ids.add(submission.assessment)
    }
    return ids
  }, [submissionsQuery.data])

  const pending = assessments.filter((a) => !submittedIds.has(a.id))
  const completed = assessments.filter((a) => submittedIds.has(a.id))

  return (
    <div className="space-y-6">
      <PageHeading />

      {assessmentsQuery.isLoading ? (
        <div className="space-y-2">
          <Skeleton className="h-20 w-full" />
          <Skeleton className="h-20 w-full" />
        </div>
      ) : assessmentsQuery.isError ? (
        <ErrorNote
          message={normalizeApiError(assessmentsQuery.error).message}
        />
      ) : assessments.length === 0 ? (
        <Card>
          <CardContent className="py-6 text-center text-sm text-muted-foreground">
            No assessments have been assigned to you yet.
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-6">
          {pending.length > 0 ? (
            <Card>
              <CardHeader>
                <CardTitle>To take</CardTitle>
                <CardDescription>
                  {pending.length} assessment
                  {pending.length === 1 ? "" : "s"} awaiting submission.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                {pending.map((assessment) => (
                  <AssessmentRow
                    key={assessment.id}
                    assessment={assessment}
                    open={openId === assessment.id}
                    onToggle={() =>
                      setOpenId((current) =>
                        current === assessment.id ? null : assessment.id
                      )
                    }
                    onSubmitted={() => setOpenId(null)}
                  />
                ))}
              </CardContent>
            </Card>
          ) : null}

          {completed.length > 0 ? (
            <Card>
              <CardHeader>
                <CardTitle>Completed</CardTitle>
                <CardDescription>
                  Your submitted assessments and their scores.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-3">
                {completed.map((assessment) => (
                  <CompletedRow key={assessment.id} assessment={assessment} />
                ))}
              </CardContent>
            </Card>
          ) : null}
        </div>
      )}
    </div>
  )
}

function AssessmentRow({
  assessment,
  open,
  onToggle,
  onSubmitted,
}: {
  assessment: StudentAssessment
  open: boolean
  onToggle: () => void
  onSubmitted: () => void
}) {
  return (
    <div
      data-assessment-id={assessment.id}
      className="space-y-3 rounded-md border border-border p-4"
    >
      <div className="space-y-1">
        <div className="flex flex-wrap items-center gap-2">
          <h3 className="font-semibold">{assessment.title}</h3>
          <Badge variant="outline">Not submitted</Badge>
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
          {assessment.deadline ? ` · due ${assessment.deadline}` : ""}
        </p>
      </div>

      <Button type="button" size="sm" aria-expanded={open} onClick={onToggle}>
        {open ? "Close" : "Open and answer"}
      </Button>

      {open ? (
        <TakeAssessment assessment={assessment} onSubmitted={onSubmitted} />
      ) : null}
    </div>
  )
}

function CompletedRow({ assessment }: { assessment: StudentAssessment }) {
  const resultQuery = useStudentAssessmentResult(assessment.id)

  return (
    <div
      data-assessment-id={assessment.id}
      className="space-y-1 rounded-md border border-border p-4"
    >
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="font-semibold">{assessment.title}</h3>
        <Badge variant="secondary">Submitted</Badge>
      </div>

      {resultQuery.isLoading ? (
        <Skeleton className="h-4 w-40" aria-hidden="true" />
      ) : resultQuery.isError ? (
        <ErrorNote message={normalizeApiError(resultQuery.error).message} />
      ) : resultQuery.data ? (
        <p className="text-sm text-muted-foreground">
          {/*
            A null score means nothing auto-gradable was answered. That is
            reported as an em dash, never as 0.
          */}
          Score: {OrDash(resultQuery.data.score)}
          {resultQuery.data.total_possible !== null
            ? ` / ${resultQuery.data.total_possible}`
            : ""}
          {resultQuery.data.percentage !== null
            ? ` (${resultQuery.data.percentage}%)`
            : ""}
        </p>
      ) : null}
    </div>
  )
}

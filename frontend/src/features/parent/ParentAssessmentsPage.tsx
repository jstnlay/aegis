import { ClipboardCheck } from "lucide-react"
import { useState } from "react"

import { Badge } from "@/components/ui/badge"
import { ErrorNote } from "@/components/feedback/Feedback"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { DataTable, type DataTableColumn } from "@/components/ui/data-table"
import { useDataTablePagination } from "@/components/ui/data-table-pagination"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { useAuth } from "@/features/auth/AuthContext"
import {
  useAssessmentDetail,
  useChildResults,
  useLinkedStudents,
  useParentAssessments,
  useSelectedChild,
  type ParentAssessmentListItem,
  type ParentAssessmentResult,
} from "@/features/parent/api"
import { formatCount, formatPercent } from "@/lib/metric-format"

/**
 * Parent's view of the assessments assigned to their children and the results
 * their children submitted.
 *
 * Two contract facts shape this screen:
 *
 * 1. **No answer key.** `AssessmentQuestionSerializer.to_representation`
 *    withholds `correct_answer` from anyone who is not the assessment's author
 *    (PH11.9). A parent sees the question text and options so they can help
 *    their child prepare; they never receive the key.
 *
 * 2. **The list and detail payloads differ.**
 *    `AssessmentViewSet.get_serializer_class()` returns
 *    `AssessmentListSerializer` for `list` (a `question_count`, no nested
 *    `questions`) and `AssessmentSerializer` for `retrieve`. This screen reads
 *    the count from the list row and fetches the detail only for the assessment
 *    the parent expands.
 *
 * An assessment may target a whole section rather than named students, and
 * `AssessmentViewSet` has no `?student=` filter, so an assessment is not
 * attributed to one selected child from the list payload alone. The list is
 * therefore shown across the parent's children; the detail supplies the real
 * targeting, and results are attributed because `AssessmentResultListSerializer`
 * carries `student`.
 */

const ASSESSMENT_TYPE_LABELS: Record<string, string> = {
  academic: "Academic",
  wellness: "Well-being",
  behavioral: "Behavioural",
}

export function ParentAssessmentsPage() {
  const { user } = useAuth()
  const [expandedId, setExpandedId] = useState<string | null>(null)

  const linkedQuery = useLinkedStudents()
  const linked = linkedQuery.data ?? []

  // A parent with one child lands on that child's record; see useSelectedChild.
  const { selectedChildId, setSelectedChildId, child } =
    useSelectedChild(linked)

  const assessmentsQuery = useParentAssessments(linkedQuery.isSuccess)
  const resultsQuery = useChildResults(selectedChildId || null)

  if (!user) return null

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-1">
        <div className="flex items-center gap-3">
          <ClipboardCheck
            className="size-5 text-muted-foreground"
            aria-hidden="true"
          />
          <h2 className="text-2xl font-bold text-foreground">Assessments</h2>
        </div>
        <p className="text-sm text-muted-foreground">
          Assessments published to your children, and the results they
          submitted. Answer keys are never shared with parents.
        </p>
      </div>

      <div className="space-y-1.5">
        <label
          htmlFor="parent-assessments-child"
          className="text-sm font-medium"
        >
          Results for
        </label>
        <Select value={selectedChildId} onValueChange={setSelectedChildId}>
          <SelectTrigger id="parent-assessments-child">
            <SelectValue placeholder="Select a student to see their results" />
          </SelectTrigger>
          <SelectContent>
            {linked.map((student) => (
              <SelectItem key={student.id} value={student.id}>
                {student.student_name} — {student.section_name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Published assessments</CardTitle>
          <CardDescription>
            Assessments targeted at your children. Expand one to read its
            questions.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <AssessmentList
            assessments={assessmentsQuery.data ?? []}
            isLoading={assessmentsQuery.isLoading || linkedQuery.isLoading}
            error={
              assessmentsQuery.isError
                ? "Unable to load assessments. Please try again."
                : null
            }
            expandedId={expandedId}
            onToggle={(id) => setExpandedId((cur) => (cur === id ? null : id))}
          />
        </CardContent>
      </Card>

      {child ? (
        <Card>
          <CardHeader>
            <CardTitle>Results</CardTitle>
            <CardDescription>
              Results submitted by {child.student_name}.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <ResultTable
              results={resultsQuery.data ?? []}
              isLoading={resultsQuery.isLoading}
              error={
                resultsQuery.isError
                  ? "Unable to load results. Please try again."
                  : null
              }
            />
          </CardContent>
        </Card>
      ) : null}
    </div>
  )
}

function AssessmentList({
  assessments,
  isLoading,
  error,
  expandedId,
  onToggle,
}: {
  assessments: readonly ParentAssessmentListItem[]
  isLoading: boolean
  error: string | null
  expandedId: string | null
  onToggle: (id: string) => void
}) {
  if (isLoading) {
    return (
      <p
        role="status"
        aria-busy="true"
        className="py-6 text-center text-sm text-muted-foreground"
      >
        Loading assessments…
      </p>
    )
  }
  if (error) {
    return (
      <div
        role="alert"
        className="rounded-md border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive"
      >
        <span>{error}</span>
      </div>
    )
  }
  if (assessments.length === 0) {
    return (
      <p className="py-6 text-center text-sm text-muted-foreground">
        No assessments have been published to your children.
      </p>
    )
  }

  return (
    <ul className="space-y-2">
      {assessments.map((assessment) => {
        const isExpanded = expandedId === assessment.id
        return (
          <li
            key={assessment.id}
            className="rounded-md border border-border"
            data-assessment-id={assessment.id}
          >
            <button
              type="button"
              aria-expanded={isExpanded}
              onClick={() => onToggle(assessment.id)}
              className="flex w-full flex-wrap items-center justify-between gap-2 p-3 text-left"
            >
              <span className="min-w-0">
                <span className="block font-medium">{assessment.title}</span>
                <span className="block text-xs text-muted-foreground">
                  {formatCount(assessment.question_count)}{" "}
                  {assessment.question_count === 1 ? "question" : "questions"}
                  {assessment.deadline
                    ? ` · due ${formatDate(assessment.deadline)}`
                    : ""}
                </span>
              </span>
              <Badge variant="secondary">
                {ASSESSMENT_TYPE_LABELS[assessment.assessment_type] ??
                  assessment.assessment_type}
              </Badge>
            </button>
            {isExpanded ? (
              <AssessmentQuestions assessmentId={assessment.id} />
            ) : null}
          </li>
        )
      })}
    </ul>
  )
}

/**
 * The questions for one assessment.
 *
 * The field is `questions`, never `correct_answer`: the backend strips the key
 * for any non-author, and this screen must not present a blank that looks like
 * a missing value rather than a deliberate redaction.
 */
function AssessmentQuestions({ assessmentId }: { assessmentId: string }) {
  const detailQuery = useAssessmentDetail(assessmentId)
  const detail = detailQuery.data

  if (detailQuery.isLoading) {
    return (
      <p
        role="status"
        aria-busy="true"
        className="border-t border-border p-3 text-sm text-muted-foreground"
      >
        Loading questions…
      </p>
    )
  }
  if (detailQuery.isError) {
    return (
      // PH11.12: `ErrorNote` rather than a hand-rolled copy of its markup. This was
      // the one error in the parent surface rendered without the shared alert's
      // icon, so the same failure looked different here than everywhere else.
      <div className="m-3">
        <ErrorNote message="Unable to load the questions for this assessment." />
      </div>
    )
  }
  if (!detail) return null

  return (
    <div className="space-y-3 border-t border-border p-3">
      {detail.description ? (
        <p className="text-sm text-muted-foreground">{detail.description}</p>
      ) : null}
      {detail.target_sections_details.length > 0 ? (
        <p className="text-xs text-muted-foreground">
          Assigned to{" "}
          {detail.target_sections_details
            .map((section) => section.name)
            .join(", ")}
        </p>
      ) : null}
      {detail.questions.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          This assessment has no questions.
        </p>
      ) : (
        <ol className="space-y-3">
          {detail.questions.map((question) => (
            <li key={question.id} className="space-y-1">
              <p className="text-sm font-medium">
                {question.order}. {question.question_text}
              </p>
              {question.options && question.options.length > 0 ? (
                <ul className="ml-4 list-inside list-disc text-sm text-muted-foreground">
                  {question.options.map((option, index) => (
                    <li key={`${question.id}-opt-${index}`}>{option}</li>
                  ))}
                </ul>
              ) : null}
            </li>
          ))}
        </ol>
      )}
    </div>
  )
}

function ResultTable({
  results,
  isLoading,
  error,
}: {
  results: readonly ParentAssessmentResult[]
  isLoading: boolean
  error: string | null
}) {
  const { pagination, pageRows } = useDataTablePagination(results, 10)

  const columns: readonly DataTableColumn<ParentAssessmentResult>[] = [
    {
      key: "assessment",
      header: "Assessment",
      cell: (result) => (
        <span className="font-medium">{result.assessment_title}</span>
      ),
    },
    {
      key: "status",
      header: "Status",
      cell: (result) => (
        <Badge variant="outline" data-result-status={result.status}>
          {result.status}
        </Badge>
      ),
    },
    {
      key: "score",
      header: "Score",
      cell: (result) => (
        <span className="font-bold">
          {result.score === null
            ? "—"
            : `${result.score}${
                result.total_possible === null
                  ? ""
                  : ` / ${result.total_possible}`
              }`}
        </span>
      ),
    },
    {
      key: "percentage",
      header: "Percentage",
      cell: (result) => <span>{formatPercent(result.percentage, 1)}</span>,
    },
    {
      key: "completed",
      header: "Completed",
      cell: (result) => (
        <span className="text-sm text-muted-foreground">
          {result.completed_at ? formatDate(result.completed_at) : "—"}
        </span>
      ),
    },
  ]

  return (
    <DataTable
      caption="Assessment results"
      columns={columns}
      rows={pageRows}
      rowKey={(result) => result.id}
      isLoading={isLoading}
      error={error}
      loadingLabel="Loading results"
      emptyMessage="No results have been submitted yet."
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

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { apiClient } from "@/lib/api"
import { fetchAllPages } from "@/lib/pagination"

/**
 * Student assessments (Final_Revision objective 2.4).
 *
 * Scope comes from the server, not from a client filter:
 * `AssessmentViewSet.get_queryset` returns, for a student, only published
 * assessments targeting them explicitly or their section with no explicit
 * student list. `AssessmentResultViewSet.get_queryset` returns only their own
 * submissions.
 *
 * The answer key never reaches this surface. `AssessmentQuestionSerializer`
 * strips `correct_answer` for anyone who is not the assessment's author or an
 * admin, so `correct_answer` is always `null` here. Grading happens server-side
 * in `auto_grade_assessment`, which scores only `multiple_choice` and
 * `true_false`, one point each; `essay` and `likert` are not auto-graded and
 * `total_possible` therefore counts only gradable questions.
 */

export type AssessmentQuestionType =
  "multiple_choice" | "true_false" | "essay" | "likert"

export const ASSESSMENT_QUESTION_TYPE_LABELS: Record<
  AssessmentQuestionType,
  string
> = {
  multiple_choice: "Multiple choice",
  true_false: "True / False",
  essay: "Essay",
  likert: "Likert scale",
}

/** `AssessmentListSerializer` — the list payload carries no nested questions. */
export interface StudentAssessment {
  id: string
  title: string
  description: string | null
  assessment_type: "academic" | "wellness" | "behavioral"
  created_by_name: string
  time_limit_minutes: number | null
  is_published: boolean
  published_at: string | null
  deadline: string | null
  question_count: number
}

/**
 * `AssessmentSerializer` on the detail route, with nested `questions`.
 *
 * `correct_answer` is always `null` for a student; the field is kept so the
 * shape matches the serializer, not because it carries anything usable.
 */
export interface StudentAssessmentDetail extends StudentAssessment {
  questions: StudentAssessmentQuestion[]
}

export interface StudentAssessmentQuestion {
  id: string
  question_text: string
  question_type: AssessmentQuestionType
  order: number
  options: string[] | null
  /** Always `null` for a student — the serializer strips it. */
  correct_answer: string | null
}

/** `AssessmentResultListSerializer`. Decimals normalized to `number | null`. */
export interface StudentAssessmentResult {
  id: string
  assessment: string
  assessment_title: string
  score: number | null
  total_possible: number | null
  percentage: number | null
  status: "in_progress" | "completed"
  started_at: string
  completed_at: string | null
}

/**
 * A submission the student has already made.
 *
 * `AssessmentResult` is unique per (assessment, student), so this is presence,
 * not a history.
 */
export interface StudentSubmission {
  assessment: string
  completed: boolean
}

const keys = {
  assessments: ["student", "assessments"] as const,
  assessment: (id: string) => ["student", "assessments", id] as const,
  results: ["student", "assessment-results"] as const,
}

/**
 * DRF decimal fields arrive as strings.
 *
 * Absent or unparseable becomes `null`, never `0`, so an ungraded result is
 * never displayed as a real zero score.
 */
export function toScoreNumber(
  value: string | number | null | undefined
): number | null {
  if (value === null || value === undefined || value === "") return null
  const parsed = typeof value === "number" ? value : Number(value)
  return Number.isNaN(parsed) ? null : parsed
}

/** Published assessments assigned to this student. */
export function useStudentAssessments() {
  return useQuery<StudentAssessment[], Error>({
    queryKey: keys.assessments,
    queryFn: async () => {
      const { results } = await fetchAllPages<StudentAssessment>(
        "/assessments/assessments/"
      )
      return results
    },
  })
}

/** One assigned assessment with its questions. */
export function useStudentAssessment(assessmentId: string | null) {
  return useQuery<StudentAssessmentDetail, Error>({
    queryKey: keys.assessment(assessmentId ?? ""),
    enabled: Boolean(assessmentId),
    queryFn: async () => {
      const { data } = await apiClient.get<StudentAssessmentDetail>(
        `/assessments/assessments/${assessmentId ?? ""}/`
      )
      return data
    },
  })
}

/** This student's own submissions. */
export function useStudentAssessmentResults() {
  return useQuery<StudentSubmission[], Error>({
    queryKey: keys.results,
    queryFn: async () => {
      const { results } = await fetchAllPages<{
        assessment: string
        status: "in_progress" | "completed"
      }>("/assessments/assessment-results/")
      return results.map((row) => ({
        assessment: row.assessment,
        completed: row.status === "completed",
      }))
    },
  })
}

/** The student's own result for one assessment, with the real score. */
export function useStudentAssessmentResult(assessmentId: string | null) {
  return useQuery<StudentAssessmentResult | null, Error>({
    queryKey: [...keys.results, assessmentId ?? ""],
    enabled: Boolean(assessmentId),
    queryFn: async () => {
      const { results } = await fetchAllPages<
        Record<string, unknown> & {
          assessment: string
          assessment_title: string
          score: string | number | null
          total_possible: string | number | null
          percentage: string | number | null
          status: "in_progress" | "completed"
          started_at: string
          completed_at: string | null
        }
      >("/assessments/assessment-results/")

      const row = results.find((r) => r.assessment === assessmentId)
      if (!row) return null
      return {
        id: String(row.id),
        assessment: row.assessment,
        assessment_title: row.assessment_title,
        score: toScoreNumber(row.score),
        total_possible: toScoreNumber(row.total_possible),
        percentage: toScoreNumber(row.percentage),
        status: row.status,
        started_at: row.started_at,
        completed_at: row.completed_at,
      }
    },
  })
}

/**
 * `POST /assessments/assessment-results/`
 *
 * `answers` maps question id to the submitted answer string. The server blocks
 * duplicate submissions, unpublished assessments, and assessments not targeted
 * at this student, then auto-grades and marks the result completed in one
 * request — so a success returns the final score rather than a draft.
 */
export function useSubmitAssessment() {
  const queryClient = useQueryClient()
  return useMutation<
    unknown,
    Error,
    { assessment: string; answers: Record<string, string> }
  >({
    mutationFn: async ({ assessment, answers }) => {
      const { data } = await apiClient.post(
        "/assessments/assessment-results/",
        {
          assessment,
          answers,
        }
      )
      return data
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: keys.results })
      void queryClient.invalidateQueries({ queryKey: keys.assessments })
    },
  })
}

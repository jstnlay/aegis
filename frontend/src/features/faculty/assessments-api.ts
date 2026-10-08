import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { apiClient } from "@/lib/api"
import { fetchAllPages } from "@/lib/pagination"

/**
 * Faculty assessments (Final_Revision objective 2.4 / panel correction).
 *
 * Ownership follows `Assessment.clean()` in `apps/assessments/models.py`:
 * an `academic` assessment must have `creator_role="faculty"` and a faculty
 * `created_by`, while `wellness` and `behavioral` must have `creator_role=
 * "guidance"`. `AssessmentViewSet.get_queryset` returns only the caller's own
 * assessments, so this surface is academic-only by construction rather than by
 * a client-side filter, and guidance's wellness/behavioral page is untouched.
 *
 * The backend already enforces this. `CanCreateAssessment` admits faculty, and
 * posting `assessment_type="academic"` infers `creator_role="faculty"`
 * server-side. `creator_role` and `created_by` are therefore never sent.
 */

/** `Assessment.AssessmentType.choices` values a faculty member may author. */
export const FACULTY_ASSESSMENT_TYPES = ["academic"] as const

export type FacultyAssessmentType = (typeof FACULTY_ASSESSMENT_TYPES)[number]

/**
 * `AssessmentListSerializer`, with the type narrowed to what faculty can see.
 *
 * The wire value is the full `academic | wellness | behavioral` union because
 * that is what the model declares; the server scope means only `academic` ever
 * arrives here.
 */
export interface FacultyAssessment {
  id: string
  title: string
  description: string | null
  assessment_type: "academic" | "wellness" | "behavioral"
  creator_role: string
  created_by: string
  created_by_name: string
  time_limit_minutes: number | null
  is_published: boolean
  published_at: string | null
  deadline: string | null
  question_count: number
  created_at: string
  updated_at: string
}

/** `AssessmentResultListSerializer`. Decimals normalized to `number | null`. */
export interface FacultyAssessmentResult {
  id: string
  assessment: string
  assessment_title: string
  student: string
  student_name: string
  student_id: string
  score: number | null
  total_possible: number | null
  percentage: number | null
  status: "in_progress" | "completed"
  started_at: string
  completed_at: string | null
}

/** `AssessmentQuestion.QuestionType.choices`. */
export type AssessmentQuestionType =
  "multiple_choice" | "true_false" | "essay" | "likert"

export const ASSESSMENT_QUESTION_TYPES: readonly AssessmentQuestionType[] = [
  "multiple_choice",
  "true_false",
  "essay",
  "likert",
]

export const ASSESSMENT_QUESTION_TYPE_LABELS: Record<
  AssessmentQuestionType,
  string
> = {
  multiple_choice: "Multiple choice",
  true_false: "True / False",
  essay: "Essay",
  likert: "Likert scale",
}

/**
 * Question types that carry an `options` array.
 *
 * `multiple_choice` uses it as the selectable choices and `likert` as the scale
 * points. `true_false` has a fixed pair and `essay` is free text.
 */
export const OPTIONS_BEARING_QUESTION_TYPES: readonly AssessmentQuestionType[] =
  ["multiple_choice", "likert"]

/** `AssessmentQuestionSerializer`. */
export interface FacultyAssessmentQuestion {
  id: string
  assessment: string
  question_text: string
  question_type: AssessmentQuestionType
  order: number
  options: string[] | null
  correct_answer: string | null
  created_at: string
  updated_at: string
}

/**
 * A student a faculty member may target.
 *
 * Derived from `EnrollmentViewSet`, which already scopes faculty to their own
 * sections. Faculty cannot read `/accounts/users/` (that is `IsAdminUser`), so
 * the enrollment list is the only roster available — the same source the faculty
 * dashboard already uses.
 */
export interface FacultyTargetStudent {
  /** `StudentProfile` UUID. */
  id: string
  name: string
  studentId: string | null
  sectionName: string | null
}

/** `POST /assessments/assessments/` body for a faculty member. */
export interface CreateFacultyAssessmentPayload {
  title: string
  assessment_type: FacultyAssessmentType
  description?: string | null
  time_limit_minutes?: number | null
  deadline?: string | null
  target_students?: string[]
}

export interface CreateFacultyQuestionPayload {
  assessment: string
  question_text: string
  question_type: AssessmentQuestionType
  order: number
  options?: string[] | null
  correct_answer?: string | null
}

const keys = {
  assessments: ["faculty", "assessments"] as const,
  assessmentResults: ["faculty", "assessment-results"] as const,
  assessmentQuestions: ["faculty", "assessment-questions"] as const,
  targetStudents: ["faculty", "target-students"] as const,
}

/**
 * The default order for a newly added question.
 *
 * `AssessmentQuestion.Meta` declares `unique_together = ("assessment", "order")`,
 * so a question cannot reuse an order that already exists on the same
 * assessment. One past the highest present order is always free, and computing
 * it from the loaded list means a page reload still lands on a free value.
 */
export function nextQuestionOrder(
  questions: ReadonlyArray<{ order: number }>
): number {
  return Math.max(...questions.map((question) => question.order), 0) + 1
}

/** This faculty member's own academic assessments. */
export function useFacultyAssessments() {
  return useQuery<FacultyAssessment[], Error>({
    queryKey: keys.assessments,
    queryFn: async () => {
      const { results } = await fetchAllPages<FacultyAssessment>(
        "/assessments/assessments/"
      )
      return results
    },
  })
}

/**
 * Results for assessments this faculty member created.
 *
 * `AssessmentResultViewSet.get_queryset` filters on
 * `assessment__created_by=user` for faculty, so this is never school-wide.
 */
export function useFacultyAssessmentResults() {
  return useQuery<FacultyAssessmentResult[], Error>({
    queryKey: keys.assessmentResults,
    queryFn: async () => {
      const { results } = await fetchAllPages<
        Record<string, unknown> & {
          score: string | number | null
          total_possible: string | number | null
          percentage: string | number | null
        }
      >("/assessments/assessment-results/")
      return results.map((record) => ({
        ...(record as unknown as FacultyAssessmentResult),
        score: toNumber(record.score),
        total_possible: toNumber(record.total_possible),
        percentage: toNumber(record.percentage),
      }))
    },
  })
}

/**
 * Decimal fields arrive as strings from DRF and must become `number | null`.
 *
 * An absent or unparseable value becomes `null`, never `0`, so a missing score
 * is never rendered as a real zero.
 */
function toNumber(value: string | number | null | undefined): number | null {
  if (value === null || value === undefined || value === "") return null
  const parsed = typeof value === "number" ? value : Number(value)
  return Number.isNaN(parsed) ? null : parsed
}

/** Students in this faculty member's own sections, for targeting. */
export function useFacultyTargetStudents() {
  return useQuery<FacultyTargetStudent[], Error>({
    queryKey: keys.targetStudents,
    queryFn: async () => {
      const { results } = await fetchAllPages<{
        id: string
        student: string
        student_name: string
        student_id: string
        section_name: string | null
      }>("/academics/enrollments/")

      const byStudent = new Map<string, FacultyTargetStudent>()
      for (const row of results) {
        if (!byStudent.has(row.student)) {
          byStudent.set(row.student, {
            id: row.student,
            name: row.student_name,
            studentId: row.student_id || null,
            sectionName: row.section_name ?? null,
          })
        }
      }
      return [...byStudent.values()]
    },
  })
}

/** Questions for one assessment. */
export function useFacultyAssessmentQuestions(assessmentId: string | null) {
  return useQuery<FacultyAssessmentQuestion[], Error>({
    queryKey: [...keys.assessmentQuestions, assessmentId ?? ""],
    enabled: Boolean(assessmentId),
    queryFn: async () => {
      const { results } = await fetchAllPages<FacultyAssessmentQuestion>(
        "/assessments/assessment-questions/"
      )
      return results.filter((question) => question.assessment === assessmentId)
    },
  })
}

/**
 * `POST /assessments/assessments/`
 *
 * `created_by` is read-only and `creator_role` is inferred from
 * `assessment_type` server-side, so neither is sent.
 */
export function useCreateFacultyAssessment() {
  const queryClient = useQueryClient()
  return useMutation<unknown, Error, CreateFacultyAssessmentPayload>({
    mutationFn: async (payload) => {
      const { data } = await apiClient.post(
        "/assessments/assessments/",
        payload
      )
      return data
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: keys.assessments })
    },
  })
}

/**
 * `POST /assessments/assessment-questions/`
 *
 * `perform_create` rejects a question on a published assessment, so the page
 * only offers this for a draft.
 */
export function useCreateFacultyAssessmentQuestion() {
  const queryClient = useQueryClient()
  return useMutation<unknown, Error, CreateFacultyQuestionPayload>({
    mutationFn: async (payload) => {
      const { data } = await apiClient.post(
        "/assessments/assessment-questions/",
        payload
      )
      return data
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: keys.assessmentQuestions,
      })
    },
  })
}

/**
 * `POST /assessments/assessments/{id}/deploy/`
 *
 * The server returns 400 "Assessment is already published." for a live
 * assessment and "Cannot publish assessment without questions." for an empty
 * one. Both are surfaced rather than pre-empted, because `is_published` and the
 * question count are server-owned.
 */
export function useDeployFacultyAssessment() {
  const queryClient = useQueryClient()
  return useMutation<unknown, Error, { id: string }>({
    mutationFn: async ({ id }) => {
      const { data } = await apiClient.post(
        `/assessments/assessments/${id}/deploy/`,
        undefined
      )
      return data
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: keys.assessments })
    },
  })
}

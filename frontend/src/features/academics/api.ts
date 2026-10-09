/**
 * Academics domain API (PH11.7).
 *
 * Every field name below is copied from the backend serializer `Meta.fields`
 * so the frontend contract cannot drift from the real API:
 *
 * - `apps/academics/serializers.py` GradeSerializer / SectionSerializer /
 *   SubjectAssignmentSerializer / GradingPeriodSerializer /
 *   EnrollmentSerializer / GradeEncodeSerializer
 * - `apps/academics/views.py` GradeViewSet.get_queryset query-parameter
 *   filtering: `student`, `subject_assignment`, `grading_period`, `status`
 *
 * ---------------------------------------------------------------------------
 * IMPORTANT — `score` arrives as a JSON *string*
 * ---------------------------------------------------------------------------
 * `Grade.score` is a `models.DecimalField`. The project does not set
 * `COERCE_DECIMAL_TO_STRING`, so DRF's default (`True`) applies and the API
 * emits `"85.00"`, not `85`. Arithmetic on the raw value silently produces
 * `NaN` (`0 + "85.00" + "90.00"` string-concatenates, then fails to coerce).
 * `normalizeScore` is the single boundary that converts the wire value into
 * a real number, and every domain type exposes `score: number | null`.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useCallback, useMemo } from "react"

import { apiClient } from "@/lib/api"
import { fetchAllPages } from "@/lib/pagination"

/* -------------------------------------------------------------------------- */
/* Normalization                                                              */
/* -------------------------------------------------------------------------- */

/**
 * Wire shape of a DRF DecimalField: a JSON string such as `"85.00"`.
 * A number is accepted too so the type stays honest if the backend later
 * sets `COERCE_DECIMAL_TO_STRING = False`.
 */
export type WireScore = string | number | null | undefined

/**
 * Convert a DRF decimal into a `number | null`.
 *
 * Returns `null` for absent values *and* for values that cannot be parsed,
 * so a malformed payload degrades to "no score recorded" instead of
 * poisoning aggregates with `NaN`.
 */
export function normalizeScore(value: WireScore): number | null {
  if (value === null || value === undefined || value === "") return null
  const parsed = typeof value === "number" ? value : Number(value)
  return Number.isFinite(parsed) ? parsed : null
}

/* -------------------------------------------------------------------------- */
/* Domain types (mirror the backend serializers)                              */
/* -------------------------------------------------------------------------- */

export type GradeStatus = "draft" | "submitted" | "finalized"

/** `Grade.StatusChoices` — the only three statuses the API can return. */
export const GRADE_STATUSES: readonly GradeStatus[] = [
  "draft",
  "submitted",
  "finalized",
] as const

export const GRADE_STATUS_LABELS: Record<GradeStatus, string> = {
  draft: "Draft",
  submitted: "Submitted",
  finalized: "Finalized",
}

export interface Grade {
  id: string
  student: string
  student_name: string
  student_id: string
  subject_assignment: string
  subject_name: string
  subject_code: string
  section_name: string
  grading_period: string
  grading_period_name: string | null
  /** Normalized from the DRF decimal string — never a raw string. */
  score: number | null
  letter_grade: string | null
  remarks: string | null
  encoded_by: string
  encoded_by_name: string
  status: GradeStatus
  created_at: string
  updated_at: string
}

/** `SubjectAssignmentSerializer` — the pick list behind grade encoding. */
export interface SubjectAssignment {
  id: string
  subject: string
  subject_name: string
  subject_code: string
  faculty: string
  faculty_name: string
  section: string
  section_name: string
  academic_year: string
  academic_year_name: string
}

/** `SectionSerializer`. */
export interface Section {
  id: string
  name: string
  grade_level: string
  grade_level_name: string
  academic_year: string
  adviser: string | null
  adviser_name: string | null
}

/** `GradingPeriodSerializer` — `order` drives chronological sorting. */
export interface GradingPeriod {
  id: string
  academic_year: string
  academic_year_name: string
  name: string
  order: number
  start_date: string | null
  end_date: string | null
}

/** `EnrollmentSerializer`. `student` is the StudentProfile UUID. */
export interface Enrollment {
  id: string
  student: string
  student_name: string
  student_id: string
  section: string
  section_name: string
  academic_year: string
  academic_year_name: string
  date_enrolled: string | null
  is_active: boolean
  created_at: string
  updated_at: string
}

/** `GradeEncodeSerializer` — the exact write payload for `POST /grades/encode/`. */
export interface GradeEncodePayload {
  student: string
  subject_assignment: string
  grading_period: string
  score?: number | null
  letter_grade?: string | null
  remarks?: string | null
}

/* -------------------------------------------------------------------------- */
/* Raw wire records (only `score` differs from the domain type)                */
/* -------------------------------------------------------------------------- */

interface GradeWireRecord extends Omit<Grade, "score"> {
  score: WireScore
}

function mapGrade(record: GradeWireRecord): Grade {
  return { ...record, score: normalizeScore(record.score) }
}

/* -------------------------------------------------------------------------- */
/* Query keys                                                                 */
/* -------------------------------------------------------------------------- */

const keys = {
  studentGrades: (studentId: string) =>
    ["academics", "grades", studentId] as const,
  facultyGrades: ["academics", "grades", "faculty"] as const,
  subjectAssignments: ["academics", "subject-assignments", "detail"] as const,
  gradingPeriods: ["academics", "grading-periods"] as const,
  enrollments: ["academics", "enrollments"] as const,
  sections: ["academics", "sections", "detail"] as const,
} as const

/* -------------------------------------------------------------------------- */
/* Grade queries                                                              */
/* -------------------------------------------------------------------------- */

/**
 * A student's own finalized grades.
 *
 * Only `status=finalized` is requested. Draft and submitted rows are not
 * released to students: the backend scopes the queryset to the caller's own
 * StudentProfile, but lifecycle state is a faculty/admin concern, and
 * `Grade.status` exists precisely so unreleased work stays hidden.
 *
 * The backend filter is `status` (a single value). There is no
 * `status__in`, so it is applied server-side here rather than by fetching
 * every status and discarding the rest client-side.
 */
export function useStudentGrades(studentId: string | null | undefined) {
  const enabled = Boolean(studentId)
  return useQuery<Grade[], Error>({
    queryKey: keys.studentGrades(studentId ?? ""),
    enabled,
    queryFn: async () => {
      const { results } = await fetchAllPages<GradeWireRecord>(
        `/academics/grades/?status=finalized&student=${studentId}`
      )
      return results.map(mapGrade)
    },
  })
}

/**
 * Every grade the signed-in faculty member is responsible for.
 *
 * Fetched unfiltered and partitioned client-side: the viewset exposes only a
 * single-value `status` parameter, so one query gives both the rows and the
 * per-status counts used by the lifecycle filter — without three round trips.
 * The queryset itself is already restricted to the caller's own subject
 * assignments by the backend.
 */
export function useFacultyGrades() {
  return useQuery<Grade[], Error>({
    queryKey: keys.facultyGrades,
    queryFn: async () => {
      const { results } =
        await fetchAllPages<GradeWireRecord>("/academics/grades/")
      return results.map(mapGrade)
    },
  })
}

export interface GradeStatusCounts {
  all: number
  draft: number
  submitted: number
  finalized: number
}

function countByStatus(grades: Grade[]): GradeStatusCounts {
  const counts: GradeStatusCounts = {
    all: grades.length,
    draft: 0,
    submitted: 0,
    finalized: 0,
  }
  for (const grade of grades) {
    if (grade.status in counts) counts[grade.status] += 1
  }
  return counts
}

/* -------------------------------------------------------------------------- */
/* Reference data for the encode form                                         */
/* -------------------------------------------------------------------------- */

export function useSubjectAssignments() {
  return useQuery<SubjectAssignment[], Error>({
    queryKey: keys.subjectAssignments,
    queryFn: async () => {
      const { results } = await fetchAllPages<SubjectAssignment>(
        "/academics/subject-assignments/"
      )
      return results
    },
  })
}

export function useGradingPeriods() {
  return useQuery<GradingPeriod[], Error>({
    queryKey: keys.gradingPeriods,
    queryFn: async () => {
      const { results } = await fetchAllPages<GradingPeriod>(
        "/academics/grading-periods/"
      )
      // `order` is the backend's own chronological sequence for a period.
      return [...results].sort((a, b) => a.order - b.order)
    },
  })
}

/**
 * Enrollments visible to the caller, with a client-side section filter.
 *
 * `EnrollmentViewSet.get_queryset` implements no query-parameter filtering —
 * only role scoping — so a `?section=` request would be silently ignored and
 * return every visible enrollment. The list is therefore fetched once and
 * narrowed here, which is also what keeps the encode form's student options
 * consistent with what faculty are actually allowed to see.
 */
export function useEnrollmentsInSection(sectionId: string | null | undefined) {
  const enabled = Boolean(sectionId)
  return useQuery<Enrollment[], Error>({
    queryKey: [...keys.enrollments, sectionId ?? ""],
    enabled,
    queryFn: async () => {
      const { results } = await fetchAllPages<Enrollment>(
        "/academics/enrollments/"
      )
      if (!sectionId) return []
      // `is_active` gates the backend's own grade/attendance integrity checks
      // (SEC-013), so only active enrollments are offered as options.
      return results.filter((e) => e.section === sectionId && e.is_active)
    },
  })
}

/**
 * Sections visible to the caller.
 *
 * `SectionViewSet` already scopes faculty to sections they advise or teach, so
 * no client-side filter is needed. Consumed by the attendance domain to build
 * the section pickers.
 */
export function useSections() {
  return useQuery<Section[], Error>({
    queryKey: keys.sections,
    queryFn: async () => {
      const { results } = await fetchAllPages<Section>("/academics/sections/")
      return results
    },
  })
}

/* -------------------------------------------------------------------------- */
/* Grade encoding                                                             */
/* -------------------------------------------------------------------------- */

/**
 * `POST /academics/grades/encode/`
 *
 * Faculty-only (`IsFacultyUser`) and the *only* grade write a faculty member
 * can perform: it always creates a row with `status = "draft"`. The backend
 * rejects the request unless the subject assignment belongs to the caller,
 * the grading period exists, the student is actively enrolled in the
 * assignment's section for the matching academic year, and no grade already
 * exists for that student/assignment/period triple.
 */
export function useEncodeGrade() {
  const queryClient = useQueryClient()
  return useMutation<Grade, Error, GradeEncodePayload>({
    mutationFn: async (payload) => {
      const { data } = await apiClient.post<GradeWireRecord>(
        "/academics/grades/encode/",
        payload
      )
      return mapGrade(data)
    },
    onSuccess: () => {
      // Invalidates both the faculty list and the student's own view, since
      // the same Grade rows back either one.
      void queryClient.invalidateQueries({ queryKey: ["academics", "grades"] })
    },
  })
}

/**
 * `GradeUpdateSerializer` — the content-only write surface of
 * `PATCH /grades/{id}/`. `status` and `encoded_by` are intentionally absent:
 * the server refuses either with 403, so a form that offered them could only
 * produce a refusal.
 */
export interface GradeUpdatePayload {
  score?: number | null
  letter_grade?: string | null
  remarks?: string | null
}

/**
 * FR-011 — revises one of the faculty member's own encoded grades.
 *
 * The student's own view is backed by the same rows, so both keys are
 * invalidated on success.
 */
export function useUpdateGrade() {
  const queryClient = useQueryClient()
  return useMutation<Grade, Error, { id: string; payload: GradeUpdatePayload }>(
    {
      mutationFn: async ({ id, payload }) => {
        const { data } = await apiClient.patch<GradeWireRecord>(
          `/academics/grades/${id}/`,
          payload
        )
        return mapGrade(data)
      },
      onSuccess: () => {
        void queryClient.invalidateQueries({
          queryKey: ["academics", "grades"],
        })
      },
    }
  )
}

/* -------------------------------------------------------------------------- */
/* Derived helpers shared by the page                                         */
/* -------------------------------------------------------------------------- */

/**
 * Group grades by grading period for display. Periods with no name fall back
 * to a single "Unassigned" bucket rather than producing several
 * indistinguishable empty groups.
 */
export function useGradesByPeriod(grades: Grade[] | undefined) {
  return useMemo(() => {
    const groups = new Map<string, Grade[]>()
    for (const grade of grades ?? []) {
      const key = grade.grading_period_name || "Unassigned"
      const bucket = groups.get(key)
      if (bucket) bucket.push(grade)
      else groups.set(key, [grade])
    }
    return Array.from(groups.entries()).map(([periodName, rows]) => ({
      periodName,
      grades: rows,
    }))
  }, [grades])
}

/** Stable key for a subject assignment select option. */
export function useAssignmentLabel(
  assignments: SubjectAssignment[] | undefined
): (id: string) => string {
  return useCallback(
    (id: string) => {
      const match = assignments?.find((a) => a.id === id)
      return match
        ? `${match.subject_code} — ${match.subject_name} (${match.section_name})`
        : "Unknown assignment"
    },
    [assignments]
  )
}

export { countByStatus }

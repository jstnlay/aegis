/**
 * Parent domain API (PH11.9).
 *
 * Every endpoint and field below is copied from the backend, not inferred.
 *
 * ---------------------------------------------------------------------------
 * Child resolution — why this reads enrollments
 * ---------------------------------------------------------------------------
 * There is no "my children" endpoint in the contract, and none is invented
 * here. `ParentStudentLink` is a real model, but no viewset exposes it:
 * `config/api_v1.py` routes `/accounts/`, `/academics/`, `/guidance/` and the
 * rest, and nothing registers a parent-children path. What *is* exposed is
 * `EnrollmentViewSet`, whose `get_queryset()` already scopes a parent to
 * `student_id__in=_get_linked_student_ids(user)` — the same
 * `ParentStudentLink` predicate the guidance and attendance viewsets use.
 *
 * So reading `/academics/enrollments/` is not "scanning arbitrary student
 * records": the server decides which rows exist, and the parent's child UUIDs
 * are exactly the ones the database returns. That was verified rather than
 * assumed — see the parent scoping test in `apps/accounts/tests.py`
 * (`test_parent_enrollment_queryset_is_linked_children_only`) and the
 * equivalent probe recorded in docs/PH11.9_NOTE.md.
 *
 * The client de-duplicates by `student` (the StudentProfile UUID) because a
 * student enrolled in more than one section yields more than one enrollment
 * row. `Enrollment.id` is the Enrollment PK and must never be used as a
 * student identity.
 *
 * ---------------------------------------------------------------------------
 * Attendance envelopes are not the same as analytics envelopes
 * ---------------------------------------------------------------------------
 * `GET /attendance/summary/` returns a **bare JSON array** (no `count`/
 * `results` envelope) — `AttendanceRecordViewSet.summary` returns
 * `Response(results)`. `GET /analytics/students/<id>/metrics/` returns
 * `{"status": "ok", "data": {...}}`. `GET /attendance/records/` returns the
 * standard paginated envelope. The three shapes are handled separately below;
 * nothing here shares a generic "list" helper across them.
 *
 * `summary` is wired as a view-level action at `/attendance/summary/`, so the
 * student is a **query parameter**. Appending it as a path segment
 * (`/attendance/summary/<uuid>`) matches no route and returns 404.
 *
 * ---------------------------------------------------------------------------
 * Guidance is read-only for parents, and that is enforced server-side
 * ---------------------------------------------------------------------------
 * `ConsultationRecordViewSet` and `RiskAlertViewSet` return HTTP 403 for a
 * parent on create/update/delete and on the acknowledge/escalate/resolve
 * actions (PH11.9 fix; see the commit for the measured before/after). No
 * mutation hooks are defined in this module, so the client cannot offer a
 * write that the server would reject.
 *
 * `InterventionViewSet` is guidance-only at the role level and has no parent
 * branch at all, so a parent has no intervention surface to fetch.
 */

import { useQuery } from "@tanstack/react-query"

import { apiClient } from "@/lib/api"
import { fetchAllPages } from "@/lib/pagination"
import type { RiskFactor } from "@/lib/risk-factor"

/* -------------------------------------------------------------------------- */
/* Child resolution                                                            */
/* -------------------------------------------------------------------------- */

export interface LinkedStudent {
  /** StudentProfile UUID — the id every other endpoint expects. */
  id: string
  student_name: string
  /** School-assigned student code, e.g. "AEGIS-QA-S0026". */
  student_id: string
  section_name: string
}

interface EnrollmentRecord {
  id: string
  student: string
  student_name: string
  student_id: string
  section_name: string
  is_active: boolean
}

export function useLinkedStudents() {
  return useQuery<LinkedStudent[], Error>({
    queryKey: ["parent", "linked-students"],
    queryFn: async () => {
      const { results } = await fetchAllPages<EnrollmentRecord>(
        "/academics/enrollments/"
      )
      // Deduplicate by StudentProfile UUID (the `student` field).
      // Enrollment `id` is the Enrollment PK, not the student UUID.
      const studentMap = new Map<string, LinkedStudent>()
      for (const enrollment of results) {
        if (!studentMap.has(enrollment.student)) {
          studentMap.set(enrollment.student, {
            id: enrollment.student,
            student_name: enrollment.student_name,
            student_id: enrollment.student_id,
            section_name: enrollment.section_name,
          })
        }
      }
      return Array.from(studentMap.values())
    },
  })
}

/* -------------------------------------------------------------------------- */
/* Academics — grades                                                          */
/* -------------------------------------------------------------------------- */

export interface ParentGrade {
  id: string
  subject_name: string
  subject_code: string
  section_name: string
  grading_period_name: string | null
  /** Decimal arrives as a JSON string; `normalizeScore` is the boundary. */
  score: string | number | null
  letter_grade: string | null
  remarks: string | null
  status: string
}

/**
 * Finalized grades for one linked child.
 *
 * `GradeViewSet.get_queryset()` already filters a parent to their linked
 * children, and the view supports `?student=` and `?status=`, so the extra
 * `student` filter narrows to the selected child rather than widening access.
 */
export function useChildGrades(studentId: string | null) {
  return useQuery<ParentGrade[], Error>({
    queryKey: ["parent", "grades", studentId],
    enabled: Boolean(studentId),
    queryFn: async () => {
      const { results } = await fetchAllPages<ParentGrade>(
        `/academics/grades/?status=finalized&student=${studentId ?? ""}`
      )
      return results
    },
  })
}

/* -------------------------------------------------------------------------- */
/* Attendance                                                                  */
/* -------------------------------------------------------------------------- */

export interface AttendanceRecord {
  id: string
  student: string
  student_name: string
  student_id_code: string
  section_name: string
  date: string
  status: "present" | "late" | "absent"
}

/**
 * Individual attendance records for one linked child.
 *
 * Paginated envelope (`{count, results}`), and the view supports `?student=`
 * plus `?date_from` / `?date_to`.
 */
export function useChildAttendance(
  studentId: string | null,
  range?: { from?: string; to?: string }
) {
  return useQuery<AttendanceRecord[], Error>({
    queryKey: [
      "parent",
      "attendance",
      studentId,
      range?.from ?? "",
      range?.to ?? "",
    ],
    enabled: Boolean(studentId),
    queryFn: async () => {
      const params = new URLSearchParams({ student: studentId ?? "" })
      if (range?.from) params.set("date_from", range.from)
      if (range?.to) params.set("date_to", range.to)
      const { results } = await fetchAllPages<AttendanceRecord>(
        `/attendance/records/?${params.toString()}`
      )
      return results
    },
  })
}

/**
 * Per-student attendance counts.
 *
 * **Bare array, not the paginated envelope** — see the module note. The view
 * accepts `?student=<uuid>`; `student` is a query parameter, not a path
 * segment.
 */
export function useChildAttendanceSummary(studentId: string | null) {
  return useQuery<
    Array<{
      student: string
      present_count: number
      late_count: number
      absent_count: number
      total_records: number
    }>,
    Error
  >({
    queryKey: ["parent", "attendance-summary", studentId],
    enabled: Boolean(studentId),
    queryFn: async () => {
      const { data } = await apiClient.get<
        Array<{
          student: string
          present_count: number
          late_count: number
          absent_count: number
          total_records: number
        }>
      >(`/attendance/summary/?student=${studentId ?? ""}`)
      return data
    },
  })
}

/* -------------------------------------------------------------------------- */
/* Assessments and results                                                     */
/* -------------------------------------------------------------------------- */

/**
 * One published assessment as the **list** endpoint returns it.
 *
 * `AssessmentViewSet.get_serializer_class()` returns
 * `AssessmentListSerializer` for `list` and `AssessmentSerializer` for
 * `retrieve`. The list form carries `question_count` and no nested
 * `questions`; only the detail route carries questions. The two are separate
 * types on purpose rather than one type with optional fields, so a list row
 * cannot be read as if it had questions.
 */
export interface ParentAssessmentListItem {
  id: string
  title: string
  description: string | null
  assessment_type: string
  creator_role: string
  time_limit_minutes: number | null
  deadline: string | null
  published_at: string | null
  question_count: number
}

/** One published assessment with its questions, as `retrieve` returns it. */
export interface ParentAssessmentDetail {
  id: string
  title: string
  description: string | null
  assessment_type: string
  creator_role: string
  time_limit_minutes: number | null
  deadline: string | null
  published_at: string | null
  target_sections_details: Array<{
    id: string
    name: string
    grade_level: string
  }>
  target_students_details: Array<{
    id: string
    student_id: string
    name: string
  }>
  /**
   * `correct_answer` is deliberately absent from this type. The backend
   * withholds the answer key from anyone who is not the assessment's author
   * (PH11.9 fix), so a parent can never receive the field. Listing it here
   * would invite a future change to render `undefined` as a missing value
   * rather than as a redaction.
   */
  questions: Array<{
    id: string
    question_text: string
    question_type: string
    order: number
    options: string[] | null
  }>
}

export interface ParentAssessmentResult {
  id: string
  assessment: string
  assessment_title: string
  /** `AssessmentResultListSerializer.student` — the StudentProfile UUID. */
  student: string
  student_name: string
  student_id: string
  score: number | null
  total_possible: number | null
  percentage: number | null
  status: string
  started_at: string | null
  completed_at: string | null
}

/**
 * Published assessments visible to this parent.
 *
 * `AssessmentViewSet.get_queryset()` scopes a parent to published assessments
 * targeted at a linked child or that child's section. The view has **no**
 * `?student=` filter, and an assessment may target a whole section rather than
 * named students, so there is no sound way to attribute an assessment to one
 * selected child from the list payload alone. The list is therefore presented
 * across the parent's children, and `useAssessmentDetail` supplies the real
 * targeting.
 */
export function useParentAssessments(enabled = true) {
  return useQuery<ParentAssessmentListItem[], Error>({
    queryKey: ["parent", "assessments"],
    enabled,
    queryFn: async () => {
      const { results } = await fetchAllPages<ParentAssessmentListItem>(
        "/assessments/assessments/"
      )
      return results
    },
  })
}

/** One assessment with its questions. Answer keys are never included. */
export function useAssessmentDetail(assessmentId: string | null) {
  return useQuery<ParentAssessmentDetail, Error>({
    queryKey: ["parent", "assessment", assessmentId],
    enabled: Boolean(assessmentId),
    queryFn: async () => {
      const { data } = await apiClient.get<ParentAssessmentDetail>(
        `/assessments/assessments/${assessmentId ?? ""}/`
      )
      return data
    },
  })
}

/**
 * Results for one linked child.
 *
 * `AssessmentResultViewSet` applies `CanViewAssessmentResult` at the object
 * level *and* scopes the queryset to `ParentStudentLink` children, so a parent
 * sees only their own child's submissions. `AssessmentResultListSerializer`
 * carries `student`, so the extra per-child filter here is a refinement of
 * the server's scope, never a widening of it.
 */
export function useChildResults(studentId: string | null) {
  return useQuery<ParentAssessmentResult[], Error>({
    queryKey: ["parent", "results", studentId],
    enabled: Boolean(studentId),
    queryFn: async () => {
      const { results } = await fetchAllPages<ParentAssessmentResult>(
        "/assessments/assessment-results/"
      )
      return results.filter((row) => row.student === studentId)
    },
  })
}

/* -------------------------------------------------------------------------- */
/* Guidance — read-only                                                       */
/* -------------------------------------------------------------------------- */

export interface ParentRiskAlert {
  id: string
  student: string
  student_name: string
  risk_level: string
  /**
   * The AI engine writes objects here and counselors write strings — the same
   * field the guidance surface renders. Typed as `string[]` this used to hand
   * React a raw object and unmount the page; see `@/lib/risk-factor`.
   */
  risk_factors: RiskFactor[]
  source: string
  status: string
  assigned_counselor_name: string | null
  generated_at: string
}

export interface ParentConsultation {
  id: string
  student: string
  student_name: string
  counselor_name: string
  session_date: string
  session_time: string | null
  session_type: string
  concern_categories: string[]
  session_notes: string
  recommendations: string | null
  next_session_date: string | null
  priority_level: string
  status: string
}

export interface ParentBehavioralNote {
  id: string
  student: string
  student_name: string
  note_type: string
  note_text: string
  date_recorded: string
}

/** Risk alerts for linked children. Read-only: the view returns 403 on writes. */
export function useChildRiskAlerts(studentId: string | null) {
  return useQuery<ParentRiskAlert[], Error>({
    queryKey: ["parent", "risk-alerts", studentId],
    enabled: Boolean(studentId),
    queryFn: async () => {
      const { results } = await fetchAllPages<ParentRiskAlert>(
        "/guidance/risk-alerts/"
      )
      return results.filter((alert) => alert.student === studentId)
    },
  })
}

/** Consultations for linked children. Read-only. */
export function useChildConsultations(studentId: string | null) {
  return useQuery<ParentConsultation[], Error>({
    queryKey: ["parent", "consultations", studentId],
    enabled: Boolean(studentId),
    queryFn: async () => {
      const { results } = await fetchAllPages<ParentConsultation>(
        "/guidance/consultations/"
      )
      return results.filter((row) => row.student === studentId)
    },
  })
}

/** Behavioral notes about linked children. Read-only, and immutable server-side. */
export function useChildBehavioralNotes(studentId: string | null) {
  return useQuery<ParentBehavioralNote[], Error>({
    queryKey: ["parent", "behavioral-notes", studentId],
    enabled: Boolean(studentId),
    queryFn: async () => {
      const { results } = await fetchAllPages<ParentBehavioralNote>(
        "/guidance/behavioral-notes/"
      )
      return results.filter((note) => note.student === studentId)
    },
  })
}

/* -------------------------------------------------------------------------- */
/* Derived helpers                                                             */
/* -------------------------------------------------------------------------- */

/** Attendance totals for one child, summed across every section row. */
export function summarizeAttendance(
  rows: ReadonlyArray<{
    present_count: number
    late_count: number
    absent_count: number
    total_records: number
  }>
): {
  present: number
  late: number
  absent: number
  total: number
  /**
   * `(present + late) / total * 100`, or `null` when there are no records at
   * all. No records is "no data", not 0%; a genuine 0% is preserved.
   */
  rate: number | null
} {
  const present = rows.reduce((sum, r) => sum + r.present_count, 0)
  const late = rows.reduce((sum, r) => sum + r.late_count, 0)
  const absent = rows.reduce((sum, r) => sum + r.absent_count, 0)
  const total = rows.reduce((sum, r) => sum + r.total_records, 0)
  return {
    present,
    late,
    absent,
    total,
    rate: total > 0 ? ((present + late) / total) * 100 : null,
  }
}

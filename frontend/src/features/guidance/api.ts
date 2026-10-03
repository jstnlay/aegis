/**
 * Guidance domain API (PH11.8).
 *
 * Every field and endpoint below is copied from the backend, not inferred:
 *
 * - `apps/guidance/serializers.py` — `RiskAlertSerializer`,
 *   `ConsultationRecordSerializer`, `InterventionSerializer`,
 *   `InterventionStepSerializer`, `ProgressNoteSerializer`,
 *   `BehavioralNoteSerializer`, `GuidanceReportSerializer`
 * - `apps/guidance/views.py` — per-role querysets, `RiskAlertViewSet`'s
 *   `acknowledge` / `escalate` / `resolve` actions, and `InterventionViewSet`'s
 *   nested `steps`, `steps/<id>`, `notes` and `complete` actions
 * - `apps/guidance/urls/guidance.py` — router basenames and the
 *   `reports/student/<uuid>/` manual path
 * - `apps/assessments/views.py` + `serializers.py` — the guidance-scoped
 *   wellness/behavioral assessment list and result list
 * - `apps/academics/views.py` — guidance is a read-all caller of
 *   `EnrollmentViewSet` and `GradeViewSet`, which is the ONLY way a counselor
 *   can obtain the student roster and a student's grade record
 * - `apps/attendance/views.py` — guidance is read-all on records and summary
 * - `apps/analytics/services.py` — the student metrics payload shape
 *
 * ---------------------------------------------------------------------------
 * Contract facts this module depends on
 * ---------------------------------------------------------------------------
 * 1. **No server-side filtering.** `REST_FRAMEWORK` sets no
 *    `DEFAULT_FILTER_BACKENDS`, so no endpoint supports `?search=` or
 *    `?ordering=`. The only query parameters that exist anywhere are the
 *    hand-written ones in `GradeViewSet` (`student`, `subject_assignment`,
 *    `grading_period`, `status`), `AttendanceRecordViewSet` (`student`,
 *    `section`, `date_from`, `date_to`, `status`) and
 *    `AttendanceSummaryView` (`section`, `student`, `date_from`, `date_to`).
 *    Every list is therefore fetched whole and narrowed client-side, and every
 *    filter is a pure function over the fetched rows.
 *
 * 2. **Guidance visibility is asymmetric.** `RiskAlertViewSet`, the
 *    `EnrollmentViewSet`, the `GradeViewSet`, the attendance endpoints and
 *    `BehavioralNoteViewSet` are read-all for guidance, but
 *    `ConsultationRecordViewSet` and `InterventionViewSet` filter to
 *    `counselor=gp` / `assigned_counselor=gp`. "Active cases" is
 *    school-wide; consultations and interventions are the signed-in
 *    counselor's own. The UI must not describe the latter as school-wide.
 *
 * 3. **Nested endpoints are bare arrays.** `steps`, `notes` and the step
 *    detail return `Response(serializer.data)` with `many=True` — a plain JSON
 *    array with no `{count, results}` envelope — so `fetchAllPages` must not
 *    be used for them.
 *
 * 4. **Decimals arrive as JSON strings.** `COERCE_DECIMAL_TO_STRING` is not
 *    set, so DRF's default (`True`) applies and every `DecimalField` is
 *    emitted as `"8.00"`. `normalizeDecimal` is the single boundary that
 *    yields a real `number | null`; nothing downstream ever parses a decimal
 *    string.
 *
 * 5. **`assigned_counselor` is writable but has no pick list.**
 *    `RiskAlertSerializer.assigned_counselor` and
 *    `InterventionSerializer.assigned_counselor` accept a `GuidanceProfile`
 *    UUID, but no endpoint lists guidance profiles — `/accounts/users/` is
 *    `IsAdminUser` and `/accounts/me/` returns only the caller's `User`. PH11.8
 *    therefore never offers a counselor picker and never sends the field; the
 *    backend's own `perform_create` assigns the caller.
 *
 * 6. **`Intervention.status` is read-only.** It is in the serializer's
 *    `read_only_fields`; the only transition is the `complete` action, which
 *    also resolves the linked risk alert. PH11.8 ships no intervention edit
 *    and no lifecycle control, so the field is display-only here.
 *
 * 7. **No delete anywhere.** `BehavioralNoteViewSet` restricts
 *    `http_method_names` to get/post/head/options (notes are immutable), and
 *    the step detail action allows only GET/PATCH. There is no step-delete or
 *    intervention-delete surface in the contract, so none is exposed.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useMemo } from "react"

import { apiClient } from "@/lib/api"
import { fetchAllPages } from "@/lib/pagination"

/* -------------------------------------------------------------------------- */
/* Normalization                                                              */
/* -------------------------------------------------------------------------- */

/**
 * Wire shape of a DRF `DecimalField`: a JSON string such as `"8.00"`.
 * A number is accepted so the type stays honest if the backend ever sets
 * `COERCE_DECIMAL_TO_STRING = False`.
 */
export type WireDecimal = string | number | null | undefined

/**
 * Convert a DRF decimal into a `number | null`.
 *
 * Unparseable and absent values both collapse to `null` so a malformed payload
 * degrades to "not recorded" instead of poisoning an aggregate with `NaN`.
 *
 * Deliberately local to this feature rather than shared with
 * `features/academics/api.ts`: the two domains normalize different endpoints,
 * and the locked architecture is feature-based — a guidance page must not
 * import academics internals.
 */
export function normalizeDecimal(value: WireDecimal): number | null {
  if (value === null || value === undefined || value === "") return null
  const parsed = typeof value === "number" ? value : Number(value)
  return Number.isFinite(parsed) ? parsed : null
}

/* -------------------------------------------------------------------------- */
/* Risk alerts                                                               */
/* -------------------------------------------------------------------------- */

/** `RiskAlert.RiskLevel.choices` — the only three levels the API can return. */
export type RiskLevel = "low" | "moderate" | "high"

export const RISK_LEVELS: readonly RiskLevel[] = [
  "low",
  "moderate",
  "high",
] as const

export const RISK_LEVEL_LABELS: Record<RiskLevel, string> = {
  low: "Low",
  moderate: "Moderate",
  high: "High",
}

/** `RiskAlert.Status.choices`. */
export type RiskAlertStatus =
  "active" | "under_monitoring" | "resolved" | "escalated"

export const RISK_ALERT_STATUSES: readonly RiskAlertStatus[] = [
  "active",
  "under_monitoring",
  "resolved",
  "escalated",
] as const

export const RISK_ALERT_STATUS_LABELS: Record<RiskAlertStatus, string> = {
  active: "Active",
  under_monitoring: "Under monitoring",
  resolved: "Resolved",
  escalated: "Escalated",
}

/**
 * Statuses that mean "this case is still open".
 *
 * `RiskAlertViewSet` exposes exactly three transitions — `acknowledge`
 * (active -> under_monitoring), `escalate` and `resolve` (both from active or
 * under_monitoring) — so `resolved` is the only terminal state. Anything
 * outside this set is finished work and must not be counted as an open case.
 */
export const OPEN_ALERT_STATUSES: readonly RiskAlertStatus[] = [
  "active",
  "under_monitoring",
  "escalated",
] as const

/** `RiskAlert.Source.choices`. */
export type RiskAlertSource = "manual" | "decision_tree"

export const RISK_ALERT_SOURCE_LABELS: Record<RiskAlertSource, string> = {
  manual: "Manual",
  decision_tree: "Decision tree",
}

/**
 * `RiskAlertSerializer`.
 *
 * `student` is the `StudentProfile` UUID. `RiskAlertSerializer` exposes **no**
 * student ID code (unlike `BehavioralNoteSerializer.student_id_code`), so
 * there is deliberately no `student_id` field here — the roster lookup in
 * `useStudentRoster` is the only way to show a human-readable code.
 */
/**
 * One entry of `RiskAlert.risk_factors`.
 *
 * `RiskAlert.risk_factors` is a bare `models.JSONField(default=list)` with no
 * serializer validation, so both shapes genuinely occur and the client must
 * accept both:
 *
 * - **object** — what the AI engine writes. `ai_engine/risk_scorer.py`
 *   `_extract_decision_path` appends
 *   `{feature, threshold, value, direction}` per decision-tree node, and
 *   `ai_engine/risk_service.py` copies `explanation.contributing_factors`
 *   straight onto the alert. `ai_engine/resolver.py` already reads these with
 *   `factor.get("feature")`, so the object is the canonical form.
 * - **string** — what a counselor types on a manual alert, and what the QA seed
 *   writes.
 *
 * Typing this as `string[]` (as PH11.8 did) made `.join()` emit
 * "[object Object]" and `.map()` hand a raw object to React as a child, which
 * throws "Objects are not valid as a React child" and unmounts the page. The
 * object's `value`/`threshold` are also the only record of *why* the model
 * escalated a student, so they are rendered rather than discarded.
 */
export interface RiskFactorObject {
  feature?: string | null
  threshold?: number | null
  value?: number | null
  direction?: string | null
}

export type RiskFactor = string | RiskFactorObject

/**
 * A readable label for one factor, keeping the decision-tree detail.
 *
 * The raw `feature` key is preserved verbatim rather than prettified: it maps
 * directly onto `ai_engine.config.FEATURE_COLUMNS`, so a counselor auditing an
 * AI escalation can trace the row, and renaming it here would put the label out
 * of step with the model.
 */
export function riskFactorLabel(factor: RiskFactor): string {
  if (typeof factor === "string") return factor

  if (factor === null || typeof factor !== "object") return ""

  const feature =
    typeof factor.feature === "string" ? factor.feature.trim() : ""
  if (!feature) return ""

  const parts: string[] = [feature]

  const direction =
    typeof factor.direction === "string" ? factor.direction.trim() : ""
  if (direction) parts.push(direction)

  if (typeof factor.value === "number" && Number.isFinite(factor.value)) {
    parts.push(`value ${factor.value}`)
  }

  if (
    typeof factor.threshold === "number" &&
    Number.isFinite(factor.threshold)
  ) {
    parts.push(`threshold ${factor.threshold}`)
  }

  return parts.join(" ")
}

/**
 * Lower-cased text for search matching.
 *
 * Returns "" for an unusable entry so a malformed factor can never inject
 * "[object Object]" into the haystack and match every query.
 */
export function riskFactorSearchText(factor: RiskFactor): string {
  if (typeof factor === "string") return factor.toLowerCase()
  if (factor === null || typeof factor !== "object") return ""
  return [riskFactorLabel(factor), featureKeyOf(factor)]
    .filter(Boolean)
    .join(" ")
    .toLowerCase()
}

/** The bare `feature` key, for filtering that must match the model column. */
function featureKeyOf(factor: RiskFactorObject): string {
  return typeof factor.feature === "string" ? factor.feature : ""
}

export interface RiskAlert {
  id: string
  student: string
  student_name: string
  risk_level: RiskLevel
  risk_factors: RiskFactor[]
  source: RiskAlertSource
  status: RiskAlertStatus
  assigned_counselor: string | null
  assigned_counselor_name: string | null
  generated_at: string
  last_updated: string
  created_at: string
  updated_at: string
}

/** `POST /guidance/risk-alerts/{id}/{transition}/` response is a full alert. */
export type RiskAlertTransition = "acknowledge" | "escalate" | "resolve"

/**
 * Which transition the backend will accept from each starting status.
 *
 * Mirrors `RiskAlertViewSet.acknowledge` / `escalate` / `resolve`, which each
 * reject an out-of-order call with 400. Rendering only the legal button avoids
 * offering an action that is guaranteed to fail.
 */
export const ALERT_TRANSITIONS_BY_STATUS: Readonly<
  Record<RiskAlertStatus, readonly RiskAlertTransition[]>
> = {
  active: ["acknowledge", "escalate", "resolve"],
  under_monitoring: ["escalate", "resolve"],
  escalated: [],
  resolved: [],
}

export const RISK_ALERT_TRANSITION_LABELS: Record<RiskAlertTransition, string> =
  {
    acknowledge: "Acknowledge",
    escalate: "Escalate",
    resolve: "Resolve",
  }

/**
 * `RiskAlertSerializer` write fields.
 *
 * `source`, `generated_at` and `last_updated` are read-only (the viewset
 * forces `source = manual` and stamps `generated_at` in `perform_create`),
 * so they are absent here by construction.
 *
 * `risk_factors` is `string[]` on the way *out* even though it is
 * `RiskFactor[]` on the way in: a counselor records free text here. Only
 * `ai_engine` writes the object form, and it does so server-side.
 */
export interface CreateRiskAlertPayload {
  student: string
  risk_level: RiskLevel
  risk_factors: string[]
  assigned_counselor?: string | null
}

/* -------------------------------------------------------------------------- */
/* Consultations                                                             */
/* -------------------------------------------------------------------------- */

/** `ConsultationRecord.SessionType.choices`. */
export type ConsultationSessionType =
  "individual_counseling" | "group" | "parent_conference" | "follow_up"

export const CONSULTATION_SESSION_TYPES: readonly ConsultationSessionType[] = [
  "individual_counseling",
  "group",
  "parent_conference",
  "follow_up",
] as const

export const CONSULTATION_SESSION_TYPE_LABELS: Record<
  ConsultationSessionType,
  string
> = {
  individual_counseling: "Individual counseling",
  group: "Group",
  parent_conference: "Parent conference",
  follow_up: "Follow up",
}

/** `ConsultationRecord.PriorityLevel.choices`. */
export type ConsultationPriority = "high" | "medium" | "low"

export const CONSULTATION_PRIORITIES: readonly ConsultationPriority[] = [
  "high",
  "medium",
  "low",
] as const

export const CONSULTATION_PRIORITY_LABELS: Record<
  ConsultationPriority,
  string
> = {
  high: "High",
  medium: "Medium",
  low: "Low",
}

/** `ConsultationRecord.Status.choices`. */
export type ConsultationStatus = "ongoing" | "completed" | "follow_up"

export const CONSULTATION_STATUSES: readonly ConsultationStatus[] = [
  "ongoing",
  "completed",
  "follow_up",
] as const

export const CONSULTATION_STATUS_LABELS: Record<ConsultationStatus, string> = {
  ongoing: "Ongoing",
  completed: "Completed",
  follow_up: "Follow up",
}

/**
 * The closed set `ConsultationRecordSerializer.validate_concern_categories`
 * accepts. Anything else is rejected with a 400, so the picker is built from
 * this list rather than free text.
 */
export const CONCERN_CATEGORIES = [
  "academic",
  "behavioral",
  "emotional",
  "family",
  "bullying",
  "other",
] as const

export type ConcernCategory = (typeof CONCERN_CATEGORIES)[number]

export const CONCERN_CATEGORY_LABELS: Record<ConcernCategory, string> = {
  academic: "Academic",
  behavioral: "Behavioral",
  emotional: "Emotional",
  family: "Family",
  bullying: "Bullying",
  other: "Other",
}

/**
 * `ConsultationRecordSerializer`.
 *
 * `counselor` is read-only and set from the caller by `perform_create`; the
 * viewset also scopes every list to the caller's own records.
 */
export interface Consultation {
  id: string
  student: string
  student_name: string
  counselor: string
  counselor_name: string
  session_date: string
  /** `HH:MM:SS`, from a `TimeField`. */
  session_time: string
  session_type: ConsultationSessionType
  concern_categories: ConcernCategory[]
  session_notes: string
  recommendations: string | null
  next_session_date: string | null
  priority_level: ConsultationPriority
  status: ConsultationStatus
  created_at: string
  updated_at: string
}

/**
 * `POST /guidance/consultations/` body.
 *
 * `session_notes` is required and must be non-blank, and
 * `concern_categories` must be a non-empty-in-practice array drawn from
 * `CONCERN_CATEGORIES` — the serializer validates the membership of each entry
 * but does not require the array to be non-empty.
 */
export interface CreateConsultationPayload {
  student: string
  session_date: string
  session_time: string
  session_type: ConsultationSessionType
  concern_categories: ConcernCategory[]
  session_notes: string
  recommendations?: string | null
  next_session_date?: string | null
  priority_level: ConsultationPriority
  status?: ConsultationStatus
}

/**
 * `PATCH /guidance/consultations/{id}/` body. Every field is optional; the
 * viewset uses `partial=True` and rejects the call unless the record belongs
 * to the caller.
 */
export type UpdateConsultationPayload = Partial<CreateConsultationPayload>

/* -------------------------------------------------------------------------- */
/* Interventions                                                             */
/* -------------------------------------------------------------------------- */

/** `Intervention.Status.choices`. */
export type InterventionStatus = "active" | "completed" | "cancelled"

export const INTERVENTION_STATUSES: readonly InterventionStatus[] = [
  "active",
  "completed",
  "cancelled",
] as const

export const INTERVENTION_STATUS_LABELS: Record<InterventionStatus, string> = {
  active: "Active",
  completed: "Completed",
  cancelled: "Cancelled",
}

/**
 * `InterventionSerializer`.
 *
 * `assigned_counselor` and `status` are read-only, and `risk_alert_student` is
 * a `SerializerMethodField`-style char that resolves the linked alert's own
 * student name — it can disagree with `student_name` when the linked alert
 * belongs to a different student, which the backend does not forbid.
 */
export interface Intervention {
  id: string
  student: string
  student_name: string
  risk_alert: string | null
  risk_alert_student: string | null
  assigned_counselor: string
  assigned_counselor_name: string
  plan_start_date: string
  target_review_date: string | null
  status: InterventionStatus
  created_at: string
  updated_at: string
}

/**
 * `POST /guidance/interventions/` body.
 *
 * `plan_start_date` is a non-null `DateField` and `target_review_date` must
 * not precede it (`Intervention.clean`).
 */
export interface CreateInterventionPayload {
  student: string
  plan_start_date: string
  target_review_date?: string | null
  risk_alert?: string | null
}

/** `InterventionStep.Status.choices`. */
export type InterventionStepStatus =
  "pending" | "in_progress" | "completed" | "scheduled"

export const INTERVENTION_STEP_STATUSES: readonly InterventionStepStatus[] = [
  "pending",
  "in_progress",
  "completed",
  "scheduled",
] as const

export const INTERVENTION_STEP_STATUS_LABELS: Record<
  InterventionStepStatus,
  string
> = {
  pending: "Pending",
  in_progress: "In progress",
  completed: "Completed",
  scheduled: "Scheduled",
}

/**
 * `InterventionStepSerializer`.
 *
 * `intervention` is read-only — the nested action supplies it from the URL —
 * and there is no delete verb for a step in the router.
 */
export interface InterventionStep {
  id: string
  intervention: string
  title: string
  description: string
  status: InterventionStepStatus
  order: number
  created_at: string
  updated_at: string
}

/**
 * `POST /guidance/interventions/{id}/steps/` body.
 *
 * `order` is a `PositiveIntegerField` with `clean()` rejecting anything below
 * 1. The backend does not re-sequence on insert, so the form sends the
 * caller's chosen position as-is.
 */
export interface CreateInterventionStepPayload {
  title: string
  description: string
  status?: InterventionStepStatus
  order: number
}

/** `PATCH /guidance/interventions/{id}/steps/{step_id}/` body. */
export type UpdateInterventionStepPayload =
  Partial<CreateInterventionStepPayload>

/** `ProgressNoteSerializer`. */
export interface ProgressNote {
  id: string
  intervention: string
  note_text: string
  recorded_by: string
  recorded_by_name: string
  next_follow_up: string | null
  created_at: string
  updated_at: string
}

/** `POST /guidance/interventions/{id}/notes/` body. */
export interface CreateProgressNotePayload {
  note_text: string
  next_follow_up?: string | null
}

/* -------------------------------------------------------------------------- */
/* Behavioral notes                                                          */
/* -------------------------------------------------------------------------- */

/** `BehavioralNote.NoteType.choices`. */
export type BehavioralNoteType = "positive" | "warning" | "incident"

export const BEHAVIORAL_NOTE_TYPES: readonly BehavioralNoteType[] = [
  "positive",
  "warning",
  "incident",
] as const

export const BEHAVIORAL_NOTE_TYPE_LABELS: Record<BehavioralNoteType, string> = {
  positive: "Positive",
  warning: "Warning",
  incident: "Incident",
}

/**
 * `BehavioralNoteSerializer` — the only guidance-readable serializer that
 * carries `student_id_code`, the human-facing student number.
 *
 * Notes are immutable: the viewset allows only get/post/head/options and
 * faculty alone may create them, so there is no write hook here.
 */
export interface BehavioralNote {
  id: string
  student: string
  student_name: string
  student_id_code: string
  recorded_by: string
  recorded_by_name: string
  note_type: BehavioralNoteType
  note_text: string
  date_recorded: string
  created_at: string
  updated_at: string
}

/* -------------------------------------------------------------------------- */
/* Guidance report                                                           */
/* -------------------------------------------------------------------------- */

/**
 * `GET /guidance/reports/student/{student_id}/` — `GuidanceReportSerializer`.
 *
 * The three summary blocks are `DictField`/`ListField`, so their inner shapes
 * are the raw aggregates the view builds rather than a fixed schema.
 */
export interface GuidanceReport {
  student: string
  student_name: string
  student_id_code: string
  behavioral_note_counts: Partial<Record<BehavioralNoteType, number>>
  consultation_summary: {
    total: number
    by_status: Partial<Record<ConsultationStatus, number>>
    by_priority: Partial<Record<ConsultationPriority, number>>
  }
  intervention_summary: {
    total: number
    active: number
    completed: number
    cancelled: number
  }
  risk_alert_history: Array<{
    id: string
    risk_level: RiskLevel
    status: RiskAlertStatus
    source: RiskAlertSource
    generated_at: string
  }>
}

/* -------------------------------------------------------------------------- */
/* Assessments (guidance scope)                                               */
/* -------------------------------------------------------------------------- */

/**
 * `AssessmentListSerializer` — the payload the list endpoint returns.
 *
 * Guidance sees only assessments they created whose `assessment_type` is
 * `wellness` or `behavioral`; the `academic` branch belongs to faculty. The
 * detail serializer adds nested `questions`, `target_sections_details` and
 * `target_students_details`, none of which PH11.8 renders.
 */
export interface GuidanceAssessment {
  id: string
  title: string
  /** `Assessment.description` is `TextField(blank=True, null=True)`. */
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

/** `AssessmentResultListSerializer`, with decimals normalized. */
export interface GuidanceAssessmentResult {
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

interface GuidanceAssessmentResultWire extends Omit<
  GuidanceAssessmentResult,
  "score" | "total_possible" | "percentage"
> {
  score: WireDecimal
  total_possible: WireDecimal
  percentage: WireDecimal
}

function mapAssessmentResult(
  record: GuidanceAssessmentResultWire
): GuidanceAssessmentResult {
  return {
    ...record,
    score: normalizeDecimal(record.score),
    total_possible: normalizeDecimal(record.total_possible),
    percentage: normalizeDecimal(record.percentage),
  }
}

/* -------------------------------------------------------------------------- */
/* Student roster (guidance's only readable roster)                            */
/* -------------------------------------------------------------------------- */

/**
 * One row of the guidance student roster, derived from `EnrollmentSerializer`.
 *
 * A counselor cannot read `/accounts/users/` (it is `IsAdminUser`) and
 * `/accounts/me/` returns only the caller, so the enrollment list — which
 * `EnrollmentViewSet` returns in full for guidance — is the only roster
 * available. `EnrollmentSerializer.student_id` is the human-facing student
 * number, which is why this type is the one place a code can be shown.
 */
export interface StudentRosterEntry {
  /** `StudentProfile` UUID — the id used by every other guidance route. */
  id: string
  name: string
  /** The human-facing student number (`EnrollmentSerializer.student_id`). */
  code: string
  /** Section names from this student's enrollments, de-duplicated. */
  sections: string[]
  academicYear: string | null
  isActive: boolean
}

/* -------------------------------------------------------------------------- */
/* Query keys                                                                 */
/* -------------------------------------------------------------------------- */

const keys = {
  riskAlerts: ["guidance", "risk-alerts"] as const,
  consultations: ["guidance", "consultations"] as const,
  interventions: ["guidance", "interventions"] as const,
  interventionSteps: (interventionId: string) =>
    ["guidance", "interventions", interventionId, "steps"] as const,
  progressNotes: (interventionId: string) =>
    ["guidance", "interventions", interventionId, "notes"] as const,
  behavioralNotes: ["guidance", "behavioral-notes"] as const,
  guidanceReport: (studentId: string) =>
    ["guidance", "report", studentId] as const,
  assessments: ["guidance", "assessments"] as const,
  assessmentResults: ["guidance", "assessment-results"] as const,
  assessmentQuestions: ["guidance", "assessment-questions"] as const,
  roster: ["guidance", "students"] as const,
  studentGrades: (studentId: string) =>
    ["academics", "grades", "student", studentId] as const,
  studentAttendance: (studentId: string) =>
    ["attendance", "summary", studentId] as const,
  dashboardStats: ["guidance", "stats"] as const,
} as const

/**
 * The root key prefix for coarse invalidation after a mutation.
 *
 * Must be an array because `invalidateQueries` prefix-matches on every
 * element, and React Query's type requires `readonly unknown[]`.
 */
const GUIDANCE_KEY = ["guidance"] as const

/* -------------------------------------------------------------------------- */
/* Risk alert queries                                                        */
/* -------------------------------------------------------------------------- */

/**
 * Every risk alert visible to the counselor, unfiltered.
 *
 * `RiskAlertViewSet.get_queryset` returns the full table for guidance, and the
 * endpoint supports no query parameters, so status/level/student narrowing is
 * done by the filter helpers below rather than by the server.
 */
export function useRiskAlerts() {
  return useQuery<RiskAlert[], Error>({
    queryKey: keys.riskAlerts,
    queryFn: async () => {
      const { results } = await fetchAllPages<RiskAlert>(
        "/guidance/risk-alerts/"
      )
      return results
    },
  })
}

export interface RiskAlertFilters {
  status?: RiskAlertStatus | "all"
  riskLevel?: RiskLevel | "all"
  studentId?: string | null
  search?: string
}

/**
 * Applies the Risk Alerts page filters to an already-fetched list.
 *
 * Exported as a pure function so the filter semantics are unit-testable
 * without React Query, and so the page and the dashboard cannot drift apart.
 */
export function filterRiskAlerts(
  alerts: RiskAlert[],
  filters: RiskAlertFilters
): RiskAlert[] {
  const needle = filters.search?.trim().toLowerCase() ?? ""

  return alerts.filter((alert) => {
    if (
      filters.status &&
      filters.status !== "all" &&
      alert.status !== filters.status
    )
      return false
    if (
      filters.riskLevel &&
      filters.riskLevel !== "all" &&
      alert.risk_level !== filters.riskLevel
    )
      return false
    if (filters.studentId && alert.student !== filters.studentId) return false
    if (needle) {
      const haystack = [
        alert.student_name,
        alert.assigned_counselor_name ?? "",
        ...alert.risk_factors.map(riskFactorSearchText),
      ]
        .join(" ")
        .toLowerCase()
      if (!haystack.includes(needle)) return false
    }
    return true
  })
}

/** Open (unresolved) alerts — the "active cases" set. */
export function openRiskAlerts(alerts: RiskAlert[]): RiskAlert[] {
  return alerts.filter((alert) => OPEN_ALERT_STATUSES.includes(alert.status))
}

/** Per-status counts for the Risk Alerts filter chips. */
export function countAlertsByStatus(
  alerts: RiskAlert[]
): Record<RiskAlertStatus | "all", number> {
  const counts: Record<RiskAlertStatus | "all", number> = {
    all: alerts.length,
    active: 0,
    under_monitoring: 0,
    resolved: 0,
    escalated: 0,
  }
  for (const alert of alerts) counts[alert.status] += 1
  return counts
}

/**
 * `POST /guidance/risk-alerts/{id}/{transition}/`
 *
 * The three transitions are separate actions rather than a PATCH, and each
 * enforces its own legal starting status (an out-of-order call is a 400).
 * Invalidation covers the alert list, the dashboard stats, and any
 * intervention list because completing a plan resolves its linked alert.
 */
export function useRiskAlertTransition() {
  const queryClient = useQueryClient()
  return useMutation<
    RiskAlert,
    Error,
    { id: string; transition: RiskAlertTransition }
  >({
    mutationFn: async ({ id, transition }) => {
      const { data } = await apiClient.post<RiskAlert>(
        `/guidance/risk-alerts/${id}/${transition}/`
      )
      return data
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: GUIDANCE_KEY })
    },
  })
}

/**
 * `POST /guidance/risk-alerts/`
 *
 * Guidance-only. The viewset forces `source = manual` and stamps
 * `generated_at`, so neither is sent. `assigned_counselor` is omitted because
 * no readable endpoint lists guidance profiles (see contract fact 5).
 */
export function useCreateRiskAlert() {
  const queryClient = useQueryClient()
  return useMutation<RiskAlert, Error, CreateRiskAlertPayload>({
    mutationFn: async (payload) => {
      const { data } = await apiClient.post<RiskAlert>(
        "/guidance/risk-alerts/",
        payload
      )
      return data
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: GUIDANCE_KEY })
    },
  })
}

/* -------------------------------------------------------------------------- */
/* Consultation queries                                                      */
/* -------------------------------------------------------------------------- */

/**
 * The signed-in counselor's consultation records, newest session first.
 *
 * The viewset already scopes this to `counselor=gp`, and `ConsultationRecord`
 * orders by `-session_date`, so no client-side identity filter is applied.
 * Status narrowing is left to the caller — the page needs all three statuses
 * to drive its filter chips.
 */
export function useConsultations() {
  return useQuery<Consultation[], Error>({
    queryKey: keys.consultations,
    queryFn: async () => {
      const { results } = await fetchAllPages<Consultation>(
        "/guidance/consultations/"
      )
      return [...results].sort((a, b) => {
        // `session_date` is the ordering the backend uses; `created_at`
        // breaks ties within a day so the order is deterministic.
        const byDate = b.session_date.localeCompare(a.session_date)
        return byDate !== 0 ? byDate : b.created_at.localeCompare(a.created_at)
      })
    },
  })
}

export interface ConsultationFilters {
  status?: ConsultationStatus | "all"
  priority?: ConsultationPriority | "all"
  search?: string
}

export function filterConsultations(
  consultations: Consultation[],
  filters: ConsultationFilters
): Consultation[] {
  const needle = filters.search?.trim().toLowerCase() ?? ""

  return consultations.filter((consultation) => {
    if (
      filters.status &&
      filters.status !== "all" &&
      consultation.status !== filters.status
    )
      return false
    if (
      filters.priority &&
      filters.priority !== "all" &&
      consultation.priority_level !== filters.priority
    )
      return false
    if (needle) {
      const haystack = [
        consultation.student_name,
        consultation.session_notes,
        consultation.concern_categories.join(" "),
      ]
        .join(" ")
        .toLowerCase()
      if (!haystack.includes(needle)) return false
    }
    return true
  })
}

export function countConsultationsByStatus(
  consultations: Consultation[]
): Record<ConsultationStatus | "all", number> {
  const counts: Record<ConsultationStatus | "all", number> = {
    all: consultations.length,
    ongoing: 0,
    completed: 0,
    follow_up: 0,
  }
  for (const consultation of consultations) {
    counts[consultation.status] += 1
  }
  return counts
}

/** `POST /guidance/consultations/` — guidance-only, counselor set by server. */
export function useCreateConsultation() {
  const queryClient = useQueryClient()
  return useMutation<Consultation, Error, CreateConsultationPayload>({
    mutationFn: async (payload) => {
      const { data } = await apiClient.post<Consultation>(
        "/guidance/consultations/",
        payload
      )
      return data
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: GUIDANCE_KEY })
    },
  })
}

/**
 * `PATCH /guidance/consultations/{id}/`
 *
 * The viewset returns 403 unless the record belongs to the caller; because the
 * list is already scoped to the caller, the UI can only ever target a row the
 * counselor owns.
 */
export function useUpdateConsultation() {
  const queryClient = useQueryClient()
  return useMutation<
    Consultation,
    Error,
    { id: string; payload: UpdateConsultationPayload }
  >({
    mutationFn: async ({ id, payload }) => {
      const { data } = await apiClient.patch<Consultation>(
        `/guidance/consultations/${id}/`,
        payload
      )
      return data
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: GUIDANCE_KEY })
    },
  })
}

/* -------------------------------------------------------------------------- */
/* Intervention queries                                                      */
/* -------------------------------------------------------------------------- */

/**
 * The signed-in counselor's intervention plans.
 *
 * `InterventionViewSet` is `IsGuidanceUser` for every action and filters to
 * `assigned_counselor=gp`, so this list is explicitly *not* school-wide.
 */
export function useInterventions() {
  return useQuery<Intervention[], Error>({
    queryKey: keys.interventions,
    queryFn: async () => {
      const { results } = await fetchAllPages<Intervention>(
        "/guidance/interventions/"
      )
      return results
    },
  })
}

export interface InterventionFilters {
  status?: InterventionStatus | "all"
  studentId?: string | null
  search?: string
}

export function filterInterventions(
  interventions: Intervention[],
  filters: InterventionFilters
): Intervention[] {
  const needle = filters.search?.trim().toLowerCase() ?? ""

  return interventions.filter((intervention) => {
    if (
      filters.status &&
      filters.status !== "all" &&
      intervention.status !== filters.status
    )
      return false
    if (filters.studentId && intervention.student !== filters.studentId)
      return false
    if (needle) {
      if (!intervention.student_name.toLowerCase().includes(needle))
        return false
    }
    return true
  })
}

export function countInterventionsByStatus(
  interventions: Intervention[]
): Record<InterventionStatus | "all", number> {
  const counts: Record<InterventionStatus | "all", number> = {
    all: interventions.length,
    active: 0,
    completed: 0,
    cancelled: 0,
  }
  for (const intervention of interventions) counts[intervention.status] += 1
  return counts
}

/** `POST /guidance/interventions/` — counselor and status set by server. */
export function useCreateIntervention() {
  const queryClient = useQueryClient()
  return useMutation<Intervention, Error, CreateInterventionPayload>({
    mutationFn: async (payload) => {
      const { data } = await apiClient.post<Intervention>(
        "/guidance/interventions/",
        payload
      )
      return data
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: GUIDANCE_KEY })
    },
  })
}

/**
 * `GET /guidance/interventions/{id}/steps/`
 *
 * A bare array, not a paginated envelope — the action returns
 * `Response(serializer.data)` with `many=True`. The backend already orders by
 * `order`.
 */
export function useInterventionSteps(
  interventionId: string | null | undefined
) {
  const enabled = Boolean(interventionId)
  return useQuery<InterventionStep[], Error>({
    queryKey: keys.interventionSteps(interventionId ?? ""),
    enabled,
    queryFn: async () => {
      const { data } = await apiClient.get<InterventionStep[]>(
        `/guidance/interventions/${interventionId}/steps/`
      )
      return data
    },
  })
}

/** `POST /guidance/interventions/{id}/steps/` */
export function useCreateInterventionStep() {
  const queryClient = useQueryClient()
  return useMutation<
    InterventionStep,
    Error,
    { interventionId: string; payload: CreateInterventionStepPayload }
  >({
    mutationFn: async ({ interventionId, payload }) => {
      const { data } = await apiClient.post<InterventionStep>(
        `/guidance/interventions/${interventionId}/steps/`,
        payload
      )
      return data
    },
    onSuccess: (_step, { interventionId }) => {
      void queryClient.invalidateQueries({
        queryKey: keys.interventionSteps(interventionId),
      })
    },
  })
}

/**
 * `PATCH /guidance/interventions/{id}/steps/{step_id}/`
 *
 * There is no delete verb for a step anywhere in the router, so a step can
 * only be created, read and updated.
 */
export function useUpdateInterventionStep() {
  const queryClient = useQueryClient()
  return useMutation<
    InterventionStep,
    Error,
    {
      interventionId: string
      stepId: string
      payload: UpdateInterventionStepPayload
    }
  >({
    mutationFn: async ({ interventionId, stepId, payload }) => {
      const { data } = await apiClient.patch<InterventionStep>(
        `/guidance/interventions/${interventionId}/steps/${stepId}/`,
        payload
      )
      return data
    },
    onSuccess: (_step, { interventionId }) => {
      void queryClient.invalidateQueries({
        queryKey: keys.interventionSteps(interventionId),
      })
    },
  })
}

/**
 * `GET /guidance/interventions/{id}/notes/` — bare array, like steps.
 */
export function useProgressNotes(interventionId: string | null | undefined) {
  const enabled = Boolean(interventionId)
  return useQuery<ProgressNote[], Error>({
    queryKey: keys.progressNotes(interventionId ?? ""),
    enabled,
    queryFn: async () => {
      const { data } = await apiClient.get<ProgressNote[]>(
        `/guidance/interventions/${interventionId}/notes/`
      )
      return data
    },
  })
}

/** `POST /guidance/interventions/{id}/notes/` */
export function useCreateProgressNote() {
  const queryClient = useQueryClient()
  return useMutation<
    ProgressNote,
    Error,
    { interventionId: string; payload: CreateProgressNotePayload }
  >({
    mutationFn: async ({ interventionId, payload }) => {
      const { data } = await apiClient.post<ProgressNote>(
        `/guidance/interventions/${interventionId}/notes/`,
        payload
      )
      return data
    },
    onSuccess: (_note, { interventionId }) => {
      void queryClient.invalidateQueries({
        queryKey: keys.progressNotes(interventionId),
      })
    },
  })
}

/* -------------------------------------------------------------------------- */
/* Behavioral notes + guidance report                                        */
/* -------------------------------------------------------------------------- */

/**
 * All behavioral notes visible to the counselor.
 *
 * `BehavioralNoteViewSet` returns the full table for guidance and implements
 * no query-parameter filtering, so a single fetch backs both the whole list
 * and the per-student history on the profile page.
 */
export function useBehavioralNotes(studentId?: string | null) {
  return useQuery<BehavioralNote[], Error>({
    queryKey: [...keys.behavioralNotes, studentId ?? "all"],
    queryFn: async () => {
      const { results } = await fetchAllPages<BehavioralNote>(
        "/guidance/behavioral-notes/"
      )
      return studentId
        ? results.filter((note) => note.student === studentId)
        : results
    },
  })
}

/**
 * `GET /guidance/reports/student/{student_id}/` — guidance-only aggregate.
 *
 * A 404 means the `StudentProfile` UUID does not exist; the profile page
 * surfaces that as "student not found" rather than an empty report.
 */
export function useGuidanceReport(studentId: string | null | undefined) {
  const enabled = Boolean(studentId)
  return useQuery<GuidanceReport, Error>({
    queryKey: keys.guidanceReport(studentId ?? ""),
    enabled,
    queryFn: async () => {
      const { data } = await apiClient.get<GuidanceReport>(
        `/guidance/reports/student/${studentId}/`
      )
      return data
    },
  })
}

/* -------------------------------------------------------------------------- */
/* Assessments                                                               */
/* -------------------------------------------------------------------------- */

/** The counselor's own wellness/behavioral assessments. */
export function useGuidanceAssessments() {
  return useQuery<GuidanceAssessment[], Error>({
    queryKey: keys.assessments,
    queryFn: async () => {
      const { results } = await fetchAllPages<GuidanceAssessment>(
        "/assessments/assessments/"
      )
      return results
    },
  })
}

/**
 * Results for the assessments the counselor created.
 *
 * `AssessmentResultViewSet` scopes guidance to `assessment__created_by=user`,
 * so this is never a school-wide result set. `percentage` is a 0-100
 * `DecimalField` (not a 0-1 ratio) and is normalized to a number here.
 */
export function useGuidanceAssessmentResults() {
  return useQuery<GuidanceAssessmentResult[], Error>({
    queryKey: keys.assessmentResults,
    queryFn: async () => {
      const { results } = await fetchAllPages<GuidanceAssessmentResultWire>(
        "/assessments/assessment-results/"
      )
      return results.map(mapAssessmentResult)
    },
  })
}

export interface AssessmentFilters {
  status?: "published" | "draft" | "all"
  assessmentType?: GuidanceAssessment["assessment_type"] | "all"
  search?: string
}

/* -------------------------------------------------------------------------- */
/* Assessment authoring (verified capabilities only)                           */
/* -------------------------------------------------------------------------- */

/**
 * The only two types a guidance counselor may author.
 *
 * `AssessmentViewSet.get_queryset` scopes guidance to
 * `assessment_type__in=["wellness", "behavioral"]`, and
 * `AssessmentSerializer.validate` infers `creator_role="guidance"` from these
 * two values and then validates it against the caller's role. Sending
 * `academic` would fail validation rather than silently create a faculty-owned
 * assessment.
 */
export const GUIDANCE_ASSESSMENT_TYPES = ["wellness", "behavioral"] as const

export type GuidanceAssessmentType = (typeof GUIDANCE_ASSESSMENT_TYPES)[number]

/** `Assessment.QuestionType.choices`. */
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
 * `options` is a JSON array of strings used as the selectable choices for
 * `multiple_choice`, and as the scale points for `likert`. `true_false` has a
 * fixed pair and `essay` is free text, so neither takes options.
 */
export const OPTIONS_BEARING_QUESTION_TYPES: readonly AssessmentQuestionType[] =
  ["multiple_choice", "likert"]

/** `AssessmentQuestionSerializer`. */
export interface AssessmentQuestion {
  id: string
  assessment: string
  question_text: string
  question_type: AssessmentQuestionType
  order: number
  /** JSON string array for the option/scale types, else `null`. */
  options: string[] | null
  /**
   * The graded answer text.
   *
   * `to_representation` strips this only for a **student** viewing a published
   * assessment, so a creator always receives it back.
   */
  correct_answer: string | null
  created_at: string
  updated_at: string
}

/** `POST /assessments/assessments/` body for a guidance counselor. */
export interface CreateAssessmentPayload {
  title: string
  assessment_type: GuidanceAssessmentType
  description?: string | null
  time_limit_minutes?: number | null
  deadline?: string | null
  /**
   * `StudentProfile` UUIDs. Only offered when the counselor has guidance
   * activity for those students, so there is something verified to send.
   */
  target_students?: string[]
}

/** `POST /assessments/assessment-questions/` body. */
export interface CreateAssessmentQuestionPayload {
  assessment: string
  question_text: string
  question_type: AssessmentQuestionType
  order: number
  options?: string[] | null
  correct_answer?: string | null
}

/**
 * The order a newly added question should default to.
 *
 * `AssessmentQuestion.Meta` declares `unique_together = ("assessment",
 * "order")`, so a question may not reuse an order that already exists on the
 * same assessment. The safest default is therefore one past the highest order
 * present:
 *
 *   []        -> 1
 *   [1]       -> 2
 *   [1, 2]    -> 3
 *   [1, 2, 3] -> 4
 *
 * This is computed from the loaded question list on every render rather than
 * by incrementing a local counter after each submit, so a page reload — or a
 * fresh form mounted for a draft that already has questions — still lands on a
 * free order instead of colliding with `unique_together`.
 *
 * The `0` seed is what makes the empty case resolve to 1 rather than
 * `Math.max()` of nothing.
 */
export function nextQuestionOrder(
  questions: ReadonlyArray<{ order: number }>
): number {
  return Math.max(...questions.map((question) => question.order), 0) + 1
}

/**
 * `POST /assessments/assessments/`
 *
 * `created_by` is a read-only field set from the caller, and `creator_role` is
 * inferred from `assessment_type` server-side, so neither is sent.
 */
export function useCreateAssessment() {
  const queryClient = useQueryClient()
  return useMutation<unknown, Error, CreateAssessmentPayload>({
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
 * `POST /assessments/assessments/{id}/deploy/`
 *
 * The real deploy action. It 400s with "Assessment is already published." if
 * the assessment is live, and with "Cannot publish assessment without
 * questions." when the plan has no questions yet — the UI surfaces both rather
 * than pre-empting them, because the published flag and the question count are
 * both server-owned.
 */
export function useDeployAssessment() {
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

/**
 * Questions for one assessment.
 *
 * `AssessmentQuestionViewSet.get_queryset` already scopes this to
 * `assessment__created_by=user`, so no client-side owner filter is applied.
 */
export function useAssessmentQuestions(
  assessmentId: string | null | undefined
) {
  return useQuery<AssessmentQuestion[], Error>({
    queryKey: [...keys.assessmentQuestions, assessmentId ?? ""],
    enabled: Boolean(assessmentId),
    queryFn: async () => {
      const { results } = await fetchAllPages<AssessmentQuestion>(
        "/assessments/assessment-questions/"
      )
      return results.filter((question) => question.assessment === assessmentId)
    },
  })
}

/**
 * `POST /assessments/assessment-questions/`
 *
 * `perform_create` rejects a question on a published assessment with
 * "Cannot add questions to published assessments.", so the page only offers the
 * control for a draft.
 */
export function useCreateAssessmentQuestion() {
  const queryClient = useQueryClient()
  return useMutation<unknown, Error, CreateAssessmentQuestionPayload>({
    mutationFn: async (payload) => {
      const { data } = await apiClient.post(
        "/assessments/assessment-questions/",
        payload
      )
      return data
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: keys.assessmentQuestions })
      void queryClient.invalidateQueries({ queryKey: keys.assessments })
    },
  })
}

export function filterAssessments(
  assessments: GuidanceAssessment[],
  filters: AssessmentFilters
): GuidanceAssessment[] {
  const needle = filters.search?.trim().toLowerCase() ?? ""

  return assessments.filter((assessment) => {
    if (filters.status === "published" && !assessment.is_published) return false
    if (filters.status === "draft" && assessment.is_published) return false
    if (
      filters.assessmentType &&
      filters.assessmentType !== "all" &&
      assessment.assessment_type !== filters.assessmentType
    )
      return false
    if (needle) {
      const haystack =
        `${assessment.title} ${assessment.description ?? ""}`.toLowerCase()
      if (!haystack.includes(needle)) return false
    }
    return true
  })
}

/* -------------------------------------------------------------------------- */
/* Student roster + per-student academic context                             */
/* -------------------------------------------------------------------------- */

interface EnrollmentWire {
  id: string
  student: string
  student_name: string
  student_id: string
  section: string
  section_name: string
  academic_year: string
  academic_year_name: string
  date_enrolled: string
  is_active: boolean
}

/**
 * The counselor's student roster, one entry per student.
 *
 * Built from `EnrollmentViewSet`, which returns every enrollment to guidance.
 * Students appear once even when enrolled in several sections or years: the
 * first row seen wins the name/code, section names accumulate, and
 * `isActive` is the OR of the rows so a student with one active and one
 * historical enrollment stays in the roster.
 */
export function useStudentRoster() {
  return useQuery<StudentRosterEntry[], Error>({
    queryKey: keys.roster,
    queryFn: async () => {
      const { results } = await fetchAllPages<EnrollmentWire>(
        "/academics/enrollments/"
      )

      const byStudent = new Map<string, StudentRosterEntry>()
      for (const enrollment of results) {
        const existing = byStudent.get(enrollment.student)
        if (!existing) {
          byStudent.set(enrollment.student, {
            id: enrollment.student,
            name: enrollment.student_name,
            code: enrollment.student_id,
            sections: [enrollment.section_name],
            academicYear: enrollment.academic_year_name,
            isActive: enrollment.is_active,
          })
          continue
        }
        if (!existing.sections.includes(enrollment.section_name)) {
          existing.sections.push(enrollment.section_name)
        }
        existing.isActive = existing.isActive || enrollment.is_active
      }

      return Array.from(byStudent.values()).sort((a, b) =>
        a.name.localeCompare(b.name)
      )
    },
  })
}

/**
 * A student's finalized grade record as seen by a counselor.
 *
 * `GradeViewSet` supports `?student=` and `?status=`, and returns everything
 * to guidance, so this is a genuine server-side filter rather than a
 * client-side narrowing of a full table. `score` is a `DecimalField` and
 * arrives as a DRF decimal string, normalized to `number | null`.
 */
export function useStudentGradeRecord(studentId: string | null | undefined) {
  const enabled = Boolean(studentId)
  return useQuery<StudentGradeRow[], Error>({
    queryKey: keys.studentGrades(studentId ?? ""),
    enabled,
    queryFn: async () => {
      const { results } = await fetchAllPages<GradeWire>(
        `/academics/grades/?student=${studentId}&status=finalized`
      )
      return results.map(mapGrade)
    },
  })
}

/** One row of a student's finalized grades. */
export interface StudentGradeRow {
  id: string
  subjectName: string
  subjectCode: string
  sectionName: string
  gradingPeriodName: string | null
  /** 0-100 (`GradeSerializer.validate_score`), or `null` if unset. */
  score: number | null
  letterGrade: string | null
}

interface GradeWire {
  id: string
  subject_name: string
  subject_code: string
  section_name: string
  grading_period_name: string | null
  score: WireDecimal
  letter_grade: string | null
}

function mapGrade(grade: GradeWire): StudentGradeRow {
  return {
    id: grade.id,
    subjectName: grade.subject_name,
    subjectCode: grade.subject_code,
    sectionName: grade.section_name,
    gradingPeriodName: grade.grading_period_name,
    score: normalizeDecimal(grade.score),
    letterGrade: grade.letter_grade,
  }
}

/**
 * A student's raw attendance tally.
 *
 * `AttendanceSummaryView` accepts `?student=` and returns a bare array grouped
 * by student+section, so a multi-section student contributes several rows that
 * are summed here.
 *
 * There is deliberately **no rate**. `AttendanceSummaryView` returns raw
 * counts only and its own docstring states that `total_records` is "the number
 * of attendance records found (not the total possible school days)" and that
 * "any attendance-rate calculation is deferred until the specification defines
 * it". Inventing `(present + late) / total` here would manufacture a
 * denominator the backend has no opinion about, so the page shows the counts
 * and leaves the ratio to the spec. A student with no records yields no rows,
 * reported as `null` rather than a misleading set of zeros.
 */
export function useStudentAttendance(studentId: string | null | undefined) {
  const enabled = Boolean(studentId)
  return useQuery<
    {
      present: number
      late: number
      absent: number
      total: number
      studentName: string
      studentIdCode: string
    } | null,
    Error
  >({
    queryKey: keys.studentAttendance(studentId ?? ""),
    enabled,
    queryFn: async () => {
      const { data } = await apiClient.get<
        Array<{
          student: string
          student_name: string
          student_id_code: string
          section_name: string
          present_count: number
          late_count: number
          absent_count: number
          total_records: number
        }>
      >(`/attendance/summary/?student=${studentId}`)
      const rows = data.filter((row) => row.student === studentId)
      const first = rows[0]
      if (!first) return null

      return {
        present: rows.reduce((sum, r) => sum + r.present_count, 0),
        late: rows.reduce((sum, r) => sum + r.late_count, 0),
        absent: rows.reduce((sum, r) => sum + r.absent_count, 0),
        total: rows.reduce((sum, r) => sum + r.total_records, 0),
        studentName: first.student_name,
        studentIdCode: first.student_id_code,
      }
    },
  })
}

/* -------------------------------------------------------------------------- */
/* Dashboard statistics                                                      */
/* -------------------------------------------------------------------------- */

export interface GuidanceStats {
  /** Open alerts school-wide, as seen by this counselor. */
  active_cases: number
  /**
   * Distinct students with at least one **open** moderate/high alert.
   *
   * Derived from the same open-alert set as `active_cases` so the two cards
   * can never disagree — see `atRiskStudentsFrom` for the rule.
   */
  at_risk_students: number
  /** The counselor's own ongoing + follow-up consultations. */
  pending_follow_up: number
  /**
   * `completed / total` assessment results as a percentage, or `null` when
   * there are no results at all. 0 of 0 is undefined, not a real 0%.
   */
  assessment_completion_rate: number | null
}

/**
 * The one rule that defines "at risk", shared by the dashboard card and every
 * page that needs the same number.
 *
 * A student counts when they hold at least one alert that is BOTH
 *   - still open (`active` / `under_monitoring` / `escalated`), and
 *   - moderate or high risk.
 *
 * Status is part of the rule, not an afterthought: `resolved` is the only
 * terminal state the backend offers, so a student whose alert was resolved is
 * no longer an active case. Filtering on risk level alone would keep counting
 * them and would contradict the Active Cases card sitting next to it. Counts
 * are distinct by student because a student may hold several open alerts.
 */
export function atRiskStudentsFrom(alerts: RiskAlert[]): string[] {
  const students = new Set<string>()
  for (const alert of alerts) {
    if (!OPEN_ALERT_STATUSES.includes(alert.status)) continue
    if (alert.risk_level !== "moderate" && alert.risk_level !== "high") continue
    students.add(alert.student)
  }
  return Array.from(students)
}

/**
 * The Guidance dashboard aggregate.
 *
 * This replaces the previous pair of hooks that each recomputed
 * `at_risk_students` independently. All four numbers now come from one query
 * over three endpoints, so they are internally consistent by construction.
 *
 * `null` is reserved for "cannot be measured" (an unfulfilled query, or 0 of 0
 * assessment results); a genuine zero is preserved and renders as "0".
 */
export function useGuidanceStats() {
  return useQuery<GuidanceStats | undefined, Error>({
    queryKey: keys.dashboardStats,
    queryFn: async () => {
      const [alerts, consultations, results] = await Promise.all([
        fetchAllPages<RiskAlert>("/guidance/risk-alerts/"),
        fetchAllPages<Consultation>("/guidance/consultations/"),
        fetchAllPages<GuidanceAssessmentResultWire>(
          "/assessments/assessment-results/"
        ),
      ])

      const open = openRiskAlerts(alerts.results)

      const completed = results.results.filter(
        (result) => result.status === "completed"
      ).length
      const total = results.results.length

      return {
        active_cases: open.length,
        at_risk_students: atRiskStudentsFrom(alerts.results).length,
        pending_follow_up: consultations.results.filter((consultation) =>
          isPendingConsultation(consultation)
        ).length,
        // 0 of 0 results is an undefined rate, not 0% — the UI shows N/A.
        // A real 0% (results exist, none completed) is preserved.
        assessment_completion_rate:
          total > 0 ? Math.round((completed / total) * 100) : null,
      }
    },
  })
}

/**
 * A consultation still awaiting the counselor's next move.
 *
 * `completed` is the only status the backend treats as finished, so it is
 * excluded; `ongoing` and `follow_up` both imply outstanding work.
 */
export function isPendingConsultation(consultation: Consultation): boolean {
  return (
    consultation.status === "ongoing" || consultation.status === "follow_up"
  )
}

/* -------------------------------------------------------------------------- */
/* Derived helpers shared by the pages                                       */
/* -------------------------------------------------------------------------- */

/** Groups consultations by student for the profile page timeline. */
export function useConsultationsByStudent(
  consultations: Consultation[] | undefined
) {
  return useMemo(() => {
    const groups = new Map<string, Consultation[]>()
    for (const consultation of consultations ?? []) {
      const bucket = groups.get(consultation.student)
      if (bucket) bucket.push(consultation)
      else groups.set(consultation.student, [consultation])
    }
    return groups
  }, [consultations])
}

/** The highest risk level among a student's alerts, for roster/profile rows. */
export function highestRiskLevel(alerts: RiskAlert[]): RiskLevel | null {
  if (alerts.length === 0) return null
  if (alerts.some((alert) => alert.risk_level === "high")) return "high"
  if (alerts.some((alert) => alert.risk_level === "moderate")) return "moderate"
  return "low"
}

/* -------------------------------------------------------------------------- */
/* Students with guidance activity                                            */
/* -------------------------------------------------------------------------- */

/** One row of the students directory. */
export interface GuidanceStudent {
  /** `StudentProfile` UUID — the id every other guidance route expects. */
  id: string
  name: string
  /**
   * The human-facing student number, when some guidance-readable record
   * carries one.
   *
   * Only `BehavioralNote` and `AssessmentResult` include a code. Risk alerts,
   * consultations and interventions do not, so this is opportunistic: the
   * directory shows the first code it finds and otherwise renders an em-dash.
   */
  code: string | null
  /** Latest of the student's activity dates, ISO `YYYY-MM-DD`. */
  latestActivity: string | null
  openAlertCount: number
  /**
   * `high`, `moderate`, or `null`.
   *
   * Only set when the student has at least one **open** moderate/high alert.
   * Carrying the level rather than a bare boolean lets the UI colour the pill by
   * what actually applies, so a moderate-only student is not painted as high.
   */
  atRiskLevel: RiskLevel | null
  consultationCount: number
  interventionCount: number
  resultCount: number
}

function laterDate(a: string | null, b: string | null): string | null {
  if (!a) return b
  if (!b) return a
  return a > b ? a : b
}

/**
 * Students with guidance activity.
 *
 * The directory is derived **only** from the four collections that describe
 * guidance's own work: school-wide risk alerts, the caller's consultations,
 * the caller's interventions, and the caller's assessment results. A student
 * with no record in any of them has no guidance activity and is not listed.
 *
 * This deliberately does not use `/academics/enrollments/`. That endpoint is a
 * school-wide enrollment table, not a guidance directory: listing every
 * enrolled student would present students a counselor has never worked with as
 * though they were part of their caseload, and enrollment is not a guidance
 * concept at all.
 *
 * `code` is opportunistic because the sources disagree about who carries a
 * student number. `BehavioralNote.student_id_code` and
 * `AssessmentResult.student_id` are real fields; the three other sources have
 * no code field, so a student whose only activity is a risk alert has no code
 * and renders as an em-dash rather than a raw UUID.
 */
export function useGuidanceStudents() {
  const alertsQuery = useRiskAlerts()
  const consultationsQuery = useConsultations()
  const interventionsQuery = useInterventions()
  const resultsQuery = useGuidanceAssessmentResults()
  const notesQuery = useBehavioralNotes()

  return useQuery<{ students: GuidanceStudent[] }, Error>({
    queryKey: [...GUIDANCE_KEY, "students"],
    queryFn: async () => {
      const sources = [
        alertsQuery,
        consultationsQuery,
        interventionsQuery,
        resultsQuery,
        notesQuery,
      ]

      // A failed source must not read as "this counselor has no students".
      // The directory is a claim about the caseload, so an unreachable
      // endpoint has to surface as an error rather than an empty list.
      const failed = sources.find((source) => source.isError)
      if (failed?.error) throw failed.error

      const alerts = alertsQuery.data
      const consultations = consultationsQuery.data
      const interventions = interventionsQuery.data
      const results = resultsQuery.data
      const notes = notesQuery.data

      const rows = new Map<string, GuidanceStudent>()

      function ensure(
        id: string,
        name: string,
        code: string | null
      ): GuidanceStudent {
        let row = rows.get(id)
        if (!row) {
          row = {
            id,
            name,
            code,
            latestActivity: null,
            openAlertCount: 0,
            atRiskLevel: null,
            consultationCount: 0,
            interventionCount: 0,
            resultCount: 0,
          }
          rows.set(id, row)
        } else {
          // A later source may supply the name or the code the first one lacked.
          if (row.name !== name && name) row.name = name
          if (row.code === null && code !== null) row.code = code
        }
        return row
      }

      for (const alert of alerts ?? []) {
        const row = ensure(alert.student, alert.student_name, null)
        if (OPEN_ALERT_STATUSES.includes(alert.status)) row.openAlertCount += 1
        if (
          OPEN_ALERT_STATUSES.includes(alert.status) &&
          (alert.risk_level === "high" || alert.risk_level === "moderate")
        ) {
          // Escalating wins: once any open alert is high, the student is high.
          if (row.atRiskLevel !== "high") row.atRiskLevel = alert.risk_level
        }
        row.latestActivity = laterDate(row.latestActivity, alert.generated_at)
      }

      for (const consultation of consultations ?? []) {
        const row = ensure(
          consultation.student,
          consultation.student_name,
          null
        )
        row.consultationCount += 1
        row.latestActivity = laterDate(
          row.latestActivity,
          consultation.session_date
        )
      }

      for (const intervention of interventions ?? []) {
        const row = ensure(
          intervention.student,
          intervention.student_name,
          null
        )
        row.interventionCount += 1
        row.latestActivity = laterDate(
          row.latestActivity,
          intervention.plan_start_date
        )
      }

      for (const result of results ?? []) {
        const row = ensure(
          result.student,
          result.student_name,
          result.student_id
        )
        row.resultCount += 1
        row.latestActivity = laterDate(
          row.latestActivity,
          result.completed_at ?? result.started_at
        )
      }

      // Behavioral notes are the other guidance-readable source that carries a
      // student number, so they contribute codes even though they are not
      // counted as an activity type of their own.
      for (const note of notes ?? []) {
        const row = ensure(
          note.student,
          note.student_name,
          note.student_id_code
        )
        row.latestActivity = laterDate(row.latestActivity, note.date_recorded)
      }

      const students = Array.from(rows.values()).sort((a, b) =>
        a.name.localeCompare(b.name)
      )
      return { students }
    },
    enabled:
      !alertsQuery.isLoading &&
      !consultationsQuery.isLoading &&
      !interventionsQuery.isLoading &&
      !resultsQuery.isLoading &&
      !notesQuery.isLoading,
  })
}

/** Client-side narrowing of the students directory. */
export interface GuidanceStudentFilters {
  search?: string
  activity?: "all" | "alerts" | "consultations" | "interventions" | "results"
}

export function filterGuidanceStudents(
  students: GuidanceStudent[],
  filters: GuidanceStudentFilters
): GuidanceStudent[] {
  const needle = filters.search?.trim().toLowerCase() ?? ""

  return students.filter((student) => {
    if (filters.activity && filters.activity !== "all") {
      const count =
        filters.activity === "alerts"
          ? student.openAlertCount
          : filters.activity === "consultations"
            ? student.consultationCount
            : filters.activity === "interventions"
              ? student.interventionCount
              : student.resultCount
      if (count === 0) return false
    }
    if (!needle) return true
    return (
      student.name.toLowerCase().includes(needle) ||
      (student.code?.toLowerCase().includes(needle) ?? false)
    )
  })
}

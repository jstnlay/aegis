/**
 * Parent-facing labels, copied from the backend model choices.
 *
 * These duplicate the equivalents in `@/features/guidance/api` on purpose.
 * A parent must not import the guidance *client* module to read a label: that
 * module bundles the counselor's mutation hooks, and importing it into a
 * parent page would put write capabilities in a read-only bundle even though
 * the server would reject every one of them.
 *
 * Sources:
 * - `apps/guidance/models.py` — `RiskAlert.RiskLevel`, `RiskAlert.Status`,
 *   `RiskAlert.Source`
 * - `apps/guidance/serializers.py` — field names on `RiskAlertSerializer`
 */

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

/** `RiskAlert.Status.choices` */
export type AlertStatus =
  "active" | "under_monitoring" | "resolved" | "escalated"

export const ALERT_STATUS_LABELS: Record<AlertStatus, string> = {
  active: "Active",
  under_monitoring: "Under monitoring",
  resolved: "Resolved",
  escalated: "Escalated",
}

/**
 * Statuses that mean the case is still open.
 *
 * A parent reading their child's record needs the same distinction the
 * counselor dashboard makes, otherwise a resolved alert looks like a live one.
 */
export const OPEN_ALERT_STATUSES: readonly AlertStatus[] = [
  "active",
  "under_monitoring",
  "escalated",
] as const

export type AlertSource = "manual" | "decision_tree"

export const RISK_ALERT_SOURCE_LABELS: Record<AlertSource, string> = {
  manual: "Recorded by the Guidance Office",
  decision_tree: "Flagged by the automated risk model",
}

/** `ConsultationRecord.SessionType.choices` */
export type ConsultationSessionType =
  "individual_counseling" | "group" | "parent_conference" | "follow_up"

export const CONSULTATION_SESSION_TYPE_LABELS: Record<
  ConsultationSessionType,
  string
> = {
  individual_counseling: "Individual counselling",
  group: "Group session",
  parent_conference: "Parent conference",
  follow_up: "Follow-up",
}

/** `ConsultationRecord.Status.choices` */
export type ConsultationStatus = "ongoing" | "follow_up" | "completed"

export const CONSULTATION_STATUS_LABELS: Record<ConsultationStatus, string> = {
  ongoing: "Ongoing",
  follow_up: "Follow-up scheduled",
  completed: "Completed",
}

/** `ConsultationRecord.PriorityLevel.choices` */
export type ConsultationPriority = "low" | "medium" | "high"

export const CONSULTATION_PRIORITY_LABELS: Record<
  ConsultationPriority,
  string
> = {
  low: "Low priority",
  medium: "Medium priority",
  high: "High priority",
}

/** `BehavioralNote.NoteType.choices` */
export type BehavioralNoteType = "positive" | "warning" | "incident"

export const BEHAVIORAL_NOTE_TYPE_LABELS: Record<BehavioralNoteType, string> = {
  positive: "Positive",
  warning: "Warning",
  incident: "Incident",
}

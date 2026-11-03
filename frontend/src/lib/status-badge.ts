/** Shared display semantics. Status labels and backend decisions stay unchanged. */
export type StatusTone = "success" | "warning" | "danger" | "info" | "neutral"
export type RiskLevel = "low" | "moderate" | "high"
export type ConsultationStatus = "ongoing" | "follow_up" | "completed"

export const STATUS_TONE_CLASSES: Readonly<Record<StatusTone, string>> = {
  success: "border-emerald-200 bg-emerald-50 text-emerald-800",
  warning: "border-amber-200 bg-amber-50 text-amber-900",
  danger: "border-red-200 bg-red-50 text-red-800",
  info: "border-sky-200 bg-sky-50 text-sky-800",
  neutral: "border-slate-200 bg-slate-50 text-slate-600",
}

const STATUS_TONES: Readonly<Record<string, StatusTone>> = {
  low: "success",
  normal: "success",
  positive: "success",
  approved: "success",
  accepted: "success",
  completed: "success",
  complete: "success",
  resolved: "success",
  finalized: "success",
  published: "success",
  present: "success",
  passing: "success",
  active: "success",
  current: "success",
  success: "success",
  successful: "success",
  moderate: "warning",
  medium: "warning",
  warning: "warning",
  under_monitoring: "warning",
  pending: "warning",
  submitted: "warning",
  not_submitted: "warning",
  in_progress: "warning",
  ongoing: "warning",
  follow_up: "warning",
  acknowledged: "warning",
  partial: "warning",
  late: "warning",
  open: "warning",
  high: "danger",
  severe: "danger",
  critical: "danger",
  urgent: "danger",
  incident: "danger",
  negative: "danger",
  rejected: "danger",
  reject: "danger",
  failed: "danger",
  absent: "danger",
  below_passing: "danger",
  overdue: "danger",
  escalated: "danger",
  processing: "info",
  scheduled: "info",
  excused: "info",
  draft: "neutral",
  cancelled: "neutral",
  canceled: "neutral",
  inactive: "neutral",
  dismissed: "neutral",
  skipped: "neutral",
  not_recorded: "neutral",
}

/** Explicit values only: never infer status from names, roles or visible text. */
export function statusTone(status: string): StatusTone {
  const key = status
    .trim()
    .toLowerCase()
    .replace(/[\s-]+/g, "_")
  return Object.hasOwn(STATUS_TONES, key) ? STATUS_TONES[key]! : "neutral"
}

export function statusBadgeClass(status: string): string {
  return STATUS_TONE_CLASSES[statusTone(status)]
}

export function riskLevelBadgeClass(level: string): string {
  return statusBadgeClass(level)
}

export function consultationStatusBadgeClass(status: string): string {
  return statusBadgeClass(status)
}

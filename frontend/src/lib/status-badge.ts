/**
 * Static, typed class maps for the guidance status badges.
 *
 * Same constraint as `grade-badge.ts`: Tailwind only emits utilities it
 * can see as complete literals in the source, so every class must be
 * spelled out here rather than composed at runtime.
 */

export type RiskLevel = "low" | "moderate" | "high"

export type ConsultationStatus = "ongoing" | "follow_up" | "completed"

/**
 * Risk levels use the PH11.2 semantic status tokens ($6.2): Low -> --success,
 * Moderate -> --warning, High -> --destructive.
 *
 * The three tokens are NOT interchangeable in role, which is why this is a
 * text treatment rather than a fill:
 * - `--warning` (oklch 0.82 0.15 80) is a light amber built for a surface. As
 *   text on a card it measures 1.77:1, so moderate uses its paired
 *   `--warning-foreground` (16.16:1) to keep the amber hue readable.
 * - `--success` (oklch 0.55 0.16 145) is a mid-tone. PH11.2 $6.1 pins both
 *   `--success` and `--success-foreground` to these values, and neither a solid
 *   fill (4.35:1) nor a `bg-success/10` tint (3.99:1) behind it reaches the
 *   4.5:1 normal-text bar -- this badge renders at text-xs. `text-success` on
 *   the card surface is the only compliant option (4.54:1).
 * - `--destructive` reads cleanly both ways; the text form is used for
 *   consistency (4.88:1).
 *
 * `bg-card` pins the measured backdrop to the surface instead of inheriting
 * the Badge `secondary` variant's `bg-secondary` (which is darker and would
 * drop success to ~4.1:1). The border restates the text hue so the pill keeps
 * its shape with the fill removed.
 */
const RISK_LEVEL_CLASSES: Readonly<Record<RiskLevel, string>> = {
  low: "bg-card text-success border-success",
  moderate: "bg-card text-warning-foreground border-warning-foreground",
  high: "bg-card text-destructive border-destructive",
}

const CONSULTATION_STATUS_CLASSES: Readonly<
  Record<ConsultationStatus, string>
> = {
  ongoing: "bg-blue-100 text-blue-800 border-blue-200",
  follow_up: "bg-purple-100 text-purple-800 border-purple-200",
  completed: "bg-muted text-muted-foreground border-border",
}

const FALLBACK_CLASS = "bg-muted text-muted-foreground border-border"

export function riskLevelBadgeClass(riskLevel: string): string {
  return RISK_LEVEL_CLASSES[riskLevel as RiskLevel] ?? FALLBACK_CLASS
}

export function consultationStatusBadgeClass(status: string): string {
  return (
    CONSULTATION_STATUS_CLASSES[status as ConsultationStatus] ?? FALLBACK_CLASS
  )
}

/**
 * Pure derivations for the Guidance dashboard's charts.
 *
 * Kept out of the `.tsx` chart files so those export components only, and kept
 * out of the API layer because none of it comes from a new endpoint: every
 * function here takes the alerts and consultations a page already holds.
 *
 * The rule all of it obeys: derive or omit, never fabricate.
 *
 * - Counts come from the records themselves. Nothing is restated from
 *   elsewhere and nothing is interpolated.
 * - An unparseable date is skipped, not counted as a zero month. An unknown
 *   date is not a date on which nothing happened.
 * - Colour is never the only signal. Every chart that paints a level also
 *   names it and counts it in text somewhere on the page.
 */

import type { RiskAlert, RiskLevel } from "@/features/guidance/api"

/** One risk level and the token that paints it. */
export const RISK_LEVEL_COLORS = {
  high: "var(--destructive)",
  moderate: "var(--chart-4)",
  low: "var(--chart-2)",
} as const

export const RISK_LEVEL_LABELS: Record<RiskLevel, string> = {
  high: "High Risk",
  moderate: "Moderate Risk",
  low: "Low Risk",
}

export interface RiskLevelRow {
  level: RiskLevel
  label: string
  count: number
}

/** Count open alerts per level. `Resolved` is a status, not a level. */
export function riskLevelRows(alerts: readonly RiskAlert[]): RiskLevelRow[] {
  const levels: RiskLevel[] = ["high", "moderate", "low"]
  return levels.map((level) => ({
    level,
    label: RISK_LEVEL_LABELS[level],
    count: alerts.filter((alert) => alert.risk_level === level).length,
  }))
}

/**
 * The four statuses the donut reports: three open levels plus Resolved.
 *
 * A resolved alert is counted once, under Resolved, and never again under its
 * risk level — an open-high alert and a resolved-high one answer different
 * questions, and summing both into "High Risk" would overstate the risk that
 * is still live.
 */
const STATUS_SERIES = [
  { key: "high", label: "High Risk", color: RISK_LEVEL_COLORS.high },
  {
    key: "moderate",
    label: "Moderate Risk",
    color: RISK_LEVEL_COLORS.moderate,
  },
  { key: "low", label: "Low Risk", color: RISK_LEVEL_COLORS.low },
  // Resolved is inactive history, so it reads as neutral grey rather than a
  // fourth severity colour. `--chart-3` was tried here and reads as near-black
  // on white, which overstates a closed case.
  { key: "resolved", label: "Resolved", color: "var(--muted-foreground)" },
] as const

export interface StatusSlice {
  key: string
  label: string
  count: number
  color: string
}

export function statusSlices(alerts: readonly RiskAlert[]): StatusSlice[] {
  return STATUS_SERIES.map((series) => ({
    key: series.key,
    label: series.label,
    color: series.color,
    count: alerts.filter((alert) =>
      series.key === "resolved"
        ? alert.status === "resolved"
        : alert.status !== "resolved" && alert.risk_level === series.key
    ).length,
  }))
}

/* -------------------------------------------------------------------------- */
/* New cases per month                                                        */
/* -------------------------------------------------------------------------- */

export interface MonthlyCases {
  key: string
  label: string
  count: number
}

const MONTH_WINDOW = 6

const MONTH_LABELS = [
  "Jan",
  "Feb",
  "Mar",
  "Apr",
  "May",
  "Jun",
  "Jul",
  "Aug",
  "Sep",
  "Oct",
  "Nov",
  "Dec",
]

/**
 * Every `created_at` that parses.
 *
 * `Number.isNaN(date.getTime())` is the parse test rather than a regex, so any
 * ISO-ish form the backend sends today or after a format change is accepted.
 */
function parsedDates(alerts: readonly RiskAlert[]): Date[] {
  return alerts
    .map((alert) => new Date(alert.created_at))
    .filter((date) => !Number.isNaN(date.getTime()))
}

/** The six month keys ending with the current month, oldest first. */
function monthWindow(now: Date): string[] {
  const keys: string[] = []
  const cursor = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), 1))
  for (let i = 0; i < MONTH_WINDOW; i += 1) {
    keys.unshift(
      `${cursor.getUTCFullYear()}-${String(cursor.getUTCMonth() + 1).padStart(2, "0")}`
    )
    cursor.setUTCMonth(cursor.getUTCMonth() - 1)
  }
  return keys
}

function monthKeyOf(date: Date): string {
  return `${date.getUTCFullYear()}-${String(date.getUTCMonth() + 1).padStart(2, "0")}`
}

/**
 * True when at least one alert falls inside the six-month window.
 *
 * This is the guard that decides whether the chart exists at all. False — no
 * parseable dates, or all of them older than the window — and the caller omits
 * the card instead of drawing six empty bars that would read as "zero new
 * cases every month".
 */
export function hasRecentCaseHistory(alerts: readonly RiskAlert[]): boolean {
  const dates = parsedDates(alerts)
  if (dates.length === 0) return false

  const window = monthWindow(new Date())
  return dates.some((date) => window.includes(monthKeyOf(date)))
}

export function newCasesPerMonth(alerts: readonly RiskAlert[]): MonthlyCases[] {
  const window = monthWindow(new Date())
  const counts = new Map<string, number>(window.map((key) => [key, 0]))

  for (const date of parsedDates(alerts)) {
    const key = monthKeyOf(date)
    const existing = counts.get(key)
    // Outside the window: the month already has its true count from older
    // alerts, and an alert older than the window must not be folded in.
    if (existing === undefined) continue
    counts.set(key, existing + 1)
  }

  return window.map((key) => ({
    key,
    label: MONTH_LABELS[Number(key.split("-")[1]) - 1] ?? key,
    count: counts.get(key) ?? 0,
  }))
}

import {
  Area,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts"

/**
 * Shared chart styling and data transforms.
 *
 * One place for everything a chart needs beyond its own data, so no screen
 * invents its own palette, axis treatment or tooltip.
 *
 * Real data only
 * --------------
 * Nothing in this module produces a value. `toChartValue` maps a real backend
 * number onto the chart's numeric axis and returns `null` for anything it
 * cannot honestly plot, which Recharts renders as a gap. It never substitutes
 * zero: a period with no finalized grades is absent, not at zero, and drawing
 * it as zero would assert a performance value the database does not contain.
 */

/**
 * The PH11.2 §15.2 sequential palette, read from the design tokens.
 *
 * Declared in `index.css` since PH11.2 and previously unreferenced. Reading
 * them at runtime keeps a chart on the same palette as every other surface, so
 * re-theming moves the charts too. `chart-3` is deliberately not used for a
 * data series: it is the darkest of the five and reads as near-black on white.
 */
export const CHART_COLORS = [
  "var(--chart-1)",
  "var(--chart-2)",
  "var(--chart-4)",
  "var(--chart-5)",
  "var(--color-chart-3)",
] as const

/** Grid lines: horizontal only, per PH11.2 §15.4. */
export const GRID_COLOR = "var(--border)"

/** Axis and label ink, so chart text matches the rest of the UI. */
export const AXIS_COLOR = "var(--muted-foreground)"

/**
 * Recharts needs resolved colours for SVG fills in some code paths, and CSS
 * custom properties are not resolvable outside a rendered element. Resolved
 * once from the document at call time, with the PH11.2 OKLCH values as the
 * fallback so a chart still renders if the token lookup fails.
 */
const FALLBACK_CHART_COLORS = [
  "oklch(0.646 0.222 41.1)",
  "oklch(0.6 0.118 184.7)",
  "oklch(0.828 0.189 84.4)",
  "oklch(0.769 0.188 70.1)",
  "oklch(0.398 0.07 227.4)",
]

function resolveToken(name: string, fallback: string): string {
  if (typeof window === "undefined" || !document?.documentElement) {
    return fallback
  }
  const value = getComputedStyle(document.documentElement)
    .getPropertyValue(name)
    .trim()
  return value || fallback
}

/** The palette as concrete colour values, for series fills and legends. */
export function chartColor(index: number): string {
  const token = CHART_COLORS[index % CHART_COLORS.length] ?? "--chart-1"
  const tokenName = token.startsWith("var(")
    ? token.slice(4, token.indexOf(")"))
    : token
  return resolveToken(
    tokenName,
    FALLBACK_CHART_COLORS[index % FALLBACK_CHART_COLORS.length]!
  )
}

/**
 * A chart value from real data, or `null` when there is nothing to plot.
 *
 * `Number(x)` on an empty string is 0, which would plot a real zero for an
 * absent value; the explicit check prevents that.
 */
export function toChartValue(value: unknown): number | null {
  if (value === null || value === undefined || value === "") return null
  const parsed = typeof value === "number" ? value : Number(value)
  return Number.isFinite(parsed) ? parsed : null
}

/** Percentages for a tooltip: 84.6154 → "84.6%". */
export function formatPercentValue(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) {
    return "No data"
  }
  return `${value.toFixed(1)}%`
}

/** Counts for a tooltip. */
export function formatCountValue(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) {
    return "No data"
  }
  return new Intl.NumberFormat().format(value)
}

/**
 * A score out of 100 for a tooltip.
 *
 * `Grade.score` is a raw 0–100 point value, not a ratio, so this appends no
 * percent sign — PH11.7 established that the unit is points out of 100.
 */
export function formatScoreValue(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) {
    return "No grades recorded"
  }
  return `${value.toFixed(2)} out of 100`
}

/**
 * Y-axis bounds for a 0–100 score chart.
 *
 * Fixed rather than auto-fitted: an auto-fitted axis on a subject whose
 * averages all sit in the eighties would render a bar chart that looks like
 * dramatic variation between 82 and 88.
 */
export const SCORE_DOMAIN: [number, number] = [0, 100]

/** A tick step that leaves a readable number of gridlines on a 0–100 axis. */
export const SCORE_TICKS = [0, 25, 50, 75, 100]

export {
  Area,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
}

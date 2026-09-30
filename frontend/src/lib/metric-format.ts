/**
 * Honest metric formatting for the dashboards.
 *
 * A dashboard card that means "the backend has no data for this metric"
 * must never render `0` / `0.00%` — that reads as a real measurement.
 * `null` / `undefined` / non-finite therefore render as an explicit
 * "N/A", while a genuine numeric zero is preserved verbatim.
 *
 * The distinction is made at the data layer (the API hooks return
 * `number | null` and only use `null` for "nothing to measure"), so these
 * formatters never have to guess.
 */

/** Rendered whenever a metric has no underlying data. */
export const NO_DATA_TEXT = "N/A"

function isMeasurable(value: number | null | undefined): value is number {
  return typeof value === "number" && Number.isFinite(value)
}

/**
 * Formats a percentage. Returns "N/A" when there is no data; a real
 * 0 is rendered as "0.0%" because it is a legitimate measurement.
 */
export function formatPercent(
  value: number | null | undefined,
  fractionDigits = 1
): string {
  if (!isMeasurable(value)) return NO_DATA_TEXT
  return `${value.toFixed(fractionDigits)}%`
}

/**
 * Formats a count. Returns "N/A" when there is no data; a real 0 is
 * rendered as "0" because it is a legitimate count.
 */
export function formatCount(value: number | null | undefined): string {
  if (!isMeasurable(value)) return NO_DATA_TEXT
  return String(value)
}

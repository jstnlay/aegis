/**
 * Static, typed class map for letter-grade badges.
 *
 * Tailwind only emits the utilities it can find as complete literals in
 * the source. A runtime-composed `` `bg-${letter}-100 text-${letter}-800` ``
 * therefore never produces any CSS: the badge renders, but with none of
 * the intended colours. Every class must be written out in full here so
 * the Tailwind scanner sees it.
 *
 * `academics.Grade.letter_grade` is a free-form CharField (max_length=5),
 * not an enum, so the map covers the standard Philippine grading scale
 * (A/B/C/D/F with +/- modifiers) and falls back to a neutral style for
 * anything unrecognised. Keys are normalised to lowercase and trimmed.
 */

export const UNKNOWN_LETTER_GRADE_CLASS =
  "bg-muted text-muted-foreground border-border"

export const MISSING_LETTER_GRADE_CLASS =
  "bg-muted text-muted-foreground border-border"

const LETTER_GRADE_CLASSES: Readonly<Record<string, string>> = {
  a: "bg-emerald-100 text-emerald-800 border-emerald-200",
  "a+": "bg-emerald-100 text-emerald-800 border-emerald-200",
  "a-": "bg-emerald-100 text-emerald-800 border-emerald-200",
  b: "bg-sky-100 text-sky-800 border-sky-200",
  "b+": "bg-sky-100 text-sky-800 border-sky-200",
  "b-": "bg-sky-100 text-sky-800 border-sky-200",
  c: "bg-amber-100 text-amber-800 border-amber-200",
  "c+": "bg-amber-100 text-amber-800 border-amber-200",
  "c-": "bg-amber-100 text-amber-800 border-amber-200",
  d: "bg-orange-100 text-orange-800 border-orange-200",
  "d+": "bg-orange-100 text-orange-800 border-orange-200",
  "d-": "bg-orange-100 text-orange-800 border-orange-200",
  f: "bg-red-100 text-red-800 border-red-200",
  "f+": "bg-red-100 text-red-800 border-red-200",
  "f-": "bg-red-100 text-red-800 border-red-200",
  inc: "bg-muted text-muted-foreground border-border",
  ng: "bg-muted text-muted-foreground border-border",
}

/**
 * Resolves the badge classes for a letter grade.
 *
 * - `null` / `undefined` / blank -> a neutral "no letter grade" style.
 * - A recognised grade           -> its mapped colour.
 * - An unrecognised value        -> a neutral style (never a raw,
 *   dynamically composed class).
 */
export function letterGradeBadgeClass(
  letterGrade: string | null | undefined
): string {
  if (typeof letterGrade !== "string") return MISSING_LETTER_GRADE_CLASS
  const key = letterGrade.trim().toLowerCase()
  if (!key) return MISSING_LETTER_GRADE_CLASS
  return LETTER_GRADE_CLASSES[key] ?? UNKNOWN_LETTER_GRADE_CLASS
}

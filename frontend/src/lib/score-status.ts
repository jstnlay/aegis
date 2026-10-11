/**
 * Passing-mark semantics for a score, for display only.
 *
 * 75 is the school's passing grade. The backend carries it as
 * `ai_engine.config.PASSING_GRADE` (overridable through `AEGIS_PASSING_GRADE`)
 * and the analytics views default their low-performance threshold to the same
 * number, so this module restates a rule that already exists rather than
 * inventing a grading scale. The server stays authoritative for every decision
 * that is more than a label.
 *
 * What this is for: a row that shows a subject and its score does not need a
 * progress bar to repeat the same number as a length. What it does need is the
 * one thing the number alone does not say out loud — whether that score
 * passes. That is a word, and a word does not read as an unfinished rule the
 * way a six-pixel bar under every row did.
 */

/** The school's passing mark, restated from `ai_engine.config`. */
export const PASSING_SCORE = 75

export type ScoreStatus = "not-recorded" | "passing" | "below-passing"

/** Classifies a score against the passing mark. Absent is its own state. */
export function scoreStatus(score: number | null | undefined): ScoreStatus {
  if (score === null || score === undefined || Number.isNaN(score)) {
    return "not-recorded"
  }
  return score >= PASSING_SCORE ? "passing" : "below-passing"
}

/** The reader-facing label for a status. */
export function scoreStatusLabel(status: ScoreStatus): string {
  switch (status) {
    case "not-recorded":
      return "Not recorded"
    case "passing":
      return "Passing"
    case "below-passing":
      return "Below passing"
  }
}

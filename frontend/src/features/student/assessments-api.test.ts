import { describe, expect, it } from "vitest"

import {
  ASSESSMENT_QUESTION_TYPE_LABELS,
  toScoreNumber,
} from "@/features/student/assessments-api"

describe("toScoreNumber", () => {
  /*
   * DRF serializes DecimalField as a string. Converting an absent value to 0
   * would report a score that does not exist, so every empty case returns null.
   */
  it("parses the string decimals DRF sends", () => {
    expect(toScoreNumber("8.00")).toBe(8)
    expect(toScoreNumber("0")).toBe(0)
    expect(toScoreNumber("97.50")).toBe(97.5)
  })

  it("accepts a number that is already numeric", () => {
    expect(toScoreNumber(12.25)).toBe(12.25)
  })

  it("returns null for every absent case rather than 0", () => {
    expect(toScoreNumber(null)).toBeNull()
    expect(toScoreNumber(undefined)).toBeNull()
    expect(toScoreNumber("")).toBeNull()
    expect(toScoreNumber("not-a-number")).toBeNull()
    expect(toScoreNumber(Number.NaN)).toBeNull()
  })

  it("keeps a real zero distinct from an absent score", () => {
    /*
     * auto_grade_assessment leaves total_possible at 0 when no question is
     * gradable, and sets percentage only when total_possible > 0. A genuine
     * zero score must survive; an absent one must not become zero.
     */
    expect(toScoreNumber("0.00")).toBe(0)
    expect(toScoreNumber(null)).not.toBe(0)
  })
})

describe("question type labels", () => {
  it("covers every Assessment.QuestionType choice", () => {
    expect(Object.keys(ASSESSMENT_QUESTION_TYPE_LABELS)).toEqual([
      "multiple_choice",
      "true_false",
      "essay",
      "likert",
    ])
  })

  it("names the types that are not auto-graded", () => {
    /*
     * auto_grade_assessment scores only AUTO_GRADABLE_TYPES
     * ("multiple_choice", "true_false"), one point each. essay and likert are
     * never scored, which the taking page states rather than implying a grade.
     */
    expect(ASSESSMENT_QUESTION_TYPE_LABELS.essay).toBe("Essay")
    expect(ASSESSMENT_QUESTION_TYPE_LABELS.likert).toBe("Likert scale")
  })
})

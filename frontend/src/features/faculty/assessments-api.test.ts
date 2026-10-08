import { describe, expect, it } from "vitest"

import {
  ASSESSMENT_QUESTION_TYPES,
  FACULTY_ASSESSMENT_TYPES,
  OPTIONS_BEARING_QUESTION_TYPES,
  nextQuestionOrder,
} from "@/features/faculty/assessments-api"

describe("faculty assessment authoring scope", () => {
  it("offers only the academic type", () => {
    /*
     * `Assessment.clean()` in apps/assessments/models.py requires an academic
     * assessment to have creator_role="faculty" and wellness/behavioral to have
     * creator_role="guidance". Offering another type would produce a 400 from
     * the serializer rather than a working form.
     */
    expect(FACULTY_ASSESSMENT_TYPES).toEqual(["academic"])
  })

  it("never offers guidance's types", () => {
    expect(FACULTY_ASSESSMENT_TYPES).not.toContain("wellness")
    expect(FACULTY_ASSESSMENT_TYPES).not.toContain("behavioral")
  })
})

describe("nextQuestionOrder", () => {
  /*
   * `AssessmentQuestion.Meta` declares unique_together = ("assessment", "order"),
   * so a new question must land on an order not already used, or the serializer
   * returns a 400.
   */
  it("starts at 1 for an empty list", () => {
    expect(nextQuestionOrder([])).toBe(1)
  })

  it("is one past the highest existing order", () => {
    expect(nextQuestionOrder([{ order: 1 }])).toBe(2)
    expect(nextQuestionOrder([{ order: 1 }, { order: 2 }])).toBe(3)
    expect(nextQuestionOrder([{ order: 1 }, { order: 2 }, { order: 3 }])).toBe(
      4
    )
  })

  it("does not assume the list is sorted", () => {
    expect(nextQuestionOrder([{ order: 3 }, { order: 1 }, { order: 2 }])).toBe(
      4
    )
  })
})

describe("question type options", () => {
  it("covers every Assessment.QuestionType choice", () => {
    expect([...ASSESSMENT_QUESTION_TYPES]).toEqual([
      "multiple_choice",
      "true_false",
      "essay",
      "likert",
    ])
  })

  it("treats only multiple_choice and likert as options-bearing", () => {
    /*
     * `multiple_choice` uses options as its selectable choices and `likert` as
     * its scale points. `true_false` has a fixed pair and `essay` is free text,
     * so neither takes options.
     */
    expect([...OPTIONS_BEARING_QUESTION_TYPES]).toEqual([
      "multiple_choice",
      "likert",
    ])
  })
})

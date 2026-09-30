import { describe, expect, it } from "vitest"

import {
  MISSING_LETTER_GRADE_CLASS,
  UNKNOWN_LETTER_GRADE_CLASS,
  letterGradeBadgeClass,
} from "./grade-badge"

/**
 * The original defect: `ParentDashboard` composed the badge class at runtime
 * (`` `bg-${letter}-100 text-${letter}-800` ``). Tailwind only emits utilities
 * it can find as complete literals, so none of those classes were ever
 * generated and every badge silently fell back to the `secondary` variant.
 *
 * The current fix uses a static, typed map, so every class below must appear
 * verbatim in the source (and therefore in the compiled CSS bundle). These
 * tests guard the *stability* of that map: no entry may ever go back to being
 * computed from a letter at runtime.
 */
describe("letterGradeBadgeClass", () => {
  it("maps each Philippine grading band to a distinct, static class set", () => {
    const expectations: Array<[string, string]> = [
      ["A", "bg-emerald-100 text-emerald-800 border-emerald-200"],
      ["B", "bg-sky-100 text-sky-800 border-sky-200"],
      ["C", "bg-amber-100 text-amber-800 border-amber-200"],
      ["D", "bg-orange-100 text-orange-800 border-orange-200"],
      ["F", "bg-red-100 text-red-800 border-red-200"],
    ]

    for (const [letter, expected] of expectations) {
      expect(letterGradeBadgeClass(letter)).toBe(expected)
    }

    // Distinct colours per band — a regression to one shared class would pass
    // the equality checks above only if all rows were changed identically.
    const classes = new Set(expectations.map(([, c]) => c))
    expect(classes.size).toBe(expectations.length)
  })

  it("treats +/- modifiers as their base band", () => {
    expect(letterGradeBadgeClass("A+")).toBe(letterGradeBadgeClass("A"))
    expect(letterGradeBadgeClass("B-")).toBe(letterGradeBadgeClass("B"))
    expect(letterGradeBadgeClass("C+")).toBe(letterGradeBadgeClass("C"))
    expect(letterGradeBadgeClass("D-")).toBe(letterGradeBadgeClass("D"))
  })

  it("is case- and whitespace-insensitive", () => {
    expect(letterGradeBadgeClass("  a  ")).toBe(letterGradeBadgeClass("A"))
    expect(letterGradeBadgeClass("b+")).toBe(letterGradeBadgeClass("B+"))
  })

  it("renders a neutral style when there is no letter grade", () => {
    expect(letterGradeBadgeClass(null)).toBe(MISSING_LETTER_GRADE_CLASS)
    expect(letterGradeBadgeClass(undefined)).toBe(MISSING_LETTER_GRADE_CLASS)
    expect(letterGradeBadgeClass("")).toBe(MISSING_LETTER_GRADE_CLASS)
    expect(letterGradeBadgeClass("   ")).toBe(MISSING_LETTER_GRADE_CLASS)
  })

  it("falls back to a neutral style for an unrecognised value", () => {
    // `letter_grade` is a free-form CharField (max_length=5), not an enum, so
    // unexpected values are possible and must degrade gracefully.
    expect(letterGradeBadgeClass("Z")).toBe(UNKNOWN_LETTER_GRADE_CLASS)
    expect(letterGradeBadgeClass("pass")).toBe(UNKNOWN_LETTER_GRADE_CLASS)
  })

  it("maps the no-grade administrative markers neutrally", () => {
    expect(letterGradeBadgeClass("INC")).toBe(MISSING_LETTER_GRADE_CLASS)
    expect(letterGradeBadgeClass("NG")).toBe(MISSING_LETTER_GRADE_CLASS)
  })

  it("never returns a class containing an unresolved template placeholder", () => {
    for (const value of ["A", "a+", "Z", "INC", "", null, undefined]) {
      const cls = letterGradeBadgeClass(value as string | null | undefined)
      expect(cls).not.toContain("${")
      expect(cls).not.toContain("undefined")
      // Every returned class must be a plain, fully-qualified utility list
      // (a coloured shade, or one of the neutral tokens).
      for (const token of cls.split(/\s+/)) {
        expect(token).toMatch(
          /^(bg|text|border)-([a-z]+-\d{2,3}|muted|muted-foreground|border)$/
        )
      }
    }
  })
})

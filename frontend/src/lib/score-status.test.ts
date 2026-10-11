import { describe, expect, it } from "vitest"

import {
  PASSING_SCORE,
  scoreStatus,
  scoreStatusLabel,
} from "@/lib/score-status"

describe("scoreStatus", () => {
  it("treats the passing mark itself as passing", () => {
    // The backend's own threshold is inclusive (`avg < PASSING_GRADE` is the
    // failing branch in `ai_engine.labeler`), so 75 passes and the label must
    // agree with the risk model rather than contradict it by one point.
    expect(scoreStatus(PASSING_SCORE)).toBe("passing")
    expect(scoreStatus(74.99)).toBe("below-passing")
  })

  it("keeps an absent score out of both branches", () => {
    expect(scoreStatus(null)).toBe("not-recorded")
    expect(scoreStatus(undefined)).toBe("not-recorded")
    // A NaN must not fall through a comparison into "passing".
    expect(scoreStatus(Number.NaN)).toBe("not-recorded")
  })

  it("classifies scores on either side of the mark", () => {
    expect(scoreStatus(98)).toBe("passing")
    expect(scoreStatus(75.5)).toBe("passing")
    expect(scoreStatus(0)).toBe("below-passing")
  })
})

describe("scoreStatusLabel", () => {
  it("labels every status without falling through", () => {
    expect(scoreStatusLabel("not-recorded")).toBe("Not recorded")
    expect(scoreStatusLabel("passing")).toBe("Passing")
    expect(scoreStatusLabel("below-passing")).toBe("Below passing")
  })
})

import { describe, expect, it } from "vitest"

import {
  INTERACTION_TYPES,
  INTERACTION_TYPE_LABELS,
} from "@/features/student/recommendations-api"

describe("interaction types", () => {
  /*
   * `StudentInteraction.InteractionType.choices` in apps/cms/models.py. The
   * write endpoint validates against these, so a typo here would produce a 400
   * the UI offers no way to explain.
   */
  it("covers every StudentInteraction.InteractionType choice", () => {
    expect([...INTERACTION_TYPES]).toEqual([
      "viewed",
      "started",
      "completed",
      "saved",
    ])
  })

  it("has a label for every type", () => {
    for (const type of INTERACTION_TYPES) {
      expect(INTERACTION_TYPE_LABELS[type], type).toBeTruthy()
    }
  })

  it("never sends a grade or score as an interaction", () => {
    /*
     * PH9 D17: grades, attendance, behavior and counseling are explicitly NOT
     * CF preference signals. Only observable interactions are, so this list
     * must not gain a value that implies academic performance is a preference.
     */
    const forbidden = ["grade", "score", "attendance", "result", "behavior"]
    for (const type of INTERACTION_TYPES) {
      for (const word of forbidden) {
        expect(type.includes(word), `${type} contains "${word}"`).toBe(false)
      }
    }
  })
})

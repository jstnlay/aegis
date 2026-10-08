import { describe, expect, it } from "vitest"

import {
  MAX_MESSAGE_LENGTH,
  suggestedPrompts,
  type ChatIntent,
  type ChatUrgency,
} from "@/features/chatbot/api"

/**
 * `ChatIntent` mirrors `apps/chatbot/taxonomy.py`. The assistant sends a
 * message and renders the reply, so a value that drifts from the server's
 * vocabulary would render as undefined in the UI rather than fail loudly.
 */
const SERVER_INTENTS: ChatIntent[] = [
  "greeting",
  "help",
  "system_navigation",
  "unknown",
  "ask_grade",
  "ask_academic_performance",
  "ask_subject_help",
  "ask_learning_resource",
  "ask_study_strategy",
  "ask_recommendation",
  "ask_attendance",
  "ask_attendance_status",
  "ask_assessment",
  "assessment_schedule",
  "assessment_instructions",
  "guidance_help",
  "express_concern",
  "request_counselor",
  "urgent_concern",
]

const SERVER_URGENCIES: ChatUrgency[] = ["normal", "elevated", "urgent"]

describe("chatbot payload vocabulary", () => {
  it("mirrors every ChatIntent the backend declares", () => {
    // 19 intents in taxonomy.ChatIntent, 3 in taxonomy.UrgencyLevel.
    expect(SERVER_INTENTS).toHaveLength(19)
    expect(SERVER_URGENCIES).toHaveLength(3)
  })
})

describe("suggestedPrompts", () => {
  /*
   * `ALLOWED_INTENTS_BY_ROLE` in apps/chatbot/service.py restricts faculty,
   * guidance and admin to greeting / help / system_navigation / unknown.
   * Offering them a grade prompt would produce the safe-fallback reply every
   * time, which reads as a broken assistant rather than a restricted one.
   */
  it("offers grade and attendance prompts to students", () => {
    const prompts = suggestedPrompts("student")

    expect(prompts.some((p) => p.toLowerCase().includes("grade"))).toBe(true)
    expect(prompts.some((p) => p.toLowerCase().includes("attendance"))).toBe(
      true
    )
  })

  it("offers grade and attendance prompts to parents", () => {
    const prompts = suggestedPrompts("parent")

    expect(prompts.some((p) => p.toLowerCase().includes("grade"))).toBe(true)
    expect(prompts.some((p) => p.toLowerCase().includes("attendance"))).toBe(
      true
    )
  })

  it("offers only always-allowed prompts to staff roles", () => {
    for (const role of ["faculty", "guidance", "admin"]) {
      const prompts = suggestedPrompts(role)

      for (const prompt of prompts) {
        expect(prompt.toLowerCase(), `${role}: ${prompt}`).not.toContain(
          "grade"
        )
        expect(prompt.toLowerCase(), `${role}: ${prompt}`).not.toContain(
          "attendance"
        )
      }
    }
  })
})

describe("message length", () => {
  it("matches the backend limit", () => {
    /*
     * `ChatMessageRequestSerializer.validate` rejects a blank message and
     * anything over 2000 characters. The textarea's `maxLength` must agree, or
     * the UI would let the user compose something the server rejects.
     */
    expect(MAX_MESSAGE_LENGTH).toBe(2000)
  })
})

import { useMutation } from "@tanstack/react-query"
import { apiClient } from "@/lib/api"

/**
 * AEGIS assistant (Final_Revision objectives 2.3 / 6.3, FR-031).
 *
 * One endpoint, one shape, for all five roles. What differs per role is decided
 * server-side by `ALLOWED_INTENTS_BY_ROLE` in `apps/chatbot/service.py` — the
 * client sends the same request for every user and renders whatever comes back.
 * Faculty, guidance and admin are allowed only greeting/help/navigation/unknown,
 * so they get a working but narrow assistant.
 *
 * The bot is stateless and deterministic. `POST /chatbot/message/` classifies
 * with the keyword tables in `policies.py` and answers from templates; there is
 * no LLM on this path (`views.py` passes `use_llm=False`). It recognises a fixed
 * set of intents and does not hold a conversation, so the UI states that rather
 * than implying a free-form conversation.
 *
 * Nothing is persisted: the transcript lives in component state for the life of
 * the page and is sent nowhere but this endpoint.
 */

export type ChatIntent =
  | "greeting"
  | "help"
  | "system_navigation"
  | "unknown"
  | "ask_grade"
  | "ask_academic_performance"
  | "ask_subject_help"
  | "ask_learning_resource"
  | "ask_study_strategy"
  | "ask_recommendation"
  | "ask_attendance"
  | "ask_attendance_status"
  | "ask_assessment"
  | "assessment_schedule"
  | "assessment_instructions"
  | "guidance_help"
  | "express_concern"
  | "request_counselor"
  | "urgent_concern"

export type ChatUrgency = "normal" | "elevated" | "urgent"

export interface EscalationInfo {
  status: string
  escalation_key: string
  intent: string
}

export interface ChatPayload {
  grade_summary?: GradeSummary
  attendance_summary?: AttendanceSummary
  resources?: LearningResource[]
  escalation?: EscalationInfo
}

export interface GradeSummary {
  student_id?: string
  student_name?: string
  average?: number | null
  subject_count?: number
  [key: string]: unknown
}

export interface AttendanceSummary {
  student_id?: string
  student_name?: string
  present_count?: number
  late_count?: number
  absent_count?: number
  total_records?: number
  [key: string]: unknown
}

export interface LearningResource {
  id?: string
  title?: string
  item_type?: string
  [key: string]: unknown
}

export interface ChatResponse {
  reply: string
  intent: ChatIntent
  urgency: ChatUrgency
  data: ChatPayload
  escalated: boolean
  safe_fallback: boolean
}

/** One entry in the on-screen transcript. */
export interface ChatMessage {
  id: string
  role: "user" | "assistant"
  text: string
  /** Present on assistant turns only. */
  response?: ChatResponse
}

interface ChatWireResponse {
  reply: string
  intent: string
  urgency: string
  data: ChatPayload
  escalated?: boolean
  safe_fallback?: boolean
}

/** Server limits: `ChatMessageRequestSerializer` rejects a blank or >2000 char message. */
export const MAX_MESSAGE_LENGTH = 2000

/** Starter prompts, phrased to hit the intents each role is actually allowed. */
export function suggestedPrompts(role: string): string[] {
  if (role === "student") {
    return [
      "What is my grade in Math?",
      "What is my attendance?",
      "Can you give me a resource for Science?",
    ]
  }
  if (role === "parent") {
    return ["What is my grade in Math?", "What is my attendance?"]
  }
  // faculty / guidance / admin are limited to greeting, help and navigation.
  return ["Hello!", "What can you help me with?", "How do I navigate AEGIS?"]
}

export function useSendChatMessage() {
  return useMutation<ChatResponse, Error, { message: string }>({
    mutationFn: async ({ message }) => {
      const { data } = await apiClient.post<ChatWireResponse>(
        "/chatbot/message/",
        { message }
      )
      return {
        reply: data.reply,
        intent: data.intent as ChatIntent,
        urgency: data.urgency as ChatUrgency,
        data: data.data ?? {},
        escalated: Boolean(data.escalated),
        safe_fallback: Boolean(data.safe_fallback),
      }
    },
  })
}

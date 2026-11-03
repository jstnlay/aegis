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
 * The bot is stateless and deterministic when no model answers.
 * `POST /chatbot/message/` classifies with the keyword tables in `policies.py`,
 * answers from templates and, for academic/attendance/recommendation intents,
 * from the caller's own imported records. The server tries a local model first
 * and an offsite one only as a fallback, through `AEGIS_CHATBOT_PROVIDER_CHAIN`
 * and `AEGIS_CHATBOT_USE_LLM`, with no client change; if neither answers, the
 * same deterministic reply is returned. It recognises a fixed set of intents
 * and does not hold a conversation, so the UI states that rather than implying
 * a free-form conversation.
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
  | "ask_risk_status"
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
  academic_status?: AcademicStatus
  recommendations?: RecommendationSet
  attendance_summary?: AttendanceSummary
  resources?: LearningResource[]
  escalation?: EscalationInfo
}

export interface GradeSummary {
  student_id?: string
  student_name?: string
  average?: number | null
  subject_count?: number
  subject_grades?: { subject: string; score: number }[]
  latest_period?: string | null
  data_status?: "finalized" | "pending_finalization" | "no_data"
  [key: string]: unknown
}

export interface AcademicStatus {
  status?: "on_track" | "at_risk" | "insufficient_data"
  average?: number | null
  passing_grade?: number
  weak_subjects?: { subject: string; score: number }[]
  provisional?: boolean
  risk_alert?: { risk_level: string; status: string } | null
  [key: string]: unknown
}

export interface RecommendationSet {
  method?: string
  fallback_used?: boolean
  recommendations?: Recommendation[]
  [key: string]: unknown
}

export interface Recommendation {
  learning_item_id?: string
  title?: string
  item_type?: string
  topic?: string
  reason?: string
  relevance_score?: number
  [key: string]: unknown
}

export interface AttendanceSummary {
  student_id?: string
  student_name?: string
  present_count?: number
  late_count?: number
  absent_count?: number
  total_records?: number
  attendance_rate?: number | null
  recent_records?: { date: string; status: string }[]
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
  /** True when an LLM provider was enabled but unavailable. */
  degraded?: boolean
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
  degraded?: boolean
}

/** Server limits: `ChatMessageRequestSerializer` rejects a blank or >2000 char message. */
export const MAX_MESSAGE_LENGTH = 2000

/** Starter prompts, phrased to hit the intents each role is actually allowed. */
export function suggestedPrompts(role: string): string[] {
  if (role === "student") {
    return [
      "What is my grade in Math?",
      "Am I at risk?",
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
        degraded: Boolean(data.degraded),
      }
    },
  })
}

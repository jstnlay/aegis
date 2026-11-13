import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseQueryResult,
} from "@tanstack/react-query"

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
 * What changed with the safety work:
 *
 * - **Turns are persisted.** `POST /chatbot/message/` writes a `ChatMessage`
 *   row, and `GET /chatbot/history/` returns the caller's own turns. The
 *   panel restores that history when it opens.
 * - **Turns are screened.** The server runs two detection layers and, when a
 *   message is sensitive, creates a flag that Guidance sees. The panel tells
 *   the student that, because a student who believes nothing was stored cannot
 *   give informed consent.
 * - **A student must accept the notice first.** Until they do, the endpoint
 *   answers HTTP 428 with the notice, and the panel shows it.
 *
 * The deterministic layer in `policies.py` remains authoritative: Gemini may
 * rewrite a non-sensitive reply, and may raise a severity, but it never
 * decides intent, urgency, routing or what a sensitive reply says.
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

export type ChatSeverity = "low" | "medium" | "high" | "critical"

export interface EscalationInfo {
  status: string
  escalation_key: string
  intent: string
}

export interface ChatPayload {
  grade_summary?: GradeSummary
  attendance_summary?: AttendanceSummary
  resources?: LearningResource[]
  /** The school documents that grounded the reply, when it was grounded. */
  knowledge?: KnowledgeSource[]
  escalation?: EscalationInfo
  safety?: ChatSafety
  flag?: ChatFlagRef
  chat_message_id?: string
  [key: string]: unknown
}

/** What the two detection layers decided about one message. */
export interface ChatSafety {
  severity: ChatSeverity
  categories: string[]
  manual_review: boolean
}

/** The flag created for a sensitive message, as the student is allowed to see it. */
export interface ChatFlagRef {
  id: string
  severity: ChatSeverity
  status: string
  manual_review: boolean
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
  /** The chatbot's own summary uses `_days`; the record pages use `_count`. */
  present_days?: number
  late_days?: number
  absent_days?: number
  total_days?: number
  attendance_rate?: number | null
  [key: string]: unknown
}

export interface LearningResource {
  id?: string
  title?: string
  item_type?: string
  [key: string]: unknown
}

/**
 * One passage of a school document that a reply was grounded in.
 *
 * `excerpt` is the window of the passage the assistant quoted; `source_label`
 * is what the student sees cited. The reply text already names the source, so
 * this is the same fact in structured form — it exists so a surface can link
 * to the document rather than repeat the sentence.
 */
export interface KnowledgeSource {
  chunk_id?: string
  document_id?: string
  title?: string
  category?: string
  source_label?: string
  source_url?: string
  excerpt?: string
  score?: number
}

export interface ChatResponse {
  reply: string
  intent: ChatIntent
  urgency: ChatUrgency
  data: ChatPayload
  escalated: boolean
  safe_fallback: boolean
}

/** The student-facing chatbot notice. */
export interface ChatNotice {
  version: string
  text: string
  accepted: boolean
  accepted_at?: string | null
}

/** A persisted turn, as `GET /chatbot/history/` returns it. */
export interface ChatHistoryEntry {
  id: string
  message: string
  reply: string
  intent: string
  urgency: string
  severity: ChatSeverity
  sensitive: boolean
  manual_review: boolean
  created_at: string
  flag_id?: string | null
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
  notice?: ChatNotice
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

/* ------------------------------------------------------------------ */
/* Notice and history                                                   */
/* ------------------------------------------------------------------ */

/**
 * The current notice and whether the caller has accepted it.
 *
 * Only a student is gated by the notice, but every role can read it: the
 * panel shows the same text to everyone, because it describes the assistant
 * rather than a student-only right.
 */
export function useChatNotice(enabled = true): UseQueryResult<ChatNotice> {
  return useQuery({
    queryKey: ["chatbot", "notice"],
    queryFn: async () => {
      const { data } = await apiClient.get<ChatNotice>("/chatbot/notice/")
      return data
    },
    enabled,
    retry: false,
  })
}

/** Accept the current notice version. */
export function useAcceptNotice() {
  const queryClient = useQueryClient()
  return useMutation<
    { detail: string; version: string; accepted_at: string },
    Error,
    { version?: string }
  >({
    mutationFn: async ({ version }) => {
      const { data } = await apiClient.post<{
        detail: string
        version: string
        accepted_at: string
      }>("/chatbot/notice/", version ? { version } : {})
      return data
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["chatbot", "notice"] })
    },
  })
}

/**
 * The public notice text, read before sign-up.
 *
 * `GET /chatbot/notice/public/` needs no token, so the registration form can
 * show the student what they are agreeing to before an account exists.
 */
export function usePublicNotice(enabled = true) {
  return useQuery({
    queryKey: ["chatbot", "notice", "public"],
    queryFn: async () => {
      const { data } = await apiClient.get<{ version: string; text: string }>(
        "/chatbot/notice/public/"
      )
      return data
    },
    enabled,
    retry: false,
  })
}

/** The caller's own persisted turns, newest first. */
export function useChatHistory(enabled = true) {
  return useQuery({
    queryKey: ["chatbot", "history"],
    queryFn: async () => {
      const { data } = await apiClient.get<{ results: ChatHistoryEntry[] }>(
        "/chatbot/history/"
      )
      return data.results ?? []
    },
    enabled,
    retry: false,
  })
}

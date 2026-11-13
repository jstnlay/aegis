import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseQueryResult,
} from "@tanstack/react-query"

import { apiClient } from "@/lib/api"

/**
 * Chatbot flag API — the safety workstream's read/write surface.
 *
 * Three roles read the same list endpoint and get three different payloads:
 *
 * - **Guidance and admin** get the full flag: student, message, reply,
 *   categories, recipients and the action history. `FlagSerializer` is what
 *   carries the conversation.
 * - **Faculty** get `FacultyFlagSerializer`, which has no student field, no
 *   message field, no reply field and no category field. A faculty notice says
 *   *a student in your class needs support* and nothing else.
 * - **Everyone else** is refused with 403.
 *
 * That asymmetry is deliberate and is enforced server-side in
 * `apps/chatbot/views.py`. The frontend mirrors it by using two different
 * types rather than one type with optional fields, so a faculty screen cannot
 * accidentally render content the server chose not to send.
 */

export type FlagSeverity = "low" | "medium" | "high" | "critical"

export type FlagStatus =
  | "open"
  | "acknowledged"
  | "under_review"
  | "resolved"
  | "false_positive"

/** The full flag, as Guidance and admin see it. */
export interface ChatFlag {
  id: string
  student: string | null
  student_name: string | null
  student_number: string | null
  severity: FlagSeverity
  status: FlagStatus
  source: string
  categories: string[]
  summary: string
  manual_review: boolean
  message: string
  reply: string
  escalation_due_at: string | null
  escalated_at: string | null
  acknowledged_at: string | null
  acknowledged_by: string | null
  resolved_at: string | null
  resolution_note: string
  created_at: string
  actions: FlagAction[]
  recipients: FlagRecipient[]
}

export interface FlagAction {
  id: string
  action: string
  note: string
  is_private: boolean
  actor_name: string
  metadata: Record<string, unknown>
  created_at: string
}

export interface FlagRecipient {
  user: string
  role: string
  notified_at: string | null
  acknowledged_at: string | null
}

/**
 * The content-blind faculty view.
 *
 * No student, no message, no reply, no summary, no categories. The field list
 * is the whole contract.
 */
export interface FacultyChatFlag {
  id: string
  severity: FlagSeverity
  status: FlagStatus
  created_at: string
  acknowledged_at: string | null
  escalated_at: string | null
}

export interface KeywordTerm {
  id: string
  term: string
  match_type: "keyword" | "phrase" | "regex"
  severity: FlagSeverity
  category: string
  is_active: boolean
  notes: string
  created_at: string
  updated_at: string
}

/**
 * One document the assistant is allowed to answer from.
 *
 * `body` is write-only on the server: it is chunked into the passages
 * retrieval searches and never returned. `chunk_count` is what says whether a
 * document is actually retrievable — a document with no chunks answers
 * nothing, whatever it is titled.
 */
export interface KnowledgeDocument {
  id: string
  title: string
  category: string
  source_label: string
  source_url: string
  origin: "manual" | "strapi" | "cms"
  external_id: string
  is_active: boolean
  chunk_count: number
  created_at: string
  updated_at: string
}

export interface KnowledgeDocumentInput {
  title: string
  category: string
  source_label?: string
  source_url?: string
  is_active?: boolean
  body?: string
}

export interface ChatbotDashboard {
  flags: {
    total: number
    open: number
    unacknowledged: number
    manual_review: number
    escalated: number
    by_severity: { severity: string; count: number }[]
    by_status: { status: string; count: number }[]
  }
  messages: {
    last_7_days: number
    sensitive_last_7_days: number
  }
  keywords: { active: number; total: number }
  /** The retrieval corpus: documents, and how many are actually indexed. */
  knowledge: {
    documents: number
    active: number
    chunks: number
    unindexed: number
  }
  acknowledgment: {
    timer_minutes: number
    /** The window per severity, after any per-severity override. */
    per_severity: Record<string, number>
    average_minutes: number | null
  }
  model: {
    configured: boolean
    sdk_installed: boolean
    model: string
    available: boolean
  }
  /** Whether student free text is encrypted at rest. */
  encryption: {
    enabled: boolean
    algorithm: string
    key_count: number
    active_key_id: string | null
    error: string | null
  }
  /** The feedback loop: the newest flags a counselor called false positives. */
  false_positives: {
    total: number
    recent: {
      id: string
      severity: FlagSeverity
      categories: string[]
      note: string
      created_at: string
    }[]
  }
}

/**
 * The flag list.
 *
 * `role` decides which shape comes back, so the two callers are separate
 * hooks rather than one hook with a flag argument.
 */
export function useGuidanceFlags(filters?: {
  status?: string
  severity?: string
}) {
  return useQuery({
    queryKey: ["chatbot", "flags", "guidance", filters ?? {}],
    queryFn: async () => {
      const { data } = await apiClient.get<{ results: ChatFlag[] }>(
        "/chatbot/flags/",
        { params: filters }
      )
      return data.results ?? []
    },
  })
}

export function useFacultyFlags(): UseQueryResult<FacultyChatFlag[]> {
  return useQuery({
    queryKey: ["chatbot", "flags", "faculty"],
    queryFn: async () => {
      const { data } = await apiClient.get<{ results: FacultyChatFlag[] }>(
        "/chatbot/flags/"
      )
      return data.results ?? []
    },
  })
}

export function useChatFlag(flagId: string | undefined) {
  return useQuery({
    queryKey: ["chatbot", "flag", flagId],
    queryFn: async () => {
      const { data } = await apiClient.get<ChatFlag>(`/chatbot/flags/${flagId}/`)
      return data
    },
    enabled: Boolean(flagId),
  })
}

/**
 * Every flag mutation invalidates the list and the detail.
 *
 * The flag list is the screen a counselor works from, so a stale list after an
 * acknowledgment is worse than a redundant refetch.
 */
function useFlagMutation<TInput extends { flagId: string }, TOutput>(
  path: (flagId: string) => string,
  body?: (input: TInput) => Record<string, unknown>
) {
  const queryClient = useQueryClient()
  return useMutation<TOutput, Error, TInput>({
    mutationFn: async (input) => {
      const { data } = await apiClient.post<TOutput>(
        path(input.flagId),
        body ? body(input) : {}
      )
      return data
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["chatbot", "flags"] })
      void queryClient.invalidateQueries({ queryKey: ["chatbot", "flag"] })
    },
  })
}

export function useAcknowledgeFlag() {
  return useFlagMutation<{ flagId: string; note?: string }, ChatFlag>(
    (flagId) => `/chatbot/flags/${flagId}/acknowledge/`,
    (input) => ({ note: input.note ?? "" })
  )
}

export function useAddCaseNote() {
  return useFlagMutation<{ flagId: string; note: string }, FlagAction>(
    (flagId) => `/chatbot/flags/${flagId}/notes/`,
    (input) => ({ note: input.note })
  )
}

export function useResolveFlag() {
  return useFlagMutation<{ flagId: string; note?: string }, ChatFlag>(
    (flagId) => `/chatbot/flags/${flagId}/resolve/`,
    (input) => ({ note: input.note ?? "" })
  )
}

export function useMarkFalsePositive() {
  return useFlagMutation<{ flagId: string; note?: string }, ChatFlag>(
    (flagId) => `/chatbot/flags/${flagId}/false-positive/`,
    (input) => ({ note: input.note ?? "" })
  )
}

export function useInterventionSuggestions() {
  return useFlagMutation<
    { flagId: string },
    { source: string; suggestions: string[] }
  >((flagId) => `/chatbot/flags/${flagId}/intervention-suggestions/`)
}

export function useAssessmentDraft() {
  return useFlagMutation<
    { flagId: string; topic?: string; count?: number },
    {
      source: string
      topic: string
      drafts: {
        question_text: string
        question_type: string
        options?: string[] | null
        correct_answer?: string | null
      }[]
    }
  >(
    (flagId) => `/chatbot/flags/${flagId}/assessment-draft/`,
    (input) => ({ topic: input.topic ?? "", count: input.count ?? 3 })
  )
}

/* ------------------------------------------------------------------ */
/* Administrator controls                                               */
/* ------------------------------------------------------------------ */

export function useChatbotDashboard() {
  return useQuery({
    queryKey: ["chatbot", "admin", "dashboard"],
    queryFn: async () => {
      const { data } = await apiClient.get<ChatbotDashboard>(
        "/chatbot/admin/dashboard/"
      )
      return data
    },
  })
}

/** Run the acknowledgment timer now. Idempotent server-side. */
export function useEscalateStaleFlags() {
  const queryClient = useQueryClient()
  return useMutation<{ escalated: number; ids: string[] }, Error, void>({
    mutationFn: async () => {
      const { data } = await apiClient.post<{ escalated: number; ids: string[] }>(
        "/chatbot/admin/escalate/",
        {}
      )
      return data
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["chatbot", "admin"] })
      void queryClient.invalidateQueries({ queryKey: ["chatbot", "flags"] })
    },
  })
}

export function useKeywordTerms() {
  return useQuery({
    queryKey: ["chatbot", "keywords"],
    queryFn: async () => {
      const { data } = await apiClient.get<{ results: KeywordTerm[] }>(
        "/chatbot/admin/keywords/"
      )
      return data.results ?? []
    },
  })
}

export function useCreateKeywordTerm() {
  const queryClient = useQueryClient()
  return useMutation<KeywordTerm, Error, Partial<KeywordTerm>>({
    mutationFn: async (payload) => {
      const { data } = await apiClient.post<KeywordTerm>(
        "/chatbot/admin/keywords/",
        payload
      )
      return data
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["chatbot", "keywords"] })
    },
  })
}

export function useUpdateKeywordTerm() {
  const queryClient = useQueryClient()
  return useMutation<
    KeywordTerm,
    Error,
    { id: string; payload: Partial<KeywordTerm> }
  >({
    mutationFn: async ({ id, payload }) => {
      const { data } = await apiClient.patch<KeywordTerm>(
        `/chatbot/admin/keywords/${id}/`,
        payload
      )
      return data
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["chatbot", "keywords"] })
    },
  })
}

export function useDeleteKeywordTerm() {
  const queryClient = useQueryClient()
  return useMutation<void, Error, string>({
    mutationFn: async (id) => {
      await apiClient.delete(`/chatbot/admin/keywords/${id}/`)
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["chatbot", "keywords"] })
    },
  })
}

/** Switch one term on or off without touching its text. */
export function useToggleKeywordTerm() {
  return useUpdateKeywordTerm()
}

/* ------------------------------------------------------------------ */
/* Knowledge corpus                                                     */
/* ------------------------------------------------------------------ */

export function useKnowledgeDocuments() {
  return useQuery({
    queryKey: ["chatbot", "knowledge"],
    queryFn: async () => {
      const { data } = await apiClient.get<{ results: KnowledgeDocument[] }>(
        "/chatbot/admin/knowledge/"
      )
      return data.results ?? []
    },
  })
}

/**
 * Create a document and index its text.
 *
 * The dashboard count is invalidated too: adding a document changes the corpus
 * size the metric shows, and a stale number next to a fresh row reads as a bug.
 */
export function useCreateKnowledgeDocument() {
  const queryClient = useQueryClient()
  return useMutation<KnowledgeDocument, Error, KnowledgeDocumentInput>({
    mutationFn: async (payload) => {
      const { data } = await apiClient.post<KnowledgeDocument>(
        "/chatbot/admin/knowledge/",
        payload
      )
      return data
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["chatbot", "knowledge"] })
      void queryClient.invalidateQueries({ queryKey: ["chatbot", "admin"] })
    },
  })
}

/** Edit a document. Omitting `body` keeps the existing passages. */
export function useUpdateKnowledgeDocument() {
  const queryClient = useQueryClient()
  return useMutation<
    KnowledgeDocument,
    Error,
    { id: string; payload: Partial<KnowledgeDocumentInput> }
  >({
    mutationFn: async ({ id, payload }) => {
      const { data } = await apiClient.patch<KnowledgeDocument>(
        `/chatbot/admin/knowledge/${id}/`,
        payload
      )
      return data
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["chatbot", "knowledge"] })
      void queryClient.invalidateQueries({ queryKey: ["chatbot", "admin"] })
    },
  })
}

export function useDeleteKnowledgeDocument() {
  const queryClient = useQueryClient()
  return useMutation<void, Error, string>({
    mutationFn: async (id) => {
      await apiClient.delete(`/chatbot/admin/knowledge/${id}/`)
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["chatbot", "knowledge"] })
      void queryClient.invalidateQueries({ queryKey: ["chatbot", "admin"] })
    },
  })
}

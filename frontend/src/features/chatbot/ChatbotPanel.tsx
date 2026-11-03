import { MessageCircle, Send } from "lucide-react"
import { useState, type FormEvent } from "react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { ErrorNote } from "@/components/feedback/Feedback"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { useAuth } from "@/features/auth/AuthContext"
import {
  MAX_MESSAGE_LENGTH,
  suggestedPrompts,
  useSendChatMessage,
  type ChatMessage,
  type ChatResponse,
} from "@/features/chatbot/api"
import { normalizeApiError } from "@/lib/error"

/**
 * The AEGIS assistant panel.
 *
 * Deliberately a panel rather than a route: it is a persistent side tool, not a
 * destination, so it opens over the current page instead of navigating away from
 * whatever the user was reading.
 *
 * What the panel does not pretend to be:
 *
 * - **It is not a conversation.** Each message is classified and answered on its
 *   own; there is no memory of earlier turns. The help text says so.
 * - **It is deterministic when no model answers.** `policies.py` classifies
 *   with keyword tables; `service._deterministic_reply` answers from templates
 *   and, for academic/attendance/recommendation intents, from the caller's own
 *   imported records. The server tries a local model first and an offsite one
 *   only as its fallback, with no client change. A reply it cannot classify
 *   returns the "rephrase" fallback rather than a guess.
 * - **It does not persist the transcript.** The transcript is component state.
 *   Closing the panel discards it. A distress signal does write a Guidance
 *   risk alert and notification, because that is the point of the escalation.
 */
/**
 * A message id that is stable and unique within the transcript.
 *
 * A module counter rather than `Date.now()`: the id must not depend on wall
 * clock time, and two messages sent inside the same millisecond would collide
 * on a timestamp.
 */
let messageCounter = 0
function nextMessageId(prefix: "u" | "a"): string {
  messageCounter += 1
  return `${prefix}-${messageCounter}`
}

export function ChatbotPanel({
  open,
  onClose,
}: {
  open: boolean
  onClose: () => void
}) {
  const { user } = useAuth()
  const send = useSendChatMessage()

  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [draft, setDraft] = useState("")

  if (!open || !user) return null

  const prompts = suggestedPrompts(user.role)
  const blank = draft.trim().length === 0
  const tooLong = draft.trim().length > MAX_MESSAGE_LENGTH

  async function submit(text: string) {
    const message = text.trim()
    if (message.length === 0 || tooLong) return

    const userMessage: ChatMessage = {
      id: nextMessageId("u"),
      role: "user",
      text: message,
    }
    setMessages((current) => [...current, userMessage])
    setDraft("")

    try {
      const response = await send.mutateAsync({ message })
      setMessages((current) => [
        ...current,
        {
          id: nextMessageId("a"),
          role: "assistant",
          text: response.reply,
          response,
        },
      ])
    } catch {
      // Surfaced from `send.isError` below. The user's message stays in the
      // transcript so they can see what was not answered.
    }
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    void submit(draft)
  }

  return (
    <Card className="flex h-full flex-col" data-chatbot-panel="open">
      <CardHeader>
        <div className="flex items-start justify-between gap-2">
          <div className="space-y-1">
            <CardTitle className="flex items-center gap-2">
              <MessageCircle className="size-4" aria-hidden="true" />
              AEGIS Assistant
            </CardTitle>
            <CardDescription>
              Answers about your grades, academic status, attendance and
              learning resources.
            </CardDescription>
          </div>
          <Button type="button" size="xs" variant="ghost" onClick={onClose}>
            Close
          </Button>
        </div>
      </CardHeader>

      <CardContent className="flex min-h-0 flex-1 flex-col gap-3">
        <div
          className="min-h-0 flex-1 space-y-3 overflow-y-auto"
          role="log"
          aria-live="polite"
          aria-label="Assistant conversation"
        >
          {messages.length === 0 ? (
            <div className="space-y-2">
              <p className="text-sm text-muted-foreground">Try one of these:</p>
              <ul className="space-y-1">
                {prompts.map((prompt) => (
                  <li key={prompt}>
                    <Button
                      type="button"
                      size="xs"
                      variant="outline"
                      onClick={() => void submit(prompt)}
                    >
                      {prompt}
                    </Button>
                  </li>
                ))}
              </ul>
            </div>
          ) : (
            messages.map((message) => (
              <ChatBubble key={message.id} message={message} />
            ))
          )}
        </div>

        {send.isError ? (
          <ErrorNote message={normalizeApiError(send.error).message} />
        ) : null}

        <form onSubmit={handleSubmit} className="space-y-1.5">
          <Label htmlFor="chatbot-message">Message</Label>
          <Textarea
            id="chatbot-message"
            rows={2}
            value={draft}
            maxLength={MAX_MESSAGE_LENGTH}
            aria-invalid={tooLong || undefined}
            aria-describedby={tooLong ? "chatbot-message-error" : undefined}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event) => {
              // Enter sends; Shift+Enter is a newline. A textarea alone would
              // make every reply require finding the send button.
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault()
                void submit(draft)
              }
            }}
          />
          {tooLong ? (
            <p
              id="chatbot-message-error"
              role="alert"
              className="text-xs text-destructive"
            >
              Message is too long.
            </p>
          ) : null}
          <Button
            type="submit"
            size="sm"
            disabled={blank || tooLong || send.isPending}
          >
            <Send className="size-4" aria-hidden="true" />
            {send.isPending ? "Sending…" : "Send"}
          </Button>
        </form>
      </CardContent>
    </Card>
  )
}

function ChatBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user"

  return (
    <div
      className={isUser ? "flex justify-end" : "flex justify-start"}
      data-chat-role={message.role}
    >
      <div
        className={`max-w-[85%] space-y-1 rounded-md px-3 py-2 text-sm ${
          isUser ? "bg-primary text-primary-foreground" : "bg-muted"
        }`}
      >
        <p>{message.text}</p>
        {message.response ? (
          <ResponseDetail response={message.response} />
        ) : null}
      </div>
    </div>
  )
}

/**
 * The structured payload the assistant returned with its reply.
 *
 * Rendered because the numbers are the point of the question — a student asking
 * "what is my average?" wants the average, not just "here is your information".
 */
const ACADEMIC_STATUS_LABELS: Record<string, string> = {
  on_track: "On track",
  at_risk: "At risk",
  insufficient_data: "Not enough data",
}

function ResponseDetail({ response }: { response: ChatResponse }) {
  const grades = response.data.grade_summary
  const status = response.data.academic_status
  const recommendations = response.data.recommendations?.recommendations ?? []
  const attendance = response.data.attendance_summary
  const resources = response.data.resources ?? []

  if (
    !grades &&
    !status &&
    recommendations.length === 0 &&
    !attendance &&
    resources.length === 0 &&
    !response.escalated
  ) {
    return null
  }

  return (
    <div className="space-y-1 border-t border-border/40 pt-1 text-xs">
      {grades ? (
        <p>
          {/* An absent average renders as a dash, never a 0. */}
          Average:{" "}
          {typeof grades.average === "number"
            ? `${grades.average.toFixed(2)}%`
            : "—"}
          {typeof grades.subject_count === "number"
            ? ` · ${grades.subject_count} subject(s)`
            : ""}
          {grades.data_status === "pending_finalization"
            ? " · provisional"
            : ""}
        </p>
      ) : null}

      {status ? (
        <p>
          Status:{" "}
          {ACADEMIC_STATUS_LABELS[status.status ?? ""] ?? "Not enough data"}
          {typeof status.passing_grade === "number"
            ? ` · passing ${status.passing_grade}`
            : ""}
        </p>
      ) : null}

      {/*
        Every weak subject, in one line. A prose answer may name only some of
        them, so the complete list is rendered from the data instead.
      */}
      {status?.weak_subjects && status.weak_subjects.length > 0 ? (
        <p>
          Needs support:{" "}
          {status.weak_subjects
            .map((subject) => `${subject.subject} (${subject.score.toFixed(2)}%)`)
            .join(", ")}
        </p>
      ) : null}

      {recommendations.length > 0 ? (
        <ul className="space-y-0.5">
          {recommendations.map((recommendation, index) => (
            <li key={recommendation.learning_item_id ?? `${index}`}>
              {recommendation.title ?? "Recommended support"}
            </li>
          ))}
        </ul>
      ) : null}

      {attendance ? (
        <p>
          Present: {attendance.present_count ?? "—"} · Late:{" "}
          {attendance.late_count ?? "—"} · Absent:{" "}
          {attendance.absent_count ?? "—"}
        </p>
      ) : null}

      {resources.length > 0 ? (
        <ul className="space-y-0.5">
          {resources.map((resource, index) => (
            <li key={resource.id ?? `${resource.title}-${index}`}>
              {resource.title ?? "Untitled resource"}
            </li>
          ))}
        </ul>
      ) : null}

      {/*
        An escalation means a real Guidance notification was dispatched
        (FR-031). Saying so is important: the reply text is a template, and only
        this fact tells the user something was actually done.
      */}
      {response.escalated ? (
        <Badge variant="destructive">Notified Guidance</Badge>
      ) : null}
    </div>
  )
}

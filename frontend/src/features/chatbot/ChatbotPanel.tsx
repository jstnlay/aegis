import "./chatbot-panel.css"
import { ArrowUp, Bot, Info, ShieldCheck, Sparkles, X } from "lucide-react"
import { useEffect, useRef, useState, type FormEvent } from "react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
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
 * - **It is deterministic, not an LLM.** `policies.py` classifies with keyword
 *   tables and `service._deterministic_reply` answers from templates. A reply it
 *   cannot classify returns the "rephrase" fallback rather than a guess.
 * - **It does not persist anything.** The transcript is component state. Closing
 *   the panel discards it, and nothing is written to the database.
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

  const logRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    if (open) inputRef.current?.focus()
  }, [open])

  useEffect(() => {
    const log = logRef.current
    if (log) log.scrollTop = log.scrollHeight
  }, [messages, send.isPending])

  if (!open || !user) return null

  const prompts = suggestedPrompts(user.role)
  const blank = draft.trim().length === 0
  const tooLong = draft.trim().length > MAX_MESSAGE_LENGTH

  async function submit(text: string) {
    const message = text.trim()
    if (
      message.length === 0 ||
      message.length > MAX_MESSAGE_LENGTH ||
      send.isPending
    )
      return

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
    <section
      className="aegis-chat"
      data-chatbot-panel="open"
      aria-label="AEGIS Assistant"
      onKeyDown={(event) => {
        if (event.key === "Escape") onClose()
      }}
    >
      <header className="aegis-chat-header">
        <div className="aegis-chat-brand">
          <span className="aegis-chat-mark">
            <Bot aria-hidden="true" />
          </span>
          <div>
            <h2>AEGIS Assistant</h2>
            <p>
              <span className="aegis-chat-status" /> Your school help desk
            </p>
          </div>
        </div>
        <button
          className="aegis-chat-close"
          type="button"
          aria-label="Close assistant"
          onClick={onClose}
        >
          <X aria-hidden="true" />
        </button>
      </header>

      <div
        className="aegis-chat-body"
        ref={logRef}
        role="log"
        aria-live="polite"
        aria-label="Assistant conversation"
      >
        <div className="aegis-chat-transcript">
          <p className="aegis-chat-session-label">
            <span /> School assistant <span />
          </p>
          <ChatBubble
            message={{
              id: "welcome",
              role: "assistant",
              text: `Hi${user.first_name?.trim() ? `, ${user.first_name.trim()}` : ""}! ${user.role === "student" || user.role === "parent" ? "I can help with grades, attendance, and learning resources. What would you like to check?" : "Need a hand finding something in AEGIS? Ask me about the tools available to you."}`,
            }}
          />
          {messages.length === 0 ? (
            <div className="aegis-chat-quick-replies">
              <p>Choose a question to get started</p>
              {prompts.map((prompt) => (
                <button
                  key={prompt}
                  type="button"
                  disabled={send.isPending}
                  onClick={() => void submit(prompt)}
                >
                  {prompt}
                </button>
              ))}
            </div>
          ) : null}
          {messages.map((message) => (
            <ChatBubble key={message.id} message={message} />
          ))}
          {send.isPending ? (
            <div className="aegis-chat-thinking" role="status">
              <Bot aria-hidden="true" />
              <span>Finding your answer</span>
              <span className="aegis-chat-dots" aria-hidden="true">
                <i />
                <i />
                <i />
              </span>
            </div>
          ) : null}
        </div>
      </div>

      <footer className="aegis-chat-footer">
        {send.isError ? (
          <ErrorNote message={normalizeApiError(send.error).message} />
        ) : null}
        <form onSubmit={handleSubmit} className="aegis-chat-composer">
          <Label htmlFor="chatbot-message" className="sr-only">
            Message
          </Label>
          <Textarea
            ref={inputRef}
            id="chatbot-message"
            rows={2}
            value={draft}
            maxLength={MAX_MESSAGE_LENGTH}
            placeholder="Ask AEGIS anything about school..."
            aria-invalid={tooLong || undefined}
            aria-describedby={
              tooLong ? "chatbot-message-error" : "chatbot-message-hint"
            }
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event) => {
              if (
                event.key === "Enter" &&
                !event.shiftKey &&
                !event.nativeEvent.isComposing
              ) {
                event.preventDefault()
                void submit(draft)
              }
            }}
          />
          <div className="aegis-chat-composer-bottom">
            <span className="aegis-chat-composer-mode">
              <Sparkles aria-hidden="true" /> School assistant
            </span>
            <span id="chatbot-message-hint" className="sr-only">
              Enter to send. Shift + Enter for a new line.
            </span>
            <Button
              type="submit"
              className="aegis-chat-send"
              disabled={blank || tooLong || send.isPending}
              aria-label={send.isPending ? "Sending message" : "Send message"}
            >
              <ArrowUp aria-hidden="true" />
            </Button>
          </div>
          {tooLong ? (
            <p id="chatbot-message-error" role="alert">
              Message is too long.
            </p>
          ) : null}
        </form>
        <div className="aegis-chat-footer-meta">
          <details className="aegis-chat-info">
            <summary>
              <Info aria-hidden="true" /> About this assistant
            </summary>
            <p>
              This assistant answers supported questions individually and does
              not remember earlier messages. This chat clears when you close the
              panel. For urgent concerns, contact Guidance directly.
            </p>
          </details>
          <span className="aegis-chat-footnote">
            <ShieldCheck aria-hidden="true" /> Here for your school day
          </span>
        </div>
      </footer>
    </section>
  )
}

function ChatBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user"

  return (
    <div
      className={`aegis-chat-message ${isUser ? "aegis-chat-message--user" : ""}`}
      data-chat-role={message.role}
    >
      {!isUser ? (
        <span className="aegis-chat-message-avatar">
          <Bot aria-hidden="true" />
        </span>
      ) : null}
      <div className="aegis-chat-message-content">
        <span className="aegis-chat-message-label">
          {isUser ? "You" : "AEGIS Assistant"}
        </span>
        <div className="aegis-chat-bubble">
          <p>{message.text}</p>
          {message.response ? (
            <ResponseDetail response={message.response} />
          ) : null}
        </div>
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
function ResponseDetail({ response }: { response: ChatResponse }) {
  const grades = response.data.grade_summary
  const attendance = response.data.attendance_summary
  const resources = response.data.resources ?? []

  if (!grades && !attendance && resources.length === 0 && !response.escalated) {
    return null
  }

  return (
    <div className="aegis-chat-response space-y-2 border-t border-border/40 pt-3 text-xs">
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
        </p>
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

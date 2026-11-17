import "./chatbot-panel.css"
import {
  ArrowLeft,
  ArrowUp,
  Bot,
  History,
  Info,
  Plus,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  Trash2,
  X,
} from "lucide-react"
import { useEffect, useMemo, useRef, useState, type FormEvent } from "react"

import { useQueryClient } from "@tanstack/react-query"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { ErrorNote } from "@/components/feedback/Feedback"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { useAuth } from "@/features/auth/AuthContext"
import {
  MAX_MESSAGE_LENGTH,
  suggestedPrompts,
  useAcceptNotice,
  useChatNotice,
  useChatThread,
  useChatThreads,
  useDeleteAllChatHistory,
  useDeleteChatThread,
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
 * What the panel does and does not pretend to be:
 *
 * - **It is deterministic first.** `policies.py` classifies with keyword tables
 *   and `service._deterministic_reply` answers from templates. Gemini may
 *   rewrite a reply for a message that is not sensitive, and may raise the
 *   severity of one that is, but it never decides intent or routing.
 * - **Chats are saved.** Every turn is written to `ChatMessage` under a
 *   `ChatThread`, so History can reopen a conversation and delete it. A safety
 *   flag is not deleted with the chat; Guidance still sees it.
 * - **It stores what you send.** A message that trips the screening is written
 *   to a flag that Guidance sees. That is stated in the panel, because a
 *   student who believes nothing is stored cannot give informed consent.
 * - **A student must accept the notice first.** Until the notice for the
 *   current version is accepted, the panel shows the notice and refuses to
 *   send.
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

function threadDate(value: string): string {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ""
  return date.toLocaleDateString(undefined, { month: "short", day: "numeric" })
}

/**
 * Slash commands are shorthand for a record question the pipeline already
 * understands. They give an explicit, typo-proof way to reach a grade or an
 * attendance count; ordinary questions keep working unchanged. The command is
 * expanded before it is sent, so the transcript shows the question that was
 * actually answered.
 */
const COMMANDS: Record<string, (argument: string) => string> = {
  grades: (argument) =>
    argument ? `What is my grade in ${argument}?` : "What is my grade?",
  attendance: () => "What is my attendance?",
  resources: (argument) =>
    argument
      ? `Do you have study materials for ${argument}?`
      : "Where can I find study materials?",
  help: () => "What can you do?",
}

function expandCommand(text: string): string | null {
  const [name = "", ...rest] = text.slice(1).split(/\s+/)
  const build = COMMANDS[name.toLowerCase()]
  return build ? build(rest.join(" ").trim()) : null
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
  const noticeQuery = useChatNotice(open)
  const acceptNotice = useAcceptNotice()
  const threadsQuery = useChatThreads(open)
  const deleteThread = useDeleteChatThread()
  const deleteAll = useDeleteAllChatHistory()
  const queryClient = useQueryClient()

  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [draft, setDraft] = useState("")
  // `undefined` means "not chosen yet": open the newest thread. `null` is an
  // explicit New chat, which must not auto-select the newest one again.
  const [activeThreadId, setActiveThreadId] = useState<
    string | null | undefined
  >(undefined)
  const [historyOpen, setHistoryOpen] = useState(false)
  const [pendingDelete, setPendingDelete] = useState<string | null>(null)
  const [confirmDeleteAll, setConfirmDeleteAll] = useState(false)

  const threadQuery = useChatThread(
    activeThreadId ?? null,
    open && Boolean(activeThreadId)
  )

  const logRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    if (open) inputRef.current?.focus()
  }, [open])

  useEffect(() => {
    const log = logRef.current
    if (log) log.scrollTop = log.scrollHeight
  }, [messages, send.isPending, threadQuery.data])

  // Open the most recent conversation once the list arrives. A rejected list
  // leaves the panel on a new chat rather than blocking it.
  useEffect(() => {
    if (!open || activeThreadId !== undefined) return
    if (threadsQuery.data === undefined) return
    setActiveThreadId(threadsQuery.data[0]?.id ?? null)
  }, [open, activeThreadId, threadsQuery.data])

  /*
   * The transcript is the active thread's saved turns plus the turns sent in
   * this sitting. Deriving it beats copying the thread into state: the copy
   * would have to be invalidated whenever the query resolves, and a stale copy
   * would show a student a transcript that no longer matches the record.
   *
   * The local turn carries the server's `chat_message_id`, so when the thread
   * refetch brings the same turn back the two collapse into one entry instead
   * of appearing twice.
   */
  const transcript = useMemo(() => {
    const byId = new Map<string, ChatMessage>()
    for (const entry of threadQuery.data?.messages ?? []) {
      byId.set(`h-${entry.id}-u`, {
        id: `h-${entry.id}-u`,
        role: "user",
        text: entry.message,
      })
      if (entry.reply) {
        byId.set(`h-${entry.id}-a`, {
          id: `h-${entry.id}-a`,
          role: "assistant",
          text: entry.reply,
        })
      }
    }
    for (const message of messages) {
      byId.set(message.id, message)
    }
    return [...byId.values()]
  }, [threadQuery.data, messages])

  if (!open || !user) return null

  const prompts = suggestedPrompts(user.role)
  const blank = draft.trim().length === 0
  const tooLong = draft.trim().length > MAX_MESSAGE_LENGTH

  const notice = noticeQuery.data
  // Only a student is gated: the notice is about a student's own messages.
  const mustAccept =
    user.role === "student" && notice !== undefined && !notice.accepted
  const threads = threadsQuery.data ?? []

  function startNewChat() {
    setActiveThreadId(null)
    setMessages([])
    setDraft("")
    setHistoryOpen(false)
    setPendingDelete(null)
    setConfirmDeleteAll(false)
  }

  function openThread(threadId: string) {
    setActiveThreadId(threadId)
    setMessages([])
    setHistoryOpen(false)
    setPendingDelete(null)
  }

  function removeThread(threadId: string) {
    deleteThread.mutate(threadId, {
      onSuccess: () => {
        setPendingDelete(null)
        if (activeThreadId === threadId) {
          setActiveThreadId(null)
          setMessages([])
        }
      },
    })
  }

  function removeAllThreads() {
    deleteAll.mutate(undefined, {
      onSuccess: () => {
        setConfirmDeleteAll(false)
        setActiveThreadId(null)
        setMessages([])
        setHistoryOpen(false)
      },
    })
  }

  async function submit(text: string) {
    const raw = text.trim()
    if (
      raw.length === 0 ||
      raw.length > MAX_MESSAGE_LENGTH ||
      send.isPending ||
      mustAccept
    )
      return

    let message = raw
    if (raw.startsWith("/")) {
      const expanded = expandCommand(raw)
      if (expanded === null) {
        // A typo is answered here, not sent to the model as prose.
        setMessages((current) => [
          ...current,
          { id: nextMessageId("u"), role: "user", text: raw },
          {
            id: nextMessageId("a"),
            role: "assistant",
            text: "Unknown command. Try /grades, /attendance, /resources, or /help.",
          },
        ])
        setDraft("")
        return
      }
      message = expanded
    }

    const userMessage: ChatMessage = {
      id: nextMessageId("u"),
      role: "user",
      text: message,
    }
    setMessages((current) => [...current, userMessage])
    setDraft("")

    try {
      const response = await send.mutateAsync({
        message,
        threadId: activeThreadId ?? null,
      })
      // The server's id for the turn, so the local copy and the saved turn
      // collapse into one entry when the thread refetch brings it back.
      const turnId = response.data.chat_message_id ?? nextMessageId("u")
      setMessages((current) => [
        ...current.map((entry) =>
          entry.id === userMessage.id ? { ...entry, id: `h-${turnId}-u` } : entry,
        ),
        {
          id: `h-${turnId}-a`,
          role: "assistant",
          text: response.reply,
          response,
        },
      ])

      const createdThreadId = response.data.thread_id
      if (!activeThreadId && createdThreadId) {
        setActiveThreadId(createdThreadId)
      }
      void queryClient.invalidateQueries({ queryKey: ["chatbot", "threads"] })
      if (createdThreadId) {
        void queryClient.invalidateQueries({
          queryKey: ["chatbot", "thread", createdThreadId],
        })
      }
    } catch (error) {
      // 428 means the notice was not accepted, or the version changed since
      // the panel loaded it. Refreshing the notice brings the gate back.
      if (normalizeApiError(error).status === 428) {
        void queryClient.invalidateQueries({ queryKey: ["chatbot", "notice"] })
      }
      // Anything else is surfaced from `send.isError` below. The user's message
      // stays in the transcript so they can see what was not answered.
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
        <div className="aegis-chat-header-actions">
          <button
            className="aegis-chat-header-button"
            type="button"
            aria-label="New chat"
            title="New chat"
            onClick={startNewChat}
          >
            <Plus aria-hidden="true" />
          </button>
          <button
            className="aegis-chat-header-button"
            type="button"
            aria-label="Chat history"
            title="Chat history"
            aria-expanded={historyOpen}
            onClick={() => {
              setHistoryOpen((current) => !current)
              setPendingDelete(null)
              setConfirmDeleteAll(false)
            }}
          >
            <History aria-hidden="true" />
          </button>
          <button
            className="aegis-chat-close"
            type="button"
            aria-label="Close assistant"
            onClick={onClose}
          >
            <X aria-hidden="true" />
          </button>
        </div>
      </header>

      <div
        className="aegis-chat-body"
        ref={logRef}
        role={historyOpen ? undefined : "log"}
        aria-live={historyOpen ? undefined : "polite"}
        aria-label={historyOpen ? "Chat history" : "Assistant conversation"}
      >
        {historyOpen ? (
          <div className="aegis-chat-history">
            <div className="aegis-chat-history-head">
              <button
                type="button"
                className="aegis-chat-history-back"
                onClick={() => setHistoryOpen(false)}
              >
                <ArrowLeft aria-hidden="true" /> Back
              </button>
              <span>Chat history</span>
            </div>

            {threadsQuery.isError ? (
              <ErrorNote
                message={normalizeApiError(threadsQuery.error).message}
              />
            ) : null}
            {threadsQuery.isLoading ? (
              <p className="aegis-chat-history-note">Loading chats…</p>
            ) : null}
            {!threadsQuery.isLoading && threads.length === 0 ? (
              <p className="aegis-chat-history-note">
                No saved chats yet. Start a conversation and it will appear
                here.
              </p>
            ) : null}

            <ul className="aegis-chat-history-list">
              {threads.map((thread) => (
                <li className="aegis-chat-history-item" key={thread.id}>
                  <button
                    type="button"
                    className="aegis-chat-history-open"
                    onClick={() => openThread(thread.id)}
                  >
                    <span className="aegis-chat-history-title">
                      {thread.title || "Untitled chat"}
                    </span>
                    <span className="aegis-chat-history-meta">
                      {threadDate(thread.updated_at)} ·{" "}
                      {thread.message_count} message
                      {thread.message_count === 1 ? "" : "s"}
                    </span>
                  </button>
                  {pendingDelete === thread.id ? (
                    <div
                      className="aegis-chat-history-confirm"
                      role="group"
                      aria-label={`Delete ${thread.title || "Untitled chat"}`}
                    >
                      <p>
                        Delete this chat? A chat that raised a safety concern
                        stays with Guidance.
                      </p>
                      <div>
                        <button
                          type="button"
                          disabled={deleteThread.isPending}
                          onClick={() => removeThread(thread.id)}
                        >
                          {deleteThread.isPending ? "Deleting…" : "Delete"}
                        </button>
                        <button
                          type="button"
                          onClick={() => setPendingDelete(null)}
                        >
                          Cancel
                        </button>
                      </div>
                    </div>
                  ) : (
                    <button
                      type="button"
                      className="aegis-chat-history-delete"
                      aria-label={`Delete chat: ${thread.title || "Untitled chat"}`}
                      onClick={() => setPendingDelete(thread.id)}
                    >
                      <Trash2 aria-hidden="true" />
                    </button>
                  )}
                </li>
              ))}
            </ul>

            {threads.length > 0 ? (
              <div className="aegis-chat-history-clear">
                {confirmDeleteAll ? (
                  <>
                    <p>
                      Delete all saved chats? Safety-related messages stay with
                      Guidance.
                    </p>
                    <div>
                      <button
                        type="button"
                        disabled={deleteAll.isPending}
                        onClick={removeAllThreads}
                      >
                        {deleteAll.isPending ? "Deleting…" : "Delete all"}
                      </button>
                      <button
                        type="button"
                        onClick={() => setConfirmDeleteAll(false)}
                      >
                        Cancel
                      </button>
                    </div>
                  </>
                ) : (
                  <button
                    type="button"
                    onClick={() => setConfirmDeleteAll(true)}
                  >
                    Delete all chats
                  </button>
                )}
              </div>
            ) : null}
          </div>
        ) : (
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
            {mustAccept ? (
              <div
                className="aegis-chat-quick-replies"
                role="group"
                aria-label="Student notice"
              >
                <p>Student notice (version {notice?.version ?? ""})</p>
                <p>{notice?.text}</p>
                <button
                  type="button"
                  disabled={acceptNotice.isPending}
                  onClick={() => void acceptNotice.mutate({})}
                >
                  {acceptNotice.isPending
                    ? "Accepting…"
                    : "I accept this notice, and I understand my messages are stored and screened."}
                </button>
                {acceptNotice.isError ? (
                  <p>{normalizeApiError(acceptNotice.error).message}</p>
                ) : null}
              </div>
            ) : null}
            {transcript.length === 0 && !mustAccept ? (
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
            {threadQuery.isError ? (
              <ErrorNote
                message={normalizeApiError(threadQuery.error).message}
              />
            ) : null}
            {transcript.map((message) => (
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
        )}
      </div>

      <footer className="aegis-chat-footer">
        {send.isError ? (
          <ErrorNote message={normalizeApiError(send.error).message} />
        ) : null}
        {!historyOpen ? (
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
              placeholder="Ask anything — or use /grades, /attendance, /resources"
              disabled={mustAccept}
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
                disabled={blank || tooLong || send.isPending || mustAccept}
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
        ) : null}
        <div className="aegis-chat-footer-meta">
          <details className="aegis-chat-info">
            <summary>
              <Info aria-hidden="true" /> About this assistant
            </summary>
            <p>
              Chats are saved in History. Delete a chat at any time; a chat that
              raised a safety concern stays with Guidance. Everything you type
              here is screened by an automated keyword check. General questions
              and recent messages in the chat may be sent to Gemini to write the
              answer; your name and school records are not. For urgent concerns,
              contact Guidance directly.
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
  const sources = response.data.knowledge ?? []
  const flag = response.data.flag

  if (
    !grades &&
    !attendance &&
    resources.length === 0 &&
    sources.length === 0 &&
    !response.escalated &&
    !flag
  ) {
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
          Present: {attendance.present_days ?? "—"} · Late:{" "}
          {attendance.late_days ?? "—"} · Absent: {attendance.absent_days ?? "—"}
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
        Where a grounded answer came from. The reply text already says the
        source, so this is not a second answer: it is the link that lets a
        student read the rule themselves instead of taking the assistant's
        word for it.
      */}
      {sources.length > 0 ? (
        <div className="aegis-chat-sources space-y-0.5">
          <p className="text-muted-foreground">Answered from:</p>
          <ul className="space-y-0.5">
            {sources.map((source, index) => (
              <li key={source.chunk_id ?? `${source.title}-${index}`}>
                {source.source_url ? (
                  <a
                    href={source.source_url}
                    target="_blank"
                    rel="noreferrer"
                    className="underline"
                  >
                    {source.source_label || source.title || "School document"}
                  </a>
                ) : (
                  source.source_label || source.title || "School document"
                )}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {/*
        A flag means a guidance counselor has been told. Saying so is
        important: the reply text is a template, and only this fact tells the
        user that something was actually done.
      */}
      {flag ? (
        <p className="flex items-center gap-1 font-medium">
          <ShieldAlert aria-hidden="true" />
          A guidance counselor has been notified.
        </p>
      ) : response.escalated ? (
        <Badge variant="destructive">Notified Guidance</Badge>
      ) : null}
    </div>
  )
}

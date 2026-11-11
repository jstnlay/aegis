import { useLayoutEffect, useRef, useState } from "react"
import { createPortal } from "react-dom"
import {
  ArrowUpRight,
  BellRing,
  ShieldAlert,
  TriangleAlert,
  X,
} from "lucide-react"
import { useAuth } from "@/features/auth/AuthContext"
import { NotificationDetails } from "./NotificationDetails"
import { normalizeApiError } from "@/lib/error"
import {
  sortNotifications,
  NOTIFICATION_TYPE_LABELS,
  useMarkNotificationRead,
  useNotifications,
  type Notification,
} from "./api"
import "./notification-previews.css"

/** Dismissing a preview never deletes or marks the inbox notification read. */
export function NotificationPreviews() {
  const { user } = useAuth()
  return user ? (
    <UserNotificationPreviews key={user.id} userId={user.id} />
  ) : null
}

function UserNotificationPreviews({ userId }: { userId: string }) {
  const storageKey = `aegis-notification-previews:${userId}`
  const [dismissed, setDismissed] = useState<Set<string>>(() => {
    try {
      const saved: unknown = JSON.parse(
        sessionStorage.getItem(storageKey) ?? "[]"
      )
      return new Set(
        Array.isArray(saved)
          ? saved.filter((id): id is string => typeof id === "string")
          : []
      )
    } catch {
      return new Set()
    }
  })
  const inbox = useNotifications({}, 15_000)
  const markRead = useMarkNotificationRead()
  const [selected, setSelected] = useState<Notification | null>(null)
  const [readError, setReadError] = useState<string>()
  const stackRef = useRef<HTMLElement>(null)
  const queue = sortNotifications(inbox.data ?? []).filter(
    (item) => !item.is_read && !dismissed.has(item.id)
  )

  const hasPreviews = queue.length > 0
  useLayoutEffect(() => {
    if (!hasPreviews) return
    const bell = document.querySelector(".app-notification-trigger")
    if (!bell) return
    function position() {
      const bounds = bell!.getBoundingClientRect()
      stackRef.current?.style.setProperty(
        "--preview-top",
        `${Math.max(12, bounds.bottom + 6)}px`
      )
      stackRef.current?.style.setProperty(
        "--preview-right",
        `${Math.max(12, window.innerWidth - bounds.right)}px`
      )
    }
    position()
    const observer = new ResizeObserver(position)
    observer.observe(bell)
    window.addEventListener("resize", position)
    window.addEventListener("scroll", position, { passive: true })
    return () => {
      observer.disconnect()
      window.removeEventListener("resize", position)
      window.removeEventListener("scroll", position)
    }
  }, [hasPreviews])

  function dismissMany(ids: string[]) {
    const next = new Set([...dismissed, ...ids])
    setDismissed(next)
    try {
      sessionStorage.setItem(storageKey, JSON.stringify([...next]))
    } catch {
      // Storage can be disabled; previews still work for the current visit.
    }
  }
  function dismiss(id: string) {
    dismissMany([id])
  }

  function view(item: Notification) {
    dismiss(item.id)
    setReadError(undefined)
    setSelected(item)
    markRead.mutate(item.id, {
      onSuccess: () =>
        setSelected((current) =>
          current?.id === item.id ? { ...current, is_read: true } : current
        ),
      onError: (error) => setReadError(normalizeApiError(error).message),
    })
  }

  return (
    <>
      {queue.length > 0
        ? createPortal(
            <aside
              ref={stackRef}
              className="notification-previews"
              aria-label="New notification previews"
            >
              <div className="notification-preview-toolbar">
                <div
                  className="notification-previews-heading"
                  role="status"
                  aria-live="polite"
                >
                  <BellRing aria-hidden="true" />
                  <span>New updates</span>
                  {queue.length > 2 ? (
                    <span className="notification-previews-count">
                      +{queue.length - 2} queued
                    </span>
                  ) : null}
                </div>
                <button
                  type="button"
                  className="notification-preview-clear"
                  onClick={() => dismissMany(queue.map((item) => item.id))}
                >
                  Clear all <X aria-hidden="true" />
                </button>
              </div>
              {queue.slice(0, 2).map((item) => (
                <article
                  key={item.id}
                  className="notification-preview"
                  data-tone={
                    item.notification_type === "BEHAVIORAL_INCIDENT"
                      ? "danger"
                      : item.notification_type === "BEHAVIORAL_WARNING" ||
                          item.notification_type === "ATTENDANCE_THRESHOLD"
                        ? "warning"
                        : "school"
                  }
                >
                  <span
                    className="notification-preview-emblem"
                    aria-hidden="true"
                  >
                    {item.notification_type === "BEHAVIORAL_INCIDENT" ? (
                      <ShieldAlert />
                    ) : item.notification_type === "BEHAVIORAL_WARNING" ||
                      item.notification_type === "ATTENDANCE_THRESHOLD" ? (
                      <TriangleAlert />
                    ) : (
                      <BellRing />
                    )}
                  </span>
                  <button
                    type="button"
                    className="notification-preview-close"
                    aria-label={`Dismiss preview: ${item.title}`}
                    onClick={() => dismiss(item.id)}
                  >
                    <X aria-hidden="true" />
                  </button>
                  <div className="notification-preview-copy">
                    <div className="notification-preview-eyebrow">
                      <span>
                        {NOTIFICATION_TYPE_LABELS[item.notification_type] ??
                          "School update"}
                      </span>
                    </div>
                    <h2>{item.title}</h2>
                    <p>{item.message}</p>
                    <time
                      className="notification-preview-time"
                      dateTime={item.created_at}
                    >
                      {new Date(item.created_at).toLocaleTimeString(undefined, {
                        hour: "numeric",
                        minute: "2-digit",
                      })}
                    </time>
                  </div>
                  <button
                    type="button"
                    className="notification-preview-view"
                    aria-label={`View notification: ${item.title}`}
                    onClick={() => view(item)}
                  >
                    View <ArrowUpRight aria-hidden="true" />
                  </button>
                </article>
              ))}
            </aside>,
            document.body
          )
        : null}
      <NotificationDetails
        notification={selected}
        onClose={() => {
          setSelected(null)
          setReadError(undefined)
        }}
        readError={readError}
      />
    </>
  )
}

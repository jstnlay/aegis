import { useState } from "react"
import { BellRing } from "lucide-react"
import { useQuery } from "@tanstack/react-query"
import { Link } from "react-router-dom"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog"
import { useAuth } from "@/features/auth/AuthContext"
import {
  NOTIFICATION_TYPE_LABELS,
  resolveNotificationHref,
  useDeleteNotification,
  type Notification,
} from "./api"
import { normalizeApiError } from "@/lib/error"
import { apiClient } from "@/lib/api"
import {
  BEHAVIORAL_NOTE_TYPE_LABELS,
  type BehavioralNote,
} from "@/features/guidance/api"

export function NotificationDetails({
  notification,
  onClose,
  readError,
}: {
  notification: Notification | null
  onClose: () => void
  readError?: string
}) {
  const { user } = useAuth()
  const deletion = useDeleteNotification()
  const [confirming, setConfirming] = useState(false)
  const noteId = notification?.link?.match(
    /^\/guidance\/behavioral-notes\/([a-zA-Z0-9-]+)\/?$/
  )?.[1]
  const noteQuery = useQuery({
    queryKey: ["notifications", "behavioral-note", user?.id, noteId],
    enabled: Boolean(noteId && user?.role === "guidance"),
    queryFn: async ({ signal }) => {
      const { data } = await apiClient.get<BehavioralNote>(
        `/guidance/behavioral-notes/${noteId}/`,
        { signal }
      )
      return data
    },
  })
  const note = user?.role === "guidance" && noteId ? noteQuery.data : undefined
  const href = note
    ? `/app/students/${encodeURIComponent(note.student)}`
    : notification
      ? resolveNotificationHref(notification.link, user?.role ?? "student")
      : null
  return (
    <Dialog
      open={Boolean(notification)}
      onOpenChange={(open) => {
        if (!open) {
          setConfirming(false)
          onClose()
        }
      }}
    >
      <DialogContent className="notification-details-dialog max-h-[85svh] overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <span className="notification-details-emblem" aria-hidden="true">
            <BellRing />
          </span>
          <DialogTitle className="pr-8 leading-snug">
            {notification?.title}
          </DialogTitle>
          <DialogDescription>
            {notification
              ? NOTIFICATION_TYPE_LABELS[notification.notification_type]
              : "Notification"}
          </DialogDescription>
        </DialogHeader>
        {notification ? (
          <>
            <div className="notification-details-meta flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
              <Badge variant="outline">
                {notification.is_read ? "Read" : "Unread"}
              </Badge>
              <time dateTime={notification.created_at}>
                {new Date(notification.created_at).toLocaleString()}
              </time>
            </div>
            {notification.sender_full_name ? (
              <p className="text-sm text-muted-foreground">
                From {notification.sender_full_name}
              </p>
            ) : null}
            <p className="notification-details-message whitespace-pre-wrap break-words text-sm leading-relaxed">
              {notification.message}
            </p>
            {noteId && user?.role === "guidance" ? (
              <section
                aria-label="Adviser behavioral note"
                className="space-y-3 rounded-lg border bg-muted/30 p-4"
              >
                <h3 className="text-sm font-semibold">
                  Adviser behavioral note
                </h3>
                {noteQuery.isLoading ? (
                  <p role="status" className="text-sm text-muted-foreground">
                    Loading adviser’s note…
                  </p>
                ) : null}
                {noteQuery.isError ? (
                  <div role="alert" className="space-y-2 text-sm">
                    <p>{normalizeApiError(noteQuery.error).message}</p>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => void noteQuery.refetch()}
                    >
                      Retry loading note
                    </Button>
                  </div>
                ) : null}
                {note ? (
                  <>
                    <dl className="grid gap-2 text-sm">
                      <div>
                        <dt className="text-xs text-muted-foreground">
                          Student
                        </dt>
                        <dd>
                          {note.student_name} — {note.student_id_code}
                        </dd>
                      </div>
                      <div>
                        <dt className="text-xs text-muted-foreground">
                          Recorded by
                        </dt>
                        <dd>{note.recorded_by_name}</dd>
                      </div>
                      <div>
                        <dt className="text-xs text-muted-foreground">
                          Date recorded
                        </dt>
                        <dd>{note.date_recorded}</dd>
                      </div>
                      <div>
                        <dt className="text-xs text-muted-foreground">Type</dt>
                        <dd>{BEHAVIORAL_NOTE_TYPE_LABELS[note.note_type]}</dd>
                      </div>
                    </dl>
                    <p className="whitespace-pre-wrap break-words border-t pt-3 text-sm leading-relaxed">
                      {note.note_text}
                    </p>
                  </>
                ) : null}
              </section>
            ) : null}
            {readError ? (
              <p role="alert" className="text-sm text-destructive">
                {readError}
              </p>
            ) : null}
            {deletion.isError ? (
              <p role="alert" className="text-sm text-destructive">
                {normalizeApiError(deletion.error).message}
              </p>
            ) : null}
            {confirming ? (
              <p className="text-sm">
                Delete this notification from your inbox?
              </p>
            ) : null}
            <div className="notification-details-actions flex flex-wrap justify-end gap-2 border-t pt-4">
              {href ? (
                <Button asChild variant="outline">
                  <Link to={href} onClick={onClose}>
                    Open related page
                  </Link>
                </Button>
              ) : null}
              <Button
                variant="outline"
                disabled={deletion.isPending}
                onClick={() =>
                  confirming
                    ? deletion.mutate(notification.id, {
                        onSuccess: () => {
                          setConfirming(false)
                          onClose()
                        },
                      })
                    : setConfirming(true)
                }
              >
                {deletion.isPending
                  ? "Deleting…"
                  : confirming
                    ? "Confirm delete"
                    : "Delete"}
              </Button>
              <Button
                onClick={() => {
                  if (confirming) setConfirming(false)
                  else onClose()
                }}
              >
                {confirming ? "Cancel" : "Close"}
              </Button>
            </div>
          </>
        ) : null}
      </DialogContent>
    </Dialog>
  )
}

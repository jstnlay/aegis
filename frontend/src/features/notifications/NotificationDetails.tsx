import { useState } from "react"
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
  const href = notification
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
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
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
            <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
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
            <p className="whitespace-pre-wrap break-words text-sm leading-relaxed">
              {notification.message}
            </p>
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
            <div className="flex flex-wrap justify-end gap-2 border-t pt-4">
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

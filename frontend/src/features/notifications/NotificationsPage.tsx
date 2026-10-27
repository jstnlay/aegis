import { Bell, CheckCheck } from "lucide-react"
import { useMemo, useState } from "react"
import { Link } from "react-router-dom"

import {
  EmptyState,
  ErrorNote,
  LoadingState,
} from "@/components/feedback/Feedback"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { NotificationSummary } from "@/components/layout/Header"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Skeleton } from "@/components/ui/skeleton"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { useAuth } from "@/features/auth/AuthContext"
import {
  NOTIFICATION_TYPES,
  NOTIFICATION_TYPE_LABELS,
  resolveNotificationHref,
  sortNotifications,
  useMarkAllNotificationsRead,
  useMarkNotificationRead,
  useNotifications,
  useUnreadNotifications,
  type Notification,
  type NotificationType,
} from "@/features/notifications/api"
import { normalizeApiError } from "@/lib/error"

/**
 * Notifications inbox, open to all five roles (PH11.9).
 *
 * The endpoint is already `recipient=request.user` scoped, so no role-specific
 * filtering is needed or possible — every role sees the same screen over their
 * own rows.
 *
 * Notification *links* are deliberately not rendered blindly. `link` carries a
 * backend API path, and the destination is only offered when it maps to a
 * screen in the caller's own navigation; see `resolveNotificationHref`.
 */

const READ_FILTERS = [
  { value: "all", label: "All" },
  { value: "unread", label: "Unread" },
  { value: "read", label: "Read" },
] as const

type ReadFilter = (typeof READ_FILTERS)[number]["value"]

const ALL_TYPES = "all" as const
type TypeFilter = typeof ALL_TYPES | NotificationType

function NotificationRow({
  notification,
  href,
  onMarkRead,
  isPending,
}: {
  notification: Notification
  href: string | null
  onMarkRead: (id: string) => void
  isPending: boolean
}) {
  return (
    <TableRow data-read={notification.is_read}>
      <TableCell className="align-top">
        <NotificationSummary notification={notification} />
      </TableCell>
      <TableCell className="align-top">
        {notification.is_read ? (
          <Badge variant="outline">Read</Badge>
        ) : (
          <Badge>Unread</Badge>
        )}
      </TableCell>
      <TableCell className="align-top">
        <div className="flex flex-wrap items-center justify-end gap-2">
          {href ? (
            <Button asChild variant="outline" size="sm">
              <Link to={href}>Open</Link>
            </Button>
          ) : null}
          {notification.is_read ? null : (
            <Button
              size="sm"
              variant="ghost"
              disabled={isPending}
              onClick={() => onMarkRead(notification.id)}
            >
              Mark read
            </Button>
          )}
        </div>
      </TableCell>
    </TableRow>
  )
}

export function NotificationsPage() {
  const { user } = useAuth()
  const [readFilter, setReadFilter] = useState<ReadFilter>("all")
  const [typeFilter, setTypeFilter] = useState<TypeFilter>(ALL_TYPES)

  const unread = useUnreadNotifications()
  const list = useNotifications({
    isRead:
      readFilter === "unread"
        ? "false"
        : readFilter === "read"
          ? "true"
          : undefined,
    type: typeFilter === ALL_TYPES ? undefined : typeFilter,
  })

  const markRead = useMarkNotificationRead()
  const markAllRead = useMarkAllNotificationsRead()

  const notifications = useMemo(
    () => (list.data ? sortNotifications(list.data) : []),
    [list.data]
  )

  const unreadCount = unread.data?.length ?? 0
  const role = user?.role ?? "student"

  return (
    <div className="space-y-6">
      <div className="space-y-1">
        <div className="flex items-center gap-3">
          <Bell className="size-5 text-muted-foreground" aria-hidden="true" />
          <h2 className="text-2xl font-bold text-foreground">Notifications</h2>
        </div>
        <p className="text-sm text-muted-foreground">
          Alerts and updates addressed to your account.
        </p>
      </div>

      <Card>
        <CardHeader className="gap-1">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <CardTitle>Inbox</CardTitle>
              <CardDescription>
                {unreadCount === 0
                  ? "You have no unread notifications."
                  : `${unreadCount} unread notification${unreadCount === 1 ? "" : "s"}.`}
              </CardDescription>
            </div>
            <Button
              variant="outline"
              onClick={() => markAllRead.mutate()}
              disabled={markAllRead.isPending || unreadCount === 0}
            >
              <CheckCheck className="size-4" aria-hidden="true" />
              Mark all read
            </Button>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap gap-4">
            <div className="space-y-1.5">
              <Label htmlFor="notification-read-filter">Status</Label>
              <Select
                value={readFilter}
                onValueChange={(value) => setReadFilter(value as ReadFilter)}
              >
                <SelectTrigger id="notification-read-filter" className="w-40">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {READ_FILTERS.map((option) => (
                    <SelectItem key={option.value} value={option.value}>
                      {option.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="notification-type-filter">Type</Label>
              <Select
                value={typeFilter}
                onValueChange={(value) => setTypeFilter(value as TypeFilter)}
              >
                <SelectTrigger id="notification-type-filter" className="w-64">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={ALL_TYPES}>All types</SelectItem>
                  {NOTIFICATION_TYPES.map((type) => (
                    <SelectItem key={type} value={type}>
                      {NOTIFICATION_TYPE_LABELS[type]}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          {markAllRead.isError ? (
            <ErrorNote message={normalizeApiError(markAllRead.error).message} />
          ) : null}
          {markRead.isError ? (
            <ErrorNote message={normalizeApiError(markRead.error).message} />
          ) : null}

          {list.isPending ? (
            <div className="space-y-2" data-testid="notifications-loading">
              <Skeleton className="h-12 w-full" />
              <Skeleton className="h-12 w-full" />
              <LoadingState label="Loading notifications" />
            </div>
          ) : list.isError ? (
            <ErrorNote message={normalizeApiError(list.error).message} />
          ) : notifications.length === 0 ? (
            <EmptyState message="No notifications match the current filters." />
          ) : (
            <div className="rounded-md border border-border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Notification</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead className="text-right">Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {notifications.map((notification) => (
                    <NotificationRow
                      key={notification.id}
                      notification={notification}
                      href={resolveNotificationHref(notification.link, role)}
                      onMarkRead={(id) => markRead.mutate(id)}
                      isPending={markRead.isPending}
                    />
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}

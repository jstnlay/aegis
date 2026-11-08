import {
  Bell,
  BellRing,
  ArrowUpRight,
  CalendarCheck,
  Inbox,
  ShieldAlert,
  TriangleAlert,
  BookOpen,
  GraduationCap,
  LayoutDashboard,
  Menu,
  ShieldCheck,
  UsersRound,
} from "lucide-react"
import { useEffect, useId, useMemo, useRef, useState } from "react"
import { Link, useLocation } from "react-router-dom"

import { Button } from "@/components/ui/button"
import { useAuth } from "@/features/auth/AuthContext"
import {
  NOTIFICATION_TYPE_LABELS,
  resolveNotificationHref,
  sortNotifications,
  useMarkNotificationRead,
  useUnreadNotifications,
  useNotifications,
  type Notification,
} from "@/features/notifications/api"
import { NotificationDetails } from "@/features/notifications/NotificationDetails"
import { getPageTitle } from "@/lib/navigation"
import { normalizeApiError } from "@/lib/error"
import "./header-account.css"
import "./notification-menu.css"
import { StudentNotebookArt } from "@/features/student/StudentJournalArtwork"
import "@/features/parent/parent-editorial.css"

/**
 * Shared application header (PH11.5).
 *
 * Shows the current page title (from the centralized navigation config),
 * and the notification bell. Account actions live in the sidebar footer.
 *
 * The menu deliberately has no "Profile" entry: the app has no self-profile
 * page — the account surface is `GET/PATCH /accounts/me/`, which the Settings
 * entry opens. A Profile item would have to point at some other screen, and
 * it previously pointed at Notifications, which is a destination that does not
 * match its label.
 */

/**
 * The id of the primary navigation the hamburger button controls.
 *
 * Shared between `Header` (which sets `aria-controls`) and `Sidebar` (which
 * renders the `id`), so the association cannot drift apart when either changes.
 */
export const PRIMARY_NAV_ID = "primary-navigation"

/**
 * The title, body and provenance of one notification.
 *
 * Shared by the bell menu and the inbox rows so the same alert reads
 * identically in both places; the inbox adds its own status and action cells
 * around it rather than a second copy of this text.
 */
export function NotificationSummary({
  notification,
}: {
  notification: Notification
}) {
  return (
    <span className="notification-summary block">
      <span
        className={
          notification.is_read
            ? "notification-title block text-sm text-muted-foreground"
            : "notification-title block text-sm font-medium text-foreground"
        }
      >
        {notification.title}
      </span>
      <span className="notification-message block text-sm text-muted-foreground">
        {notification.message}
      </span>
      <span className="notification-meta block text-xs text-muted-foreground">
        {NOTIFICATION_TYPE_LABELS[notification.notification_type]}
        {notification.sender_full_name
          ? ` · from ${notification.sender_full_name}`
          : ""}{" "}
      </span>
      <time
        className="notification-time block text-xs text-muted-foreground"
        dateTime={notification.created_at}
        title={new Date(notification.created_at).toLocaleString()}
      >
        {new Date(notification.created_at).toLocaleString(undefined, {
          month: "short",
          day: "numeric",
          year: "numeric",
          hour: "numeric",
          minute: "2-digit",
        })}
      </time>
    </span>
  )
}

function UserChip() {
  const { user } = useAuth()
  const unread = useUnreadNotifications()
  const inbox = useNotifications()
  const [selectedNotification, setSelectedNotification] =
    useState<Notification | null>(null)
  const unreadCount = unread.data?.length ?? 0
  const markRead = useMarkNotificationRead()
  const role = user?.role ?? "student"
  // Keep read updates in the menu; the unread query is only for the badge.
  const [bellOpen, setBellOpen] = useState(false)
  const bellRef = useRef<HTMLDivElement>(null)
  const bellButtonRef = useRef<HTMLButtonElement>(null)
  const menuId = useId()
  /*
   * Same dismissal contract as the account menu: click outside or Escape. Kept
   * as its own effect because the two panels have independent open state and a
   * shared one would close the wrong panel when focus moved between them.
   */
  useEffect(() => {
    if (!bellOpen) return
    function onPointerDown(event: PointerEvent) {
      if (bellRef.current && !bellRef.current.contains(event.target as Node)) {
        setBellOpen(false)
      }
    }
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setBellOpen(false)
        bellButtonRef.current?.focus()
      }
    }
    document.addEventListener("pointerdown", onPointerDown)
    document.addEventListener("keydown", onKeyDown)
    return () => {
      document.removeEventListener("pointerdown", onPointerDown)
      document.removeEventListener("keydown", onKeyDown)
    }
  }, [bellOpen])

  const unreadNotifications = useMemo(
    () => sortNotifications(inbox.data ?? []),
    [inbox.data]
  )

  return (
    <div className="app-header-actions flex items-center gap-1">
      <div ref={bellRef} className="notification-menu-anchor relative">
        <Button
          ref={bellButtonRef}
          variant="ghost"
          size="icon"
          onClick={() => setBellOpen((open) => !open)}
          aria-label={
            unreadCount > 0
              ? `Notifications, ${unreadCount} unread`
              : "Notifications"
          }
          aria-expanded={bellOpen}
          aria-haspopup="menu"
          aria-controls={bellOpen ? menuId : undefined}
          className="app-notification-trigger relative text-muted-foreground"
        >
          <Bell aria-hidden="true" />
          {unreadCount > 0 && (
            <span aria-hidden="true" className="app-notification-count">
              {unreadCount > 99 ? "99+" : unreadCount}
            </span>
          )}
        </Button>

        {bellOpen && (
          <div
            role="menu"
            aria-label="Notifications"
            id={menuId}
            className="app-notification-menu"
          >
            <div className="notification-menu-heading">
              <span className="notification-heading-icon" aria-hidden="true">
                <BellRing />
              </span>
              <div>
                <h2>Notifications</h2>
                <p>Your latest school updates</p>
              </div>
              <span className="notification-unread-label">
                {unreadCount} unread
              </span>
            </div>
            <div className="notification-menu-list">
              {inbox.isLoading ? (
                <p role="status" className="notification-state">
                  Loading notifications…
                </p>
              ) : inbox.isError ? (
                <div className="notification-state">
                  <p>Unable to load notifications.</p>
                  <button
                    type="button"
                    onClick={() => {
                      void inbox.refetch()
                    }}
                  >
                    Try again
                  </button>
                </div>
              ) : unreadNotifications.length === 0 ? (
                <div className="notification-empty">
                  <span aria-hidden="true">
                    <Inbox />
                  </span>
                  <strong>You're all caught up</strong>
                  <p>No notifications yet.</p>
                  <small>New school updates will appear here.</small>
                </div>
              ) : (
                unreadNotifications.map((notification) => {
                  const href = resolveNotificationHref(notification.link, role)
                  const incident =
                    notification.notification_type === "BEHAVIORAL_INCIDENT"
                  const warning =
                    notification.notification_type === "BEHAVIORAL_WARNING" ||
                    notification.notification_type === "ATTENDANCE_THRESHOLD"
                  const ItemIcon = incident
                    ? ShieldAlert
                    : warning
                      ? notification.notification_type ===
                        "ATTENDANCE_THRESHOLD"
                        ? CalendarCheck
                        : TriangleAlert
                      : notification.notification_type === "GRADE_POSTED"
                        ? BookOpen
                        : Bell
                  return (
                    <div
                      key={notification.id}
                      className="notification-item"
                      data-tone={
                        incident ? "danger" : warning ? "warning" : "school"
                      }
                    >
                      <button
                        type="button"
                        role="menuitem"
                        onClick={() => {
                          setSelectedNotification(notification)
                          if (!notification.is_read)
                            markRead.mutate(notification.id, {
                              onSuccess: () =>
                                setSelectedNotification((current) =>
                                  current?.id === notification.id
                                    ? { ...current, is_read: true }
                                    : current
                                ),
                            })
                          setBellOpen(false)
                        }}
                        className="notification-item-button"
                      >
                        <span
                          className="notification-item-icon"
                          aria-hidden="true"
                        >
                          <ItemIcon />
                        </span>
                        <NotificationSummary notification={notification} />
                        <span className="text-xs font-medium">
                          View · {notification.is_read ? "Read" : "Unread"}
                        </span>
                      </button>
                      {href ? (
                        <Link
                          to={href}
                          role="menuitem"
                          onClick={() => {
                            markRead.mutate(notification.id)
                            setBellOpen(false)
                          }}
                          className="notification-related-link"
                        >
                          Open the related page{" "}
                          <ArrowUpRight aria-hidden="true" />
                        </Link>
                      ) : null}
                    </div>
                  )
                })
              )}
            </div>
            <div className="notification-menu-footer">
              <Link
                to="/app/notifications"
                role="menuitem"
                onClick={() => setBellOpen(false)}
                className="notification-inbox-link"
              >
                Open the inbox <ArrowUpRight aria-hidden="true" />
              </Link>
            </div>
          </div>
        )}
      </div>
      <NotificationDetails
        key={selectedNotification?.id ?? "closed"}
        notification={selectedNotification}
        onClose={() => setSelectedNotification(null)}
        readError={
          markRead.isError
            ? normalizeApiError(markRead.error).message
            : undefined
        }
      />
    </div>
  )
}

export function Header({
  onMenuClick,
  menuOpen = false,
  menuButtonRef,
  brandContainerRef,
}: {
  onMenuClick: () => void
  /** Whether the mobile navigation drawer is currently open. */
  menuOpen?: boolean
  /**
   * Ref to the hamburger button, so `AppShell` can return focus to it when the
   * drawer closes. See the focus-restoration effect there.
   */
  menuButtonRef?: React.Ref<HTMLButtonElement>
  brandContainerRef?: React.Ref<HTMLDivElement>
}) {
  const { user } = useAuth()
  const location = useLocation()
  const pageTitle = getPageTitle(location.pathname)
  const dashboard = /^\/app\/dashboard(?:\/|$)/.test(location.pathname)
  const firstName = user?.first_name?.trim() || ""
  const teacherName = [
    firstName
      .split(/\s+/)
      .filter(Boolean)
      .map((part) => `${Array.from(part)[0]}.`)
      .join(" "),
    user?.last_name?.trim(),
  ]
    .filter(Boolean)
    .join(" ")
  const welcomeName =
    user?.role === "faculty"
      ? teacherName
        ? `Teacher ${teacherName}`
        : "Teacher"
      : firstName
  const dashboardTitle =
    user?.role === "admin"
      ? "Administration overview"
      : user?.role === "parent"
        ? "Your family portal"
        : `Welcome back${welcomeName ? `, ${welcomeName}` : ""}!`
  const dashboardDescription =
    user?.role === "faculty"
      ? "Your classes, teaching tasks, and student progress—all in one place."
      : user?.role === "guidance"
        ? "An overview of student support activities and follow-ups."
        : user?.role === "admin"
          ? "School-wide aggregates. Individual student records are not shown here."
          : user?.role === "parent"
            ? "Follow your child's learning, attendance, and school support."
            : "Keep up with your grades, attendance, and next steps."
  const DashboardIcon =
    user?.role === "faculty"
      ? BookOpen
      : user?.role === "guidance"
        ? ShieldCheck
        : user?.role === "admin"
          ? LayoutDashboard
          : user?.role === "parent"
            ? UsersRound
            : GraduationCap
  const headerRef = useRef<HTMLElement>(null)
  const [scrollState, setScrollState] = useState({
    pathname: location.pathname,
    hidden: false,
  })
  const schoolTheme =
    user?.role === "admin" ||
    user?.role === "guidance" ||
    user?.role === "student" ||
    user?.role === "parent" ||
    user?.role === "faculty"
  const hidden =
    schoolTheme &&
    !menuOpen &&
    scrollState.pathname === location.pathname &&
    scrollState.hidden

  useEffect(() => {
    if (!schoolTheme) return
    let previousY = Math.max(0, window.scrollY)

    function onScroll() {
      const currentY = Math.max(0, window.scrollY)
      if (currentY > 24 && Math.abs(currentY - previousY) < 4) return
      const scrollingDown = currentY > previousY
      previousY = currentY
      const usingHeader = headerRef.current?.querySelector(
        ':focus-visible, [aria-haspopup="menu"][aria-expanded="true"]'
      )
      setScrollState({
        pathname: location.pathname,
        hidden: currentY > 24 && scrollingDown && !usingHeader,
      })
    }

    window.addEventListener("scroll", onScroll, { passive: true })
    return () => window.removeEventListener("scroll", onScroll)
  }, [schoolTheme, location.pathname])

  return (
    <header
      ref={headerRef}
      data-hidden={hidden}
      data-dashboard={dashboard}
      onFocusCapture={() =>
        setScrollState({ pathname: location.pathname, hidden: false })
      }
      className="app-header sticky top-0 z-30 flex h-14 shrink-0 items-center gap-3 border-b border-border bg-background px-4 lg:px-6"
    >
      {schoolTheme ? (
        <div className="app-header-brand-host" ref={brandContainerRef} />
      ) : null}
      {/*
        PH11.11: `aria-expanded` and `aria-controls` were added. The control
        opened and closed the drawer but reported no state, so a screen-reader
        user activating it got no confirmation that anything had changed and had
        no way to associate the button with the region it governs. `aria-controls`
        points at the `<nav id>` the drawer contains.
      */}
      <Button
        ref={menuButtonRef}
        variant="ghost"
        size="icon"
        className="app-navigation-trigger lg:hidden"
        onClick={onMenuClick}
        aria-label="Open navigation"
        aria-expanded={menuOpen}
        aria-controls={PRIMARY_NAV_ID}
      >
        <Menu aria-hidden="true" />
      </Button>

      {/*
        The document's `h1` since PH11.11. The header renders the page title for
        every route, so it is the one place that can own the document's top-level
        heading; each page's own title sits one level below it as an `h2`, which
        is what removed the two-`h1` duplication this file previously caused on
        all twenty-nine in-shell pages.

        Uppercased and set in the brand maroon to match the reference's header
        (`DASHBOARD`, `RISK ALERTS`, …). The transformation is presentational,
        so assistive technology still reads the heading's original casing.

        Deliberately a plain bar: the school banner photo lives behind each
        page's title block in the content area, not here. A previous version
        put it in this header with `overflow-hidden`, which clipped the account
        menu open state — the Sign out item was unreachable.
      */}
      {dashboard ? (
        <div className="app-dashboard-heading">
          <span className="app-dashboard-heading-icon" aria-hidden="true">
            <DashboardIcon />
          </span>
          <div className="app-dashboard-heading-copy">
            <h1>
              {user?.role === "faculty" ? (
                <>
                  Welcome back,{" "}
                  <span className="app-dashboard-teacher-title">Teacher</span>
                  {teacherName ? ` ${teacherName}` : ""}!
                </>
              ) : user?.role === "student" ? (
                <>
                  <span className="student-greeting-intro">Welcome back</span>
                  {welcomeName ? (
                    <>
                      ,{" "}
                      <span className="student-greeting-name">
                        {welcomeName}!
                      </span>
                    </>
                  ) : (
                    "!"
                  )}
                </>
              ) : (
                dashboardTitle
              )}
            </h1>
            <p>{dashboardDescription}</p>
            {user?.role === "student" ? (
              <p className="student-journal-motto">
                One step at a time. Make today yours.
              </p>
            ) : null}
          </div>
        </div>
      ) : (
        <h1 className="min-w-0 flex-1 truncate text-lg font-semibold tracking-wide text-primary uppercase">
          {pageTitle}
        </h1>
      )}

      {dashboard && user?.role === "student" ? <StudentNotebookArt /> : null}
      {dashboard && user?.role === "parent" ? (
        <img
          className="parent-portal-illustration"
          src="/illustrations/parent-teen-portal.svg"
          alt=""
          aria-hidden="true"
          draggable={false}
        />
      ) : null}
      <UserChip />
    </header>
  )
}

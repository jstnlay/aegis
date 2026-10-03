import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import { apiClient } from "@/lib/api"
import { getNavItemsForRole } from "@/lib/navigation"
import { fetchAllPages } from "@/lib/pagination"
import type { Role } from "@/types/auth"

/**
 * Notifications domain API (PH11.9).
 *
 * Verified against `apps/notifications/`:
 *
 * - `NotificationViewSet` is a `ReadOnlyModelViewSet` — the list and detail
 *   routes are GET-only. There is no create/update/delete route: notifications
 *   are produced only by `dispatch_event()`, so no authoring UI is possible or
 *   appropriate.
 * - `get_queryset()` is `Notification.objects.filter(recipient=request.user)`,
 *   so cross-user leakage is impossible regardless of any id passed. Filters
 *   are `is_read` ("true"/"false") and `notification_type`.
 * - `permission_classes = [IsAuthenticated]` — the endpoint is open to all five
 *   roles, so no role needs its own variant.
 * - `mark_read` and `mark_all_read` return `{success, message}` (plus `count`
 *   for read-all), **not** the serialized notification. Invalidating the list
 *   after either is therefore the only way to see the new `is_read` value.
 * - `NotificationPreferenceView` is a `RetrieveUpdateAPIView` whose `get_object`
 *   does `get_or_create`, so the row always exists on read and the client never
 *   creates one.
 *
 * No realtime push, no email delivery and no per-type preference matrix exist
 * server-side, so none are offered here.
 */

/** `NotificationType` choices — the complete set the API can return. */
export type NotificationType =
  | "GRADE_POSTED"
  | "ATTENDANCE_THRESHOLD"
  | "BEHAVIORAL_WARNING"
  | "BEHAVIORAL_INCIDENT"
  | "ASSESSMENT_DEPLOYED"
  | "ASSESSMENT_COMPLETED"
  | "RISK_ALERT_GENERATED"
  | "INTERVENTION_UPDATE"
  | "ANNOUNCEMENT_PUBLISHED"
  | "CONSULTATION_SCHEDULED"

export const NOTIFICATION_TYPES: readonly NotificationType[] = [
  "GRADE_POSTED",
  "ATTENDANCE_THRESHOLD",
  "BEHAVIORAL_WARNING",
  "BEHAVIORAL_INCIDENT",
  "ASSESSMENT_DEPLOYED",
  "ASSESSMENT_COMPLETED",
  "RISK_ALERT_GENERATED",
  "INTERVENTION_UPDATE",
  "ANNOUNCEMENT_PUBLISHED",
  "CONSULTATION_SCHEDULED",
]

export const NOTIFICATION_TYPE_LABELS: Record<NotificationType, string> = {
  GRADE_POSTED: "Grade posted",
  ATTENDANCE_THRESHOLD: "Attendance threshold exceeded",
  BEHAVIORAL_WARNING: "Behavioral warning",
  BEHAVIORAL_INCIDENT: "Behavioral incident",
  ASSESSMENT_DEPLOYED: "Assessment deployed",
  ASSESSMENT_COMPLETED: "Assessment completed",
  RISK_ALERT_GENERATED: "Risk alert generated",
  INTERVENTION_UPDATE: "Intervention update",
  ANNOUNCEMENT_PUBLISHED: "Announcement published",
  CONSULTATION_SCHEDULED: "Consultation scheduled",
}

/** `NotificationSerializer` — read-only on every field. */
export interface Notification {
  id: string
  notification_type: NotificationType
  title: string
  message: string
  link: string | null
  is_read: boolean
  read_at: string | null
  sender: string | null
  sender_full_name: string | null
  created_at: string
}

/**
 * Notification *preferences* are deliberately not declared here.
 *
 * `GET/PUT /notifications/preferences/` already has one implementation in
 * `features/settings/api.ts`, consumed by `AccountSettingsPage`. A second copy
 * would be two sources of truth for one endpoint — the bug PH11.7 hit with
 * `averageGrade`. Preferences belong to account settings; this module owns the
 * inbox.
 */

export interface NotificationFilters {
  isRead?: "true" | "false"
  type?: NotificationType
}

/**
 * True when the role's own navigation contains a **working** link to a route.
 *
 * Deliberately not `isRouteVisibleToRole`: that helper reports membership in
 * the navigation tree, and the tree also holds `planned` placeholder entries
 * which render as non-navigable. A student has a planned `assessments` entry,
 * so that check would hand a student a link to the guidance-only assessments
 * screen and bounce them off `RequireRole`. A `planned` item is a roadmap note,
 * not a destination.
 */
function roleCanOpenRoute(role: Role, route: string): boolean {
  return getNavItemsForRole(role).some(
    (item) => item.route === route && item.status === "available"
  )
}

/**
 * Maps a notification's `link` onto a frontend route.
 *
 * `Notification.link` is a plain `CharField(max_length=500)` and every producer
 * fills it with a **backend API path**, not a SPA route — e.g.
 * `/guidance/risk-alerts`, `/academics/grades/{id}`,
 * `/attendance/summary?student={id}` (see `apps/assessments/utils.py`,
 * `apps/guidance/views.py`, `apps/attendance/views.py`,
 * `ai_engine/risk_service.py`). Handing one of those to the router would
 * navigate away from the SPA, so each shape is mapped to the screen a user can
 * actually reach.
 *
 * Returns `null` when there is no equivalent screen, or when the mapped screen
 * is not a working link in the caller's navigation. The caller then renders
 * the notification without a link rather than offering a dead or forbidden
 * one — a parent must not be pointed at the counselor-only risk-alerts screen
 * just because the backend addressed a notification that way.
 *
 * The route is also required to be a relative path beginning with a single
 * slash. `link` is free text on the model, so an absolute or protocol-relative
 * value is refused rather than rendered as an anchor.
 */
const LINK_ROUTE_PREFIXES: ReadonlyArray<readonly [string, string]> = [
  ["/guidance/risk-alerts", "risk-alerts"],
  ["/guidance/behavioral-notes", "students"],
  ["/guidance/consultations", "consultations"],
  ["/guidance/interventions", "interventions"],
  ["/guidance/reports", "students"],
  ["/assessments/assessment-results", "assessments"],
  ["/assessments", "assessments"],
  ["/academics/grades", "academics"],
  ["/academics/enrollments", "academics"],
  ["/academics/sections", "academics"],
  ["/academics", "academics"],
  ["/attendance", "attendance"],
]

export function resolveNotificationHref(
  link: string | null | undefined,
  role: Role
): string | null {
  if (typeof link !== "string") return null

  const trimmed = link.trim()
  if (!trimmed.startsWith("/")) return null
  // "//host" and "/\evil" are protocol-relative / backslash-smuggled forms.
  if (trimmed.startsWith("//") || trimmed.startsWith("/\\")) return null

  // Compare on the path only: producers append a query string
  // (`/attendance/summary?student=...`), and React Router ignores it anyway.
  const path = trimmed.split("?")[0] ?? trimmed

  for (const [prefix, route] of LINK_ROUTE_PREFIXES) {
    if (path !== prefix && !path.startsWith(`${prefix}/`)) continue
    // Guard the destination, not just the source: the notification may address
    // a screen this role cannot open.
    return roleCanOpenRoute(role, route) ? `/app/${route}` : null
  }

  return null
}

/** Query key factory so list and unread-count reads stay distinct. */
const KEY = "notifications" as const

function buildUrl(filters: NotificationFilters): string {
  const params = new URLSearchParams()
  if (filters.isRead) params.set("is_read", filters.isRead)
  if (filters.type) params.set("notification_type", filters.type)
  const query = params.toString()
  return query ? `/notifications/?${query}` : "/notifications/"
}

export function useNotifications(filters: NotificationFilters = {}) {
  const url = buildUrl(filters)
  return useQuery({
    queryKey: [KEY, "list", filters.isRead ?? null, filters.type ?? null],
    queryFn: async ({ signal }) => {
      const { results } = await fetchAllPages<Notification>(url, { signal })
      return results
    },
  })
}

/** Unread notifications only — the badge count and the default view. */
export function useUnreadNotifications() {
  return useNotifications({ isRead: "false" })
}

export function useMarkNotificationRead() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (id: string) =>
      apiClient.post(`/notifications/${id}/read/`).then((r) => r.data),
    // The action returns only `{success, message}`, so the list must be
    // refetched to observe the new `is_read`.
    onSuccess: () => client.invalidateQueries({ queryKey: [KEY] }),
  })
}

export function useMarkAllNotificationsRead() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: () =>
      apiClient.post("/notifications/read-all/").then((r) => r.data),
    onSuccess: () => client.invalidateQueries({ queryKey: [KEY] }),
  })
}

/** Unread count for the navigation badge. */
export function useUnreadCount(): number {
  const { data } = useUnreadNotifications()
  return data?.length ?? 0
}

/** Newest first, matching `Notification.Meta.ordering = ["-created_at"]`. */
export function sortNotifications(
  notifications: Notification[]
): Notification[] {
  return [...notifications].sort((a, b) =>
    b.created_at.localeCompare(a.created_at)
  )
}

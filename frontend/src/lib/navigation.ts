import {
  Bell,
  BookOpen,
  CalendarCheck,
  ClipboardCheck,
  ClipboardList,
  FileText,
  LayoutDashboard,
  MessageSquare,
  Settings,
  Shield,
  UserCog,
  Users,
  type LucideIcon,
} from "lucide-react"

import type { Role } from "@/types/auth"

/**
 * Centralized role-aware navigation model (PH11.5).
 *
 * One source of truth for navigation — consumed by the Sidebar and the
 * header page-title lookup. No role checks are scattered across dozens
 * of components.
 *
 * Backend authorization remains authoritative — this model only controls
 * the frontend user experience.
 *
 * Item status:
 * - "available"  — a real screen/route exists (Dashboard for everyone,
 *                  Academics for faculty/admin as the documented
 *                  first-domain entry point, Attendance for student/faculty,
 *                  and the PH11.8 guidance surface).
 * - "planned"    — intentionally documented placeholder; the route is NOT
 *                  created yet and no fake page exists. Rendered in the
 *                  sidebar as an informative, non-navigable entry.
 *
 * Resolution rules (see getVisibleNavigationForRole):
 * - Available items are shown as links only to roles in `allowedRoles`
 *   (an empty allowedRoles means all roles).
 * - Planned items are shown to the roles whose tree places them — they
 *   preview the roadmap and are never links.
 */

export type NavItemStatus = "available" | "planned"

export interface NavItem {
  /** Route path relative to /app (e.g. "dashboard", "academics"). */
  route: string
  /** Human-readable label. */
  label: string
  /** Lucide icon component. */
  icon: LucideIcon
  /** Roles allowed to reach this item's route. Empty/undefined = all roles. */
  allowedRoles?: readonly Role[]
  /** Whether a real route exists for this item (see NavItemStatus). */
  status: NavItemStatus
}

export interface NavGroup {
  /** Group heading text. */
  heading: string
  /** Navigation items in this group. */
  items: readonly NavItem[]
}

/* ------------------------------------------------------------------ */
/* Items                                                              */
/* ------------------------------------------------------------------ */

const DASHBOARD: NavItem = {
  route: "dashboard",
  label: "Dashboard",
  icon: LayoutDashboard,
  status: "available",
}

const ACADEMICS: NavItem = {
  route: "academics",
  label: "Academics",
  icon: BookOpen,
  // Students get the read-only grade record; faculty get grade encoding.
  allowedRoles: ["student", "faculty", "admin"],
  status: "available",
}

/**
 * Attendance is a real route for students and faculty only (PH11.7).
 * Roles without a verified surface get their own planned item rather than a
 * link that would bounce off `RequireRole`.
 */
const ATTENDANCE: NavItem = {
  route: "attendance",
  label: "Attendance",
  icon: CalendarCheck,
  allowedRoles: ["student", "faculty"],
  status: "available",
}

/** Roadmap entry for roles whose attendance surface is not implemented yet. */
const ATTENDANCE_PLANNED: NavItem = {
  route: "attendance",
  label: "Attendance",
  icon: CalendarCheck,
  allowedRoles: ["parent", "admin", "guidance"],
  status: "planned",
}

/**
 * Faculty/admin assessment roadmap entry.
 *
 * Deliberately *not* the same object as `GUIDANCE_ASSESSMENTS` below. PH11.8
 * shipped `/app/assessments` for guidance, but `RequireRole` keeps that route
 * guidance-only, so faculty and admin keep an honest planned entry rather than a
 * link that would bounce off the guard. When their assessment surface lands it
 * gets its own route.
 */
const ASSESSMENTS: NavItem = {
  route: "assessments",
  label: "Assessments",
  icon: ClipboardCheck,
  allowedRoles: ["faculty", "admin"],
  status: "planned",
}

/** PH11.8: the guidance assessments surface, backed by a real route. */
const GUIDANCE_ASSESSMENTS: NavItem = {
  route: "assessments",
  label: "Assessments",
  icon: ClipboardCheck,
  allowedRoles: ["guidance"],
  status: "available",
}

/** PH11.8 removed the old `GUIDANCE` nav item entirely.
 *
 * `/app/guidance` is not a page and is deliberately left unregistered, so an
 * entry for it could only ever be a placeholder. The guidance surface is
 * reached through the real per-domain routes below instead.
 */
const USERS: NavItem = {
  route: "users",
  label: "Users",
  icon: Users,
  allowedRoles: ["admin"],
  status: "planned",
}

const REPORTS: NavItem = {
  route: "reports",
  label: "Reports",
  icon: FileText,
  allowedRoles: ["faculty", "guidance", "admin"],
  status: "planned",
}

const SETTINGS: NavItem = {
  route: "settings",
  label: "Settings",
  icon: Settings,
  allowedRoles: ["admin"],
  status: "planned",
}

const RISK_ALERTS: NavItem = {
  route: "risk-alerts",
  label: "Risk Alerts",
  icon: Shield,
  allowedRoles: ["guidance"],
  status: "available",
}

const CONSULTATIONS: NavItem = {
  route: "consultations",
  label: "Consultations",
  icon: MessageSquare,
  allowedRoles: ["guidance"],
  status: "available",
}

const INTERVENTIONS: NavItem = {
  route: "interventions",
  label: "Interventions",
  icon: ClipboardList,
  allowedRoles: ["guidance"],
  status: "available",
}

const STUDENTS: NavItem = {
  route: "students",
  label: "Students",
  icon: Users,
  allowedRoles: ["guidance"],
  status: "available",
}

/**
 * PH11.9 built the settings page for every role.
 *
 * `AccountSettingsPage` reads `GET/PATCH /accounts/me/` (self-scoped),
 * `POST /accounts/password/change/` and `GET/PUT /notifications/preferences/`
 * (`get_or_create(request.user)`). None of those endpoints can address another
 * account, so there is no cross-account surface for a role guard to protect —
 * the scope was the caller's own, which is what "account settings" means.
 *
 * `allowedRoles` is left empty, which this module reads as "every role".
 * PH11.8 kept this guidance-only only because that batch had changed the
 * counselor's sidebar.
 */
const ACCOUNT_SETTINGS: NavItem = {
  route: "account-settings",
  label: "Account Settings",
  icon: UserCog,
  status: "available",
}

/**
 * PH11.9: real route, open to all five roles.
 *
 * `NotificationViewSet.get_queryset()` is
 * `Notification.objects.filter(recipient=request.user)`, so one screen serves
 * every role over its own rows and no role can see another's.
 */
const NOTIFICATIONS: NavItem = {
  route: "notifications",
  label: "Notifications",
  icon: Bell,
  status: "available",
}

/* ------------------------------------------------------------------ */
/* Role-specific navigation trees                                     */
/* ------------------------------------------------------------------ */

const OVERVIEW_GROUP: NavGroup = { heading: "Overview", items: [DASHBOARD] }

/** Every role gets an Account group now that settings is open to all of them. */
const ACCOUNT_GROUP: NavGroup = {
  heading: "Account",
  items: [ACCOUNT_SETTINGS],
}

const STUDENT_NAVIGATION: readonly NavGroup[] = [
  OVERVIEW_GROUP,
  {
    heading: "Learning",
    items: [ACADEMICS, ATTENDANCE, ASSESSMENTS, REPORTS],
  },
  {
    heading: "Communication",
    items: [NOTIFICATIONS],
  },
  ACCOUNT_GROUP,
]

const PARENT_NAVIGATION: readonly NavGroup[] = [
  OVERVIEW_GROUP,
  {
    heading: "My Child",
    // PH11.9 widens these to real links as the parent academics, attendance and
    // assessment routes land. Until a route exists *and* `RequireRole` admits
    // `parent`, they must stay planned — a link would bounce off the guard,
    // which is the exact failure PH11.7 avoided by keeping parent on its own
    // `ATTENDANCE_PLANNED` item.
    items: [ATTENDANCE_PLANNED, ASSESSMENTS, REPORTS],
  },
  {
    heading: "Communication",
    items: [NOTIFICATIONS],
  },
  ACCOUNT_GROUP,
]

const FACULTY_NAVIGATION: readonly NavGroup[] = [
  OVERVIEW_GROUP,
  {
    heading: "Teaching",
    items: [ACADEMICS, ATTENDANCE, ASSESSMENTS, REPORTS],
  },
  {
    heading: "Communication",
    items: [NOTIFICATIONS],
  },
  ACCOUNT_GROUP,
]

const GUIDANCE_NAVIGATION: readonly NavGroup[] = [
  OVERVIEW_GROUP,
  {
    heading: "Student Support",
    items: [
      RISK_ALERTS,
      CONSULTATIONS,
      INTERVENTIONS,
      STUDENTS,
      GUIDANCE_ASSESSMENTS,
      REPORTS,
    ],
  },
  {
    heading: "Communication",
    items: [NOTIFICATIONS],
  },
  ACCOUNT_GROUP,
]

const ADMIN_NAVIGATION: readonly NavGroup[] = [
  OVERVIEW_GROUP,
  {
    heading: "Administration",
    // `ATTENDANCE` allows only student/faculty, so admin keeps the planned
    // item until the PH11.9 admin attendance route admits `admin`.
    items: [ACADEMICS, ATTENDANCE_PLANNED, ASSESSMENTS, USERS, REPORTS],
  },
  {
    heading: "System",
    items: [SETTINGS],
  },
  {
    heading: "Communication",
    items: [NOTIFICATIONS],
  },
  ACCOUNT_GROUP,
]

const ROLE_NAVIGATION: Record<Role, readonly NavGroup[]> = {
  student: STUDENT_NAVIGATION,
  parent: PARENT_NAVIGATION,
  faculty: FACULTY_NAVIGATION,
  guidance: GUIDANCE_NAVIGATION,
  admin: ADMIN_NAVIGATION,
}

/* ------------------------------------------------------------------ */
/* Public API                                                         */
/* ------------------------------------------------------------------ */

/** Whether a role may be linked to an item's route. */
function roleAllowed(item: NavItem, role: Role): boolean {
  return !item.allowedRoles || item.allowedRoles.length === 0
    ? true
    : item.allowedRoles.includes(role)
}

/**
 * Resolves the navigation visible to a role.
 *
 * - Available items become links only for roles in their allowedRoles.
 * - Planned items appear as roadmap entries for roles whose tree places
 *   them. Groups with no visible items are dropped.
 */
export function getVisibleNavigationForRole(role: Role): readonly NavGroup[] {
  return ROLE_NAVIGATION[role]
    .map((group) => ({
      heading: group.heading,
      items: group.items.filter((item) =>
        item.status === "planned" ? true : roleAllowed(item, role)
      ),
    }))
    .filter((group) => group.items.length > 0)
}

/** Returns the flat, resolved navigation items for the given role. */
export function getNavItemsForRole(role: Role): readonly NavItem[] {
  return getVisibleNavigationForRole(role).flatMap((group) => group.items)
}

/** The route for an item ("dashboard" -> "/app/dashboard"). */
export function itemHref(item: NavItem): string {
  return `/app/${item.route}`
}

/** True when a route appears in the given role's resolved navigation. */
export function isRouteVisibleToRole(role: Role, route: string): boolean {
  return getNavItemsForRole(role).some((item) => item.route === route)
}

/** Page title for a pathname within the /app area (used by the header). */
export function getPageTitle(pathname: string): string {
  const segment = pathname.replace(/^\/app\/?/, "").split("/")[0] ?? ""

  const allItems: readonly NavItem[] = [
    DASHBOARD,
    ACADEMICS,
    ATTENDANCE,
    ATTENDANCE_PLANNED,
    ASSESSMENTS,
    GUIDANCE_ASSESSMENTS,
    USERS,
    REPORTS,
    SETTINGS,
    RISK_ALERTS,
    CONSULTATIONS,
    INTERVENTIONS,
    STUDENTS,
    ACCOUNT_SETTINGS,
    NOTIFICATIONS,
  ]

  const match = allItems.find((item) => item.route === segment)
  if (match) return match.label
  return segment ? "AEGIS" : "Dashboard"
}

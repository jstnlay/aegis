import {
  BookOpen,
  CalendarCheck,
  ClipboardCheck,
  FileText,
  LayoutDashboard,
  MessageSquare,
  Settings,
  Shield,
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
 *                  first-domain entry point).
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

const ASSESSMENTS: NavItem = {
  route: "assessments",
  label: "Assessments",
  icon: ClipboardCheck,
  allowedRoles: ["faculty", "guidance", "admin"],
  status: "planned",
}

const GUIDANCE: NavItem = {
  route: "guidance",
  label: "Guidance",
  icon: MessageSquare,
  allowedRoles: ["guidance", "admin"],
  status: "planned",
}

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
  status: "planned",
}

const NOTIFICATIONS: NavItem = {
  route: "notifications",
  label: "Notifications",
  icon: MessageSquare,
  status: "planned",
}

/* ------------------------------------------------------------------ */
/* Role-specific navigation trees                                     */
/* ------------------------------------------------------------------ */

const OVERVIEW_GROUP: NavGroup = { heading: "Overview", items: [DASHBOARD] }

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
]

const PARENT_NAVIGATION: readonly NavGroup[] = [
  OVERVIEW_GROUP,
  {
    heading: "My Child",
    items: [ATTENDANCE_PLANNED, REPORTS],
  },
  {
    heading: "Communication",
    items: [NOTIFICATIONS],
  },
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
]

const GUIDANCE_NAVIGATION: readonly NavGroup[] = [
  OVERVIEW_GROUP,
  {
    heading: "Student Support",
    items: [RISK_ALERTS, ASSESSMENTS, GUIDANCE, REPORTS],
  },
  {
    heading: "Communication",
    items: [NOTIFICATIONS],
  },
]

const ADMIN_NAVIGATION: readonly NavGroup[] = [
  OVERVIEW_GROUP,
  {
    heading: "Administration",
    items: [
      ACADEMICS,
      ATTENDANCE_PLANNED,
      ASSESSMENTS,
      USERS,
      GUIDANCE,
      REPORTS,
    ],
  },
  {
    heading: "System",
    items: [SETTINGS],
  },
  {
    heading: "Communication",
    items: [NOTIFICATIONS],
  },
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
    GUIDANCE,
    USERS,
    REPORTS,
    SETTINGS,
    RISK_ALERTS,
    NOTIFICATIONS,
  ]

  const match = allItems.find((item) => item.route === segment)
  if (match) return match.label
  return segment ? "AEGIS" : "Dashboard"
}

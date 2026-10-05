import {
  Bell,
  BookOpen,
  CalendarCheck,
  ClipboardCheck,
  ClipboardList,
  FileText,
  LayoutDashboard,
  MessageSquare,
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

/**
 * PH11.9 removed the `ATTENDANCE_PLANNED` roadmap item entirely.
 *
 * PH11.7 kept it for parent, admin and guidance. PH11.9 gave parent a real
 * attendance view inside `parent/academics` and admin one at `admin/attendance`,
 * which covers both. Guidance still has no attendance route: it can read every
 * record and the summary through the same endpoints, but no guidance attendance
 * screen was in scope, and a planned entry for a route that does not exist is
 * the same placeholder failure PH11.8 removed for `/app/guidance`. Guidance
 * still reads attendance data on the student profile page, which is a real
 * route.
 */

/* ------------------------------------------------------------------ */
/* PH11.9 admin navigation                                             */
/* ------------------------------------------------------------------ */

/**
 * PH11.9 admin tree.
 *
 * PH11.7 shipped admin a placeholder tree: `users` and `settings` were planned
 * entries pointing at routes that did not exist, and `academics` linked to a
 * page that described implemented functionality as future work. This tree
 * contains only routes that exist, each backed by an endpoint verified during
 * this phase.
 */
const ADMIN_ACADEMIC_STRUCTURE: NavItem = {
  route: "admin/academics",
  label: "Academic Structure",
  icon: BookOpen,
  allowedRoles: ["admin"],
  status: "available",
}

/**
 * Grade oversight and finalization.
 *
 * `GradeViewSet.get_permissions()` grants the `finalize` action to
 * `IsAdminUser`, so this is the one grade write an administrator holds.
 * `encode` and `batch_import` are `IsFacultyUser`, so no score-entry control is
 * offered.
 */
const ADMIN_GRADES: NavItem = {
  route: "admin/grades",
  label: "Grades",
  icon: ClipboardCheck,
  allowedRoles: ["admin"],
  status: "available",
}

/**
 * Attendance oversight.
 *
 * Read-only for admin: `AttendanceRecordViewSet.get_permissions()` gates every
 * write verb on `IsFacultyUser`. The page states this rather than offering a
 * form the backend would reject.
 */
const ADMIN_ATTENDANCE: NavItem = {
  route: "admin/attendance",
  label: "Attendance",
  icon: CalendarCheck,
  allowedRoles: ["admin"],
  status: "available",
}

/** School-wide aggregates. NFR-010 requires these stay anonymised. */
const ADMIN_ANALYTICS: NavItem = {
  route: "admin/analytics",
  label: "Analytics",
  icon: LayoutDashboard,
  allowedRoles: ["admin"],
  status: "available",
}

/**
 * User administration.
 *
 * `UserListView`, `UserDetailView` and `UserCreateView` are the complete user
 * contract: list, retrieve and create. There is no update, deactivate, delete,
 * role-reassignment or password-reset route, and the page says so explicitly.
 */
const ADMIN_USERS: NavItem = {
  route: "admin/users",
  label: "Users",
  icon: Users,
  allowedRoles: ["admin"],
  status: "available",
}

/** Import jobs and the controlled CSV/XLSX exports. */
const ADMIN_DATA: NavItem = {
  route: "admin/data",
  label: "Imports & Exports",
  icon: FileText,
  allowedRoles: ["admin"],
  status: "available",
}

/**
 * School content through the CMS proxy.
 *
 * Read-only: content is authored in Strapi and the AEGIS proxy exposes no write
 * endpoint, so there is no authoring form.
 */
const ADMIN_CMS: NavItem = {
  route: "admin/cms",
  label: "Content",
  icon: FileText,
  allowedRoles: ["admin"],
  status: "available",
}

/**
 * The audit trail.
 *
 * Read-only by design: `AuditLogViewSet` is a `ReadOnlyModelViewSet` whose
 * `http_method_names` maps no write route, which is the correct property for an
 * append-only trail.
 */
const ADMIN_AUDIT: NavItem = {
  route: "admin/audit",
  label: "Audit Logs",
  icon: Shield,
  allowedRoles: ["admin"],
  status: "available",
}

/**
 * PH11.9: the parent's academic record, covering both grades and attendance.
 *
 * `GET /academics/grades/`, `GET /attendance/records/` and
 * `GET /attendance/summary/` are all scoped by the backend to
 * `ParentStudentLink` children, so this page selects among the caller's own
 * children and cannot reach another family's records. This is why parent no
 * longer needs the `ATTENDANCE_PLANNED` placeholder above: a real surface
 * replaced it.
 */
const PARENT_ACADEMICS: NavItem = {
  route: "parent/academics",
  label: "Academic Record",
  icon: BookOpen,
  allowedRoles: ["parent"],
  status: "available",
}

/**
 * PH11.9: the parent's assessment and results view.
 *
 * Read-only. The backend withholds `correct_answer` from any caller who is not
 * the assessment's author, so no answer key reaches this screen.
 */
const PARENT_ASSESSMENTS: NavItem = {
  route: "parent/assessments",
  label: "Assessments",
  icon: ClipboardCheck,
  allowedRoles: ["parent"],
  status: "available",
}

/**
 * PH11.9: the parent's read-only view of Guidance Office records.
 *
 * `ConsultationRecordViewSet` and `RiskAlertViewSet` answer 403 for a parent on
 * every mutating verb and on acknowledge/escalate/resolve, so this is a reading
 * surface and the page renders no mutation control.
 */
const PARENT_SUPPORT: NavItem = {
  route: "parent/support",
  label: "Student Support",
  icon: Shield,
  allowedRoles: ["parent"],
  status: "available",
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
/**
 * PH11.9 removed the `USERS` and `SETTINGS` planned entries entirely.
 *
 * `users` became the real `admin/users` route (see `ADMIN_USERS`).
 *
 * `settings` is gone because there is no SystemSetting model, view or route
 * anywhere in the backend — the only mention is a comment in
 * `apps/attendance/views.py` saying the absence threshold "will be replaced by
 * SystemSetting lookup when CMS module is built (Phase 7)", and that never
 * happened. A planned entry for a route that cannot exist is the same
 * placeholder failure PH11.8 removed for `/app/guidance`. `Account Settings`
 * remains, and that is the real self-scoped `GET/PATCH /accounts/me/` surface.
 */

/**
 * Roadmap entry for roles with no report surface.
 *
 * PH11.9 checked for a report or export contract: the only related thing that
 * exists is the controlled CSV/XLSX export family under
 * `/data-import/exports/`, which is a file download available to
 * administrators and is surfaced as "Imports & Exports". No AcademicReport API
 * exists, so this stays planned rather than pointing at one.
 */
const REPORTS: NavItem = {
  route: "reports",
  label: "Reports",
  icon: FileText,
  allowedRoles: ["faculty", "guidance", "admin", "student"],
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
    /*
     * PH11.9 replaces this group's placeholders with real routes.
     *
     * `ATTENDANCE_PLANNED` and `ASSESSMENTS` were both planned entries kept
     * honest by having no route: a link would have bounced off `RequireRole`.
     * Both now exist at their own routes with `RequireRole` admitting `parent`,
     * so leaving them planned would tell the reader a feature is unavailable
     * when it is one click away.
     *
     * `REPORTS` stays planned. PH11.9 checked for a report contract and there
     * is none: the only related endpoints are the controlled CSV/XLSX exports
     * under `/data-import/exports/`, which are administrator file downloads,
     * not a report a parent can request.
     */
    items: [PARENT_ACADEMICS, PARENT_ASSESSMENTS, PARENT_SUPPORT, REPORTS],
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
    items: [
      ADMIN_ACADEMIC_STRUCTURE,
      ADMIN_GRADES,
      ADMIN_ATTENDANCE,
      ADMIN_ANALYTICS,
    ],
  },
  {
    heading: "School Operations",
    items: [ADMIN_USERS, ADMIN_DATA, ADMIN_CMS, ADMIN_AUDIT, REPORTS],
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

/**
 * Page title for a pathname within the /app area (used by the header).
 *
 * PH11.9 introduced nested routes (`/app/parent/academics`), so matching on
 * the first path segment alone would title that page "AEGIS". The longest
 * matching route wins, which prefers a nested item over a top-level item that
 * happens to share its prefix.
 */
export function getPageTitle(pathname: string): string {
  const path = pathname.replace(/^\/app\/?/, "").replace(/\/+$/, "")
  const segment = path.split("/")[0] ?? ""

  const allItems: readonly NavItem[] = [
    DASHBOARD,
    ACADEMICS,
    ATTENDANCE,
    ASSESSMENTS,
    GUIDANCE_ASSESSMENTS,
    REPORTS,
    RISK_ALERTS,
    CONSULTATIONS,
    INTERVENTIONS,
    STUDENTS,
    ACCOUNT_SETTINGS,
    NOTIFICATIONS,
    PARENT_ACADEMICS,
    PARENT_ASSESSMENTS,
    PARENT_SUPPORT,
    ADMIN_ACADEMIC_STRUCTURE,
    ADMIN_GRADES,
    ADMIN_ATTENDANCE,
    ADMIN_ANALYTICS,
    ADMIN_USERS,
    ADMIN_DATA,
    ADMIN_CMS,
    ADMIN_AUDIT,
  ]

  const match = allItems
    .filter((item) => path === item.route || path.startsWith(`${item.route}/`))
    .sort((a, b) => b.route.length - a.route.length)[0]

  if (match) return match.label
  return segment ? "AEGIS" : "Dashboard"
}

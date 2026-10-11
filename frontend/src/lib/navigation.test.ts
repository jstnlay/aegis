import { describe, expect, it } from "vitest"

import {
  getNavItemsForRole,
  getPageTitle,
  getVisibleNavigationForRole,
  isRouteVisibleToRole,
  itemHref,
} from "@/lib/navigation"
import { ROLES } from "@/types/auth"

describe("role navigation configuration", () => {
  it("defines navigation for every backend role", () => {
    for (const role of ROLES) {
      const groups = getVisibleNavigationForRole(role)
      expect(groups.length, role).toBeGreaterThan(0)
      expect(groups.every((g) => g.items.length > 0)).toBe(true)
    }
  })

  it("every role gets a Dashboard entry pointing at /app/dashboard", () => {
    for (const role of ROLES) {
      const items = getNavItemsForRole(role)
      const dashboard = items.find((item) => item.route === "dashboard")
      expect(dashboard, role).toBeDefined()
      expect(dashboard?.status).toBe("available")
      expect(itemHref(dashboard!)).toBe("/app/dashboard")
    }
  })

  it("only real routes are marked available", () => {
    // Every "available" route below has a real entry in `appRoutes`. Adding a
    // name here without adding the route is exactly the fake-page failure this
    // test exists to prevent.
    const REAL_AVAILABLE_ROUTES = [
      // PH11.7
      "dashboard",
      "academics",
      "attendance",
      // PH11.8
      "risk-alerts",
      "consultations",
      "interventions",
      "students",
      "assessments",
      // PH11.9: notifications and account settings, both open to all roles
      "notifications",
      "account-settings",
      // PH11.9 parent surfaces, each backed by a real route in `appRoutes`
      "parent/academics",
      "parent/assessments",
      "parent/support",
      // PH11.9 admin surfaces, likewise
      "admin/academics",
      "admin/grades",
      "admin/attendance",
      "admin/analytics",
      "admin/users",
      "admin/data",
      "admin/cms",
      "admin/audit",
      // Faculty assessments and bulk upload, each backed by a real route in `appRoutes`
      "faculty/assessments",
      "faculty/import",
      // Advisory class roster + behavioral notes (TC-FAC-07/08)
      "faculty/advisory",
      // Student assessments, likewise
      "student/assessments",
      // Student class schedule (TC-STU-04), backed by the `schedule` route
      "schedule",
      // Reports compiles the controlled exports each role is authorized for
      "reports",
    ]

    for (const role of ROLES) {
      const items = getNavItemsForRole(role)
      const available = items.filter((item) => item.status === "available")
      for (const item of available) {
        expect(REAL_AVAILABLE_ROUTES, `${role} / ${item.route}`).toContain(
          item.route
        )
      }
      expect(available.length, role).toBeGreaterThanOrEqual(1)
    }
  })

  it("available routes only link for their allowed roles", () => {
    // Academics exists for student/faculty/admin; Attendance is only a link
    // for the two roles PH11.7 implemented.
    expect(getNavItemsForRole("faculty")).toContainEqual(
      expect.objectContaining({ route: "academics", status: "available" })
    )
    // PH11.9 removed admin from this route: it served `AcademicsLandingPage`,
    // a placeholder pointing at "the Administration section of this workspace"
    // when no such routes existed. Admin now has `admin/academics`.
    expect(
      getNavItemsForRole("admin").find((i) => i.route === "academics")
    ).toBeUndefined()
    expect(getNavItemsForRole("admin")).toContainEqual(
      expect.objectContaining({
        route: "admin/academics",
        status: "available",
      })
    )
    expect(getNavItemsForRole("student")).toContainEqual(
      expect.objectContaining({ route: "academics", status: "available" })
    )

    for (const role of ["student", "faculty"] as const) {
      expect(getNavItemsForRole(role), role).toContainEqual(
        expect.objectContaining({ route: "attendance", status: "available" })
      )
    }
    // PH11.9 removed the `ATTENDANCE_PLANNED` roadmap item. Parent reached a
    // real attendance view inside `parent/academics` and admin reached one at
    // `admin/attendance`; guidance has no attendance route of its own, so it
    // gets no entry rather than a placeholder pointing at nothing.
    for (const role of ROLES) {
      expect(
        getNavItemsForRole(role).find((i) => i.route === "attendance")?.status,
        role
      ).not.toBe("planned")
    }

    const studentAvailable = getNavItemsForRole("student").filter(
      (i) => i.status === "available"
    )
    /*
     * `account-settings` and `notifications` are absent by design: the header
     * owns both surfaces (the bell and the account menu), so no sidebar tree
     * carries a second entry for either. The routes still exist and both are
     * still titled by `getPageTitle`.
     */
    expect(studentAvailable.map((i) => i.route).sort()).toEqual([
      "academics",
      "attendance",
      "dashboard",
      "reports",
      "schedule",
      "student/assessments",
    ])
  })

  it("navigation trees are role-aware", () => {
    const student = getNavItemsForRole("student").map((i) => i.route)
    const admin = getNavItemsForRole("admin").map((i) => i.route)

    // PH11.9 gave admin eight real routes.
    for (const route of [
      "admin/academics",
      "admin/grades",
      "admin/attendance",
      "admin/analytics",
      "admin/users",
      "admin/data",
      "admin/cms",
      "admin/audit",
    ]) {
      expect(admin, route).toContain(route)
    }
    // PH11.9 removed the admin Settings item: there is no SystemSetting model,
    // view or route anywhere in the backend, so the entry could only ever point
    // at a page that cannot exist.
    expect(admin).not.toContain("settings")
    // Admin is off the student/faculty academics route, which served a
    // placeholder describing implemented functionality as future work.
    expect(admin).not.toContain("academics")
    expect(student).not.toContain("admin/users")
    // PH11.7 added Academics + Attendance for students.
    expect(student).toContain("academics")
    expect(student).toContain("attendance")

    const guidance = getNavItemsForRole("guidance").map((i) => i.route)
    expect(guidance).toContain("risk-alerts")
    expect(guidance).toContain("consultations")
    expect(guidance).toContain("interventions")
    expect(guidance).toContain("students")
    // The header owns account settings, so no tree carries a second entry.
    expect(guidance).not.toContain("account-settings")
    expect(admin).not.toContain("risk-alerts")

    const parent = getNavItemsForRole("parent").map((i) => i.route)
    // PH11.9 gave parent three real routes. `attendance` is gone because the
    // attendance data lives inside `parent/academics`; a separate link would
    // duplicate it.
    expect(parent).toContain("parent/academics")
    expect(parent).toContain("parent/assessments")
    expect(parent).toContain("parent/support")
    expect(parent).not.toContain("attendance")
    // Reports is available: the controlled exports answer within a parent's
    // linked-children scope, so the page compiles only authorized downloads.
    expect(parent).toContain("reports")
    expect(parent).not.toContain("users")
    expect(parent).not.toContain("students")
  })

  /**
   * The parent routes are parent-only.
   *
   * Each reads data the backend scopes to `ParentStudentLink` children. Handing
   * one of these links to another role would show that role a page whose every
   * list is empty, or worse, a page whose selectors are built from the wrong
   * scope.
   */
  it("keeps the parent routes off every other role", () => {
    for (const role of ["student", "faculty", "guidance", "admin"] as const) {
      const available = getNavItemsForRole(role)
        .filter((i) => i.status === "available")
        .map((i) => i.route)

      for (const route of [
        "parent/academics",
        "parent/assessments",
        "parent/support",
      ]) {
        expect(available, `${role} / ${route}`).not.toContain(route)
      }
    }
  })

  it("groups with no visible items are dropped", () => {
    const student = getVisibleNavigationForRole("student")
    expect(student.some((g) => g.items.length === 0)).toBe(false)
    expect(
      student.some((g) => g.heading === "Overview" && g.items.length === 1)
    ).toBe(true)
  })
  it("gives guidance the PH11.8 surface as available links", () => {
    const guidance = getNavItemsForRole("guidance")
    for (const route of [
      "risk-alerts",
      "consultations",
      "interventions",
      "students",
      "assessments",
    ]) {
      expect(guidance, route).toContainEqual(
        expect.objectContaining({ route, status: "available" })
      )
      expect(itemHref(guidance.find((i) => i.route === route)!)).toBe(
        `/app/${route}`
      )
    }
  })

  it("keeps the guidance surface off every other role", () => {
    for (const role of ["student", "parent", "faculty", "admin"] as const) {
      const available = getNavItemsForRole(role)
        .filter((i) => i.status === "available")
        .map((i) => i.route)

      for (const route of [
        "risk-alerts",
        "consultations",
        "interventions",
        "students",
      ]) {
        expect(available, `${role} / ${route}`).not.toContain(route)
      }
      // `/app/assessments` resolves to the guidance page, so no other role may
      // be handed an available link to it.
      expect(available, role).not.toContain("assessments")
    }
  })

  /**
   * The manual-QA overhaul moved both surfaces into the header: the bell opens
   * notifications and the account menu opens account settings. A second entry
   * for either in the sidebar put the same destination two places apart on all
   * five roles.
   *
   * The routes themselves are untouched — both remain real, self-scoped
   * screens (`recipient=request.user`, and `/accounts/me/` plus
   * `/notifications/preferences/` are caller-scoped), which is what the PH11.9
   * test that used to live here was protecting. Only the entry points moved,
   * so this asserts absence from the trees rather than presence.
   */
  it("keeps notifications and account settings out of every navigation tree", () => {
    for (const role of ROLES) {
      const available = getNavItemsForRole(role)
        .filter((i) => i.status === "available")
        .map((i) => i.route)

      expect(available, role).not.toContain("notifications")
      expect(available, role).not.toContain("account-settings")
    }
  })

  it("no longer shows a Planned entry for notifications or settings", () => {
    for (const role of ROLES) {
      const planned = getNavItemsForRole(role)
        .filter((i) => i.status === "planned")
        .map((i) => i.route)

      expect(planned, role).not.toContain("notifications")
      expect(planned, role).not.toContain("account-settings")
    }
  })

  it("gives faculty a real assessments surface, guidance keeps its own", () => {
    /*
     * `/app/assessments` still resolves to the guidance page, which
     * `RequireRole` keeps guidance-only. Faculty therefore have their own route
     * at `faculty/assessments` covering the academic assessments they author,
     * and must not be sent to the guidance path by the shared planned entry.
     *
     * The split mirrors `Assessment.clean()`: academic requires
     * creator_role="faculty", wellness and behavioral require
     * creator_role="guidance", so the two surfaces cannot overlap.
     */
    const facultyItem = getNavItemsForRole("faculty").find(
      (i) => i.route === "faculty/assessments"
    )
    expect(facultyItem).toBeDefined()
    expect(facultyItem?.status).toBe("available")

    // The shared planned entry no longer reaches faculty.
    expect(
      getNavItemsForRole("faculty").find((i) => i.route === "assessments")
    ).toBeUndefined()

    const guidanceItem = getNavItemsForRole("guidance").find(
      (i) => i.route === "assessments"
    )
    expect(guidanceItem?.status).toBe("available")
  })

  it("does not route guidance or other roles to the faculty assessments page", () => {
    for (const role of ["guidance", "admin", "student", "parent"] as const) {
      expect(
        getNavItemsForRole(role).find((i) => i.route === "faculty/assessments"),
        role
      ).toBeUndefined()
    }
  })

  /**
   * Admin has a real assessment surface, so the planned placeholder is gone.
   *
   * `AssessmentViewSet.get_queryset()` returns the full table for `admin` and
   * `IsAssessmentCreator` grants admins full object-level authority over every
   * assessment, so admin reads the same endpoint guidance authors through. A
   * planned entry for a capability that exists is the placeholder failure this
   * module's tests exist to catch.
   */
  it("gives admin a real assessments link", () => {
    expect(
      getNavItemsForRole("admin").find((i) => i.route === "assessments")
    ).toBeUndefined()
  })

  it("has no /app/guidance nav item at all", () => {
    // PH11.8 removed the legacy GUIDANCE item entirely. `/app/guidance` is not
    // a page and is left unregistered, so a nav entry could only ever be a
    // placeholder pointing at a 404.
    for (const role of ROLES) {
      expect(
        getNavItemsForRole(role).find((i) => i.route === "guidance"),
        role
      ).toBeUndefined()
    }
  })

  it("still keeps the guidance dashboard reachable", () => {
    // Removing the /app/guidance placeholder must not disturb the real
    // /app/dashboard/guidance landing page.
    for (const role of ROLES) {
      const dashboard = getNavItemsForRole(role).find(
        (i) => i.route === "dashboard"
      )
      expect(dashboard?.status, role).toBe("available")
    }
  })
})

describe("route visibility", () => {
  it("follows the resolved role navigation", () => {
    expect(isRouteVisibleToRole("admin", "dashboard")).toBe(true)
    expect(isRouteVisibleToRole("admin", "admin/users")).toBe(true)
    expect(isRouteVisibleToRole("student", "academics")).toBe(true)
    expect(isRouteVisibleToRole("parent", "admin/users")).toBe(false)
    expect(isRouteVisibleToRole("student", "settings")).toBe(false)
    expect(isRouteVisibleToRole("guidance", "risk-alerts")).toBe(true)
    expect(isRouteVisibleToRole("guidance", "assessments")).toBe(true)
    expect(isRouteVisibleToRole("parent", "parent/support")).toBe(true)
    expect(isRouteVisibleToRole("student", "parent/support")).toBe(false)
  })

  /**
   * Each role's own routes are visible only to that role.
   *
   * The parent and admin routes read data the backend scopes by role or by
   * `ParentStudentLink` children, so handing one of these links to another role
   * would show a page whose every list is empty at best.
   */
  it("keeps the admin routes off every other role", () => {
    for (const role of ["student", "parent", "faculty", "guidance"] as const) {
      const available = getNavItemsForRole(role)
        .filter((i) => i.status === "available")
        .map((i) => i.route)

      for (const route of [
        "admin/academics",
        "admin/grades",
        "admin/attendance",
        "admin/analytics",
        "admin/users",
        "admin/data",
        "admin/cms",
        "admin/audit",
      ]) {
        expect(available, `${role} / ${route}`).not.toContain(route)
      }
    }
  })

  it("keeps the parent routes off every other role", () => {
    for (const role of ["student", "faculty", "guidance", "admin"] as const) {
      const available = getNavItemsForRole(role)
        .filter((i) => i.status === "available")
        .map((i) => i.route)

      for (const route of [
        "parent/academics",
        "parent/assessments",
        "parent/support",
      ]) {
        expect(available, `${role} / ${route}`).not.toContain(route)
      }
    }
  })

  /**
   * The class schedule (TC-STU-04) is student-only.
   *
   * `ScheduleViewSet` does return rows for every role, but the other roles
   * already read the same timetable inside their own surfaces (faculty
   * academics, parent/academics), so a second link for them would duplicate a
   * screen rather than add one.
   */
  it("keeps the schedule route student-only", () => {
    expect(
      getNavItemsForRole("student").find((i) => i.route === "schedule")
    ).toEqual(expect.objectContaining({ status: "available" }))

    for (const role of ["parent", "faculty", "guidance", "admin"] as const) {
      expect(
        getNavItemsForRole(role).find((i) => i.route === "schedule"),
        role
      ).toBeUndefined()
    }
  })

  /**
   * The advisory class surface (TC-FAC-07 / TC-FAC-08) is faculty-only.
   *
   * Both endpoints behind it are scoped to the faculty role server-side
   * (`EnrollmentViewSet` for the roster, `IsFacultyUser` for note creation),
   * so a link for any other role could only ever land on a restricted page.
   */
  it("keeps the advisory route faculty-only", () => {
    expect(
      getNavItemsForRole("faculty").find((i) => i.route === "faculty/advisory")
    ).toEqual(expect.objectContaining({ status: "available" }))

    for (const role of ["student", "parent", "guidance", "admin"] as const) {
      expect(
        getNavItemsForRole(role).find((i) => i.route === "faculty/advisory"),
        role
      ).toBeUndefined()
    }
  })
})

describe("page titles from navigation", () => {
  it("resolves the dashboard title", () => {
    expect(getPageTitle("/app/dashboard")).toBe("Dashboard")
    expect(getPageTitle("/app")).toBe("Dashboard")
  })

  it("resolves known route titles", () => {
    expect(getPageTitle("/app/academics")).toBe("Academics")
    expect(getPageTitle("/app/attendance")).toBe("Attendance")
    // TC-STU-04: the schedule route must title itself, or the header above the
    // page falls back to "Dashboard" while the body renders the timetable.
    expect(getPageTitle("/app/schedule")).toBe("Schedule")
    // TC-FAC-07/08: the advisory route must do the same, or the header reads
    // "Faculty Dashboard" while the body shows the class list.
    expect(getPageTitle("/app/faculty/advisory")).toBe("Advisory Class")
  })

  /**
   * PH11.9 introduced nested routes. Matching on the first path segment alone
   * would title every parent page "AEGIS", because the header resolves the
   * title from the pathname.
   */
  it("resolves nested parent route titles", () => {
    expect(getPageTitle("/app/parent/academics")).toBe("Academic Record")
    expect(getPageTitle("/app/parent/assessments")).toBe("Assessments")
    expect(getPageTitle("/app/parent/support")).toBe("Student Support")
  })

  it("still titles the top-level routes correctly now that nesting exists", () => {
    // The longest-match rule must not let `parent/assessments` shadow the
    // guidance `/app/assessments`, or `students` lose its title.
    expect(getPageTitle("/app/assessments")).toBe("Assessments")
    expect(getPageTitle("/app/students")).toBe("Students")
    expect(getPageTitle("/app/account-settings")).toBe("Account Settings")
  })

  it("falls back for unknown routes", () => {
    const fallback = getPageTitle("/app/does-not-exist")
    expect(["AEGIS", "Dashboard"]).toContain(fallback)
  })
})

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
    expect(getNavItemsForRole("admin")).toContainEqual(
      expect.objectContaining({ route: "academics", status: "available" })
    )
    expect(getNavItemsForRole("student")).toContainEqual(
      expect.objectContaining({ route: "academics", status: "available" })
    )

    for (const role of ["student", "faculty"] as const) {
      expect(getNavItemsForRole(role), role).toContainEqual(
        expect.objectContaining({ route: "attendance", status: "available" })
      )
    }
    // Parent/admin attendance stays planned — no verified surface yet.
    for (const role of ["parent", "admin"] as const) {
      const attendance = getNavItemsForRole(role).find(
        (i) => i.route === "attendance"
      )
      expect(attendance, role).toBeDefined()
      expect(attendance?.status, role).toBe("planned")
    }

    const studentAvailable = getNavItemsForRole("student").filter(
      (i) => i.status === "available"
    )
    expect(studentAvailable.map((i) => i.route).sort()).toEqual([
      "academics",
      "account-settings",
      "attendance",
      "dashboard",
      "notifications",
    ])
  })

  it("navigation trees are role-aware", () => {
    const student = getNavItemsForRole("student").map((i) => i.route)
    const admin = getNavItemsForRole("admin").map((i) => i.route)

    expect(admin).toContain("users")
    expect(admin).toContain("settings")
    expect(admin).toContain("academics")
    expect(student).not.toContain("users")
    expect(student).not.toContain("settings")
    // PH11.7 added Academics + Attendance for students.
    expect(student).toContain("academics")
    expect(student).toContain("attendance")

    const guidance = getNavItemsForRole("guidance").map((i) => i.route)
    expect(guidance).toContain("risk-alerts")
    expect(guidance).toContain("consultations")
    expect(guidance).toContain("interventions")
    expect(guidance).toContain("students")
    expect(guidance).toContain("account-settings")
    expect(admin).not.toContain("risk-alerts")

    const parent = getNavItemsForRole("parent").map((i) => i.route)
    expect(parent).toContain("attendance")
    expect(parent).toContain("reports")
    expect(parent).not.toContain("users")
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
      "account-settings",
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
   * PH11.9 opened two surfaces to every role.
   *
   * Neither can reach another account: `/notifications/` is
   * `recipient=request.user`, and `/accounts/me/` plus
   * `/notifications/preferences/` are both caller-scoped. That is what makes
   * an all-role link safe here, as opposed to the guidance resources above,
   * which stay role-scoped because they address *other* students.
   */
  it("gives every role notifications and account settings as real links", () => {
    for (const role of ROLES) {
      const available = getNavItemsForRole(role)
        .filter((i) => i.status === "available")
        .map((i) => i.route)

      expect(available, role).toContain("notifications")
      expect(available, role).toContain("account-settings")
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

  it("keeps faculty and admin assessments planned and guidance-only", () => {
    for (const role of ["faculty", "admin"] as const) {
      const item = getNavItemsForRole(role).find(
        (i) => i.route === "assessments"
      )
      expect(item, role).toBeDefined()
      expect(item?.status, role).toBe("planned")
    }

    const guidanceItem = getNavItemsForRole("guidance").find(
      (i) => i.route === "assessments"
    )
    expect(guidanceItem?.status).toBe("available")
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
    expect(isRouteVisibleToRole("admin", "academics")).toBe(true)
    expect(isRouteVisibleToRole("student", "academics")).toBe(true)
    expect(isRouteVisibleToRole("parent", "users")).toBe(false)
    expect(isRouteVisibleToRole("student", "settings")).toBe(false)
    expect(isRouteVisibleToRole("guidance", "risk-alerts")).toBe(true)
    expect(isRouteVisibleToRole("student", "assessments")).toBe(true)
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
  })

  it("falls back for unknown routes", () => {
    const fallback = getPageTitle("/app/does-not-exist")
    expect(["AEGIS", "Dashboard"]).toContain(fallback)
  })
})

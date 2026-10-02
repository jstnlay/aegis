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
    // Dashboard, Academics and Attendance have real routes (PH11.7).
    // Everything else must stay honest "planned" state — no fake pages are
    // created behind nav links.
    for (const role of ROLES) {
      const items = getNavItemsForRole(role)
      const available = items.filter((item) => item.status === "available")
      for (const item of available) {
        expect(
          ["dashboard", "academics", "attendance"],
          `${role} / ${item.route}`
        ).toContain(item.route)
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
      "attendance",
      "dashboard",
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
    expect(guidance).toContain("guidance")
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

import { describe, expect, it } from "vitest"

import {
  ROLE_LABELS,
  hasRole,
  isAdmin,
  isRole,
  userDisplayName,
} from "@/lib/roles"
import { ROLES, type Role, type User } from "@/types/auth"

const baseUser: User = {
  id: "u-1",
  email: "student@school.edu",
  username: "student1",
  first_name: "Ana",
  last_name: "Cruz",
  role: "student",
  phone_number: null,
  address: null,
  language_preference: null,
  is_active: true,
  created_at: "2025-01-01T00:00:00Z",
  updated_at: "2025-01-01T00:00:00Z",
}

describe("human-readable role labels", () => {
  it("maps every backend role to a human-readable label", () => {
    const expected: Record<Role, string> = {
      student: "Student",
      parent: "Parent",
      faculty: "Faculty",
      guidance: "Guidance Counselor",
      admin: "Administrator",
    }
    for (const role of ROLES) {
      expect(ROLE_LABELS[role], role).toBe(expected[role])
    }
  })

  it("never uses the backend identifier as the display label", () => {
    for (const role of ROLES) {
      expect(ROLE_LABELS[role]).not.toBe(role)
    }
  })
})

describe("role helpers", () => {
  it("isRole / isAdmin / hasRole behave correctly", () => {
    const admin: User = { ...baseUser, role: "admin" }
    expect(isRole(admin, "admin")).toBe(true)
    expect(isRole(admin, "student")).toBe(false)
    expect(isAdmin(admin)).toBe(true)
    expect(isAdmin(null)).toBe(false)
    expect(hasRole(admin, ["admin", "guidance"])).toBe(true)
    expect(hasRole(admin, ["student"])).toBe(false)
    expect(hasRole(null, ["admin"])).toBe(false)
  })
})

describe("userDisplayName", () => {
  it("joins first and last name", () => {
    expect(userDisplayName(baseUser)).toBe("Ana Cruz")
  })

  it("falls back to email when names are absent", () => {
    const user: User = {
      ...baseUser,
      first_name: "",
      last_name: "",
    }
    expect(userDisplayName(user)).toBe(user.email)
  })

  it("returns an empty string for no user", () => {
    expect(userDisplayName(null)).toBe("")
    expect(userDisplayName(undefined)).toBe("")
  })
})

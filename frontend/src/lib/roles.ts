import type { Role, User } from "@/types/auth"

/**
 * Role / permission foundation.
 *
 * Frontend guards improve UX only — they DO NOT replace backend
 * authorization (see core/permissions.py). Server rules remain
 * authoritative.
 */

export const ROLE_LABELS: Record<Role, string> = {
  student: "Student",
  parent: "Parent",
  faculty: "Faculty",
  guidance: "Guidance Counselor",
  admin: "Administrator",
}

export function isRole(user: User | null | undefined, role: Role): boolean {
  return user?.role === role
}

/** True when the user has one of the allowed roles. */
export function hasRole(
  user: User | null | undefined,
  allowedRoles: readonly Role[]
): boolean {
  if (!user) return false
  return allowedRoles.includes(user.role)
}

export function isAdmin(user: User | null | undefined): boolean {
  return isRole(user, "admin")
}

export function userDisplayName(user: User | null | undefined): string {
  if (!user) return ""
  if (user.first_name || user.last_name) {
    return [user.first_name, user.last_name].filter(Boolean).join(" ").trim()
  }
  return user.email
}

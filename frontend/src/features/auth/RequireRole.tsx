import { Navigate } from "react-router-dom"
import type { ReactNode } from "react"

import { LoadingScreen } from "@/components/layout/LoadingScreen"
import { AccessRestricted } from "@/features/auth/AccessRestricted"
import { useAuth } from "@/features/auth/AuthContext"
import { hasRole } from "@/lib/roles"
import type { Role } from "@/types/auth"

/**
 * Role gate (foundation).
 *
 * Guards improve UX; the backend remains the authorization authority
 * (core/permissions.py).
 *
 * A role mismatch no longer redirects silently: the URL *is* the answer to
 * "where was I trying to go", so it is kept and `AccessRestricted` explains
 * the mismatch in place (TC-SYS-07 / TC-STU-09). A missing session still
 * redirects — that is a different problem with its own page.
 */
export function RequireRole({
  allowedRoles,
  children,
}: {
  allowedRoles: readonly Role[]
  children: ReactNode
}) {
  const { status, user } = useAuth()

  if (status === "loading") {
    return <LoadingScreen />
  }

  if (!user) {
    return <Navigate to="/login" replace />
  }

  if (!hasRole(user, allowedRoles)) {
    return <AccessRestricted allowedRoles={allowedRoles} />
  }

  return children
}

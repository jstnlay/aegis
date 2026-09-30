import { Navigate } from "react-router-dom"
import type { ReactNode } from "react"

import { LoadingScreen } from "@/components/layout/LoadingScreen"
import { useAuth } from "@/features/auth/AuthContext"
import { hasRole } from "@/lib/roles"
import type { Role } from "@/types/auth"

/**
 * Role gate (foundation).
 *
 * Guards improve UX; the backend remains the authorization authority
 * (core/permissions.py). Unauthorized users are sent to the app home.
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

  if (!user || !hasRole(user, allowedRoles)) {
    return <Navigate to="/app" replace />
  }

  return children
}

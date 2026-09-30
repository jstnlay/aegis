import { Navigate, Outlet, useLocation } from "react-router-dom"

import { LoadingScreen } from "@/components/layout/LoadingScreen"
import { useAuth } from "@/features/auth/AuthContext"

/**
 * Authenticated application boundary.
 *
 * - redirects unauthenticated users to /login
 * - redirects onboarded (must-change-password) users to /change-password
 * - renders the protected subtree for authenticated users
 */
export function ProtectedRoute() {
  const { status, mustChangePassword } = useAuth()
  const location = useLocation()

  if (status === "loading") {
    return <LoadingScreen />
  }

  if (status === "unauthenticated") {
    return <Navigate to="/login" replace state={{ from: location }} />
  }

  if (mustChangePassword) {
    return <Navigate to="/change-password" replace state={{ from: location }} />
  }

  return <Outlet />
}

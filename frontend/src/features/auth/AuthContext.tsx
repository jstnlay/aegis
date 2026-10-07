import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react"

import { onSessionExpired } from "@/lib/api"
import { tokenStorage } from "@/lib/auth-storage"
import { normalizeApiError } from "@/lib/error"
import { queryClient } from "@/lib/queryClient"
import type { User } from "@/types/auth"
import {
  changePasswordRequest,
  fetchCurrentUser,
  loginRequest,
  logoutRequest,
  restorePersistedTokens,
} from "@/features/auth/api"

export type AuthStatus =
  "loading" | "unauthenticated" | "authenticated" | "restricted"

/**
 * `restricted` = authenticated with `must_change_password` (PH8.7):
 * the backend only allows password change + logout until onboarding
 * completes, so the rest of the app must be kept away.
 */
export interface AuthContextValue {
  status: AuthStatus
  user: User | null
  mustChangePassword: boolean
  isAuthenticated: boolean
  /**
   * True when the session ended by expiring, as opposed to the user signing out.
   *
   * PH11.11. Expiry and sign-out are indistinguishable in the UI without it: both
   * clear the tokens and set `unauthenticated`, and `ProtectedRoute` sends both to
   * `/login`. A user whose refresh token expired mid-task was therefore dropped on
   * a sign-in form that said nothing about why, with no sign that unsaved work was
   * lost and nothing to tell them whether signing in again will just work. This
   * lets `LoginPage` state the cause once, and it is cleared as soon as the user
   * signs in, so the explanation cannot outlive the event.
   */
  sessionExpired: boolean
  login: (email: string, password: string) => Promise<void>
  logout: () => Promise<void>
  changePassword: (
    currentPassword: string,
    newPassword: string
  ) => Promise<void>
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<AuthStatus>("loading")
  const [user, setUser] = useState<User | null>(null)
  const [mustChangePassword, setMustChangePassword] = useState(false)
  const [sessionExpired, setSessionExpired] = useState(false)

  useEffect(() => {
    let cancelled = false

    async function bootstrap() {
      if (!restorePersistedTokens()) {
        if (!cancelled) setStatus("unauthenticated")
        return
      }

      try {
        const currentUser = await fetchCurrentUser()
        if (cancelled) return
        setUser(currentUser)
        setMustChangePassword(false)
        setStatus("authenticated")
      } catch (error) {
        if (cancelled) return
        const normalized = normalizeApiError(error)
        if (normalized.isPasswordChangeRequired) {
          setMustChangePassword(true)
          setStatus("restricted")
          return
        }
        tokenStorage.clear()
        setUser(null)
        setStatus("unauthenticated")
      }
    }

    void bootstrap()

    /*
     * PH11.11. The silent-refresh flow gives up here: `onSessionExpired` fires
     * only after a refresh has actually failed, so the tokens are gone and no
     * further request can succeed. Two things were wrong for the user:
     *
     * 1. The cached query data was left in place. `logout` clears the query
     *    client; this path did not, so the next person to sign in on this browser
     *    could be served the previous user's cached dashboards from react-query's
     *    memory cache until each one happened to refetch. Every query key here is
     *    role-scoped but not user-scoped, so those keys really do collide.
     * 2. The transition was indistinguishable from a sign-out, so the sign-in
     *    page could not say why the user was back there.
     */
    const unsubscribe = onSessionExpired(() => {
      if (cancelled) return
      queryClient.clear()
      setUser(null)
      setMustChangePassword(false)
      setSessionExpired(true)
      setStatus("unauthenticated")
    })

    return () => {
      cancelled = true
      unsubscribe()
    }
  }, [])

  const login = useCallback(async (email: string, password: string) => {
    const response = await loginRequest(email, password)
    tokenStorage.setTokens(response.access, response.refresh)
    setMustChangePassword(response.must_change_password)
    // Cleared here rather than on the failure path: the explanation belongs to
    // the sign-in form, so it must not survive a successful sign-in and reappear
    // if a later one fails for an unrelated reason.
    setSessionExpired(false)

    if (response.must_change_password) {
      setUser(null)
      setStatus("restricted")
      return
    }

    try {
      const currentUser = await fetchCurrentUser()
      setUser(currentUser)
      setMustChangePassword(false)
      setStatus("authenticated")
    } catch (error) {
      const normalized = normalizeApiError(error)

      if (normalized.isPasswordChangeRequired) {
        setUser(null)
        setMustChangePassword(true)
        setStatus("restricted")
        return
      }

      tokenStorage.clear()
      setUser(null)
      setMustChangePassword(false)
      setStatus("unauthenticated")
    }
  }, [])

  const logout = useCallback(async () => {
    const refresh = tokenStorage.getRefreshToken()
    try {
      if (refresh) await logoutRequest(refresh)
    } catch {
      // Logout is best-effort: clear local state regardless of server response.
    }
    tokenStorage.clear()
    setUser(null)
    setMustChangePassword(false)
    setSessionExpired(false)
    setStatus("unauthenticated")
    queryClient.clear()
  }, [])

  const changePassword = useCallback(
    async (currentPassword: string, newPassword: string) => {
      await changePasswordRequest({
        current_password: currentPassword,
        new_password: newPassword,
      })
      try {
        const currentUser = await fetchCurrentUser()
        setUser(currentUser)
        setMustChangePassword(false)
        setStatus("authenticated")
      } catch (error) {
        const normalized = normalizeApiError(error)

        if (normalized.isPasswordChangeRequired) {
          setUser(null)
          setMustChangePassword(true)
          setStatus("restricted")
          return
        }

        tokenStorage.clear()
        setUser(null)
        setMustChangePassword(false)
        setStatus("unauthenticated")
      }
    },
    []
  )

  const value = useMemo<AuthContextValue>(
    () => ({
      status,
      user,
      mustChangePassword,
      isAuthenticated: status === "authenticated",
      sessionExpired,
      login,
      logout,
      changePassword,
    }),
    [
      status,
      user,
      mustChangePassword,
      sessionExpired,
      login,
      logout,
      changePassword,
    ]
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error("useAuth must be used within <AuthProvider>")
  }
  return context
}

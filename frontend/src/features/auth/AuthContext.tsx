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

    const unsubscribe = onSessionExpired(() => {
      if (cancelled) return
      setUser(null)
      setMustChangePassword(false)
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
      login,
      logout,
      changePassword,
    }),
    [status, user, mustChangePassword, login, logout, changePassword]
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

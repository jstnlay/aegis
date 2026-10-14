import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react"

import { onSessionExpired } from "@/lib/api"
import {
  ACCESS_TOKEN_STORAGE_KEY,
  accessTokenAccountId,
  tokenStorage,
} from "@/lib/auth-storage"
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
 * Why this tab is back at the sign-in page without having signed out.
 *
 * `"expiry"` — the silent-refresh flow gave up, so the tokens are gone.
 * `"other-account"` — a different account signed in on this browser and
 * replaced the shared token pair (see the storage listener in the provider).
 *
 * The two read very differently to the person affected, and only one of them
 * means "your credentials aged out".
 */
export type SessionEndReason = "expiry" | "other-account"

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
   * True when this tab lost a session it had, rather than the user signing
   * out. Kept as the boolean the rest of the app reads; `sessionEndedBy` is
   * the reason behind it.
   */
  sessionExpired: boolean
  /**
   * Which of the two causes ended the session, or `null` when the user signed
   * out (or never signed in). Lets `LoginPage` say what actually happened
   * instead of one sentence that has to cover both.
   */
  sessionEndedBy: SessionEndReason | null
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
  const [sessionEndedBy, setSessionEndedBy] = useState<SessionEndReason | null>(
    null
  )
  const sessionExpired = sessionEndedBy !== null

  /**
   * Drops this tab's view of a session that is no longer usable.
   *
   * PH11 QA cycle 2 (TC-GUI-05). Two accounts signed in on one browser
   * "combined without authentication": the tab still rendered the first
   * account's UI and cached rows while its requests went out carrying the
   * second account's bearer token, which is how a counselor got
   * "You do not have permission to perform this action." for a control their
   * own role allows. The backend was right to refuse — the request really was
   * the student's.
   *
   * Deliberately does NOT clear `tokenStorage` on the `"other-account"` path:
   * the pair in storage belongs to the account that just signed in, and
   * removing it would sign *them* out too. This tab only gives up its own
   * state — the React user and the query cache, whose keys are role-scoped but
   * not user-scoped and therefore collide between accounts.
   */
  const endSession = useCallback((reason: SessionEndReason) => {
    queryClient.clear()
    setUser(null)
    setMustChangePassword(false)
    setSessionEndedBy(reason)
    setStatus("unauthenticated")
  }, [])

  /**
   * The account this tab believes it is, for the cross-tab listener below.
   *
   * The listener is registered once, so it reads the subject through a ref
   * rather than closing over `user` and being torn down on every sign-in.
   */
  const signedInAccountRef = useRef<string | null>(null)
  useEffect(() => {
    signedInAccountRef.current = user?.id ?? null
  }, [user])

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
     * PH11.11, extended by PH11 QA cycle 2 (TC-GUI-05). The silent-refresh
     * flow gives up here: `onSessionExpired` fires only after a refresh has
     * actually failed, so the tokens are gone and no further request can
     * succeed. `endSession` covers both things that were wrong for the user:
     *
     * 1. The cached query data is cleared. `logout` clears the query client;
     *    this path did not, so the next person to sign in on this browser could
     *    be served the previous user's cached dashboards from react-query's
     *    memory cache until each one happened to refetch. Every query key here
     *    is role-scoped but not user-scoped, so those keys really do collide.
     * 2. The transition is explainable, so the sign-in page can say why the
     *    user is back there.
     */
    /*
     * PH11 QA cycle 2 (TC-GUI-05): another tab replaced the shared session.
     *
     * `tokenStorage` holds one bearer pair per origin under a fixed key pair,
     * so a sign-in anywhere on this browser overwrites the session everywhere
     * — there is no per-tab token to keep the accounts apart, and the frozen
     * API contract offers nothing server-side to distinguish them. A tab that
     * was mid-task kept its React state (still the first account) and kept
     * serving that account's cached dashboards while every request it issued
     * was authenticated as the second. `storage` is the only signal that the
     * slot changed hands, and it is what makes the tab stop acting as somebody
     * it is not.
     *
     * The event fires only in *other* tabs, which is exactly right: the tab
     * that just signed in updates its own state through `login`.
     */
    function onTokenStorageChanged(event: StorageEvent) {
      // Every other key is unrelated local state (the archived-items filter,
      // the mobile drawer). Only the bearer pair matters here.
      if (event.key !== ACCESS_TOKEN_STORAGE_KEY) return

      const mine = signedInAccountRef.current
      // This tab was never signed in as anyone, so there is no session of ours
      // for another tab to have replaced.
      if (!mine) return

      if (event.newValue) {
        const subject = accessTokenAccountId(event.newValue)
        // Unreadable is left alone: it is far more likely a shape this reader
        // does not understand than a different account, and signing a user out
        // of a session that is still theirs is the worse failure.
        if (subject !== null && subject !== mine) {
          endSession("other-account")
        }
        // Same subject, or unknown: a silent refresh rotated our own pair.
        return
      }

      // The pair was removed — another tab signed out on this browser. Our own
      // tokens went with it; without this the tab kept rendering the previous
      // account's cached data until the first request happened to 401.
      endSession("expiry")
    }

    window.addEventListener("storage", onTokenStorageChanged)

    const unsubscribe = onSessionExpired(() => {
      if (cancelled) return
      endSession("expiry")
    })

    return () => {
      cancelled = true
      window.removeEventListener("storage", onTokenStorageChanged)
      unsubscribe()
    }
  }, [endSession])

  const login = useCallback(async (email: string, password: string) => {
    const response = await loginRequest(email, password)
    tokenStorage.setTokens(response.access, response.refresh)
    /*
     * PH11 QA cycle 2 (TC-GUI-05): sign-in starts from an empty cache.
     *
     * `logout` and the session-expiry path already clear the query client;
     * `login` did not, so a second account signing in on the same browser was
     * served the first account's cached dashboards for up to `staleTime`
     * (60 s) — and `AccountSettingsPage` was seeded from their cached
     * `/accounts/me/` profile. Every query key is role-scoped but not
     * user-scoped, so those keys really do collide, which is the same defect
     * the session-expiry comment below describes from the other direction.
     *
     * Cleared only once the new tokens are stored: if the sign-in fails, the
     * account that was already signed in keeps its cache.
     */
    queryClient.clear()
    setMustChangePassword(response.must_change_password)
    // Cleared here rather than on the failure path: the explanation belongs to
    // the sign-in form, so it must not survive a successful sign-in and reappear
    // if a later one fails for an unrelated reason.
    setSessionEndedBy(null)

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
    setSessionEndedBy(null)
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
      sessionEndedBy,
      login,
      logout,
      changePassword,
    }),
    [
      status,
      user,
      mustChangePassword,
      sessionExpired,
      sessionEndedBy,
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

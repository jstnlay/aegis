import { LogOut, Menu } from "lucide-react"
import { useLocation } from "react-router-dom"

import { Button } from "@/components/ui/button"
import { useAuth } from "@/features/auth/AuthContext"
import { getPageTitle } from "@/lib/navigation"
import { ROLE_LABELS, userDisplayName } from "@/lib/roles"

/**
 * Shared application header (PH11.5).
 *
 * Shows the current page title (from the centralized navigation config),
 * the authenticated user's name and role, and a sign-out action.
 */

/**
 * The id of the primary navigation the hamburger button controls.
 *
 * Shared between `Header` (which sets `aria-controls`) and `Sidebar` (which
 * renders the `id`), so the association cannot drift apart when either changes.
 */
export const PRIMARY_NAV_ID = "primary-navigation"

function UserChip() {
  const { user, logout } = useAuth()
  const name = userDisplayName(user)
  const initials = name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? "")
    .join("")

  return (
    <div className="flex items-center gap-2">
      <div className="hidden min-w-0 text-right sm:block">
        <p className="truncate text-sm leading-tight font-medium text-foreground">
          {name || "Signed in"}
        </p>
        <p className="truncate text-xs leading-tight text-muted-foreground">
          {user ? ROLE_LABELS[user.role] : ""}
        </p>
      </div>

      <span
        aria-hidden="true"
        className="flex size-9 shrink-0 items-center justify-center rounded-full bg-primary text-sm font-semibold text-primary-foreground"
      >
        {initials || "—"}
      </span>

      <Button
        variant="ghost"
        size="icon"
        onClick={() => void logout()}
        aria-label="Sign out"
        className="text-muted-foreground"
      >
        <LogOut aria-hidden="true" />
      </Button>
    </div>
  )
}

export function Header({
  onMenuClick,
  menuOpen = false,
  menuButtonRef,
}: {
  onMenuClick: () => void
  /** Whether the mobile navigation drawer is currently open. */
  menuOpen?: boolean
  /**
   * Ref to the hamburger button, so `AppShell` can return focus to it when the
   * drawer closes. See the focus-restoration effect there.
   */
  menuButtonRef?: React.Ref<HTMLButtonElement>
}) {
  const location = useLocation()
  const pageTitle = getPageTitle(location.pathname)

  return (
    <header className="sticky top-0 z-30 flex h-14 shrink-0 items-center gap-3 border-b border-border bg-background px-4 lg:px-6">
      {/*
        PH11.11: `aria-expanded` and `aria-controls` were added. The control
        opened and closed the drawer but reported no state, so a screen-reader
        user activating it got no confirmation that anything had changed and had
        no way to associate the button with the region it governs. `aria-controls`
        points at the `<nav id>` the drawer contains.
      */}
      <Button
        ref={menuButtonRef}
        variant="ghost"
        size="icon"
        className="lg:hidden"
        onClick={onMenuClick}
        aria-label="Open navigation"
        aria-expanded={menuOpen}
        aria-controls={PRIMARY_NAV_ID}
      >
        <Menu aria-hidden="true" />
      </Button>

      {/*
        The document's `h1` since PH11.11. The header renders the page title for
        every route, so it is the one place that can own the document's top-level
        heading; each page's own title sits one level below it as an `h2`, which
        is what removed the two-`h1` duplication this file previously caused on
        all twenty-nine in-shell pages.
      */}
      <h1 className="min-w-0 flex-1 truncate text-lg font-semibold text-foreground">
        {pageTitle}
      </h1>

      <UserChip />
    </header>
  )
}

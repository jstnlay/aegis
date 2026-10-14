import { Bell, LogOut, Menu, Settings } from "lucide-react"
import { useEffect, useRef, useState } from "react"
import { Link, useLocation } from "react-router-dom"

import { Button } from "@/components/ui/button"
import { useAuth } from "@/features/auth/AuthContext"
import { useUnreadCount } from "@/features/notifications/api"
import { getPageTitle } from "@/lib/navigation"
import { ROLE_LABELS, userDisplayName } from "@/lib/roles"

/**
 * Shared application header (PH11.5).
 *
 * Shows the current page title (from the centralized navigation config),
 * the bell, and the account menu (Settings, Sign out).
 *
 * The menu deliberately has no "Profile" entry: the app has no self-profile
 * page — the account surface is `GET/PATCH /accounts/me/`, which the Settings
 * entry opens. A Profile item would have to point at some other screen, and
 * it previously pointed at Notifications, which is a destination that does not
 * match its label.
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
  const unread = useUnreadCount()
  const [menuOpen, setMenuOpen] = useState(false)
  const menuRef = useRef<HTMLDivElement>(null)
  const name = userDisplayName(user)
  const initials = name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? "")
    .join("")

  useEffect(() => {
    if (!menuOpen) return
    function onPointerDown(event: PointerEvent) {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setMenuOpen(false)
      }
    }
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") setMenuOpen(false)
    }
    document.addEventListener("pointerdown", onPointerDown)
    document.addEventListener("keydown", onKeyDown)
    return () => {
      document.removeEventListener("pointerdown", onPointerDown)
      document.removeEventListener("keydown", onKeyDown)
    }
  }, [menuOpen])

  return (
    <div className="flex items-center gap-1">
      <Button
        variant="ghost"
        size="icon"
        asChild
        aria-label={
          unread > 0 ? `Notifications, ${unread} unread` : "Notifications"
        }
        className="relative text-muted-foreground"
      >
        <Link to="/app/notifications">
          <Bell aria-hidden="true" />
          {unread > 0 && (
            <span
              aria-hidden="true"
              className="absolute top-1 right-1 size-2 rounded-full bg-destructive"
            />
          )}
        </Link>
      </Button>

      <div ref={menuRef} className="relative">
        <button
          type="button"
          onClick={() => setMenuOpen((open) => !open)}
          aria-expanded={menuOpen}
          aria-haspopup="menu"
          aria-label="Account menu"
          className="flex items-center gap-2 rounded-md px-1 py-1 hover:bg-accent"
        >
          <span className="hidden min-w-0 text-right sm:block">
            <span className="block truncate text-sm leading-tight font-medium text-foreground">
              {name || "Signed in"}
            </span>
            <span className="block truncate text-xs leading-tight text-muted-foreground">
              {user ? ROLE_LABELS[user.role] : ""}
            </span>
          </span>
          <span
            aria-hidden="true"
            className="flex size-9 shrink-0 items-center justify-center rounded-full bg-primary text-sm font-semibold text-primary-foreground"
          >
            {initials || "—"}
          </span>
        </button>

        {menuOpen && (
          <div
            role="menu"
            aria-label="Account"
            className="absolute right-0 z-50 mt-2 w-48 rounded-md border border-border bg-popover py-1 shadow-md"
          >
            <div className="px-3 py-2">
              <p className="truncate text-sm font-medium">
                {name || "Signed in"}
              </p>
              <p className="truncate text-xs text-muted-foreground">
                {user ? ROLE_LABELS[user.role] : ""}
              </p>
            </div>
            <Link
              to="/app/account-settings"
              role="menuitem"
              onClick={() => setMenuOpen(false)}
              className="flex items-center gap-2 px-3 py-2 text-sm hover:bg-accent"
            >
              <Settings aria-hidden="true" className="size-4" />
              Settings
            </Link>
            <button
              type="button"
              role="menuitem"
              onClick={() => {
                setMenuOpen(false)
                void logout()
              }}
              className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm hover:bg-accent"
            >
              <LogOut aria-hidden="true" className="size-4" />
              Sign out
            </button>
          </div>
        )}
      </div>
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

        Uppercased and set in the brand maroon to match the reference's header
        (`DASHBOARD`, `RISK ALERTS`, …). The transformation is presentational,
        so assistive technology still reads the heading's original casing.

        Deliberately a plain bar: the school banner photo lives behind each
        page's title block in the content area, not here. A previous version
        put it in this header with `overflow-hidden`, which clipped the account
        menu open state — the Sign out item was unreachable.
      */}
      <h1 className="min-w-0 flex-1 truncate text-lg font-semibold tracking-wide text-primary uppercase">
        {pageTitle}
      </h1>

      <UserChip />
    </header>
  )
}

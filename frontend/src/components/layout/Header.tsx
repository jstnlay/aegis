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

export function Header({ onMenuClick }: { onMenuClick: () => void }) {
  const location = useLocation()
  const pageTitle = getPageTitle(location.pathname)

  return (
    <header className="sticky top-0 z-30 flex h-14 shrink-0 items-center gap-3 border-b border-border bg-background px-4 lg:px-6">
      <Button
        variant="ghost"
        size="icon"
        className="lg:hidden"
        onClick={onMenuClick}
        aria-label="Open navigation"
      >
        <Menu aria-hidden="true" />
      </Button>

      <h1 className="min-w-0 flex-1 truncate text-lg font-semibold text-foreground">
        {pageTitle}
      </h1>

      <UserChip />
    </header>
  )
}

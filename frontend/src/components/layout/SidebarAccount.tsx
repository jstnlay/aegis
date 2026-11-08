import { useRef, useState } from "react"
import { DropdownMenu } from "radix-ui"
import { ChevronUp, LogOut, Settings } from "lucide-react"
import { Link } from "react-router-dom"
import { useAuth } from "@/features/auth/AuthContext"
import { ROLE_LABELS, userDisplayName } from "@/lib/roles"
import { SignOutDialog } from "./SignOutDialog"
import "./sidebar-account.css"

export function SidebarAccount({
  inert = false,
  onMenuChange,
  onNavigate,
}: {
  inert?: boolean
  onMenuChange?: (open: boolean) => void
  onNavigate?: () => void
}) {
  const { user } = useAuth()
  const trigger = useRef<HTMLButtonElement>(null)
  const [signOutOpen, setSignOutOpen] = useState(false)
  const name = userDisplayName(user) || "Signed in"
  const initials = name
    .split(/\s+/)
    .filter(Boolean)
    .filter((_, index, parts) => index === 0 || index === parts.length - 1)
    .map((part) => part[0])
    .join("")
    .toUpperCase()

  return (
    <>
      <DropdownMenu.Root onOpenChange={onMenuChange}>
        <DropdownMenu.Trigger
          ref={trigger}
          disabled={inert}
          className="app-sidebar-footer app-sidebar-account"
          aria-label="Account menu"
          title={`${name}${user?.email ? ` · ${user.email}` : ""}`}
        >
          <span className="app-sidebar-user-avatar" aria-hidden="true">
            {initials}
          </span>
          <span className="app-sidebar-user-copy">
            <span className="sidebar-account-role">
              {user ? ROLE_LABELS[user.role] : "Your account"}
            </span>
            <span className="sidebar-account-name">{name}</span>
            <span className="sidebar-account-detail" title={user?.email}>
              {user?.email || (user ? ROLE_LABELS[user.role] : "Account")}
            </span>
          </span>
          <ChevronUp className="sidebar-account-chevron" aria-hidden="true" />
        </DropdownMenu.Trigger>
        <DropdownMenu.Portal>
          <DropdownMenu.Content
            className="sidebar-account-menu"
            side="top"
            align="start"
            sideOffset={8}
            collisionPadding={12}
            aria-label="Account"
          >
            <div className="sidebar-account-menu-heading">
              <strong>{name}</strong>
              <span>{user ? ROLE_LABELS[user.role] : "Account"}</span>
            </div>
            <DropdownMenu.Item asChild>
              <Link
                to="/app/account-settings"
                aria-label="Settings"
                onClick={onNavigate}
              >
                <Settings aria-hidden="true" />
                <span>
                  <strong>Settings</strong>
                  <small>Manage your account</small>
                </span>
              </Link>
            </DropdownMenu.Item>
            <DropdownMenu.Separator className="sidebar-account-separator" />
            <DropdownMenu.Item
              aria-label="Sign out"
              className="sidebar-account-sign-out"
              onSelect={() => setSignOutOpen(true)}
            >
              <LogOut aria-hidden="true" />
              <span>
                <strong>Sign out</strong>
                <small>End active session</small>
              </span>
            </DropdownMenu.Item>
          </DropdownMenu.Content>
        </DropdownMenu.Portal>
      </DropdownMenu.Root>
      <SignOutDialog
        open={signOutOpen}
        onOpenChange={setSignOutOpen}
        returnFocusRef={trigger}
      />
    </>
  )
}

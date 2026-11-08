import { NavLink } from "react-router-dom"
import { createPortal } from "react-dom"
import { ChevronRight } from "lucide-react"
import { useCallback, useEffect, useState, useSyncExternalStore } from "react"

import { Badge } from "@/components/ui/badge"
import { PRIMARY_NAV_ID } from "@/components/layout/Header"
import { useAuth } from "@/features/auth/AuthContext"
import {
  getVisibleNavigationForRole,
  itemHref,
  type NavGroup,
  type NavItem,
} from "@/lib/navigation"
import { cn } from "@/lib/utils"
import { SidebarAccount } from "./SidebarAccount"

/**
 * Shared role-aware sidebar (PH11.5).
 *
 * One component for all five roles — driven by the centralized
 * navigation configuration. Available items render as links; planned
 * items render as informative, non-navigable entries (no fake routes).
 */

function Brand() {
  return (
    <div className="app-sidebar-brand flex shrink-0 items-center gap-2.5 px-4 py-4">
      {/* A round disc rather than a rounded square: the seal art itself has an
          alpha channel, so on the brand-maroon rail it reads as the circular
          badge the reference shows instead of an unstyled white tile. */}
      <div className="flex size-11 shrink-0 items-center justify-center overflow-hidden rounded-full bg-white">
        <img
          src="/hcci-logo.png"
          alt=""
          aria-hidden="true"
          className="size-full object-cover"
        />
      </div>
      <div className="app-sidebar-brand-copy min-w-0">
        <p className="text-lg font-bold leading-tight text-sidebar-foreground">
          AEGIS
        </p>
        <p className="truncate text-xs leading-tight text-sidebar-foreground/75">
          HIS CARE CHRISTIAN INSTITUTE
        </p>
      </div>
    </div>
  )
}

function AvailableNavLink({
  item,
  compact,
}: {
  item: NavItem
  compact: boolean
}) {
  const Icon = item.icon
  return (
    <NavLink
      to={itemHref(item)}
      title={compact ? item.label : undefined}
      className={({ isActive }) =>
        cn(
          "flex h-9 items-center gap-2.5 rounded-lg px-3 text-sm font-medium transition-colors focus-visible:ring-2 focus-visible:ring-sidebar-ring",
          isActive
            ? "bg-sidebar-primary text-sidebar-primary-foreground"
            : "text-sidebar-foreground/85 hover:bg-sidebar-accent hover:text-sidebar-accent-foreground"
        )
      }
    >
      {({ isActive }) => (
        <>
          <span className="app-sidebar-item-icon" aria-hidden="true">
            <Icon className="size-4" />
          </span>
          <span className="app-sidebar-label">{item.label}</span>
          {isActive ? (
            <ChevronRight
              className="app-sidebar-current-arrow"
              aria-hidden="true"
            />
          ) : null}
        </>
      )}
    </NavLink>
  )
}

function PlannedNavEntry({ item }: { item: NavItem }) {
  const Icon = item.icon
  return (
    <div className="flex h-9 items-center justify-between rounded-lg px-3 text-sm text-sidebar-foreground/70">
      <span className="flex items-center gap-2.5">
        <Icon className="size-4" aria-hidden="true" />
        <span className="app-sidebar-label">{item.label}</span>
      </span>
      <Badge
        variant="outline"
        className="app-sidebar-label border-sidebar-border text-sidebar-foreground/70"
      >
        Planned
      </Badge>
    </div>
  )
}

function NavItemRow({ item, compact }: { item: NavItem; compact: boolean }) {
  return item.status === "available" ? (
    <AvailableNavLink item={item} compact={compact} />
  ) : (
    <PlannedNavEntry item={item} />
  )
}

function NavGroupSection({
  group,
  compact,
}: {
  group: NavGroup
  compact: boolean
}) {
  return (
    <li>
      <p className="px-3 pt-4 pb-1.5 text-xs font-semibold tracking-wider text-sidebar-foreground/70 uppercase">
        {group.heading}
      </p>
      <ul className="space-y-0.5">
        {group.items.map((item) => (
          <li key={item.route}>
            <NavItemRow item={item} compact={compact} />
          </li>
        ))}
      </ul>
    </li>
  )
}

/**
 * True while the viewport is at least the `lg` breakpoint.
 *
 * `inert` is a DOM attribute, not a class, so it cannot be made responsive with
 * a `max-lg:` prefix the way the drawer's transform is. The sidebar has to be
 * marked inert only while it is *both* closed and narrow; marking it inert while
 * closed on a desktop viewport would take the whole navigation out of the tab
 * order on the one layout where it is permanently visible.
 *
 * `useSyncExternalStore` rather than a `matchMedia` listener in an effect: the
 * snapshot is read during render, so the first paint after a resize already has
 * the right value instead of one frame of the wrong one.
 */
function useIsWideViewport(): boolean {
  const query = "(min-width: 64rem)"

  const subscribe = useCallback((onChange: () => void) => {
    if (typeof window === "undefined" || !window.matchMedia) return () => {}
    const list = window.matchMedia(query)
    list.addEventListener("change", onChange)
    return () => list.removeEventListener("change", onChange)
  }, [])

  const getSnapshot = useCallback(() => {
    if (typeof window === "undefined" || !window.matchMedia) return true
    return window.matchMedia(query).matches
  }, [])

  // `true` on the server and in a test environment without `matchMedia`: the
  // desktop layout is the safe default, because the alternative would strip the
  // navigation from the tab order when nothing can tell us the viewport is narrow.
  const getServerSnapshot = useCallback(() => true, [])

  return useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot)
}

/**
 * Closes the mobile drawer on Escape.
 *
 * A `keydown` listener on the document rather than on the `<aside>`, because the
 * drawer is not a focus trap — the reader is free to tab out of it into the page
 * behind it, and Escape has to work wherever focus happens to be while the
 * drawer is open. Guarded on `active` so no listener exists at all when the
 * drawer is closed.
 */
function useEscapeToClose(active: boolean, onEscape: () => void) {
  useEffect(() => {
    if (!active) return

    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") onEscape()
    }

    document.addEventListener("keydown", onKeyDown)
    return () => document.removeEventListener("keydown", onKeyDown)
  }, [active, onEscape])
}

export function Sidebar({
  open,
  onOpenChange,
  brandContainer = null,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  brandContainer?: HTMLDivElement | null
}) {
  const { user } = useAuth()
  const navigation = user ? getVisibleNavigationForRole(user.role) : []

  const close = useCallback(() => onOpenChange(false), [onOpenChange])
  const isWide = useIsWideViewport()
  useEscapeToClose(open, close)
  const [accountOpen, setAccountOpen] = useState(false)
  const [compact, setCompact] = useState(false)
  const [hovered, setHovered] = useState(false)
  const [focused, setFocused] = useState(false)
  const schoolTheme =
    user?.role === "admin" ||
    user?.role === "guidance" ||
    user?.role === "student" ||
    user?.role === "parent" ||
    user?.role === "faculty"
  const autoCompact = schoolTheme && isWide
  const isCompact = autoCompact && compact

  useEffect(() => {
    if (!autoCompact || hovered || focused || open || accountOpen) return
    const timeout = window.setTimeout(() => setCompact(true), 2400)
    return () => window.clearTimeout(timeout)
  }, [autoCompact, hovered, focused, open, accountOpen])

  useEffect(() => {
    if (!autoCompact) return
    let previousY = Math.max(0, window.scrollY)

    function minimizeOnScrollDown() {
      const currentY = Math.max(0, window.scrollY)
      if (currentY > previousY) setCompact(true)
      previousY = currentY
    }

    // Listen to page scrolling only; the navigation has its own scroll area.
    window.addEventListener("scroll", minimizeOnScrollDown, { passive: true })
    return () => window.removeEventListener("scroll", minimizeOnScrollDown)
  }, [autoCompact])

  /*
   * PH11.11. While the drawer is closed on a narrow viewport it was translated
   * off screen but still in the DOM, so its links stayed in the tab order: a
   * keyboard user tabbed invisibly through the entire navigation before reaching
   * anything on the page, and a screen reader announced it as available content.
   * `inert` removes it from both while it is off screen, and is reverted the
   * moment it is open or the viewport is wide.
   */
  const inertWhenOffCanvas = !open && !isWide

  const branding = <Brand />

  return (
    <>
      {/* Mobile backdrop */}
      {open && !isWide ? (
        <div
          data-slot="navigation-backdrop"
          className="fixed inset-0 z-40 bg-foreground/40 lg:hidden"
          aria-hidden="true"
          onClick={close}
        />
      ) : null}

      <div className="app-sidebar-dock">
        <aside
          aria-label="Primary"
          data-state={open ? "open" : "closed"}
          data-compact={isCompact}
          onPointerEnter={(event) => {
            if (event.pointerType === "touch") return
            setHovered(true)
            if ((event.target as Element).closest(".app-sidebar-toggle")) return
            setCompact(false)
          }}
          onPointerLeave={(event) => {
            setHovered(false)
            if (
              autoCompact &&
              !accountOpen &&
              event.pointerType !== "touch" &&
              !event.currentTarget.querySelector(":focus-visible")
            ) {
              setCompact(true)
            }
          }}
          onFocusCapture={(event) => {
            setFocused(true)
            if ((event.target as Element).closest(".app-sidebar-toggle")) return
            setCompact(false)
          }}
          onBlurCapture={(event) => {
            if (!event.currentTarget.contains(event.relatedTarget))
              setFocused(false)
          }}
          className={cn(
            /*
             * Desktop: the rail is pinned for the full viewport and scrolls its
             * own navigation, so a long module page never takes the main menu
             * off screen (Cycle-3 TC-SYS-12). Mobile keeps the off-canvas drawer.
             */
            "app-sidebar flex w-64 flex-col border-r border-sidebar-border bg-sidebar transition-transform duration-normal ease-out motion-reduce:transition-none max-lg:fixed max-lg:inset-y-0 max-lg:left-0 max-lg:-translate-x-full lg:sticky lg:top-0 lg:h-svh lg:translate-x-0",
            open && "max-lg:translate-x-0"
          )}
        >
          {brandContainer && autoCompact
            ? createPortal(
                <div className="app-header-brand" data-compact={isCompact}>
                  {branding}
                </div>,
                brandContainer
              )
            : branding}

          {/* `min-h-0` lets this column shrink inside the pinned rail, so the
            nav is the part that scrolls rather than the whole sidebar. */}
          <nav
            id={PRIMARY_NAV_ID}
            className="min-h-0 flex-1 overflow-y-auto px-2 py-2"
            aria-label="Main"
            inert={inertWhenOffCanvas}
          >
            <ul>
              {navigation.map((group) => (
                <NavGroupSection
                  key={group.heading}
                  group={group}
                  compact={isCompact}
                />
              ))}
            </ul>
          </nav>

          <SidebarAccount
            inert={inertWhenOffCanvas}
            onMenuChange={setAccountOpen}
            onNavigate={close}
          />
        </aside>
      </div>
    </>
  )
}

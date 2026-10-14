import { NavLink } from "react-router-dom"
import { useCallback, useEffect, useSyncExternalStore } from "react"

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

/**
 * Shared role-aware sidebar (PH11.5).
 *
 * One component for all five roles — driven by the centralized
 * navigation configuration. Available items render as links; planned
 * items render as informative, non-navigable entries (no fake routes).
 */

function Brand() {
  return (
    <div className="flex items-center gap-2.5 px-4 py-4">
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
      <div className="min-w-0">
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

function AvailableNavLink({ item }: { item: NavItem }) {
  const Icon = item.icon
  return (
    <NavLink
      to={itemHref(item)}
      end={item.route === "dashboard"}
      className={({ isActive }) =>
        cn(
          // `rounded-lg` because the active state is a white pill on the brand
          // rail, and a near-square pill reads as an accident rather than a
          // choice.
          "flex h-9 items-center gap-2.5 rounded-lg px-3 text-sm font-medium transition-colors focus-visible:ring-2 focus-visible:ring-sidebar-ring",
          isActive
            ? "bg-sidebar-primary text-sidebar-primary-foreground"
            : "text-sidebar-foreground/85 hover:bg-sidebar-accent hover:text-sidebar-accent-foreground"
        )
      }
    >
      <Icon className="size-4" aria-hidden="true" />
      {item.label}
    </NavLink>
  )
}

function PlannedNavEntry({ item }: { item: NavItem }) {
  const Icon = item.icon
  return (
    <div className="flex h-9 items-center justify-between rounded-lg px-3 text-sm text-sidebar-foreground/70">
      <span className="flex items-center gap-2.5">
        <Icon className="size-4" aria-hidden="true" />
        {item.label}
      </span>
      <Badge
        variant="outline"
        className="border-sidebar-border text-sidebar-foreground/70"
      >
        Planned
      </Badge>
    </div>
  )
}

function NavItemRow({ item }: { item: NavItem }) {
  return item.status === "available" ? (
    <AvailableNavLink item={item} />
  ) : (
    <PlannedNavEntry item={item} />
  )
}

function NavGroupSection({ group }: { group: NavGroup }) {
  return (
    <li>
      <p className="px-3 pt-4 pb-1.5 text-xs font-semibold tracking-wider text-sidebar-foreground/70 uppercase">
        {group.heading}
      </p>
      <ul className="space-y-0.5">
        {group.items.map((item) => (
          <li key={item.route}>
            <NavItemRow item={item} />
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
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const { user } = useAuth()
  const navigation = user ? getVisibleNavigationForRole(user.role) : []

  const close = useCallback(() => onOpenChange(false), [onOpenChange])
  const isWide = useIsWideViewport()
  useEscapeToClose(open, close)

  /*
   * PH11.11. While the drawer is closed on a narrow viewport it was translated
   * off screen but still in the DOM, so its links stayed in the tab order: a
   * keyboard user tabbed invisibly through the entire navigation before reaching
   * anything on the page, and a screen reader announced it as available content.
   * `inert` removes it from both while it is off screen, and is reverted the
   * moment it is open or the viewport is wide.
   */
  const inertWhenOffCanvas = !open && !isWide

  return (
    <>
      {/* Mobile backdrop */}
      {open ? (
        <div
          className="fixed inset-0 z-40 bg-foreground/40 lg:hidden"
          aria-hidden="true"
          onClick={close}
        />
      ) : null}

      <aside
        aria-label="Primary"
        data-state={open ? "open" : "closed"}
        className={cn(
          "flex w-64 flex-col border-r border-sidebar-border bg-sidebar transition-transform duration-normal ease-out motion-reduce:transition-none max-lg:fixed max-lg:inset-y-0 max-lg:left-0 max-lg:-translate-x-full lg:static lg:translate-x-0",
          open && "max-lg:translate-x-0"
        )}
      >
        <Brand />

        <nav
          id={PRIMARY_NAV_ID}
          className="flex-1 overflow-y-auto px-2 py-2"
          aria-label="Main"
          inert={inertWhenOffCanvas}
        >
          <ul>
            {navigation.map((group) => (
              <NavGroupSection key={group.heading} group={group} />
            ))}
          </ul>
        </nav>

        <div className="border-t border-sidebar-border p-3">
          <p className="px-1 text-xs text-sidebar-foreground/70">AEGIS</p>
        </div>
      </aside>
    </>
  )
}

import { useState } from "react"
import { Outlet, useLocation } from "react-router-dom"

import { ErrorBoundary } from "@/components/ErrorBoundary"
import { Header } from "@/components/layout/Header"
import { Sidebar } from "@/components/layout/Sidebar"
import { SkipLink } from "@/components/layout/SkipLink"

/**
 * Shared application shell for all five roles (admin, faculty, guidance,
 * student, parent). One shell — no per-role copies (PH11.3).
 *
 * Structure: skip link, dark sidebar, top bar, main content outlet.
 *
 * The outlet is wrapped in a route-scoped `ErrorBoundary` keyed on the
 * pathname, so one malformed record fails that page only: the sidebar, header
 * and router stay mounted, the user sees a recovery state with a Retry, and
 * navigating to any other route clears the error without a reload.
 */
export function AppShell() {
  const [menuOpen, setMenuOpen] = useState(false)
  const location = useLocation()

  return (
    <div className="flex min-h-svh bg-background">
      <SkipLink />

      <Sidebar open={menuOpen} onOpenChange={setMenuOpen} />

      <div className="flex min-w-0 flex-1 flex-col">
        <Header onMenuClick={() => setMenuOpen(true)} />

        <main id="main-content" className="flex-1 scroll-mt-14" tabIndex={-1}>
          <div className="mx-auto w-full max-w-6xl px-4 py-6 lg:px-6">
            <ErrorBoundary resetKeys={[location.pathname]}>
              <Outlet />
            </ErrorBoundary>
          </div>
        </main>
      </div>
    </div>
  )
}

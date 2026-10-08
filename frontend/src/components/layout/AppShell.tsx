import { useEffect, useRef, useState } from "react"
import { Outlet, useLocation } from "react-router-dom"

import { ErrorBoundary } from "@/components/ErrorBoundary"
import { Header } from "@/components/layout/Header"
import { Sidebar } from "@/components/layout/Sidebar"
import { SkipLink } from "@/components/layout/SkipLink"
import { ChatbotPanel } from "@/features/chatbot/ChatbotPanel"

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
  const location = useLocation()
  const [menuOpen, setMenuOpen] = useState(false)
  const [chatOpen, setChatOpen] = useState(false)
  const [lastPath, setLastPath] = useState(location.pathname)
  const menuButtonRef = useRef<HTMLButtonElement>(null)
  const wasMenuOpen = useRef(false)

  /*
   * PH11.11: close the drawer on navigation. Following a link inside the drawer
   * used to leave it open, so the reader landed on the next page with the
   * navigation still covering it.
   *
   * Reset during render rather than in an effect: setting state in an effect
   * means one commit where the drawer is still open over the new page, and the
   * `react-hooks` rules reject it. Comparing against the previous path and
   * resetting is React's documented approach for deriving state from a prop
   * change, and it is the pattern `useDataTablePagination` already uses here.
   */
  if (location.pathname !== lastPath) {
    setLastPath(location.pathname)
    setMenuOpen(false)
  }

  /*
   * PH11.11: return focus to the hamburger button when the drawer closes.
   *
   * Escape closes the drawer, but the focus was left wherever the reader had
   * reached inside it — on a link that is now `inert`, or on an element that has
   * scrolled out of view. A keyboard user closing a panel with Escape expects to
   * be returned to where they opened it from, which is the behaviour PH11.2 §16.3
   * asks for. Skipped on navigation, where the route-change focus below owns it.
   */
  useEffect(() => {
    if (wasMenuOpen.current && !menuOpen) {
      menuButtonRef.current?.focus()
    }
    wasMenuOpen.current = menuOpen
  }, [menuOpen])

  /*
   * PH11.11: move focus to the main region on navigation.
   *
   * A client-side route change replaces the page content without a page load, so
   * focus stayed on the link that was activated — in a document that no longer
   * contained it. The next Tab press therefore restarted from the top of the
   * page with no announcement of the change. Focusing `main` (which the skip
   * link already targets, and which is `tabindex="-1"` for exactly this reason)
   * announces the new page and puts the reader at the start of its content.
   *
   * Not applied on the first render: focusing on mount would steal focus from
   * whatever opened the shell.
   */
  const isFirstRender = useRef(true)
  useEffect(() => {
    if (isFirstRender.current) {
      isFirstRender.current = false
      return
    }
    document.getElementById("main-content")?.focus()
  }, [location.pathname])

  return (
    <div className="flex min-h-svh bg-background">
      <SkipLink />

      <Sidebar open={menuOpen} onOpenChange={setMenuOpen} />

      <div className="flex min-w-0 flex-1 flex-col">
        <Header
          menuOpen={menuOpen}
          menuButtonRef={menuButtonRef}
          onMenuClick={() => setMenuOpen(true)}
        />

        <main id="main-content" className="flex-1 scroll-mt-14" tabIndex={-1}>
          <div className="mx-auto w-full max-w-6xl px-4 py-6 lg:px-6">
            {/*
              A sibling of the outlet rather than a route. The assistant is a
              persistent side tool, so opening it must not navigate away from
              whatever the user was reading — and the transcript is component
              state, so it is discarded on navigation, which is the honest
              behaviour for a chat that does not persist anything.
            */}
            <div className="mb-4 flex justify-end">
              <button
                type="button"
                onClick={() => setChatOpen((open) => !open)}
                aria-expanded={chatOpen}
                aria-controls="chatbot-panel"
                className="rounded-md border border-border px-3 py-1.5 text-sm font-medium hover:bg-accent"
              >
                {chatOpen ? "Close assistant" : "Ask the assistant"}
              </button>
            </div>

            <div id="chatbot-panel">
              <ChatbotPanel
                open={chatOpen}
                onClose={() => setChatOpen(false)}
              />
            </div>

            <ErrorBoundary resetKeys={[location.pathname]}>
              <Outlet />
            </ErrorBoundary>
          </div>
        </main>
      </div>
    </div>
  )
}

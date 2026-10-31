import {
  useEffect,
  useRef,
  useState,
  useSyncExternalStore,
  type ReactNode,
} from "react"
import { Link } from "react-router-dom"

import { SchoolLockup } from "@/components/brand/SchoolLockup"
import "./public-school.css"

function subscribeToScroll(callback: () => void) {
  window.addEventListener("scroll", callback, { passive: true })
  return () => window.removeEventListener("scroll", callback)
}

function isHeaderScrolled() {
  return window.scrollY > 24
}

function getServerSnapshot() {
  return false
}

export function SchoolHeader({
  children,
  brandPosition = "start",
}: {
  children: ReactNode
  brandPosition?: "start" | "end"
}) {
  const header = useRef<HTMLElement>(null)
  const [hidden, setHidden] = useState(false)
  const scrolled = useSyncExternalStore(
    subscribeToScroll,
    isHeaderScrolled,
    getServerSnapshot
  )

  useEffect(() => {
    let previousY = Math.max(0, window.scrollY)

    function onScroll() {
      const currentY = Math.max(0, window.scrollY)
      if (currentY === previousY) return

      const scrollingDown = currentY > previousY
      previousY = currentY
      const usingNavigation = header.current?.querySelector(
        ':focus-visible, [aria-controls="public-nav-menu"][aria-expanded="true"]'
      )

      setHidden(currentY > 24 && scrollingDown && !usingNavigation)
    }

    window.addEventListener("scroll", onScroll, { passive: true })
    return () => window.removeEventListener("scroll", onScroll)
  }, [])

  const brand = (
    <Link
      to="/"
      aria-label="His Care Christian Institute — home"
      className="school-header-brand min-w-0 rounded-md border-0 shadow-none outline-none"
    >
      <SchoolLockup />
    </Link>
  )

  return (
    <header
      ref={header}
      className="school-header sticky top-0 z-40"
      data-scrolled={scrolled}
      data-hidden={scrolled && hidden}
      onFocusCapture={() => setHidden(false)}
    >
      <div className="school-header-inner">
        {brandPosition === "start" && brand}
        <div className="school-header-actions flex shrink-0 items-center gap-4">
          {children}
        </div>
        {brandPosition === "end" && brand}
      </div>
    </header>
  )
}

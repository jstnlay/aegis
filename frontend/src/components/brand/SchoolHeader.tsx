import type { ReactNode } from "react"
import { Link } from "react-router-dom"

import { SchoolLockup } from "@/components/brand/SchoolLockup"

/**
 * Shared public header for the landing and school pages: the identity
 * lockup (linked home) on the left, page-supplied navigation and actions on
 * the right. Deliberately separate from the authenticated `Header` — this
 * chrome only ever renders signed out.
 */
export function SchoolHeader({ children }: { children: ReactNode }) {
  return (
    <header className="border-b border-border bg-background">
      <div className="mx-auto flex min-h-16 w-full max-w-5xl items-center justify-between gap-3 px-4 py-2 lg:px-6">
        <Link to="/" aria-label="His Care Christian Institute — home">
          <SchoolLockup />
        </Link>
        <div className="flex shrink-0 items-center gap-3">{children}</div>
      </div>
    </header>
  )
}

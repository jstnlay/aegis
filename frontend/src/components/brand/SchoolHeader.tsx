import type { ReactNode } from "react"
import { Link } from "react-router-dom"

import { SchoolLockup } from "@/components/brand/SchoolLockup"

export function SchoolHeader({ children }: { children: ReactNode }) {
  return (
    <header className="sticky top-0 z-40 border-b border-border bg-background/85 backdrop-blur-md">
      <div className="mx-auto flex min-h-16 w-full max-w-6xl items-center justify-between gap-3 px-4 py-2 lg:px-6">
        <Link to="/" aria-label="His Care Christian Institute — home">
          <SchoolLockup />
        </Link>
        <div className="flex shrink-0 items-center gap-3">{children}</div>
      </div>
    </header>
  )
}

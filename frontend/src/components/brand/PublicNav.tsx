import { useEffect, useRef, useState } from "react"
import { Menu, X } from "lucide-react"
import { Link } from "react-router-dom"

const DESKTOP_LINK =
  "text-muted-foreground transition-colors hover:text-foreground"
const MOBILE_LINK =
  "block rounded-md px-3 py-2 text-sm transition-colors hover:bg-muted hover:text-foreground"

function NavLinks({
  className,
  onNavigate,
}: {
  className: string
  onNavigate?: () => void
}) {
  return (
    <>
      <Link to="/" onClick={onNavigate} className={className}>
        Home
      </Link>
      <a href="#about" onClick={onNavigate} className={className}>
        About
      </a>
      <a href="#announcements" onClick={onNavigate} className={className}>
        Announcements
      </a>
      <a href="#resources" onClick={onNavigate} className={className}>
        Resources
      </a>
      <a href="#faq" onClick={onNavigate} className={className}>
        FAQ
      </a>
      <a href="#contact" onClick={onNavigate} className={className}>
        Contact
      </a>
    </>
  )
}

/**
 * Landing-page section nav. A plain row from `lg` up; below that a disclosure
 * menu, because `About` and `Contact` sat in a `hidden sm:flex` row — on a
 * phone the header only ever showed the lockup and the sign-in button, so the
 * sections had no way in. Closes on pick, on Escape and on a tap outside.
 *
 * The row starts at `lg`, not `sm`: the six entries plus the lockup and the
 * sign-in button do not fit the 640px–1024px band, where the old two-entry row
 * did. Below `lg` the disclosure carries all of them.
 */
export function PublicNav() {
  const [open, setOpen] = useState(false)
  const wrapper = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false)
    }
    const onPointerDown = (event: PointerEvent) => {
      if (!wrapper.current?.contains(event.target as Node)) setOpen(false)
    }

    document.addEventListener("keydown", onKeyDown)
    document.addEventListener("pointerdown", onPointerDown)
    return () => {
      document.removeEventListener("keydown", onKeyDown)
      document.removeEventListener("pointerdown", onPointerDown)
    }
  }, [open])

  return (
    <div ref={wrapper} className="relative order-last sm:order-none">
      <nav
        aria-label="Primary"
        className="hidden items-center gap-5 text-sm lg:flex"
      >
        <NavLinks className={DESKTOP_LINK} />
      </nav>

      <button
        type="button"
        aria-expanded={open}
        aria-label="Menu"
        onClick={() => setOpen((value) => !value)}
        className="inline-flex size-8 items-center justify-center rounded-sm border border-border text-foreground transition-colors outline-none hover:bg-muted focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring lg:hidden"
      >
        {open ? (
          <X aria-hidden="true" className="size-4" />
        ) : (
          <Menu aria-hidden="true" className="size-4" />
        )}
      </button>

      {open ? (
        <nav
          id="public-nav-menu"
          aria-label="Primary"
          className="absolute top-full right-0 z-50 mt-2 flex w-44 flex-col rounded-lg border border-border bg-background p-1.5 shadow-lg motion-safe:animate-in motion-safe:fade-in motion-safe:slide-in-from-top-2 lg:hidden"
        >
          <NavLinks className={MOBILE_LINK} onNavigate={() => setOpen(false)} />
        </nav>
      ) : null}
    </div>
  )
}

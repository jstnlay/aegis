import { Link } from "react-router-dom"

const LINK =
  "rounded-sm underline-offset-4 transition-colors hover:text-foreground hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"

export function PublicFooter() {
  return (
    <footer className="border-t border-border bg-muted/30">
      <div className="mx-auto w-full max-w-6xl space-y-4 px-4 py-8 text-xs text-muted-foreground lg:px-6">
        <nav
          aria-label="Legal and school links"
          className="flex flex-wrap gap-x-5 gap-y-2"
        >
          <Link className={LINK} to="/school">
            About the school
          </Link>
          <Link className={LINK} to="/privacy">
            Privacy Policy
          </Link>
          <Link className={LINK} to="/terms">
            Terms of Use
          </Link>
          <Link className={LINK} to="/cookies">
            Cookie Policy
          </Link>
        </nav>

        <p className="max-w-prose leading-relaxed">
          AEGIS sets no cookies and no tracking. It stores sign-in tokens and a
          few display preferences in your browser. The{" "}
          <Link className={LINK} to="/cookies">
            Cookie Policy
          </Link>{" "}
          names every item.
        </p>

        <p className="leading-relaxed">
          His Care Christian Institute · AEGIS school information system
        </p>
      </div>
    </footer>
  )
}

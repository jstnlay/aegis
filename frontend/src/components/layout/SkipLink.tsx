/**
 * Keyboard users jump straight to content, skipping nav (PH11.2 $16.4).
 */
export function SkipLink() {
  return (
    <a
      href="#main-content"
      className="sr-only z-50 rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:ring-2 focus:ring-ring"
    >
      Skip to main content
    </a>
  )
}

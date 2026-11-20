/**
 * Aegi's mark.
 *
 * A small, hand-built vector rather than a raster image: the header renders it
 * at 23px and the message avatar at 18px, sizes where a generated image would
 * blur. Both shapes use the school palette so the assistant looks like part of
 * AEGIS rather than a stock bot glyph.
 */

/** Header and avatar mark. Inherits `color` so CSS keeps control of the tint. */
export function AegiMark({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.7}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M12 6.4V3.6" />
      <circle cx="12" cy="3" r="1.4" fill="currentColor" stroke="none" />
      <rect x="3.4" y="6.4" width="17.2" height="13.6" rx="4.4" />
      <circle cx="9.3" cy="12.2" r="1.15" fill="currentColor" stroke="none" />
      <circle cx="14.7" cy="12.2" r="1.15" fill="currentColor" stroke="none" />
      <path d="M9.4 15.5c.9 1.1 2.1 1.6 3.1 1.6s2-.5 2.9-1.6" />
    </svg>
  )
}

/**
 * The welcome mascot. Decorative only: the panel already says who is talking,
 * so this carries no meaning a screen reader needs.
 */
export function AegiMascot() {
  return (
    <svg viewBox="0 0 96 96" fill="none" aria-hidden="true" focusable="false">
      <circle cx="48" cy="52" r="34" fill="#f3e6ea" />
      <path
        d="M48 27V17"
        stroke="#7e9c7b"
        strokeWidth="2.6"
        strokeLinecap="round"
      />
      <circle cx="48" cy="13" r="4.4" fill="#7e9c7b" />
      <rect
        x="18"
        y="26"
        width="60"
        height="50"
        rx="16"
        fill="#8c4759"
        stroke="#632c3e"
        strokeWidth="3"
      />
      <rect x="26" y="34" width="44" height="34" rx="12" fill="#fdf6f0" />
      <circle cx="39" cy="48" r="4.8" fill="#4a2531" />
      <circle cx="57" cy="48" r="4.8" fill="#4a2531" />
      <circle cx="30.5" cy="58" r="3.2" fill="#e0a8b6" opacity="0.75" />
      <circle cx="65.5" cy="58" r="3.2" fill="#e0a8b6" opacity="0.75" />
      <path
        d="M40.5 58.5c2.2 2.6 5 3.6 7.5 3.6s5.3-1 7.5-3.6"
        stroke="#4a2531"
        strokeWidth="2.6"
        strokeLinecap="round"
      />
    </svg>
  )
}

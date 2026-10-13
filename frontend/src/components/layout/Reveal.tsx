import type { ReactNode } from "react"
import { useEffect, useRef, useState } from "react"

import { cn } from "@/lib/utils"

/**
 * A lightweight viewport-reveal wrapper used on the public landing and
 * school pages. CSS-only motion would fire on page load for every section at
 * once; observing the intersection gives a gentle one-by-one reveal. Motion
 * is disabled entirely under `prefers-reduced-motion`.
 */
export function Reveal({
  children,
  className,
  delay = 0,
}: {
  children: ReactNode
  className?: string
  delay?: number
}) {
  const ref = useRef<HTMLDivElement>(null)
  const [visible, setVisible] = useState(() => {
    if (typeof window === "undefined") return false
    const reducedMotion =
      typeof window.matchMedia === "function" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches
    return reducedMotion || typeof IntersectionObserver === "undefined"
  })

  useEffect(() => {
    const element = ref.current
    if (!element || visible) return

    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          setVisible(true)
          observer.disconnect()
        }
      },
      { threshold: 0.14, rootMargin: "0px 0px -8% 0px" }
    )
    observer.observe(element)
    return () => observer.disconnect()
  }, [visible])

  return (
    <div
      ref={ref}
      style={delay ? { transitionDelay: `${delay}ms` } : undefined}
      className={cn(
        "motion-safe:transition-[opacity,transform] motion-safe:duration-700 motion-safe:ease-out motion-reduce:transition-none",
        visible
          ? "opacity-100 translate-y-0"
          : "motion-safe:opacity-0 motion-safe:translate-y-3",
        className
      )}
    >
      {children}
    </div>
  )
}

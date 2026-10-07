import { useCallback, useId, useRef, type ReactNode } from "react"

import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"

/**
 * A tab strip that satisfies the ARIA tabs pattern.
 *
 * PH11.11. Three admin pages — `AdminAcademicsPage`, `AdminDataPage` and
 * `AdminCmsPage` — each declared `role="tablist"` with `role="tab"` children and
 * stopped there. That leaves three of the pattern's requirements unmet:
 *
 * - **No `aria-controls`, and no `role="tabpanel"` on the content.** Each page
 *   rendered the selected panel as a sibling `<div>`, so a screen reader had no
 *   way to associate a tab with what it reveals.
 * - **No arrow-key navigation.** All tabs were ordinary tab stops, so reaching
 *   the seventh tab on `AdminAcademicsPage` meant seven Tab presses. The pattern
 *   expects one tab stop for the strip, with arrow keys moving between tabs.
 * - **No visible focus indicator on `AdminCmsPage`**, which hand-rolled its tab
 *   buttons without the shared `Button`'s `focus-visible:` ring. A keyboard user
 *   had no indication of where they were on that page.
 *
 * One component, used by all three, so the contract cannot be satisfied on one
 * page and missed on another again. The panels are declared here rather than
 * inferred, which keeps `aria-controls` and `role="tabpanel"` honest by
 * construction: the id a tab points at is the id of the element rendering it.
 *
 * Only the selected panel is mounted, matching the previous behaviour on all
 * three pages — the panels fetch on mount, so keeping the others mounted would
 * issue requests the reader never asked for.
 */

export interface TabItem<T extends string> {
  id: T
  label: string
  /** The selected tab's content. */
  content: ReactNode
}

export interface TabsProps<T extends string> {
  /** Accessible name for the strip, e.g. "Academic structure". */
  label: string
  /** The selected tab. */
  value: T
  /** Called with the newly selected tab. */
  onValueChange: (value: T) => void
  items: ReadonlyArray<TabItem<T>>
}

export function Tabs<T extends string>({
  label,
  value,
  onValueChange,
  items,
}: TabsProps<T>) {
  const baseId = useId()
  const tabRefs = useRef(new Map<T, HTMLButtonElement>())

  // Roving tabindex: the selected tab is the strip's only tab stop, so Tab
  // moves past the whole group into the panel rather than through every tab.
  const focusTab = useCallback((id: T) => {
    tabRefs.current.get(id)?.focus()
  }, [])

  /**
   * Arrow keys move between tabs; Home and End jump to the ends.
   *
   * Follows the pattern's own convention of wrapping at the ends, and moves
   * focus only — activation stays with the reader, so arrowing past a tab never
   * silently changes which panel is loaded.
   */
  function onKeyDown(event: React.KeyboardEvent<HTMLDivElement>) {
    const index = items.findIndex((item) => item.id === value)
    if (index < 0) return

    let next: number | null = null
    if (event.key === "ArrowRight") next = (index + 1) % items.length
    else if (event.key === "ArrowLeft")
      next = (index - 1 + items.length) % items.length
    else if (event.key === "Home") next = 0
    else if (event.key === "End") next = items.length - 1

    if (next === null) return
    event.preventDefault()
    focusTab(items[next]?.id as T)
  }

  return (
    <>
      <div
        className="flex flex-wrap gap-2"
        role="tablist"
        aria-label={label}
        onKeyDown={onKeyDown}
      >
        {items.map((item) => {
          const selected = item.id === value
          return (
            <Button
              key={item.id}
              ref={(node) => {
                if (node) tabRefs.current.set(item.id, node)
                else tabRefs.current.delete(item.id)
              }}
              role="tab"
              id={`${baseId}-tab-${item.id}`}
              type="button"
              variant={selected ? "default" : "outline"}
              aria-selected={selected}
              aria-controls={`${baseId}-panel-${item.id}`}
              // Roving tabindex: only the selected tab is reachable by Tab.
              tabIndex={selected ? 0 : -1}
              onClick={() => onValueChange(item.id)}
            >
              {item.label}
            </Button>
          )
        })}
      </div>

      {/*
        The panel wraps the selected tab's content, so `aria-controls` resolves
        to a real element. `tabIndex={0}` because a panel reached this way is a
        focusable region in the pattern: the tab strip's next Tab press lands
        here rather than skipping the content entirely.
      */}
      <div
        role="tabpanel"
        id={`${baseId}-panel-${value}`}
        aria-labelledby={`${baseId}-tab-${value}`}
        tabIndex={0}
        className={cn("focus:outline-none")}
      >
        {items.find((item) => item.id === value)?.content}
      </div>
    </>
  )
}

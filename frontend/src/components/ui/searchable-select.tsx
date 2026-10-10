import { useEffect, useId, useMemo, useRef, useState } from "react"
import { Check, ChevronDown, Search } from "lucide-react"

import { cn } from "@/lib/utils"

export interface SearchableOption {
  value: string
  label: string
}

/**
 * Searchable select for long/roster lists (sections, students).
 *
 * A plain button + listbox popover with a filter input — no new dependency.
 * The list is capped (`max-h-64`) with its own scroll so a large roster never
 * eats the page, and typing narrows the options. Small enum filters keep the
 * plain Radix `Select`; this is only for unbounded lists.
 */
export function SearchableSelect({
  id,
  label,
  value,
  onChange,
  options,
  placeholder = "Select an option",
  searchPlaceholder = "Search options",
  disabled = false,
  emptyMessage = "No matching options",
}: {
  id: string
  label: string
  value: string
  onChange: (value: string) => void
  options: SearchableOption[]
  placeholder?: string
  searchPlaceholder?: string
  disabled?: boolean
  emptyMessage?: string
}) {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState("")
  const rootRef = useRef<HTMLDivElement>(null)
  const searchId = useId()
  const listId = useId()

  const selected = options.find((o) => o.value === value) ?? null
  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return options
    return options.filter((o) => o.label.toLowerCase().includes(q))
  }, [options, query])

  useEffect(() => {
    if (!open) return
    function onPointerDown(event: PointerEvent) {
      if (rootRef.current && !rootRef.current.contains(event.target as Node)) {
        setOpen(false)
      }
    }
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") setOpen(false)
    }
    document.addEventListener("pointerdown", onPointerDown)
    document.addEventListener("keydown", onKeyDown)
    return () => {
      document.removeEventListener("pointerdown", onPointerDown)
      document.removeEventListener("keydown", onKeyDown)
    }
  }, [open])

  return (
    <div ref={rootRef} className="relative">
      <button
        id={id}
        type="button"
        disabled={disabled}
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        aria-haspopup="listbox"
        aria-controls={listId}
        aria-label={label}
        className="flex h-9 w-full items-center justify-between gap-1.5 rounded-sm border border-input bg-transparent py-2 pr-2 pl-3 text-sm whitespace-nowrap outline-none select-none focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
      >
        <span className="min-w-0 flex-1 truncate text-left data-[placeholder]:text-muted-foreground">
          {selected ? (
            selected.label
          ) : (
            <span className="text-muted-foreground">{placeholder}</span>
          )}
        </span>
        <ChevronDown
          aria-hidden="true"
          className="size-4 shrink-0 text-muted-foreground"
        />
      </button>

      {open && !disabled && (
        <div className="absolute z-50 mt-1 w-full rounded-md bg-popover shadow-md ring-1 ring-foreground/10">
          <div className="flex items-center gap-2 border-b border-border px-2 py-1.5">
            <Search
              aria-hidden="true"
              className="size-4 shrink-0 text-muted-foreground"
            />
            <input
              id={searchId}
              type="search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder={searchPlaceholder}
              aria-label={`Search ${label}`}
              className="h-7 w-full bg-transparent text-sm outline-none placeholder:text-muted-foreground"
            />
          </div>
          <ul
            id={listId}
            role="listbox"
            aria-label={label}
            className="max-h-64 overflow-y-auto p-1"
          >
            {filtered.length === 0 && (
              <li
                className="px-2 py-2 text-sm text-muted-foreground"
                role="option"
                aria-selected="false"
              >
                {emptyMessage}
              </li>
            )}
            {filtered.map((option) => {
              const active = option.value === value
              return (
                <li
                  key={option.value}
                  role="option"
                  aria-selected={active}
                  tabIndex={0}
                  onClick={() => {
                    onChange(option.value)
                    setOpen(false)
                    setQuery("")
                  }}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault()
                      onChange(option.value)
                      setOpen(false)
                      setQuery("")
                    }
                  }}
                  className={cn(
                    "flex w-full cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm hover:bg-accent",
                    active && "bg-accent"
                  )}
                >
                  <span className="min-w-0 flex-1 truncate">
                    {option.label}
                  </span>
                  {active && (
                    <Check aria-hidden="true" className="size-4 shrink-0" />
                  )}
                </li>
              )
            })}
          </ul>
        </div>
      )}
    </div>
  )
}

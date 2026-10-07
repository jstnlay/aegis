import * as React from "react"
import { cn } from "@/lib/utils"

/**
 * A table inside a horizontally scrollable container.
 *
 * The scroll container is not decorative: PH11.2 §12.4 keeps data tables as
 * tables that scroll horizontally on narrow screens, so on a phone the content
 * genuinely extends past the viewport and has to be reachable.
 *
 * `scrollLabel` opts the container into being focusable and named. WCAG 2.1.1
 * requires that content reachable only by scrolling be operable from the
 * keyboard, and a `overflow-x-auto` div is not focusable by default — a table
 * whose cells contain no links or buttons cannot be scrolled at all without it.
 * It is opt-in rather than automatic so a caller chooses the accessible name
 * instead of inheriting a derived one, and so a table that does not overflow
 * does not gain a redundant tab stop.
 */
function Table({
  className,
  scrollLabel,
  ...props
}: React.ComponentProps<"table"> & { scrollLabel?: string }) {
  return (
    <div
      data-slot="table-container"
      className="relative w-full overflow-x-auto"
      {...(scrollLabel
        ? { tabIndex: 0, role: "region", "aria-label": scrollLabel }
        : null)}
    >
      <table
        data-slot="table"
        className={cn("w-full caption-bottom text-sm", className)}
        {...props}
      />
    </div>
  )
}

function TableHeader({ className, ...props }: React.ComponentProps<"thead">) {
  return (
    <thead
      data-slot="table-header"
      className={cn("[&_tr]:border-b", className)}
      {...props}
    />
  )
}

function TableBody({ className, ...props }: React.ComponentProps<"tbody">) {
  return (
    <tbody
      data-slot="table-body"
      className={cn("[&_tr:last-child]:border-0", className)}
      {...props}
    />
  )
}

function TableFooter({ className, ...props }: React.ComponentProps<"tfoot">) {
  return (
    <tfoot
      data-slot="table-footer"
      className={cn(
        "border-t bg-muted/50 font-medium [&>tr]:last:border-b-0",
        className
      )}
      {...props}
    />
  )
}

function TableRow({ className, ...props }: React.ComponentProps<"tr">) {
  return (
    <tr
      data-slot="table-row"
      className={cn(
        "border-b transition-colors hover:bg-muted/50 has-aria-expanded:bg-muted/50 data-[state=selected]:bg-muted",
        className
      )}
      {...props}
    />
  )
}

function TableHead({ className, ...props }: React.ComponentProps<"th">) {
  return (
    <th
      data-slot="table-head"
      className={cn(
        "h-10 px-3 text-left align-middle font-semibold whitespace-nowrap bg-muted text-foreground [&:has([role=checkbox])]:pr-0",
        className
      )}
      {...props}
    />
  )
}

/**
 * A table cell.
 *
 * `whitespace-nowrap` was removed from the base class in PH11.11 and is now
 * opt-in per cell. It was correct for the majority of cells — codes, numbers,
 * dates and short labels all read better on one line, and PH11.2 §12.4
 * deliberately keeps data tables as tables that scroll horizontally on narrow
 * screens rather than converting them to cards. But it was inherited by free
 * text as well: a CMS announcement body, a notification `TextField` message, a
 * teacher's remarks or a risk-factor list rendered as a single unbroken line
 * whose width is the length of the text, which made the table wider than any
 * amount of horizontal scrolling usefully serves and meant the content was
 * clipped at the right edge instead of wrapped.
 *
 * Cells that want the old behaviour — and DataTable callers can ask for it
 * without touching markup, via `DataTableColumn.cellClassName` — pass
 * `whitespace-nowrap` themselves. Defaulting to wrap costs nothing for a short
 * value and is correct for a long one, so the safer default is the wrap.
 */
function TableCell({ className, ...props }: React.ComponentProps<"td">) {
  return (
    <td
      data-slot="table-cell"
      className={cn(
        "px-3 py-2 align-middle [&:has([role=checkbox])]:pr-0",
        className
      )}
      {...props}
    />
  )
}

function TableCaption({
  className,
  ...props
}: React.ComponentProps<"caption">) {
  return (
    <caption
      data-slot="table-caption"
      className={cn("mt-4 text-sm text-muted-foreground", className)}
      {...props}
    />
  )
}

export {
  Table,
  TableHeader,
  TableBody,
  TableFooter,
  TableHead,
  TableRow,
  TableCell,
  TableCaption,
}

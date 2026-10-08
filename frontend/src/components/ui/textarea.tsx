import { forwardRef } from "react"

import { cn } from "@/lib/utils"

/**
 * Multi-line text input.
 *
 * The one the guidance page used for assessment descriptions was a bare
 * `<textarea>` with the border/ring classes inlined, so the assistant panel
 * needed the same thing and copying that block would have produced a third
 * copy. This is the shared element; both call sites now use it.
 */
export const Textarea = forwardRef<
  HTMLTextAreaElement,
  React.TextareaHTMLAttributes<HTMLTextAreaElement>
>(({ className, ...props }, ref) => (
  <textarea
    ref={ref}
    className={cn(
      "w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-xs outline-none focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50",
      className
    )}
    {...props}
  />
))

Textarea.displayName = "Textarea"

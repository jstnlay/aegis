import { SCHOOL_CAMPUS_LINE, SCHOOL_NAME } from "@/lib/school-content"
import { cn } from "@/lib/utils"

/**
 * School identity lockup: the circular seal overlapping a maroon banner
 * carrying the school name and campus line — the header/footer treatment the
 * school's design uses on every public surface. Composed from the seal image
 * plus text (not a pre-rendered bitmap) so the words stay selectable and
 * crisp at any zoom.
 */
export function SchoolLockup({ className }: { className?: string }) {
  return (
    <span className={cn("flex min-w-0 items-center", className)}>
      <img
        src="/hcci-logo.png"
        alt="His Care Christian Institute seal"
        width={381}
        height={377}
        className="relative z-10 size-11 shrink-0 rounded-full"
      />
      <span className="-ml-3 min-w-0 rounded-md bg-primary py-1.5 pr-3 pl-5 text-primary-foreground">
        <span className="block truncate text-[13px] leading-tight font-bold sm:text-sm">
          {SCHOOL_NAME}
        </span>
        <span className="block truncate text-[10px] leading-tight opacity-90 sm:text-xs">
          {SCHOOL_CAMPUS_LINE}
        </span>
      </span>
    </span>
  )
}

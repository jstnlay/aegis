import { CalendarDays } from "lucide-react"
import { useMemo } from "react"

import {
  EmptyState,
  ErrorNote,
  LoadingState,
} from "@/components/feedback/Feedback"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { normalizeApiError } from "@/lib/error"
import {
  SCHEDULE_DAY_LABELS,
  SCHEDULE_DAY_ORDER,
  formatScheduleTime,
  useStudentSchedule,
  type ScheduleDay,
  type ScheduleEntry,
} from "@/features/student/schedule-api"

/**
 * The student's own class schedule (TC-STU-04 / FR-018).
 *
 * The QA cycle recorded "Class schedule page is not available in the system
 * navigation" as a missing feature. The data was already served —
 * `ScheduleViewSet` returns a student their own section's timetable — so this
 * is the missing surface, grouped by day and rendered read-only: there is no
 * schedule write on any role but admin, and a student has none to make.
 */

function PageHeading() {
  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center gap-3">
        <CalendarDays
          className="size-5 text-muted-foreground"
          aria-hidden="true"
        />
        <h2 className="text-2xl font-bold text-foreground">Class schedule</h2>
      </div>
      <p className="text-sm text-muted-foreground">
        The periods on record for your section, grouped by day. Ask your teacher
        or the registrar if a class you are enrolled in is missing.
      </p>
    </div>
  )
}

function ScheduleRow({ entry }: { entry: ScheduleEntry }) {
  const detail = entry.subject_assignment_detail

  return (
    <li className="flex flex-wrap items-baseline gap-x-3 gap-y-1 rounded-md border border-border px-3 py-2">
      <span className="min-w-32 font-medium tabular-nums">
        {formatScheduleTime(entry.start_time)} –{" "}
        {formatScheduleTime(entry.end_time)}
      </span>
      <span className="font-semibold">{detail.subject_name}</span>
      {detail.subject_code ? (
        <span className="text-xs text-muted-foreground">
          {detail.subject_code}
        </span>
      ) : null}
      {detail.faculty_name ? (
        <span className="text-sm text-muted-foreground">
          {detail.faculty_name}
        </span>
      ) : null}
      {entry.room ? (
        <span className="ml-auto text-sm text-muted-foreground">
          Room {entry.room}
        </span>
      ) : null}
    </li>
  )
}

export function StudentSchedulePage() {
  const scheduleQuery = useStudentSchedule()

  const byDay = useMemo(() => {
    const groups = new Map<ScheduleDay, ScheduleEntry[]>()
    for (const entry of scheduleQuery.data ?? []) {
      const bucket = groups.get(entry.day_of_week)
      if (bucket) bucket.push(entry)
      else groups.set(entry.day_of_week, [entry])
    }
    for (const entries of groups.values()) {
      entries.sort((a, b) => a.start_time.localeCompare(b.start_time))
    }
    return groups
  }, [scheduleQuery.data])

  const visibleDays = SCHEDULE_DAY_ORDER.filter((day) => byDay.has(day))

  return (
    <div className="space-y-6">
      <PageHeading />

      {scheduleQuery.isLoading ? (
        <LoadingState label="Loading class schedule" />
      ) : scheduleQuery.isError ? (
        <ErrorNote message={normalizeApiError(scheduleQuery.error).message} />
      ) : visibleDays.length === 0 ? (
        <EmptyState message="No class periods are on record for your section yet." />
      ) : (
        <div className="space-y-4">
          {visibleDays.map((day) => (
            <Card key={day}>
              <CardHeader>
                <CardTitle as="h3">{SCHEDULE_DAY_LABELS[day]}</CardTitle>
              </CardHeader>
              <CardContent>
                <ul className="space-y-2">
                  {(byDay.get(day) ?? []).map((entry) => (
                    <ScheduleRow key={entry.id} entry={entry} />
                  ))}
                </ul>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}

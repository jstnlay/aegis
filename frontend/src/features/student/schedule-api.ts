import { useQuery } from "@tanstack/react-query"

import { fetchAllPages } from "@/lib/pagination"

/**
 * Class schedule for the signed-in student (TC-STU-04 / FR-018).
 *
 * `ScheduleViewSet.get_queryset()` scopes a student to
 * `subject_assignment__section_id=sp.section_id` and the view is read-only for
 * every non-admin role (`IsAdminOrReadOnly`), so the list below is the
 * student's own section timetable by construction — nothing here filters by
 * identity, and nothing here can write.
 *
 * The QA log recorded this as "missing feature: class schedule page is not
 * available in the navigation"; the endpoint existed all along, so this adds
 * the surface rather than any data.
 */

export type ScheduleDay = "mon" | "tue" | "wed" | "thu" | "fri"

/** `Schedule.DayChoices` — the label, not the raw key. */
export const SCHEDULE_DAY_LABELS: Record<ScheduleDay, string> = {
  mon: "Monday",
  tue: "Tuesday",
  wed: "Wednesday",
  thu: "Thursday",
  fri: "Friday",
}

/** Canonical display order; `Schedule.Meta.ordering` sorts by the raw key. */
export const SCHEDULE_DAY_ORDER: readonly ScheduleDay[] = [
  "mon",
  "tue",
  "wed",
  "thu",
  "fri",
]

export interface ScheduleSubjectAssignment {
  id: string
  subject_name: string
  subject_code: string
  faculty_name: string | null
  section_name: string
  academic_year_name: string
}

/** One row of `GET /academics/schedules/` (`ScheduleSerializer`). */
export interface ScheduleEntry {
  id: string
  day_of_week: ScheduleDay
  /** `TimeField` serializes as "HH:MM:SS". */
  start_time: string
  end_time: string
  room: string | null
  subject_assignment_detail: ScheduleSubjectAssignment
}

/**
 * "HH:MM:SS" (or "HH:MM") → "7:30 AM".
 *
 * The `time-to-string` conversion happens here rather than in the page so the
 * display never sees a raw database clock value, and a malformed time degrades
 * to itself instead of throwing mid-render.
 */
export function formatScheduleTime(value: string): string {
  const match = /^(\d{1,2}):(\d{2})(?::\d{2})?$/.exec(value.trim())
  if (!match) return value

  const hour = Number(match[1])
  const minute = match[2]
  if (!Number.isInteger(hour) || hour > 23) return value

  const suffix = hour >= 12 ? "PM" : "AM"
  const hour12 = hour % 12 === 0 ? 12 : hour % 12
  return `${hour12}:${minute} ${suffix}`
}

export function useStudentSchedule() {
  return useQuery<ScheduleEntry[], Error>({
    queryKey: ["student", "schedule"],
    queryFn: async () => {
      const { results } = await fetchAllPages<ScheduleEntry>(
        "/academics/schedules/"
      )
      return results
    },
  })
}

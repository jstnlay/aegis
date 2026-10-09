import { describe, expect, it } from "vitest"

import {
  SCHEDULE_DAY_LABELS,
  SCHEDULE_DAY_ORDER,
  formatScheduleTime,
} from "@/features/student/schedule-api"

describe("formatScheduleTime", () => {
  it("renders the clock values DRF sends in 12-hour form", () => {
    expect(formatScheduleTime("07:30:00")).toBe("7:30 AM")
    expect(formatScheduleTime("13:05:00")).toBe("1:05 PM")
    expect(formatScheduleTime("00:15:00")).toBe("12:15 AM")
    expect(formatScheduleTime("12:00:00")).toBe("12:00 PM")
    // Some serializers drop the seconds; both must render.
    expect(formatScheduleTime("08:00")).toBe("8:00 AM")
  })

  it("passes an unparseable value through instead of throwing", () => {
    expect(formatScheduleTime("")).toBe("")
    expect(formatScheduleTime("not a time")).toBe("not a time")
    expect(formatScheduleTime("25:99:99")).toBe("25:99:99")
  })
})

describe("day labels", () => {
  it("covers every Schedule.DayChoices key in weekday order", () => {
    expect(SCHEDULE_DAY_ORDER).toEqual(["mon", "tue", "wed", "thu", "fri"])
    expect(Object.keys(SCHEDULE_DAY_LABELS).sort()).toEqual(
      [...SCHEDULE_DAY_ORDER].sort()
    )
    expect(SCHEDULE_DAY_LABELS.mon).toBe("Monday")
    expect(SCHEDULE_DAY_LABELS.fri).toBe("Friday")
  })
})

import { describe, expect, it } from "vitest"

import { NO_DATA_TEXT, formatCount, formatPercent } from "@/lib/metric-format"

describe("formatPercent", () => {
  it("renders a real measurement", () => {
    expect(formatPercent(87.456, 2)).toBe("87.46%")
    expect(formatPercent(87.456, 1)).toBe("87.5%")
    expect(formatPercent(50, 0)).toBe("50%")
  })

  it("preserves a legitimate zero instead of masking it as N/A", () => {
    // 0% is a real measurement: every attendance record was an absence.
    expect(formatPercent(0, 1)).toBe("0.0%")
    expect(formatPercent(0, 2)).toBe("0.00%")
  })

  it("renders N/A for absent data rather than 0.00%", () => {
    expect(formatPercent(null, 2)).toBe(NO_DATA_TEXT)
    expect(formatPercent(undefined, 2)).toBe(NO_DATA_TEXT)
  })

  it("renders N/A for non-finite values instead of NaN%", () => {
    expect(formatPercent(Number.NaN, 2)).toBe(NO_DATA_TEXT)
    expect(formatPercent(Number.POSITIVE_INFINITY, 2)).toBe(NO_DATA_TEXT)
  })
})

describe("formatCount", () => {
  it("renders a real count", () => {
    expect(formatCount(12)).toBe("12")
  })

  it("preserves a legitimate zero count", () => {
    // Zero active risk alerts is a real count, not missing data.
    expect(formatCount(0)).toBe("0")
  })

  it("renders N/A for absent data rather than 0", () => {
    expect(formatCount(null)).toBe(NO_DATA_TEXT)
    expect(formatCount(undefined)).toBe(NO_DATA_TEXT)
    expect(formatCount(Number.NaN)).toBe(NO_DATA_TEXT)
  })
})

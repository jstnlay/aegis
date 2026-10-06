import { describe, expect, it } from "vitest"

import {
  ariaSortFor,
  nextSortState,
  sortRows,
  type DataTableSort,
} from "./data-table-sort"

/**
 * PH11.10 client-side sorting.
 *
 * Every assertion here is about correctness a reader would notice: that a
 * numeric column orders by magnitude rather than as text, that a date column
 * orders chronologically rather than lexically, that a missing value does not
 * masquerade as zero, and that the source array is never mutated.
 */
describe("sortRows", () => {
  const rows = [
    { name: "Cara", score: 9, date: "2026-10-02" },
    { name: "Ana", score: 10, date: "2026-09-30" },
    { name: "Bea", score: 100, date: "2026-1-05" },
  ]

  it("orders numbers by magnitude, not lexically", () => {
    const sorted = sortRows(rows, { sortValue: (row) => row.score })

    // Lexically "100" < "10" < "9", which is the bug this guards.
    expect(sorted.map((row) => row.score)).toEqual([9, 10, 100])
  })

  it("orders ISO dates chronologically", () => {
    const sorted = sortRows(rows, { sortValue: (row) => row.date })

    // "2026-1-05" sorts after "2026-10-02" as a string but before it as a date.
    expect(sorted.map((row) => row.date)).toEqual([
      "2026-1-05",
      "2026-09-30",
      "2026-10-02",
    ])
  })

  it("orders strings case- and digit-insensitively", () => {
    const sorted = sortRows(rows, { sortValue: (row) => row.name })

    expect(sorted.map((row) => row.name)).toEqual(["Ana", "Bea", "Cara"])
  })

  it("does not mutate the input array", () => {
    const original = [...rows]
    sortRows(rows, { sortValue: (row) => row.score })

    expect(rows).toEqual(original)
  })

  it("returns a new array even when already ordered", () => {
    const sorted = sortRows(rows, { sortValue: (row) => row.name })

    expect(sorted).not.toBe(rows)
  })

  it("sinks a missing value below real ones, and treats empty string as missing", () => {
    const withGaps = [
      { label: "b", score: 1 },
      { label: "a", score: null },
      { label: "c", score: 2 },
      { label: "d", score: "" },
      { label: "e", score: undefined },
    ]
    const sorted = sortRows(withGaps, { sortValue: (row) => row.score })

    // 0 would sort as the smallest number if a gap were read as zero.
    expect(sorted.map((row) => row.label)).toEqual(["b", "c", "a", "d", "e"])
  })

  it("keeps all-missing rows in their original relative order", () => {
    const allMissing = [
      { label: "first", score: null },
      { label: "second", score: null },
      { label: "third", score: undefined },
    ]
    const sorted = sortRows(allMissing, { sortValue: (row) => row.score })

    expect(sorted.map((row) => row.label)).toEqual([
      "first",
      "second",
      "third",
    ])
  })

  it("breaks ties on the tie-break value", () => {
    const tied = [
      { name: "Zoe", team: "Delta" },
      { name: "Amy", team: "Alpha" },
      { name: "Max", team: "Charlie" },
    ]
    const sorted = sortRows(tied, {
      // Every primary value is missing, so the tie-break decides the order.
      sortValue: () => null,
      tieBreak: (row) => row.team,
    })

    expect(sorted.map((row) => row.team)).toEqual([
      "Alpha",
      "Charlie",
      "Delta",
    ])
  })

  it("uses the tie-break only when the primary values are equal", () => {
    const mixed = [
      { name: "Zoe", score: 1, team: "Delta" },
      { name: "Amy", score: 5, team: "Alpha" },
      { name: "Max", score: 1, team: "Charlie" },
    ]
    const sorted = sortRows(mixed, {
      sortValue: (row) => row.score,
      tieBreak: (row) => row.team,
    })

    // Zoe and Max tie on score 1, so the tie-break orders them (Charlie before
    // Delta) rather than leaving them in input order. Amy is last on score, so
    // its team is irrelevant.
    expect(sorted.map((row) => row.name)).toEqual(["Max", "Zoe", "Amy"])
  })

  it("compares booleans as false before true", () => {
    const flagged = [
      { name: "a", active: true },
      { name: "b", active: false },
      { name: "c", active: false },
    ]
    const sorted = sortRows(flagged, { sortValue: (row) => row.active })

    expect(sorted.map((row) => row.name)).toEqual(["b", "c", "a"])
  })

  it("compares Date instances by time, ignoring an invalid one", () => {
    const dated = [
      { name: "later", at: new Date("2026-10-02T00:00:00Z") },
      { name: "invalid", at: new Date("not a date") },
      { name: "earlier", at: new Date("2026-09-30T00:00:00Z") },
    ]
    const sorted = sortRows(dated, { sortValue: (row) => row.at })

    expect(sorted.map((row) => row.name)).toEqual([
      "earlier",
      "later",
      "invalid",
    ])
  })

  it("ignores a numeric string with surrounding whitespace as a number", () => {
    const spaced = [
      { name: "padded", score: " 7 " },
      { name: "plain", score: "10" },
    ]
    const sorted = sortRows(spaced, { sortValue: (row) => row.score })

    expect(sorted.map((row) => row.name)).toEqual(["padded", "plain"])
  })

  it("sorts a single row and an empty list without error", () => {
    expect(sortRows([], { sortValue: () => 1 })).toEqual([])

    const single = [{ n: 1 }]
    expect(
      sortRows(single, { sortValue: (row) => row.n }).map((row) => row.n)
    ).toEqual([1])
  })
})

describe("nextSortState", () => {
  it("starts ascending on an unsorted column", () => {
    expect(nextSortState(null, "name")).toEqual({ key: "name", direction: "asc" })
  })

  it("flips direction on the active column", () => {
    const asc: DataTableSort = { key: "name", direction: "asc" }

    expect(nextSortState(asc, "name")).toEqual({
      key: "name",
      direction: "desc",
    })
  })

  it("flips back to ascending", () => {
    const desc: DataTableSort = { key: "name", direction: "desc" }

    expect(nextSortState(desc, "name").direction).toBe("asc")
  })

  it("starts ascending when a different column is chosen", () => {
    const current: DataTableSort = { key: "name", direction: "desc" }

    expect(nextSortState(current, "score")).toEqual({
      key: "score",
      direction: "asc",
    })
  })
})

describe("ariaSortFor", () => {
  it("reports the direction of the active column", () => {
    expect(ariaSortFor({ key: "name", direction: "asc" }, "name")).toBe(
      "ascending"
    )
    expect(ariaSortFor({ key: "name", direction: "desc" }, "name")).toBe(
      "descending"
    )
  })

  it("reports nothing for an inactive column", () => {
    // `undefined` rather than "none": aria-sort belongs only on the sorted
    // header, and "none" on every other column would be noise.
    expect(ariaSortFor({ key: "name", direction: "asc" }, "score")).toBeUndefined()
    expect(ariaSortFor(null, "name")).toBeUndefined()
  })
})
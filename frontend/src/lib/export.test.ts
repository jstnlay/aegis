import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { apiClient } from "@/lib/api"
import { downloadExport } from "@/lib/export"

vi.mock("@/lib/api", () => ({
  apiClient: { get: vi.fn() },
}))

const mockedGet = vi.mocked(apiClient.get)

beforeEach(() => {
  // jsdom implements neither object URLs nor real downloads.
  URL.createObjectURL = vi.fn(() => "blob:aegis")
  URL.revokeObjectURL = vi.fn()
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {})
})

afterEach(() => {
  vi.clearAllMocks()
  vi.restoreAllMocks()
})

describe("downloadExport", () => {
  it("uses the hyphenated guidance-records route (TC-ADM-05)", async () => {
    mockedGet.mockResolvedValue({
      data: new Blob(["student_id\n"], { type: "text/csv" }),
      headers: {},
    })

    await downloadExport("guidance_records", "csv")

    expect(mockedGet).toHaveBeenCalledWith(
      "/data-import/exports/guidance-records/",
      { params: { file_format: "csv" }, responseType: "blob" }
    )
  })

  it("keeps the existing route for the other kinds", async () => {
    mockedGet.mockResolvedValue({
      data: new Blob(["student_id\n"], { type: "text/csv" }),
      headers: {},
    })

    await downloadExport("grades", "xlsx", "reimport")

    expect(mockedGet).toHaveBeenCalledWith("/data-import/exports/grades/", {
      params: { file_format: "xlsx", schema: "reimport" },
      responseType: "blob",
    })
  })
})

import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import type { ReactNode } from "react"
import { AxiosError, AxiosHeaders } from "axios"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { FacultyImportPage } from "./FacultyImportPage"
import { apiClient } from "@/lib/api"
import { fetchAllPages } from "@/lib/pagination"

/**
 * TC-FAC-18 / TC-FAC-19 — the faculty export surface.
 *
 * The QA log recorded exports as "not implemented yet" for faculty: the only
 * download UI was the admin data page. These tests pin the behaviour the log
 * asks for — grades and attendance offered to staff, the request going to the
 * real controlled-export endpoint, and the server's no-data message surfacing
 * instead of an empty (header-only) file.
 */

vi.mock("@/lib/api", () => ({
  apiClient: { get: vi.fn(), post: vi.fn() },
}))

vi.mock("@/lib/pagination", () => ({
  fetchAllPages: vi.fn(),
}))

const mockedGet = vi.mocked(apiClient.get)
const mockedPost = vi.mocked(apiClient.post)
const mockedFetchAllPages = vi.mocked(fetchAllPages)

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  )
  return render(<FacultyImportPage />, { wrapper })
}

function itemContaining(text: string): HTMLElement {
  const label = screen.getByText(text)
  const item = label.closest("li")
  if (!item) throw new Error(`no list item contains "${text}"`)
  return item
}

function exportError(
  status: number,
  code: string,
  message: string
): AxiosError {
  // Shape the interceptor leaves behind after hydrating the blob body.
  return new AxiosError(
    "Request failed with status code " + status,
    undefined,
    undefined,
    undefined,
    {
      data: { success: false, error: { code, message, details: null } },
      status,
      statusText: "",
      headers: new AxiosHeaders(),
      config: { headers: new AxiosHeaders() },
    }
  )
}

beforeEach(() => {
  mockedFetchAllPages.mockResolvedValue({ count: 0, results: [] })
  // jsdom implements neither object URLs nor real downloads.
  URL.createObjectURL = vi.fn(() => "blob:aegis")
  URL.revokeObjectURL = vi.fn()
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {})
})

afterEach(() => {
  vi.clearAllMocks()
  vi.restoreAllMocks()
})

describe("FacultyImportPage exports", () => {
  it("offers exactly the three faculty export types", () => {
    renderPage()

    expect(
      screen.getByRole("heading", { name: /imports & exports/i })
    ).toBeInTheDocument()
    expect(itemContaining("Subject performance report")).toBeInTheDocument()
    expect(itemContaining("Attendance report")).toBeInTheDocument()
    // FR-016 / TC-FAC-20: the advisory class summary joins them.
    expect(itemContaining("Advisory class summary")).toBeInTheDocument()
    // The students roster is admin-only (ADMIN_ONLY_EXPORT_TYPES).
    expect(screen.queryByText(/roster/i)).not.toBeInTheDocument()
  })

  it("downloads the subject performance report from the real endpoint (TC-FAC-18)", async () => {
    mockedGet.mockResolvedValue({
      data: new Blob(["student_id,subject_code\n"], { type: "text/csv" }),
      headers: {
        "content-disposition":
          "attachment; filename*=UTF-8''aegis_grades_export.csv",
      },
    })
    renderPage()

    fireEvent.click(
      within(itemContaining("Subject performance report")).getByRole("button", {
        name: /download csv/i,
      })
    )

    await waitFor(() =>
      expect(mockedGet).toHaveBeenCalledWith("/data-import/exports/grades/", {
        params: { file_format: "csv" },
        responseType: "blob",
      })
    )
    expect(URL.createObjectURL).toHaveBeenCalledTimes(1)
    expect(URL.revokeObjectURL).toHaveBeenCalledTimes(1)
  })

  it("surfaces the server's no-data message instead of a broken file (TC-FAC-19)", async () => {
    mockedGet.mockRejectedValue(
      exportError(400, "EXPORT_EMPTY", "No data is available for this export.")
    )
    renderPage()

    fireEvent.click(
      within(itemContaining("Attendance report")).getByRole("button", {
        name: /download csv/i,
      })
    )

    const alert = await screen.findByRole("alert")
    expect(alert).toHaveTextContent("No data is available for this export.")
    // Nothing was downloaded.
    expect(URL.createObjectURL).not.toHaveBeenCalled()
  })

  it("honours the selected format", async () => {
    mockedGet.mockResolvedValue({
      data: new Blob(["PK"], {
        type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      }),
      headers: {
        "content-disposition":
          "attachment; filename*=UTF-8''aegis_attendance_export.xlsx",
      },
    })
    renderPage()

    fireEvent.keyDown(screen.getByRole("combobox", { name: /format/i }), {
      key: "ArrowDown",
    })
    fireEvent.click(await screen.findByRole("option", { name: /excel/i }))

    fireEvent.click(
      within(itemContaining("Attendance report")).getByRole("button", {
        name: /download xlsx/i,
      })
    )

    await waitFor(() =>
      expect(mockedGet).toHaveBeenCalledWith(
        "/data-import/exports/attendance/",
        { params: { file_format: "xlsx" }, responseType: "blob" }
      )
    )
  })

  it("downloads the advisory class summary from its own endpoint (TC-FAC-20)", async () => {
    mockedGet.mockResolvedValue({
      data: new Blob(["student_id,average\nSTU-001,90.00\n"], {
        type: "text/csv",
      }),
      headers: {
        "content-disposition":
          "attachment; filename*=UTF-8''aegis_advisory_export.csv",
      },
    })
    renderPage()

    fireEvent.click(
      within(itemContaining("Advisory class summary")).getByRole("button", {
        name: /download csv/i,
      })
    )

    await waitFor(() =>
      expect(mockedGet).toHaveBeenCalledWith("/data-import/exports/advisory/", {
        params: { file_format: "csv" },
        responseType: "blob",
      })
    )
    expect(URL.createObjectURL).toHaveBeenCalledTimes(1)
  })
})

describe("FacultyImportPage upload", () => {
  it("posts the named worksheet with the file", async () => {
    mockedPost.mockResolvedValue({
      data: { id: "job-1", status: "completed" },
    })
    renderPage()

    const file = new File(["PK"], "attendance.xlsx", {
      type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    })
    fireEvent.change(screen.getByLabelText(/^file$/i), {
      target: { files: [file] },
    })
    fireEvent.change(screen.getByLabelText(/sheet/i), {
      target: { value: "Valid Attendance" },
    })
    fireEvent.click(screen.getByRole("button", { name: /upload and import/i }))

    await waitFor(() => expect(mockedPost).toHaveBeenCalledTimes(1))
    const call = mockedPost.mock.calls[0]!
    expect(call[0]).toBe("/academics/grades/batch-import/")
    const body = call[1] as FormData
    expect(body.get("sheet")).toBe("Valid Attendance")
    expect(body.get("file")).toBe(file)
  })

  it("omits a blank worksheet so single-sheet workbooks stay unchanged", async () => {
    mockedPost.mockResolvedValue({
      data: { id: "job-2", status: "completed" },
    })
    renderPage()

    fireEvent.change(screen.getByLabelText(/^file$/i), {
      target: { files: [new File(["PK"], "grades.xlsx")] },
    })
    fireEvent.change(screen.getByLabelText(/sheet/i), {
      target: { value: "   " },
    })
    fireEvent.click(screen.getByRole("button", { name: /upload and import/i }))

    await waitFor(() => expect(mockedPost).toHaveBeenCalledTimes(1))
    const body = mockedPost.mock.calls[0]![1] as FormData
    expect(body.get("sheet")).toBeNull()
  })
})

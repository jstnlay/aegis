import { apiClient } from "@/lib/api"

/**
 * Controlled export downloads (§5 Data import/export).
 *
 * These endpoints return a **file**, not a job resource, so they are a
 * download and not a query. `?file_format` is required and anything other
 * than csv/xlsx is rejected with a 400.
 *
 * Lives in `lib/` rather than in the admin feature because both the admin
 * data page and the faculty import page drive the same endpoint.
 */

/**
 * The controlled-export kinds the backend authorizes.
 *
 * `grades`, `attendance`, `students` and `guidance_records` match
 * `ExportType.ALL` (the administrator authority list, of which `students`,
 * `guidance_records` are admin-only). `advisory` is the faculty-only advisory
 * class summary (FR-016 / TC-FAC-20) and is deliberately not part of that
 * list.
 */
export type ExportKind =
  "grades" | "attendance" | "students" | "advisory" | "guidance_records"

/**
 * Which header flavor the file carries: `standard` is the human-readable
 * document, `reimport` (PH12 / TC-ADM-03/04/05) is the round-trip file whose
 * columns are exactly the matching import template's, so the download can be
 * uploaded unchanged.
 */
export type ExportSchema = "standard" | "reimport"
export type ExportFormat = "csv" | "xlsx"

/**
 * Trigger a controlled export download.
 *
 * `students` is admin-only; `advisory` is faculty-only; grades and
 * attendance are available to staff within their own scope. An empty scope
 * answers 400 `EXPORT_EMPTY` ("No data is available for this export.")
 * instead of a header-only file; the API layer reads that envelope back out
 * of the blob so callers can surface the real message.
 */
export async function downloadExport(
  kind: ExportKind,
  format: ExportFormat,
  schema: ExportSchema = "standard"
): Promise<void> {
  const response = await apiClient.get(`/data-import/exports/${kind}/`, {
    params:
      schema === "reimport"
        ? { file_format: format, schema }
        : { file_format: format },
    responseType: "blob",
  })

  const filename = filenameFromDisposition(
    response.headers["content-disposition"]
  )
  const blobUrl = URL.createObjectURL(response.data as Blob)
  try {
    const anchor = document.createElement("a")
    anchor.href = blobUrl
    anchor.download = filename ?? `aegis-${kind}.${format}`
    document.body.appendChild(anchor)
    anchor.click()
    anchor.remove()
  } finally {
    // Releasing the object URL is not optional: without it the downloaded blob
    // is retained for the lifetime of the document.
    URL.revokeObjectURL(blobUrl)
  }
}

/**
 * Offer rows the client already holds as a CSV file (TC-GUI-09).
 *
 * Used where the data is a read the caller is authorized to make and there
 * is no server-side export to ask for — the guidance report is exactly that:
 * one GET, rendered, and offered as a file. The rows are the API's own
 * values; nothing is recomputed or padded here.
 *
 * Cells are quoted by `JSON.stringify`, so a comma or a quote inside a value
 * cannot break the column layout, and a leading `=`/`+`/`-`/`@` is prefixed
 * with a tab the way the server's export neutralizes formula injection.
 */
export function downloadCsv(filename: string, rows: readonly string[][]): void {
  const body = rows
    .map((row) =>
      row
        .map((cell) => {
          const text = cell ?? ""
          const guarded = /^[=+\-@\t\r]/.test(text) ? `\t${text}` : text
          return JSON.stringify(guarded)
        })
        .join(",")
    )
    .join("\r\n")

  const blob = new Blob([`\ufeff${body}`], { type: "text/csv;charset=utf-8" })
  const url = URL.createObjectURL(blob)
  try {
    const anchor = document.createElement("a")
    anchor.href = url
    anchor.download = filename
    document.body.appendChild(anchor)
    anchor.click()
    anchor.remove()
  } finally {
    URL.revokeObjectURL(url)
  }
}

/**
 * Offer one student's guidance report as a file (FR-032 / TC-GUI-09).
 *
 * The report endpoint takes the same `?file_format` the controlled exports
 * do and returns a download, so this is a GET with `responseType: "blob"`
 * rather than a query. Deriving the rows here instead would mean a second
 * rendering of the report in the browser, which is exactly how the file and
 * the screen come to disagree.
 */
export async function downloadGuidanceReport(
  studentId: string,
  format: ExportFormat
): Promise<void> {
  const response = await apiClient.get(
    `/guidance/reports/student/${studentId}/`,
    { params: { file_format: format }, responseType: "blob" }
  )

  const filename =
    filenameFromDisposition(response.headers["content-disposition"]) ??
    `aegis-guidance-report.${format}`
  const blobUrl = URL.createObjectURL(response.data as Blob)
  try {
    const anchor = document.createElement("a")
    anchor.href = blobUrl
    anchor.download = filename
    document.body.appendChild(anchor)
    anchor.click()
    anchor.remove()
  } finally {
    URL.revokeObjectURL(blobUrl)
  }
}

/**
 * Pull the filename out of a `Content-Disposition` header.
 *
 * The backend builds it with `build_content_disposition()`, which RFC 5987
 * encodes as `filename*=UTF-8''...`. The plain `filename="..."` parameter is
 * read as a fallback for the non-ASCII case.
 */
export function filenameFromDisposition(
  header: string | undefined | null
): string | null {
  if (!header) return null

  const extended = /filename\*=UTF-8''([^;]+)/i.exec(header)
  if (extended?.[1]) {
    try {
      return decodeURIComponent(extended[1])
    } catch {
      return extended[1]
    }
  }

  const plain = /filename="([^"]+)"/i.exec(header)
  return plain?.[1] ?? null
}

import { Tabs } from "@/components/ui/tabs"
import { FileText } from "lucide-react"
import { useState } from "react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { DataTable, type DataTableColumn } from "@/components/ui/data-table"
import { useDataTablePagination } from "@/components/ui/data-table-pagination"
import { ErrorNote } from "@/components/feedback/Feedback"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  downloadExport,
  IMPORT_TYPE_LABELS,
  IMPORT_JOB_STATUS_LABELS,
  useCreateImportJob,
  useImportJob,
  useImportJobs,
  useImportTemplate,
  type ExportKind,
  type ImportJobStatus,
  type ImportJobSummary,
  type ImportType,
} from "@/features/admin/api"
import { normalizeApiError } from "@/lib/error"
import { downloadCsv } from "@/lib/export"

/**
 * Imports and exports.
 *
 * Both directions are shaped by what the backend actually supports.
 *
 * Imports: `ImportJobViewSet` allows only admin and faculty, restricts itself
 * to `get`/`post`/`head`/`options`, and **finishes small files inside the
 * request** — `create` calls `_run_job` inline, so a job of up to 200 rows
 * reaches a terminal state within the request that created it. A larger file
 * is handed to a worker (`apps/data_import/runner.py`) and polled here until it
 * is done. There is no "start" step and no retry or delete route, so neither
 * control exists here; a job that never finishes is retried by re-uploading,
 * which corrects the same records. The five `JobStatus` values are the real
 * choices, including `partial` for a job where some rows failed.
 *
 * Every accepted `ImportType` is backed by a domain importer as of PH11,
 * including `guidance_records`, which writes real `ConsultationRecord` rows.
 * The schema behind each type comes from
 * `GET /data-import/templates/{type}/`, so the header the tester downloads
 * is the header the importer validates — and it ships headers only, because
 * an example row would have to contain an invented `student_id` or `score`.
 *
 * Exports: three separate GET endpoints returning a **file**, not a job list.
 * They are a download rather than a query, and each requires `?file_format` —
 * anything but csv or xlsx is rejected with a 400.
 */

const STATUS_VARIANT: Record<
  ImportJobStatus,
  "default" | "secondary" | "destructive" | "outline"
> = {
  pending: "outline",
  processing: "secondary",
  completed: "default",
  partial: "secondary",
  failed: "destructive",
}

export function AdminDataPage() {
  const [tab, setTab] = useState<"imports" | "exports">("imports")

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-1">
        <div className="flex items-center gap-3">
          <FileText
            className="size-5 text-muted-foreground"
            aria-hidden="true"
          />
          <h2 className="text-2xl font-bold text-foreground">
            Imports &amp; Exports
          </h2>
        </div>
        <p className="text-sm text-muted-foreground">
          Bulk data movement in and out, with the per-row results of every
          import.
        </p>
      </div>

      {/* PH11.11: shared `Tabs` — adds `aria-controls`, a real `tabpanel`, and
          arrow-key roving focus. See `components/ui/tabs.tsx`. */}
      <Tabs
        label="Data operations"
        value={tab}
        onValueChange={setTab}
        items={[
          { id: "imports", label: "Imports", content: <ImportsCard /> },
          { id: "exports", label: "Exports", content: <ExportsCard /> },
        ]}
      />
    </div>
  )
}

/** Rows per page for the import history, which grows by one job per upload. */
const PAGE_SIZE = 20

/** Page sizes offered for the import history. */
const PAGE_SIZE_OPTIONS = [20, 50, 100] as const

function ImportsCard() {
  const jobsQuery = useImportJobs()
  const createJob = useCreateImportJob()
  const [file, setFile] = useState<File | null>(null)
  const [importType, setImportType] = useState<ImportType>("grades")
  const [sheet, setSheet] = useState("")
  const [expanded, setExpanded] = useState<string | null>(null)

  /*
   * PH11.10: import history grows by one job per upload and was rendered in
   * full. Paginated; the backend's own ordering (newest first) is left alone
   * because that is the order an administrator reads this list in.
   */
  const { pagination, pageRows, setPageSize } = useDataTablePagination(
    jobsQuery.data ?? [],
    PAGE_SIZE
  )

  const columns: readonly DataTableColumn<ImportJobSummary>[] = [
    {
      key: "file",
      header: "File",
      cell: (job) => (
        <div className="min-w-0">
          <div className="font-medium">{job.file_name || "(unnamed)"}</div>
          <div className="text-xs text-muted-foreground">
            {IMPORT_TYPE_LABELS[job.import_type] ?? job.import_type}
          </div>
        </div>
      ),
    },
    {
      key: "uploaded_by",
      header: "Uploaded by",
      cell: (job) => (
        <span className="text-sm text-muted-foreground">
          {job.uploaded_by?.name ?? "—"}
        </span>
      ),
    },
    {
      key: "status",
      header: "Status",
      cell: (job) => (
        <Badge
          variant={STATUS_VARIANT[job.status]}
          data-job-status={job.status}
        >
          {IMPORT_JOB_STATUS_LABELS[job.status] ?? job.status}
        </Badge>
      ),
    },
    {
      key: "rows",
      header: "Rows",
      cell: (job) => (
        <span className="text-sm text-muted-foreground">
          {job.processed_rows} of {job.total_rows}
          {job.error_rows > 0 ? ` · ${job.error_rows} failed` : ""}
        </span>
      ),
    },
    {
      key: "completed",
      header: "Completed",
      cell: (job) => (
        <span className="text-sm text-muted-foreground">
          {job.completed_at ? formatDateTime(job.completed_at) : "—"}
        </span>
      ),
    },
    {
      key: "actions",
      header: "Actions",
      cell: (job) => (
        <Button
          type="button"
          variant="outline"
          size="xs"
          aria-expanded={expanded === job.id}
          onClick={() => setExpanded((cur) => (cur === job.id ? null : job.id))}
        >
          {expanded === job.id ? "Hide rows" : "Row results"}
        </Button>
      ),
    },
  ]

  return (
    <>
      <Card>
        <CardHeader>
          <CardTitle>Upload a file</CardTitle>
          <CardDescription>
            CSV or XLSX. The server detects the real type from the file&apos;s
            contents rather than its extension. A small file finishes before
            you get the response; a large one keeps running in the background
            and this list refreshes itself until it is done.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <form
            className="space-y-3"
            onSubmit={(event) => {
              event.preventDefault()
              if (!file) return
              createJob.mutate({ file, importType, sheet })
            }}
          >
            <div className="grid gap-3 sm:grid-cols-3">
              <div className="space-y-1.5">
                <Label htmlFor="import-type">Import type</Label>
                <Select
                  value={importType}
                  onValueChange={(value) => setImportType(value as ImportType)}
                >
                  <SelectTrigger id="import-type">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {(Object.keys(IMPORT_TYPE_LABELS) as ImportType[]).map(
                      (type) => (
                        <SelectItem key={type} value={type}>
                          {IMPORT_TYPE_LABELS[type]}
                        </SelectItem>
                      )
                    )}
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="import-file">File</Label>
                <Input
                  id="import-file"
                  type="file"
                  accept=".csv,.xlsx"
                  onChange={(event) => setFile(event.target.files?.[0] ?? null)}
                />
              </div>

              {/* XLSX only. A workbook with a README or a second sheet needs
                  this: without a name, the server requires exactly one
                  visible worksheet and rejects the rest. */}
              <div className="space-y-1.5">
                <Label htmlFor="import-sheet">Sheet (XLSX only)</Label>
                <Input
                  id="import-sheet"
                  placeholder="e.g. Attendance"
                  value={sheet}
                  onChange={(event) => setSheet(event.target.value)}
                />
                <p className="text-xs text-muted-foreground">
                  Optional. Leave blank when the workbook has one sheet.
                </p>
              </div>
            </div>

            {createJob.isError ? (
              <ErrorNote message={normalizeApiError(createJob.error).message} />
            ) : null}

            <Button type="submit" disabled={!file || createJob.isPending}>
              {createJob.isPending ? "Processing…" : "Upload and import"}
            </Button>
          </form>

          <TemplateGuide importType={importType} />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Import history</CardTitle>
          <CardDescription>
            Every job, newest first as the backend orders them. Expand one to
            see its per-row results.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <DataTable
            caption="Import jobs"
            columns={columns}
            rows={pageRows}
            rowKey={(job) => job.id}
            isLoading={jobsQuery.isLoading}
            error={
              jobsQuery.isError
                ? normalizeApiError(jobsQuery.error).message
                : null
            }
            loadingLabel="Loading import jobs"
            emptyMessage="No files have been imported yet."
            pagination={pagination}
            pageSizeOptions={PAGE_SIZE_OPTIONS}
            onPageSizeChange={setPageSize}
          />

          {expanded ? <ImportJobRecords jobId={expanded} /> : null}
        </CardContent>
      </Card>
    </>
  )
}

function ImportJobRecords({ jobId }: { jobId: string }) {
  const detailQuery = useImportJob(jobId)

  if (detailQuery.isLoading) {
    return (
      <p
        role="status"
        aria-busy="true"
        className="text-sm text-muted-foreground"
      >
        Loading row results…
      </p>
    )
  }
  if (detailQuery.isError) {
    return <ErrorNote message={normalizeApiError(detailQuery.error).message} />
  }
  const detail = detailQuery.data
  if (!detail) return null

  const failed = detail.records.filter((record) => record.status === "error")

  return (
    <div className="space-y-3">
      {detail.error_log.length > 0 ? (
        <div className="space-y-1">
          {detail.error_log.map((entry, index) => (
            <p
              key={`${jobId}-log-${index}`}
              className="text-sm text-destructive"
            >
              {entry.code}: {entry.message}
            </p>
          ))}
        </div>
      ) : null}

      <p className="text-sm text-muted-foreground">
        {detail.record_summary.success} succeeded ·{" "}
        {detail.record_summary.error} failed · {detail.record_summary.skipped}{" "}
        skipped
      </p>

      {failed.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          No rows failed in this job.
        </p>
      ) : (
        <ul className="space-y-1">
          {failed.map((record) => (
            <li
              key={record.id}
              className="rounded-md border border-destructive/30 bg-destructive/10 p-2 text-sm"
            >
              <p className="font-medium">Row {record.row_number}</p>
              {record.error_message ? (
                <p className="text-destructive">{record.error_message}</p>
              ) : null}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

/**
 * The column guide for the selected import type.
 *
 * Fetched rather than restated in the client, so the header row the tester
 * downloads is built from the same list the importer validates — the two
 * cannot drift. The file ships headers only: an example row would have to
 * contain an invented `student_id` or `score`, which would either be written
 * as a record that never happened or fail validation and teach the wrong
 * lesson. The tester adds their own rows beneath the headers.
 */
function TemplateGuide({ importType }: { importType: ImportType }) {
  const templateQuery = useImportTemplate(importType)
  const template = templateQuery.data

  return (
    <div className="space-y-2 rounded-md border border-border p-3">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 space-y-1">
          <p className="text-sm font-medium">Column guide</p>
          <p className="text-xs text-muted-foreground">
            {IMPORT_TYPE_LABELS[importType]} — required columns first, in the
            order the importer reports a missing one.
          </p>
        </div>
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={!template}
          onClick={() => {
            if (!template) return
            downloadCsv(`aegis-${importType}-template.csv`, [template.header])
          }}
        >
          Download template (.csv)
        </Button>
      </div>

      {templateQuery.isError ? (
        <p className="text-xs text-muted-foreground">
          No column guide is available for this import type.
        </p>
      ) : templateQuery.isLoading ? (
        <p
          role="status"
          aria-busy="true"
          className="text-xs text-muted-foreground"
        >
          Loading the column guide…
        </p>
      ) : template ? (
        <>
          <ul className="space-y-1">
            {template.columns.map((column) => (
              <li
                key={column.name}
                className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5"
              >
                <code className="font-mono text-xs">{column.name}</code>
                <span
                  className={
                    column.required
                      ? "text-xs font-medium text-foreground"
                      : "text-xs text-muted-foreground"
                  }
                >
                  {column.required ? "required" : "optional"}
                </span>
                <span className="text-xs text-muted-foreground">
                  — {column.hint}
                </span>
              </li>
            ))}
          </ul>

          {template.forbidden_columns.length > 0 ? (
            <p className="text-xs text-muted-foreground">
              Server-controlled, rejected if present:{" "}
              <code className="font-mono">
                {template.forbidden_columns.join(", ")}
              </code>
            </p>
          ) : null}

          <p className="text-xs text-muted-foreground">
            The downloaded file contains these headers and no rows — add your
            own data beneath them.
          </p>
        </>
      ) : null}
    </div>
  )
}

const EXPORTS: readonly {
  kind: ExportKind
  label: string
  description: string
}[] = [
  {
    kind: "grades",
    label: "Grades",
    description: "Every grade record in scope, with its subject and period.",
  },
  {
    kind: "attendance",
    label: "Attendance",
    description: "Every attendance record in scope.",
  },
  {
    kind: "students",
    label: "Students",
    description: "The student roster. Administrators only.",
  },
]

function ExportsCard() {
  const [format, setFormat] = useState<"csv" | "xlsx">("csv")
  const [pendingKind, setPendingKind] = useState<ExportKind | null>(null)
  const [error, setError] = useState<string | null>(null)

  const run = async (kind: ExportKind) => {
    setPendingKind(kind)
    setError(null)
    try {
      await downloadExport(kind, format)
    } catch (caught) {
      setError(normalizeApiError(caught).message)
    } finally {
      setPendingKind(null)
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Controlled exports</CardTitle>
        <CardDescription>
          Each export is generated server-side from an authorised queryset. The
          response is a file, not a job you poll for.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="space-y-1.5 sm:max-w-xs">
          <Label htmlFor="export-format">Format</Label>
          <Select
            value={format}
            onValueChange={(value) => setFormat(value as "csv" | "xlsx")}
          >
            <SelectTrigger id="export-format">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="csv">CSV</SelectItem>
              <SelectItem value="xlsx">Excel (XLSX)</SelectItem>
            </SelectContent>
          </Select>
        </div>

        {error ? <ErrorNote message={error} /> : null}

        <ul className="space-y-3">
          {EXPORTS.map((entry) => (
            <li
              key={entry.kind}
              className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-border p-3"
            >
              <div className="min-w-0">
                <p className="font-medium">{entry.label}</p>
                <p className="text-xs text-muted-foreground">
                  {entry.description}
                </p>
              </div>
              <Button
                type="button"
                variant="outline"
                onClick={() => void run(entry.kind)}
                disabled={pendingKind !== null}
              >
                {pendingKind === entry.kind
                  ? "Preparing…"
                  : `Download ${format.toUpperCase()}`}
              </Button>
            </li>
          ))}
        </ul>

        <p className="text-xs text-muted-foreground">
          Each download is written to the audit log as an export event against
          the real dataset it covers.
        </p>
      </CardContent>
    </Card>
  )
}

function formatDateTime(value: string): string {
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return value
  return parsed.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  })
}

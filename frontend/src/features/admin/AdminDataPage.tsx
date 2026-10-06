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
  IMPORT_TYPE_PARSES_ONLY,
  IMPORT_JOB_STATUS_LABELS,
  useCreateImportJob,
  useImportJob,
  useImportJobs,
  type ExportKind,
  type ImportJobStatus,
  type ImportJobSummary,
  type ImportType,
} from "@/features/admin/api"
import { normalizeApiError } from "@/lib/error"

/**
 * Imports and exports.
 *
 * Both directions are shaped by what the backend actually supports.
 *
 * Imports: `ImportJobViewSet` allows only admin and faculty, restricts itself
 * to `get`/`post`/`head`/`options`, and **runs the pipeline synchronously** —
 * `create` calls `_run_job` inline, so a job reaches a terminal state within
 * the request that created it. There is no "start" step and no retry or delete
 * route, so neither control exists here. The five `JobStatus` values are the
 * real choices, including `partial` for a job where some rows failed.
 *
 * One import type needs a caveat the UI must not hide: `guidance_records` is an
 * accepted `ImportType` and an admin may submit it, but
 * `_dispatch_domain_processing` has no guidance importer and falls through to
 * the legacy parse-only path, which marks rows successful without writing any
 * domain record. The form labels it accordingly.
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
          <h1 className="text-2xl font-bold text-foreground">
            Imports &amp; Exports
          </h1>
        </div>
        <p className="text-sm text-muted-foreground">
          Bulk data movement in and out, with the per-row results of every
          import.
        </p>
      </div>

      <div
        className="flex flex-wrap gap-2"
        role="tablist"
        aria-label="Data operations"
      >
        {(
          [
            { id: "imports", label: "Imports" },
            { id: "exports", label: "Exports" },
          ] as const
        ).map((entry) => (
          <Button
            key={entry.id}
            role="tab"
            type="button"
            variant={tab === entry.id ? "default" : "outline"}
            aria-selected={tab === entry.id}
            onClick={() => setTab(entry.id)}
          >
            {entry.label}
          </Button>
        ))}
      </div>

      {tab === "imports" ? <ImportsCard /> : <ExportsCard />}
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
            contents rather than its extension, and processes the upload
            synchronously — the response already carries the finished job.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <form
            className="space-y-3"
            onSubmit={(event) => {
              event.preventDefault()
              if (!file) return
              createJob.mutate({ file, importType })
            }}
          >
            <div className="grid gap-3 sm:grid-cols-2">
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
            </div>

            {IMPORT_TYPE_PARSES_ONLY.includes(importType) ? (
              <p className="text-xs text-muted-foreground">
                {IMPORT_TYPE_LABELS[importType]} currently validates and reports
                rows only — it does not write guidance records, because the
                backend has no guidance importer behind this type.
              </p>
            ) : null}

            {createJob.isError ? (
              <ErrorNote message={normalizeApiError(createJob.error).message} />
            ) : null}

            <Button type="submit" disabled={!file || createJob.isPending}>
              {createJob.isPending ? "Processing…" : "Upload and import"}
            </Button>
          </form>
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

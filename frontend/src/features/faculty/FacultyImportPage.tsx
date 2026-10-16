import { Download, Upload } from "lucide-react"
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
  FACULTY_IMPORT_TYPES,
  useFacultyImportJob,
  useFacultyImportJobs,
  type FacultyImportJob,
  type FacultyImportType,
} from "@/features/faculty/api"
import { normalizeApiError } from "@/lib/error"
import {
  downloadExport,
  type ExportFormat,
  type ExportKind,
} from "@/lib/export"

/**
 * Faculty bulk upload and controlled downloads (Final_Revision objective
 * 1.2.3; TC-FAC-18 / TC-FAC-19 / TC-FAC-20).
 *
 * Scope is deliberately narrower than the admin imports page:
 *
 * - Imports: only `grades` and `attendance`.
 *   `ALL_FACULTY_IMPORT_TYPES` in `apps/data_import/constants.py` is
 *   exactly those two; students and guidance_records are admin-only and are
 *   not offered here at all.
 * - Exports: the three kinds in `ALL_FACULTY_EXPORT_TYPES` — the subject
 *   performance report, the attendance report, and the advisory class
 *   summary. The students roster stays admin-only.
 * - Each import option posts to its own batch-import alias
 *   (`/academics/grades/batch-import/`, `/attendance/records/batch-import/`),
 *   which pins `import_type` server-side. The server therefore cannot receive a
 *   grades file under the attendance type, whatever this form sends.
 * - The list below is only this faculty's own uploads:
 *   `ImportJobViewSet.get_queryset` filters by `uploaded_by` for faculty.
 *
 * The pipeline finishes small files in the request, and hands larger ones to a
 * worker; either way the per-row outcome shown here is real, and the list polls
 * itself while a job is still running. Nothing here invents counts.
 */

const STATUS_VARIANT: Record<
  string,
  "default" | "secondary" | "destructive" | "outline"
> = {
  pending: "outline",
  processing: "secondary",
  completed: "default",
  partial: "secondary",
  failed: "destructive",
}

export function FacultyImportPage() {
  const [file, setFile] = useState<File | null>(null)
  const [importType, setImportType] = useState<FacultyImportType>("grades")
  const [sheet, setSheet] = useState("")

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-1">
        <div className="flex items-center gap-3">
          <Upload className="size-5 text-muted-foreground" aria-hidden="true" />
          <h2 className="text-2xl font-bold text-foreground">
            Imports &amp; exports
          </h2>
        </div>
        <p className="text-sm text-muted-foreground">
          Upload grades or attendance in bulk instead of encoding row by row, or
          download your own records as a file.
        </p>
      </div>

      <UploadCard
        file={file}
        importType={importType}
        sheet={sheet}
        onFileChange={setFile}
        onImportTypeChange={setImportType}
        onSheetChange={setSheet}
      />
      <HistoryCard />
      <ExportsCard />
    </div>
  )
}

function UploadCard({
  file,
  importType,
  sheet,
  onFileChange,
  onImportTypeChange,
  onSheetChange,
}: {
  file: File | null
  importType: FacultyImportType
  sheet: string
  onFileChange: (file: File | null) => void
  onImportTypeChange: (value: FacultyImportType) => void
  onSheetChange: (value: string) => void
}) {
  const createJob = useFacultyImportJob()

  return (
    <Card>
      <CardHeader>
        <CardTitle>Upload a file</CardTitle>
        <CardDescription>
          CSV or XLSX. The server detects the real type from the file&apos;s
          contents rather than its extension. A small file finishes before you
          get the response; a large one keeps running in the background and
          the history below refreshes itself until it is done.
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
              <Label htmlFor="faculty-import-type">Import type</Label>
              <Select
                value={importType}
                onValueChange={(value) =>
                  onImportTypeChange(value as FacultyImportType)
                }
              >
                <SelectTrigger id="faculty-import-type">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {FACULTY_IMPORT_TYPES.map((option) => (
                    <SelectItem key={option.type} value={option.type}>
                      {option.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="faculty-import-file">File</Label>
              <Input
                id="faculty-import-file"
                type="file"
                accept=".csv,.xlsx"
                onChange={(event) =>
                  onFileChange(event.target.files?.[0] ?? null)
                }
              />
            </div>

            {/* XLSX only. Name the sheet when the workbook carries more than
                one — the server never guesses which sheet holds the data. */}
            <div className="space-y-1.5">
              <Label htmlFor="faculty-import-sheet">Sheet (XLSX only)</Label>
              <Input
                id="faculty-import-sheet"
                placeholder="e.g. Attendance"
                value={sheet}
                onChange={(event) => onSheetChange(event.target.value)}
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

function HistoryCard() {
  const jobsQuery = useFacultyImportJobs()

  const columns: readonly DataTableColumn<FacultyImportJob>[] = [
    {
      key: "file",
      header: "File",
      cell: (job) => (
        <div className="min-w-0">
          <div className="font-medium">{job.file_name || "(unnamed)"}</div>
          <div className="text-xs text-muted-foreground">
            {FACULTY_IMPORT_TYPES.find((t) => t.type === job.import_type)
              ?.label ?? job.import_type}
          </div>
        </div>
      ),
    },
    {
      key: "status",
      header: "Status",
      cell: (job) => (
        <Badge variant={STATUS_VARIANT[job.status] ?? "outline"}>
          {job.status}
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
      key: "uploaded",
      header: "Uploaded",
      cell: (job) => (
        <span className="text-sm text-muted-foreground">
          {formatDateTime(job.created_at)}
        </span>
      ),
    },
  ]

  return (
    <Card>
      <CardHeader>
        <CardTitle>Your uploads</CardTitle>
        <CardDescription>
          Jobs you submitted, newest first. Only your own uploads are listed.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <DataTable
          caption="Your batch upload history"
          columns={columns}
          rows={jobsQuery.data ?? []}
          rowKey={(job) => job.id}
          isLoading={jobsQuery.isLoading}
          error={
            jobsQuery.isError
              ? normalizeApiError(jobsQuery.error).message
              : null
          }
          loadingLabel="Loading your uploads"
          emptyMessage="You have not uploaded a file yet."
        />
      </CardContent>
    </Card>
  )
}

/**
 * Controlled downloads (TC-FAC-18 / TC-FAC-19).
 *
 * Exactly the two export types faculty may reach — `ALL_FACULTY_EXPORT_TYPES`
 * in `apps/data_import/constants.py` is grades and attendance; the students
 * roster is admin-only and is not offered here. Each response is a file
 * within the caller's own scope, and an empty scope answers 400
 * `EXPORT_EMPTY`, which is shown as the server's message rather than a
 * broken download.
 */
const FACULTY_EXPORTS: readonly {
  kind: ExportKind
  label: string
  description: string
}[] = [
  {
    kind: "grades",
    label: "Subject performance report",
    description: "Grades you have encoded, with subject and grading period.",
  },
  {
    kind: "attendance",
    label: "Attendance report",
    description: "Attendance you have recorded for your sections.",
  },
  {
    kind: "advisory",
    label: "Advisory class summary",
    description:
      "One row per student in your class: attendance counts and grade average over your own sections.",
  },
]

function ExportsCard() {
  const [format, setFormat] = useState<ExportFormat>("csv")
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
        <CardTitle>Exports</CardTitle>
        <CardDescription>
          Download your own grades or attendance as a CSV or XLSX file. If
          nothing is on record yet, the server answers with a message instead of
          an empty file.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="space-y-1.5 sm:max-w-xs">
          <Label htmlFor="faculty-export-format">Format</Label>
          <Select
            value={format}
            onValueChange={(value) => setFormat(value as ExportFormat)}
          >
            <SelectTrigger id="faculty-export-format">
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
          {FACULTY_EXPORTS.map((entry) => (
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
                <Download className="size-4" aria-hidden="true" />
                {pendingKind === entry.kind
                  ? "Preparing…"
                  : `Download ${format.toUpperCase()}`}
              </Button>
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  )
}

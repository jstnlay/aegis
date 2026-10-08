import { Upload } from "lucide-react"
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

/**
 * Faculty bulk upload (Final_Revision objective 1.2.3).
 *
 * Scope is deliberately narrower than the admin imports page:
 *
 * - Only `grades` and `attendance`. `ALL_FACULTY_IMPORT_TYPES` in
 *   `apps/data_import/constants.py` is exactly those two; students and
 *   guidance_records are admin-only and are not offered here at all.
 * - Each option posts to its own batch-import alias
 *   (`/academics/grades/batch-import/`, `/attendance/records/batch-import/`),
 *   which pins `import_type` server-side. The server therefore cannot receive a
 *   grades file under the attendance type, whatever this form sends.
 * - The list below is only this faculty's own uploads:
 *   `ImportJobViewSet.get_queryset` filters by `uploaded_by` for faculty.
 *
 * The pipeline runs synchronously, so a successful upload returns a terminal job
 * and the per-row outcome is real. Nothing here invents counts.
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

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-1">
        <div className="flex items-center gap-3">
          <Upload className="size-5 text-muted-foreground" aria-hidden="true" />
          <h2 className="text-2xl font-bold text-foreground">Batch upload</h2>
        </div>
        <p className="text-sm text-muted-foreground">
          Upload grades or attendance in bulk instead of encoding row by row.
        </p>
      </div>

      <UploadCard
        file={file}
        importType={importType}
        onFileChange={setFile}
        onImportTypeChange={setImportType}
      />
      <HistoryCard />
    </div>
  )
}

function UploadCard({
  file,
  importType,
  onFileChange,
  onImportTypeChange,
}: {
  file: File | null
  importType: FacultyImportType
  onFileChange: (file: File | null) => void
  onImportTypeChange: (value: FacultyImportType) => void
}) {
  const createJob = useFacultyImportJob()

  return (
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

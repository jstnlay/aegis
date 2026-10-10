import { useState } from "react"
import { FileDown } from "lucide-react"

import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { ErrorNote } from "@/components/feedback/Feedback"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { useAuth } from "@/features/auth/AuthContext"
import { normalizeApiError } from "@/lib/error"
import {
  downloadExport,
  type ExportFormat,
  type ExportKind,
} from "@/lib/export"

interface ReportDef {
  kind: ExportKind
  label: string
  description: string
}

/**
 * Reports: compiled file downloads, one list per role.
 *
 * There is no separate report model. Each entry is a controlled export the
 * backend authorizes for the caller's own scope (staff see their sections,
 * students their rows, parents their linked children, admins the school).
 * Kinds outside a role's scope are not offered — a control that can only be
 * refused should not exist.
 */
const REPORTS_BY_ROLE: Record<string, readonly ReportDef[]> = {
  admin: [
    {
      kind: "grades",
      label: "Grades report",
      description: "Every grade record in scope, with subject and period.",
    },
    {
      kind: "attendance",
      label: "Attendance report",
      description: "Every attendance record in scope.",
    },
    {
      kind: "students",
      label: "Students report",
      description: "The enrollment roster. Administrators only.",
    },
  ],
  faculty: [
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
        "One row per student in your class: attendance counts and grade average.",
    },
  ],
  guidance: [
    {
      kind: "grades",
      label: "Grades report",
      description: "Grade records in your guidance scope.",
    },
    {
      kind: "attendance",
      label: "Attendance report",
      description: "Attendance records in your guidance scope.",
    },
  ],
  student: [
    {
      kind: "grades",
      label: "My grades report",
      description: "Your finalized grade records.",
    },
    {
      kind: "attendance",
      label: "My attendance report",
      description: "Your attendance records.",
    },
  ],
  parent: [
    {
      kind: "grades",
      label: "Child grades report",
      description: "Finalized grades for your linked children.",
    },
    {
      kind: "attendance",
      label: "Child attendance report",
      description: "Attendance records for your linked children.",
    },
  ],
}

export function ReportsPage() {
  const { user } = useAuth()
  const [format, setFormat] = useState<ExportFormat>("csv")
  const [pendingKind, setPendingKind] = useState<ExportKind | null>(null)
  const [error, setError] = useState<string | null>(null)

  if (!user) return null
  const reports = REPORTS_BY_ROLE[user.role] ?? []

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
    <div className="space-y-6">
      <div className="flex flex-col gap-1">
        <div className="flex items-center gap-3">
          <FileDown
            className="size-5 text-muted-foreground"
            aria-hidden="true"
          />
          <h2 className="text-2xl font-bold text-foreground">Reports</h2>
        </div>
        <p className="text-sm text-muted-foreground">
          File downloads compiled for your role. Each file contains only what
          you are authorized to see.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Available reports</CardTitle>
          <CardDescription>
            Showing {reports.length} report
            {reports.length === 1 ? "" : "s"}.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="max-w-xs space-y-1.5">
            <Label htmlFor="reports-format">File format</Label>
            <Select
              value={format}
              onValueChange={(value) => setFormat(value as ExportFormat)}
            >
              <SelectTrigger id="reports-format">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="csv">CSV</SelectItem>
                <SelectItem value="xlsx">Excel</SelectItem>
              </SelectContent>
            </Select>
          </div>

          {error ? <ErrorNote message={error} /> : null}

          <ul className="space-y-2">
            {reports.map((report) => (
              <li
                key={report.kind}
                className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-border p-3"
              >
                <div className="min-w-0">
                  <p className="font-medium">{report.label}</p>
                  <p className="text-xs text-muted-foreground">
                    {report.description}
                  </p>
                </div>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  disabled={pendingKind !== null}
                  onClick={() => void run(report.kind)}
                >
                  {pendingKind === report.kind
                    ? "Preparing…"
                    : `Download ${format.toUpperCase()}`}
                </Button>
              </li>
            ))}
          </ul>
        </CardContent>
      </Card>
    </div>
  )
}

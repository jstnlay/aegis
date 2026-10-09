import { ShieldAlert } from "lucide-react"
import { useMemo } from "react"

import { Badge } from "@/components/ui/badge"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { DataTable, type DataTableColumn } from "@/components/ui/data-table"
import {
  ALERT_STATUS_LABELS,
  BEHAVIORAL_NOTE_TYPE_LABELS,
  CONSULTATION_PRIORITY_LABELS,
  CONSULTATION_SESSION_TYPE_LABELS,
  CONSULTATION_STATUS_LABELS,
  RISK_ALERT_SOURCE_LABELS,
  RISK_LEVEL_LABELS,
  OPEN_ALERT_STATUSES,
  type AlertStatus,
  type BehavioralNoteType,
  type ConsultationPriority,
  type ConsultationSessionType,
  type ConsultationStatus,
  type RiskLevel,
} from "@/features/parent/labels"
import {
  useChildBehavioralNotes,
  useChildConsultations,
  useChildRiskAlerts,
  type LinkedStudent,
  type ParentBehavioralNote,
  type ParentConsultation,
  type ParentRiskAlert,
} from "@/features/parent/api"
import { useDataTablePagination } from "@/components/ui/data-table-pagination"
import { riskFactorLabel } from "@/lib/risk-factor"
import {
  consultationStatusBadgeClass,
  riskLevelBadgeClass,
} from "@/lib/status-badge"

/**
 * Parent's read-only view of the Guidance Office's involvement with a child.
 *
 * Every control that would mutate a guidance record is absent by design. The
 * backend answers 403 for a parent on consultation create/update/delete and on
 * the acknowledge/escalate/resolve transitions (PH11.9), so an actionable
 * button here could only ever produce an error. The counselor drives the
 * lifecycle; the parent reads it.
 *
 * Data is fetched per selected child and additionally filtered by that child's
 * UUID on the client. The client filter is a refinement, never the control: the
 * server already scopes each queryset to `ParentStudentLink` children, so an
 * unlinked student's rows cannot arrive in the first place.
 */

interface SupportProps {
  child: LinkedStudent
}

/*
 * Stable empty-array identities.
 *
 * `query.data ?? []` allocates a fresh array on every render, which makes the
 * `useMemo` below re-run each time and defeats its purpose. These are shared
 * constants so an unresolved query produces the same reference every render.
 */
const EMPTY_ALERTS: readonly ParentRiskAlert[] = []
const EMPTY_CONSULTATIONS: readonly ParentConsultation[] = []
const EMPTY_NOTES: readonly ParentBehavioralNote[] = []

export function ParentSupportPage({ child }: SupportProps) {
  const alertsQuery = useChildRiskAlerts(child.id)
  const consultationsQuery = useChildConsultations(child.id)
  const notesQuery = useChildBehavioralNotes(child.id)

  const alerts = alertsQuery.data ?? EMPTY_ALERTS
  const consultations = consultationsQuery.data ?? EMPTY_CONSULTATIONS
  const notes = notesQuery.data ?? EMPTY_NOTES

  const openAlerts = useMemo(
    () =>
      alerts.filter((alert) =>
        (OPEN_ALERT_STATUSES as readonly string[]).includes(alert.status)
      ),
    [alerts]
  )

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-1">
        <div className="flex items-center gap-3">
          <ShieldAlert
            className="size-5 text-muted-foreground"
            aria-hidden="true"
          />
          <h2 className="text-2xl font-bold text-foreground">
            {child.student_name}&apos;s Student Support
          </h2>
        </div>
        <p className="text-sm text-muted-foreground">
          A read-only record of the Guidance Office&apos;s involvement with{" "}
          {child.student_name}. Alerts and sessions are recorded and updated by
          the counselor, not by you.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Risk alerts</CardTitle>
          <CardDescription>
            {openAlerts.length > 0
              ? `${openAlerts.length} open alert${openAlerts.length === 1 ? "" : "s"}.`
              : "No open risk alerts."}{" "}
            Resolved alerts remain listed below as history.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <RiskAlertTable
            alerts={alerts}
            isLoading={alertsQuery.isLoading}
            error={
              alertsQuery.isError
                ? "Unable to load risk alerts. Please try again."
                : null
            }
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Counselling sessions</CardTitle>
          <CardDescription>
            Sessions recorded by the Guidance Office for {child.student_name}.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <ConsultationTable
            consultations={consultations}
            isLoading={consultationsQuery.isLoading}
            error={
              consultationsQuery.isError
                ? "Unable to load counselling sessions. Please try again."
                : null
            }
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Behavioural notes</CardTitle>
          <CardDescription>
            Notes recorded by class teachers. These are immutable once written.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <BehavioralNoteList
            notes={notes}
            isLoading={notesQuery.isLoading}
            error={
              notesQuery.isError
                ? "Unable to load behavioural notes. Please try again."
                : null
            }
          />
        </CardContent>
      </Card>
    </div>
  )
}

const alertColumns: readonly DataTableColumn<ParentRiskAlert>[] = [
  {
    key: "level",
    header: "Risk level",
    cell: (alert) => (
      <Badge
        variant="secondary"
        className={riskLevelBadgeClass(alert.risk_level)}
        data-risk-level={alert.risk_level}
      >
        {RISK_LEVEL_LABELS[alert.risk_level as RiskLevel] ?? alert.risk_level}
      </Badge>
    ),
  },
  {
    key: "status",
    header: "Status",
    cell: (alert) => (
      <Badge variant="outline" data-alert-status={alert.status}>
        {ALERT_STATUS_LABELS[alert.status as AlertStatus] ?? alert.status}
      </Badge>
    ),
  },
  {
    key: "factors",
    header: "Recorded factors",
    cell: (alert) =>
      alert.risk_factors.length === 0 ? (
        <span className="text-muted-foreground">None recorded</span>
      ) : (
        <ul className="space-y-0.5">
          {alert.risk_factors.map((factor, index) => (
            <li key={`${alert.id}-factor-${index}`} className="text-xs">
              {/*
                The AI engine stores objects here (`{feature, value,
                threshold, direction}`) and counselors store free text.
                Rendering the raw entry used to hand React an object and
                unmount the page.
              */}
              {riskFactorLabel(factor) || "Unlabelled factor"}
            </li>
          ))}
        </ul>
      ),
  },
  {
    key: "source",
    header: "How it was raised",
    cell: (alert) => (
      <span className="text-sm text-muted-foreground">
        {RISK_ALERT_SOURCE_LABELS[
          alert.source as keyof typeof RISK_ALERT_SOURCE_LABELS
        ] ?? alert.source}
      </span>
    ),
  },
  {
    key: "generated",
    header: "Logged",
    cell: (alert) => (
      <span className="text-sm text-muted-foreground">
        {formatDate(alert.generated_at)}
      </span>
    ),
  },
  {
    key: "counselor",
    header: "Counselor",
    cell: (alert) =>
      alert.assigned_counselor_name ? (
        <span className="text-sm">{alert.assigned_counselor_name}</span>
      ) : (
        <span className="text-muted-foreground">Unassigned</span>
      ),
  },
]

function RiskAlertTable({
  alerts,
  isLoading,
  error,
}: {
  alerts: readonly ParentRiskAlert[]
  isLoading: boolean
  error: string | null
}) {
  const { pagination, pageRows } = useDataTablePagination(alerts, 10)

  return (
    <DataTable
      caption="Risk alerts"
      columns={alertColumns}
      rows={pageRows}
      rowKey={(alert) => alert.id}
      isLoading={isLoading}
      error={error}
      loadingLabel="Loading risk alerts"
      emptyMessage="No risk alerts have been logged for this student."
      pagination={pagination}
    />
  )
}

const consultationColumns: readonly DataTableColumn<ParentConsultation>[] = [
  {
    key: "date",
    header: "Session date",
    cell: (row) => (
      <span className="text-sm font-medium">
        {formatDate(row.session_date)}
      </span>
    ),
  },
  {
    key: "type",
    header: "Type",
    cell: (row) => (
      <span className="text-sm">
        {CONSULTATION_SESSION_TYPE_LABELS[
          row.session_type as ConsultationSessionType
        ] ?? row.session_type}
      </span>
    ),
  },
  {
    key: "status",
    header: "Status",
    cell: (row) => (
      <Badge
        variant="outline"
        className={consultationStatusBadgeClass(row.status)}
      >
        {CONSULTATION_STATUS_LABELS[row.status as ConsultationStatus] ??
          row.status}
      </Badge>
    ),
  },
  {
    key: "priority",
    header: "Priority",
    cell: (row) => (
      <span className="text-sm">
        {CONSULTATION_PRIORITY_LABELS[
          row.priority_level as ConsultationPriority
        ] ?? row.priority_level}
      </span>
    ),
  },
  {
    key: "concerns",
    header: "Concerns",
    cell: (row) =>
      row.concern_categories.length === 0 ? (
        <span className="text-muted-foreground">—</span>
      ) : (
        <span className="text-sm">{row.concern_categories.join(", ")}</span>
      ),
  },
  {
    key: "next",
    header: "Next session",
    cell: (row) =>
      row.next_session_date ? (
        <span className="text-sm">{formatDate(row.next_session_date)}</span>
      ) : (
        <span className="text-muted-foreground">—</span>
      ),
  },
]

function ConsultationTable({
  consultations,
  isLoading,
  error,
}: {
  consultations: readonly ParentConsultation[]
  isLoading: boolean
  error: string | null
}) {
  const { pagination, pageRows } = useDataTablePagination(consultations, 10)

  return (
    <DataTable
      caption="Counselling sessions"
      columns={consultationColumns}
      rows={pageRows}
      rowKey={(row) => row.id}
      isLoading={isLoading}
      error={error}
      loadingLabel="Loading counselling sessions"
      emptyMessage="No counselling sessions have been recorded for this student."
      pagination={pagination}
    />
  )
}

function BehavioralNoteList({
  notes,
  isLoading,
  error,
}: {
  notes: readonly ParentBehavioralNote[]
  isLoading: boolean
  error: string | null
}) {
  if (isLoading) {
    return (
      <p
        role="status"
        aria-busy="true"
        className="py-6 text-center text-sm text-muted-foreground"
      >
        Loading behavioural notes…
      </p>
    )
  }
  if (error) {
    return (
      <div
        role="alert"
        className="rounded-md border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive"
      >
        <span>{error}</span>
      </div>
    )
  }
  if (notes.length === 0) {
    return (
      <p className="py-6 text-center text-sm text-muted-foreground">
        No behavioural notes have been recorded for this student.
      </p>
    )
  }

  return (
    <ul className="space-y-2">
      {notes.map((note) => (
        <li key={note.id} className="rounded-md border border-border p-3">
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="outline">
              {BEHAVIORAL_NOTE_TYPE_LABELS[
                note.note_type as BehavioralNoteType
              ] ?? note.note_type}
            </Badge>
            <span className="text-xs text-muted-foreground">
              {formatDate(note.date_recorded)}
            </span>
          </div>
          <p className="mt-2 text-sm">{note.note_text}</p>
        </li>
      ))}
    </ul>
  )
}

function formatDate(value: string): string {
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return value
  return parsed.toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  })
}

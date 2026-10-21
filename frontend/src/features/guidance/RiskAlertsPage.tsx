import { ShieldAlert } from "lucide-react"
import { useMemo, useState, type FormEvent } from "react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { DataTable, type DataTableColumn } from "@/components/ui/data-table"
import { MetricCard } from "@/components/ui/metric-card"
import { useDataTablePagination } from "@/components/ui/data-table-pagination"
import { orderRows, type DataTableSort } from "@/components/ui/data-table-sort"
import {
  ALERT_TRANSITIONS_BY_STATUS,
  RISK_ALERT_STATUSES,
  RISK_ALERT_STATUS_LABELS,
  RISK_ALERT_TRANSITION_LABELS,
  RISK_ALERT_SOURCE_LABELS,
  RISK_LEVELS,
  RISK_LEVEL_LABELS,
  RISK_LEVEL_ORDER,
  countAlertsByStatus,
  filterRiskAlerts,
  riskFactorLabel,
  useCreateRiskAlert,
  useRiskAlertTransition,
  useRiskAlerts,
  useStudentRoster,
  type RiskAlert,
  type RiskAlertStatus,
  type RiskAlertTransition,
  type RiskLevel,
} from "@/features/guidance/api"
import { normalizeApiError } from "@/lib/error"
import { formatCount } from "@/lib/metric-format"
import { riskLevelBadgeClass } from "@/lib/status-badge"

/** Rows per page for a list that covers every alert in the school. */
const PAGE_SIZE = 25

/** Page sizes offered for this list. */
const PAGE_SIZE_OPTIONS = [25, 50, 100] as const

function PageHeading({
  title,
  description,
}: {
  title: string
  description: string
}) {
  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center gap-3">
        <ShieldAlert
          className="size-5 text-muted-foreground"
          aria-hidden="true"
        />
        <h2 className="text-2xl font-bold text-foreground">{title}</h2>
      </div>
      <p className="text-sm text-muted-foreground">{description}</p>
    </div>
  )
}

function ErrorNote({ message }: { message: string }) {
  return (
    <div
      role="alert"
      className="flex items-start gap-2 rounded-md border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive"
    >
      <span>{message}</span>
    </div>
  )
}

function AlertStatusBadge({ status }: { status: RiskAlertStatus }) {
  return (
    <Badge variant="outline" data-alert-status={status}>
      {RISK_ALERT_STATUS_LABELS[status]}
    </Badge>
  )
}

/** ISO timestamp -> short local date, or the raw string if unparseable. */
function formatDate(iso: string): string {
  const parsed = new Date(iso)
  if (Number.isNaN(parsed.getTime())) return iso
  return parsed.toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  })
}

/**
 * Status filter row with live counts.
 *
 * The counts come from `countAlertsByStatus` over the unfiltered list, so the
 * chip totals always describe the whole visible set rather than shrinking as
 * the user narrows it — otherwise "Resolved (0)" would be indistinguishable
 * from "no resolved alerts exist".
 */
function StatusFilterChips({
  counts,
  value,
  onChange,
}: {
  counts: ReturnType<typeof countAlertsByStatus>
  value: RiskAlertStatus | "all"
  onChange: (next: RiskAlertStatus | "all") => void
}) {
  const options: ReadonlyArray<RiskAlertStatus | "all"> = [
    "all",
    ...RISK_ALERT_STATUSES,
  ]

  return (
    <div
      className="flex flex-wrap gap-2"
      role="group"
      aria-label="Filter by status"
    >
      {options.map((option) => {
        const active = value === option
        return (
          <Button
            key={option}
            type="button"
            size="sm"
            variant={active ? "default" : "outline"}
            aria-pressed={active}
            onClick={() => onChange(option)}
          >
            {option === "all" ? "All" : RISK_ALERT_STATUS_LABELS[option]}{" "}
            <span className="tabular-nums opacity-80">{counts[option]}</span>
          </Button>
        )
      })}
    </div>
  )
}

/**
 * Per-row lifecycle actions.
 *
 * Only the transitions the backend will accept from the alert's current
 * status are rendered (`ALERT_TRANSITIONS_BY_STATUS` mirrors the viewset's
 * guards, each of which rejects an out-of-order call with a 400). Offering an
 * illegal action would surface as a server error rather than a disabled
 * control, so the button set is derived from verified state instead.
 */
function TransitionButtons({
  alert,
  onTransition,
  isPending,
  isPendingThisAlert,
}: {
  alert: RiskAlert
  onTransition: (input: { id: string; transition: RiskAlertTransition }) => void
  isPending: boolean
  isPendingThisAlert: boolean
}) {
  const transitions = ALERT_TRANSITIONS_BY_STATUS[alert.status]

  if (transitions.length === 0) {
    return (
      <span className="text-xs text-muted-foreground">
        No actions available
      </span>
    )
  }

  return (
    <div className="flex flex-wrap gap-1.5">
      {transitions.map((transition) => (
        <Button
          key={transition}
          type="button"
          size="xs"
          variant={transition === "escalate" ? "destructive" : "outline"}
          disabled={isPending}
          onClick={() => onTransition({ id: alert.id, transition })}
        >
          {isPendingThisAlert && transition === "acknowledge"
            ? "Working…"
            : RISK_ALERT_TRANSITION_LABELS[transition]}
        </Button>
      ))}
    </div>
  )
}

/**
 * New alert form.
 *
 * Two deliberate omissions, both because the contract offers no source:
 * - No counselor field. `assigned_counselor` is writable, but no endpoint a
 *   counselor may read lists guidance profiles, so there is nothing to populate
 *   a picker with; the backend assigns the caller.
 * - No source field. `RiskAlertViewSet.perform_create` forces `source =
 *   "manual"` and it is read-only on the serializer.
 */
function NewAlertDialog() {
  const rosterQuery = useStudentRoster()
  const create = useCreateRiskAlert()

  const [open, setOpen] = useState(false)
  const [studentId, setStudentId] = useState("")
  const [riskLevel, setRiskLevel] = useState<RiskLevel>("moderate")
  const [factorsText, setFactorsText] = useState("")

  const roster = rosterQuery.data ?? []

  const factorList = useMemo(
    () =>
      factorsText
        .split("\n")
        .map((line) => line.trim())
        .filter((line) => line.length > 0),
    [factorsText]
  )

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!studentId) return
    try {
      await create.mutateAsync({
        student: studentId,
        risk_level: riskLevel,
        risk_factors: factorList,
      })
      setStudentId("")
      setFactorsText("")
      setOpen(false)
    } catch {
      // Surfaced from `create.isError` below; a failed create must leave the
      // dialog open with the entered values intact so nothing is retyped.
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button>New risk alert</Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>New risk alert</DialogTitle>
          <DialogDescription>
            Log an observation about a student. The alert is assigned to you and
            recorded with a manual source.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-1.5">
            {/*
              The student is mandatory — the submit button stays disabled
              without one — and the requirement is now carried two ways: the
              visible asterisk for the sighted reader and `aria-required` on the
              trigger for the programmatic one. The asterisk is a SIBLING of the
              label, never a child: anything inside `<label>` counts towards the
              control's accessible name, which would make it "Student *" and
              have every announcement say the requirement twice.
            */}
            <div className="flex items-center gap-1">
              <Label htmlFor="alert-student">Student</Label>
              <span aria-hidden="true" className="text-destructive">
                *
              </span>
            </div>
            <Select
              value={studentId}
              onValueChange={setStudentId}
              disabled={rosterQuery.isLoading || roster.length === 0}
            >
              <SelectTrigger id="alert-student" aria-required="true">
                <SelectValue
                  placeholder={
                    rosterQuery.isLoading
                      ? "Loading students"
                      : roster.length === 0
                        ? "No students in roster"
                        : "Select a student"
                  }
                />
              </SelectTrigger>
              <SelectContent>
                {roster.map((entry) => (
                  <SelectItem key={entry.id} value={entry.id}>
                    {entry.name} — {entry.code}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <p className="text-xs text-muted-foreground">
              The roster comes from enrollments, which is the only student list
              a counselor can read.
            </p>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="alert-level">Risk level</Label>
            <Select
              value={riskLevel}
              onValueChange={(value) => setRiskLevel(value as RiskLevel)}
            >
              <SelectTrigger id="alert-level">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {RISK_LEVELS.map((level) => (
                  <SelectItem key={level} value={level}>
                    {RISK_LEVEL_LABELS[level]}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="alert-factors">Risk factors</Label>
            <textarea
              id="alert-factors"
              rows={3}
              value={factorsText}
              onChange={(event) => setFactorsText(event.target.value)}
              placeholder={"One factor per line, e.g.\nChronic absenteeism"}
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-xs outline-none focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring"
            />
            <p className="text-xs text-muted-foreground">
              {factorList.length} factor{factorList.length === 1 ? "" : "s"}{" "}
              will be saved. Optional.
            </p>
          </div>

          {create.isError ? (
            <ErrorNote message={normalizeApiError(create.error).message} />
          ) : null}

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => setOpen(false)}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              disabled={create.isPending || !studentId || roster.length === 0}
            >
              {create.isPending ? "Creating…" : "Create alert"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

export function RiskAlertsPage() {
  const alertsQuery = useRiskAlerts()
  const rosterQuery = useStudentRoster()
  const transition = useRiskAlertTransition()

  const [status, setStatus] = useState<RiskAlertStatus | "all">("all")
  const [riskLevel, setRiskLevel] = useState<RiskLevel | "all">("all")
  const [search, setSearch] = useState("")

  const alerts = useMemo(() => alertsQuery.data ?? [], [alertsQuery.data])

  const visible = useMemo(
    () => filterRiskAlerts(alerts, { status, riskLevel, search }),
    [alerts, status, riskLevel, search]
  )

  const counts = useMemo(() => countAlertsByStatus(alerts), [alerts])

  const [sort, setSort] = useState<DataTableSort | null>(null)

  /**
   * Student UUID -> human-facing code.
   *
   * `RiskAlertSerializer` carries no student ID code, so the only verified way
   * to show one is the enrollment roster. A student who has no enrollment is
   * omitted rather than rendered as a raw UUID.
   */
  const codeByStudent = useMemo(() => {
    const map = new Map<string, string>()
    for (const entry of rosterQuery.data ?? []) map.set(entry.id, entry.code)
    return map
  }, [rosterQuery.data])

  const isFiltered =
    status !== "all" || riskLevel !== "all" || search.trim().length > 0

  const columns = useMemo<readonly DataTableColumn<RiskAlert>[]>(
    () => [
      {
        key: "student",
        header: "Student",
        sortValue: (row) => row.student_name,
        sortTieBreak: (row) => codeByStudent.get(row.student) ?? null,
        cell: (row) => (
          <>
            <div className="font-medium whitespace-nowrap">
              {row.student_name}
            </div>
            {codeByStudent.get(row.student) ? (
              <div className="text-xs text-muted-foreground">
                {codeByStudent.get(row.student)}
              </div>
            ) : null}
          </>
        ),
      },
      {
        key: "riskLevel",
        header: "Level",
        /*
         * Ranked by the declared order of the risk levels rather than
         * alphabetically, so ascending reads low → moderate → high.
         */
        sortValue: (row) => RISK_LEVEL_ORDER[row.risk_level],
        sortTieBreak: (row) => row.student_name,
        cell: (row) => (
          <Badge
            variant="secondary"
            className={riskLevelBadgeClass(row.risk_level)}
            data-risk-level={row.risk_level}
          >
            {RISK_LEVEL_LABELS[row.risk_level]}
          </Badge>
        ),
      },
      {
        key: "status",
        header: "Status",
        sortValue: (row) => row.status,
        sortTieBreak: (row) => row.student_name,
        cell: (row) => <AlertStatusBadge status={row.status} />,
      },
      {
        key: "factors",
        header: "Factors",
        /*
         * Free text, and unbounded length: an AI-derived alert whose factor does
         * not map to a known label renders the raw key (`riskFactorLabel` falls
         * back to the raw value), so this cell can be far wider than any column
         * label. Wrapping plus a minimum width keeps it readable instead of
         * pushing the rest of the row off screen.
         */
        cellClassName: "whitespace-normal align-top min-w-[12rem]",
        cell: (row) =>
          row.risk_factors.length === 0 ? (
            <span className="text-muted-foreground">—</span>
          ) : (
            <ul className="space-y-0.5">
              {row.risk_factors.map((factor, index) => (
                <li key={`${row.id}-factor-${index}`} className="text-xs">
                  {riskFactorLabel(factor) || "Unlabelled factor"}
                </li>
              ))}
            </ul>
          ),
      },
      {
        key: "source",
        header: "Source",
        sortValue: (row) => row.source,
        cellClassName: "text-sm text-muted-foreground",
        cell: (row) => RISK_ALERT_SOURCE_LABELS[row.source],
      },
      {
        key: "generated",
        header: "Generated",
        sortValue: (row) => row.generated_at,
        sortTieBreak: (row) => row.student_name,
        cellClassName: "text-sm text-muted-foreground",
        cell: (row) => formatDate(row.generated_at),
      },
      {
        key: "actions",
        header: "Actions",
        cell: (row) => (
          <TransitionButtons
            alert={row}
            isPending={transition.isPending}
            isPendingThisAlert={
              transition.isPending && transition.variables?.id === row.id
            }
            onTransition={(input) => transition.mutate(input)}
          />
        ),
      },
    ],
    [codeByStudent, transition]
  )

  /*
   * PH11.10: the alert table rendered every matching row and reimplemented the
   * three list states by hand. It now uses `DataTable`, gains client-side
   * sorting (the guidance viewsets declare no `ordering` filter backend, so
   * there is nothing to send) and gains pagination for a list that reaches
   * every alert in the school.
   */
  const sorted = useMemo(
    () => orderRows(visible, sort, columns),
    [visible, sort, columns]
  )

  const { pagination, pageRows, setPageSize } = useDataTablePagination(
    sorted,
    PAGE_SIZE,
    `alerts:${status}:${riskLevel}:${search}`
  )

  return (
    <div className="space-y-6">
      <PageHeading
        title="Risk Alerts"
        description="Every risk alert across the school, with the transitions each alert currently allows."
      />

      {/*
        Status summary, per the reference: one centered tile per status plus
        the total. Counted over the unfiltered list (`counts`), so narrowing
        the table never shrinks them — a filtered "Resolved (0)" would be
        indistinguishable from "nothing was ever resolved". Zeros here are
        measured (no alerts in that status), not missing, which is why an
        empty file still draws five zeroes rather than hiding the row.
      */}
      <div className="grid grid-cols-2 gap-3 sm:gap-4 md:grid-cols-3 lg:grid-cols-5">
        <MetricCard
          centered
          title="Total Alerts"
          isLoading={alertsQuery.isLoading}
          isError={alertsQuery.isError}
        >
          {formatCount(counts.all)}
        </MetricCard>
        <MetricCard
          centered
          title="Active"
          hint="Currently active"
          isLoading={alertsQuery.isLoading}
          isError={alertsQuery.isError}
        >
          {formatCount(counts.active)}
        </MetricCard>
        <MetricCard
          centered
          title="Under monitoring"
          hint="Being monitored"
          isLoading={alertsQuery.isLoading}
          isError={alertsQuery.isError}
        >
          {formatCount(counts.under_monitoring)}
        </MetricCard>
        <MetricCard
          centered
          title="Resolved"
          hint="Successfully resolved"
          isLoading={alertsQuery.isLoading}
          isError={alertsQuery.isError}
        >
          {formatCount(counts.resolved)}
        </MetricCard>
        <MetricCard
          centered
          title="Escalated"
          hint="Requires immediate attention"
          isLoading={alertsQuery.isLoading}
          isError={alertsQuery.isError}
        >
          {formatCount(counts.escalated)}
        </MetricCard>
      </div>

      <Card>
        <CardHeader>
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="space-y-1">
              <CardTitle>Alerts</CardTitle>
              <CardDescription>
                Showing {visible.length} of {alerts.length}. Alerts are visible
                school-wide to guidance.
              </CardDescription>
            </div>
            <NewAlertDialog />
          </div>
        </CardHeader>

        <CardContent className="space-y-4">
          <StatusFilterChips
            counts={counts}
            value={status}
            onChange={setStatus}
          />

          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            <div className="space-y-1.5">
              <Label htmlFor="alert-filter-level">Risk level</Label>
              <Select
                value={riskLevel}
                onValueChange={(value) =>
                  setRiskLevel(value as RiskLevel | "all")
                }
              >
                <SelectTrigger id="alert-filter-level">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All levels</SelectItem>
                  {RISK_LEVELS.map((level) => (
                    <SelectItem key={level} value={level}>
                      {RISK_LEVEL_LABELS[level]}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-1.5 sm:col-span-1 lg:col-span-2">
              <Label htmlFor="alert-search">Search</Label>
              <Input
                id="alert-search"
                type="search"
                value={search}
                placeholder="Student, counselor, or risk factor"
                onChange={(event) => setSearch(event.target.value)}
              />
            </div>
          </div>

          {transition.isError ? (
            <ErrorNote message={normalizeApiError(transition.error).message} />
          ) : null}

          {/*
            A successful transition is just as much a change to the page as a
            failed one, and it used to be silent: the row's status badge and its
            button set both mutate after the refetch, but nothing announced it,
            so a screen-reader user got no confirmation that the action landed.
            `role="status"` rather than `alert` because nothing went wrong and
            the reader should not be interrupted — the same distinction
            `Feedback.tsx` draws between `ErrorNote` and `EmptyState`.
          */}
          {transition.isSuccess && transition.variables ? (
            <p role="status" className="text-sm text-muted-foreground">
              {RISK_ALERT_TRANSITION_LABELS[transition.variables.transition]}{" "}
              recorded. The alert list has been refreshed.
            </p>
          ) : null}

          <DataTable
            caption="Risk alerts"
            columns={columns}
            rows={pageRows}
            rowKey={(row) => row.id}
            rowProps={(row) => ({ "data-alert-id": row.id })}
            isLoading={alertsQuery.isLoading}
            error={
              alertsQuery.isError
                ? normalizeApiError(alertsQuery.error).message
                : null
            }
            loadingLabel="Loading risk alerts"
            emptyMessage={
              isFiltered
                ? "No alerts match the current filters."
                : "No risk alerts have been logged."
            }
            pagination={pagination}
            pageSizeOptions={PAGE_SIZE_OPTIONS}
            onPageSizeChange={setPageSize}
            sort={sort}
            onSortChange={setSort}
          />
        </CardContent>
      </Card>

      <p className="text-xs text-muted-foreground">
        Resolved alerts are closed cases and are excluded from the at-risk count
        on the Guidance dashboard. Only the transitions the backend accepts from
        each status are offered.
      </p>
    </div>
  )
}

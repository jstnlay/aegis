import { MessageSquareText } from "lucide-react"
import { useCallback, useMemo, useState, type FormEvent } from "react"

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
import { Field } from "@/components/ui/form-field"
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
import { useDataTablePagination } from "@/components/ui/data-table-pagination"
import { orderRows, type DataTableSort } from "@/components/ui/data-table-sort"
import {
  CONCERN_CATEGORIES,
  CONCERN_CATEGORY_LABELS,
  CONSULTATION_PRIORITIES,
  CONSULTATION_PRIORITY_LABELS,
  CONSULTATION_PRIORITY_RANK,
  CONSULTATION_SESSION_TYPES,
  CONSULTATION_SESSION_TYPE_LABELS,
  CONSULTATION_STATUSES,
  CONSULTATION_STATUS_LABELS,
  countConsultationsByStatus,
  filterConsultations,
  useConsultations,
  useCreateConsultation,
  useStudentRoster,
  useUpdateConsultation,
  type ConcernCategory,
  type Consultation,
  type ConsultationPriority,
  type ConsultationSessionType,
  type ConsultationStatus,
} from "@/features/guidance/api"
import { normalizeApiError } from "@/lib/error"
import { useHideCompleted } from "@/lib/archive"
import {
  consultationStatusBadgeClass,
  riskLevelBadgeClass,
} from "@/lib/status-badge"

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
        <MessageSquareText
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

function ConsultationStatusBadge({ status }: { status: ConsultationStatus }) {
  return (
    <Badge
      variant="outline"
      className={consultationStatusBadgeClass(status)}
      data-consultation-status={status}
    >
      {CONSULTATION_STATUS_LABELS[status]}
    </Badge>
  )
}

/**
 * `TimeField` renders `HH:MM:SS`; the seconds are always zero in practice and
 * only add noise in a table cell.
 */
function formatTime(value: string): string {
  return value.slice(0, 5)
}

/**
 * Priority reuses the risk-level badge map.
 *
 * `ConsultationRecord.PriorityLevel` and `RiskAlert.RiskLevel` are the same
 * three values carrying the same ordinal meaning, so they share one treatment
 * rather than duplicating an identical class map.
 */
function PriorityBadge({ priority }: { priority: ConsultationPriority }) {
  return (
    <Badge
      variant="secondary"
      className={riskLevelBadgeClass(priority)}
      data-priority={priority}
    >
      {CONSULTATION_PRIORITY_LABELS[priority]}
    </Badge>
  )
}

/**
 * Status filter row with live counts.
 *
 * Counts come from the unfiltered list so the chip totals always describe the
 * whole visible set instead of collapsing to zero as the user narrows it.
 */
function StatusFilterChips({
  counts,
  value,
  onChange,
}: {
  counts: ReturnType<typeof countConsultationsByStatus>
  value: ConsultationStatus | "all"
  onChange: (next: ConsultationStatus | "all") => void
}) {
  const options: ReadonlyArray<ConsultationStatus | "all"> = [
    "all",
    ...CONSULTATION_STATUSES,
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
            {option === "all" ? "All" : CONSULTATION_STATUS_LABELS[option]}{" "}
            <span className="tabular-nums opacity-80">{counts[option]}</span>
          </Button>
        )
      })}
    </div>
  )
}

/**
 * Concern-category toggle group.
 *
 * There is no multi-select primitive in `components/ui`, and a set of pressed
 * buttons maps onto the `concern_categories` JSON array more honestly than a
 * `<select multiple>` would. The backend validates membership of each entry
 * against a closed set, so the options are built from `CONCERN_CATEGORIES`
 * rather than free text.
 */
function ConcernCategoryPicker({
  value,
  onToggle,
  legend,
}: {
  value: ConcernCategory[]
  onToggle: (category: ConcernCategory) => void
  legend: string
}) {
  return (
    <fieldset className="space-y-1.5">
      <legend className="text-sm font-medium">{legend}</legend>
      <div className="flex flex-wrap gap-1.5">
        {CONCERN_CATEGORIES.map((category) => {
          const selected = value.includes(category)
          return (
            <Button
              key={category}
              type="button"
              size="sm"
              variant={selected ? "secondary" : "outline"}
              aria-pressed={selected}
              onClick={() => onToggle(category)}
            >
              {CONCERN_CATEGORY_LABELS[category]}
            </Button>
          )
        })}
      </div>
    </fieldset>
  )
}

/**
 * `POST /guidance/consultations/` form.
 *
 * There is deliberately no counselor field: `counselor` is a read-only
 * serializer field that `perform_create` sets from the caller, and the list is
 * already scoped to that caller.
 *
 * `onSaved` exists because the dialog closes on success, which unmounts
 * everything inside it — including any confirmation the form might render. The
 * live region that reports the save therefore has to live on the page, outside
 * this component; this only tells the page what to say.
 */
function NewConsultationDialog({
  onSaved,
}: {
  onSaved: (message: string) => void
}) {
  const rosterQuery = useStudentRoster()
  const create = useCreateConsultation()

  const [open, setOpen] = useState(false)
  const [studentId, setStudentId] = useState("")
  const [sessionDate, setSessionDate] = useState("")
  const [sessionTime, setSessionTime] = useState("")
  const [sessionType, setSessionType] = useState<ConsultationSessionType>(
    "individual_counseling"
  )
  const [concerns, setConcerns] = useState<ConcernCategory[]>([])
  const [notes, setNotes] = useState("")
  const [priority, setPriority] = useState<ConsultationPriority>("medium")
  const [nextSessionDate, setNextSessionDate] = useState("")

  const roster = rosterQuery.data ?? []
  // `validate_session_notes` rejects a blank value, so the form mirrors that
  // instead of letting the server 400 on an avoidable field.
  const notesBlank = notes.trim().length === 0

  function toggleConcern(category: ConcernCategory) {
    setConcerns((current) =>
      current.includes(category)
        ? current.filter((item) => item !== category)
        : [...current, category]
    )
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!studentId || !sessionDate || !sessionTime || notesBlank) return
    try {
      await create.mutateAsync({
        student: studentId,
        session_date: sessionDate,
        session_time: sessionTime,
        session_type: sessionType,
        concern_categories: concerns,
        session_notes: notes.trim(),
        priority_level: priority,
        next_session_date: nextSessionDate || null,
      })
      setStudentId("")
      setSessionDate("")
      setSessionTime("")
      setConcerns([])
      setNotes("")
      setNextSessionDate("")
      setOpen(false)
      onSaved("Consultation recorded. The sessions list has been refreshed.")
    } catch {
      // Surfaced from `create.isError` below; a failed create keeps the dialog
      // open with the entered values so nothing has to be retyped.
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button>New consultation</Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>New consultation</DialogTitle>
          <DialogDescription>
            Record a counseling session. The counselor is set to you by the
            server.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-1.5">
            {/*
              Mandatory, and the requirement is now marked both ways: the
              asterisk for the sighted reader, `aria-required` on the trigger for
              the programmatic one. The asterisk sits outside the `<label>` so the
              accessible name stays exactly "Student" — anything inside the label
              is part of the name and would be announced as "Student *".
            */}
            <div className="flex items-center gap-1">
              <Label htmlFor="consultation-student">Student</Label>
              <span aria-hidden="true" className="text-destructive">
                *
              </span>
            </div>
            <Select
              value={studentId}
              onValueChange={setStudentId}
              disabled={rosterQuery.isLoading || roster.length === 0}
            >
              <SelectTrigger id="consultation-student" aria-required="true">
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
          </div>

          <div className="grid gap-3 sm:grid-cols-2">
            {/*
              `Field` rather than a hand-rolled label+`Input` pair: the session
              date is fully controlled, mandatory, and has no error state, which
              is exactly the shape `Field` was extracted for. It renders the
              asterisk outside the label and sets `aria-required` itself, so the
              accessible name stays the field name.
            */}
            <Field
              label="Session date"
              id="consultation-date"
              type="date"
              required
              value={sessionDate}
              onChange={setSessionDate}
            />
            {/*
              The session time stays hand-rolled: `Field` accepts only
              "text" | "date" | "number", and a `type="time"` control must not be
              silently downgraded to a text input. Marked the same way by hand —
              asterisk outside the label, `aria-required` on the control.
            */}
            <div className="space-y-1.5">
              <div className="flex items-center gap-1">
                <Label htmlFor="consultation-time">Session time</Label>
                <span aria-hidden="true" className="text-destructive">
                  *
                </span>
              </div>
              <Input
                id="consultation-time"
                type="time"
                aria-required="true"
                value={sessionTime}
                onChange={(event) => setSessionTime(event.target.value)}
              />
            </div>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="consultation-type">Session type</Label>
            <Select
              value={sessionType}
              onValueChange={(value) =>
                setSessionType(value as ConsultationSessionType)
              }
            >
              <SelectTrigger id="consultation-type">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {CONSULTATION_SESSION_TYPES.map((type) => (
                  <SelectItem key={type} value={type}>
                    {CONSULTATION_SESSION_TYPE_LABELS[type]}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <ConcernCategoryPicker
            legend="Concern categories"
            value={concerns}
            onToggle={toggleConcern}
          />

          <div className="space-y-1.5">
            <div className="flex items-center gap-1">
              <Label htmlFor="consultation-notes">Session notes</Label>
              <span aria-hidden="true" className="text-destructive">
                *
              </span>
            </div>
            <textarea
              id="consultation-notes"
              rows={4}
              aria-required="true"
              value={notes}
              onChange={(event) => setNotes(event.target.value)}
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-xs outline-none focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring"
            />
            <p className="text-xs text-muted-foreground">
              Required. The server rejects blank notes.
            </p>
          </div>

          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="consultation-priority">Priority</Label>
              <Select
                value={priority}
                onValueChange={(value) =>
                  setPriority(value as ConsultationPriority)
                }
              >
                <SelectTrigger id="consultation-priority">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {CONSULTATION_PRIORITIES.map((level) => (
                    <SelectItem key={level} value={level}>
                      {CONSULTATION_PRIORITY_LABELS[level]}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="consultation-next">Next session date</Label>
              <Input
                id="consultation-next"
                type="date"
                value={nextSessionDate}
                onChange={(event) => setNextSessionDate(event.target.value)}
              />
              <p className="text-xs text-muted-foreground">Optional.</p>
            </div>
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
              disabled={
                create.isPending ||
                !studentId ||
                !sessionDate ||
                !sessionTime ||
                notesBlank ||
                roster.length === 0
              }
            >
              {create.isPending ? "Creating…" : "Create consultation"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

/**
 * `PATCH /guidance/consultations/{id}/` form.
 *
 * Only the case-management fields are editable here. `student`, `session_date`
 * and `session_time` identify the session itself, so the dialog leaves them
 * alone rather than offering an edit that would silently rewrite history.
 */
function EditConsultationDialog({
  consultation,
  onSaved,
}: {
  consultation: Consultation
  onSaved: (message: string) => void
}) {
  const update = useUpdateConsultation()

  const [open, setOpen] = useState(false)
  const [status, setStatus] = useState<ConsultationStatus>(consultation.status)
  const [priority, setPriority] = useState<ConsultationPriority>(
    consultation.priority_level
  )
  const [notes, setNotes] = useState(consultation.session_notes)
  const [recommendations, setRecommendations] = useState(
    consultation.recommendations ?? ""
  )
  const [nextSessionDate, setNextSessionDate] = useState(
    consultation.next_session_date ?? ""
  )

  const notesBlank = notes.trim().length === 0

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (notesBlank) return
    try {
      await update.mutateAsync({
        id: consultation.id,
        payload: {
          status,
          priority_level: priority,
          session_notes: notes.trim(),
          recommendations: recommendations.trim() || null,
          next_session_date: nextSessionDate || null,
        },
      })
      setOpen(false)
      onSaved(
        `Consultation for ${consultation.student_name} on ${consultation.session_date} updated.`
      )
    } catch {
      // Surfaced from `update.isError` below.
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        {/*
          One of these renders per row, up to a page of them. The visible verb
          alone gave every button the same accessible name, so a screen reader
          read "Update, Update, Update…" with nothing to tell the rows apart.
          The label names the student and date the button acts on and still
          contains the visible "Update", which WCAG 2.5.3 (Label in Name)
          requires.
        */}
        <Button
          type="button"
          size="xs"
          variant="outline"
          aria-label={`Update consultation for ${consultation.student_name} on ${consultation.session_date}`}
        >
          Update
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Update consultation</DialogTitle>
          <DialogDescription>
            {consultation.student_name} — {consultation.session_date}{" "}
            {formatTime(consultation.session_time)}
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor={`consultation-edit-status-${consultation.id}`}>
                Status
              </Label>
              <Select
                value={status}
                onValueChange={(value) =>
                  setStatus(value as ConsultationStatus)
                }
              >
                <SelectTrigger
                  id={`consultation-edit-status-${consultation.id}`}
                >
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {CONSULTATION_STATUSES.map((option) => (
                    <SelectItem key={option} value={option}>
                      {CONSULTATION_STATUS_LABELS[option]}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor={`consultation-edit-priority-${consultation.id}`}>
                Priority
              </Label>
              <Select
                value={priority}
                onValueChange={(value) =>
                  setPriority(value as ConsultationPriority)
                }
              >
                <SelectTrigger
                  id={`consultation-edit-priority-${consultation.id}`}
                >
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {CONSULTATION_PRIORITIES.map((level) => (
                    <SelectItem key={level} value={level}>
                      {CONSULTATION_PRIORITY_LABELS[level]}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          <div className="space-y-1.5">
            <div className="flex items-center gap-1">
              <Label htmlFor={`consultation-edit-notes-${consultation.id}`}>
                Session notes
              </Label>
              <span aria-hidden="true" className="text-destructive">
                *
              </span>
            </div>
            <textarea
              id={`consultation-edit-notes-${consultation.id}`}
              rows={4}
              aria-required="true"
              value={notes}
              onChange={(event) => setNotes(event.target.value)}
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-xs outline-none focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring"
            />
            <p className="text-xs text-muted-foreground">
              Required. The server rejects blank notes.
            </p>
          </div>

          <div className="space-y-1.5">
            <Label
              htmlFor={`consultation-edit-recommendations-${consultation.id}`}
            >
              Recommendations
            </Label>
            <textarea
              id={`consultation-edit-recommendations-${consultation.id}`}
              rows={3}
              value={recommendations}
              onChange={(event) => setRecommendations(event.target.value)}
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-xs outline-none focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring"
            />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor={`consultation-edit-next-${consultation.id}`}>
              Next session date
            </Label>
            <Input
              id={`consultation-edit-next-${consultation.id}`}
              type="date"
              value={nextSessionDate}
              onChange={(event) => setNextSessionDate(event.target.value)}
            />
            <p className="text-xs text-muted-foreground">
              Clear the field to send null and remove the scheduled follow-up.
            </p>
          </div>

          {update.isError ? (
            <ErrorNote message={normalizeApiError(update.error).message} />
          ) : null}

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => setOpen(false)}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={update.isPending || notesBlank}>
              {update.isPending ? "Saving…" : "Save changes"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

/** Rows per page for a counselor's full session history. */
const PAGE_SIZE = 25

/** Page sizes offered for this list. */
const PAGE_SIZE_OPTIONS = [25, 50, 100] as const

export function ConsultationsPage() {
  const consultationsQuery = useConsultations()
  const rosterQuery = useStudentRoster()

  const [status, setStatus] = useState<ConsultationStatus | "all">("all")
  const [priority, setPriority] = useState<ConsultationPriority | "all">("all")
  const [search, setSearch] = useState("")
  const [sort, setSort] = useState<DataTableSort | null>(null)
  const { hideCompleted, setHidden } = useHideCompleted(
    "aegis:archive:consultations"
  )

  /*
   * Success confirmation for a create or an edit.
   *
   * Both dialogs close on success, and closing unmounts the portal — so a
   * confirmation rendered inside either form would be destroyed before it could
   * be read. The live region therefore lives here, on the page, and the dialogs
   * report through `onSaved`.
   */
  const [notice, setNotice] = useState<string | null>(null)
  const announceSaved = useCallback((message: string) => {
    setNotice(message)
  }, [])

  const consultations = useMemo(
    () => consultationsQuery.data ?? [],
    [consultationsQuery.data]
  )

  const visible = useMemo(() => {
    const filtered = filterConsultations(consultations, {
      status,
      priority,
      search,
    })
    // Archive: completed sessions stay on the server; this only hides them.
    return hideCompleted
      ? filtered.filter((row) => row.status !== "completed")
      : filtered
  }, [consultations, status, priority, search, hideCompleted])

  const counts = useMemo(
    () => countConsultationsByStatus(consultations),
    [consultations]
  )

  /**
   * Student UUID -> code.
   *
   * `ConsultationRecordSerializer` carries no student ID code, so the enrollment
   * roster is the only verified source. A student with no enrollment is omitted
   * rather than rendered as a raw UUID.
   */
  const codeByStudent = useMemo(() => {
    const map = new Map<string, string>()
    for (const entry of rosterQuery.data ?? []) map.set(entry.id, entry.code)
    return map
  }, [rosterQuery.data])

  const isFiltered =
    status !== "all" || priority !== "all" || search.trim().length > 0

  const columns = useMemo<readonly DataTableColumn<Consultation>[]>(
    () => [
      {
        key: "student",
        header: "Student",
        sortValue: (row) => row.student_name,
        sortTieBreak: (row) => codeByStudent.get(row.student) ?? null,
        cell: (row) => (
          <>
            <div className="font-medium">{row.student_name}</div>
            {codeByStudent.get(row.student) ? (
              <div className="text-xs text-muted-foreground">
                {codeByStudent.get(row.student)}
              </div>
            ) : null}
          </>
        ),
      },
      {
        key: "session",
        header: "Session",
        sortValue: (row) => row.session_date,
        sortTieBreak: (row) => row.session_time,
        cell: (row) => (
          <>
            <div className="text-sm">{row.session_date}</div>
            <div className="text-xs text-muted-foreground">
              {formatTime(row.session_time)}
            </div>
          </>
        ),
      },
      {
        key: "type",
        header: "Type",
        sortValue: (row) => row.session_type,
        cellClassName: "text-sm text-muted-foreground",
        cell: (row) => CONSULTATION_SESSION_TYPE_LABELS[row.session_type],
      },
      {
        key: "concerns",
        header: "Concerns",
        cell: (row) =>
          row.concern_categories.length === 0 ? (
            <span className="text-muted-foreground">—</span>
          ) : (
            <div className="flex flex-wrap gap-1">
              {row.concern_categories.map((category) => (
                <Badge key={category} variant="outline">
                  {CONCERN_CATEGORY_LABELS[category]}
                </Badge>
              ))}
            </div>
          ),
      },
      {
        key: "priority",
        header: "Priority",
        // Ranked so ascending reads low → medium → high.
        sortValue: (row) => CONSULTATION_PRIORITY_RANK[row.priority_level],
        sortTieBreak: (row) => row.session_date,
        cell: (row) => <PriorityBadge priority={row.priority_level} />,
      },
      {
        key: "status",
        header: "Status",
        sortValue: (row) => row.status,
        sortTieBreak: (row) => row.session_date,
        cell: (row) => <ConsultationStatusBadge status={row.status} />,
      },
      {
        key: "nextSession",
        header: "Next session",
        sortValue: (row) => row.next_session_date,
        sortTieBreak: (row) => row.session_date,
        cellClassName: "text-sm text-muted-foreground",
        cell: (row) => row.next_session_date ?? "—",
      },
      {
        key: "actions",
        header: "Actions",
        cell: (row) => (
          <EditConsultationDialog consultation={row} onSaved={announceSaved} />
        ),
      },
    ],
    [announceSaved, codeByStudent]
  )

  /*
   * PH11.10: pagination and client-side sorting for a counselor's full session
   * history. The server returns the counselor's own consultations with no
   * `ordering` parameter, so the ordering happens here over rows already in
   * memory. The default order (newest first) is preserved until a column is
   * chosen.
   */
  const sorted = useMemo(
    () => orderRows(visible, sort, columns),
    [visible, sort, columns]
  )

  const { pagination, pageRows, setPageSize } = useDataTablePagination(
    sorted,
    PAGE_SIZE,
    `consultations:${status}:${priority}:${search}`
  )

  return (
    <div className="space-y-6">
      <PageHeading
        title="Consultations"
        description="Counseling sessions you have recorded. The server returns only your own consultations."
      />

      <Card>
        <CardHeader>
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="space-y-1">
              <CardTitle>Sessions</CardTitle>
              <CardDescription>
                Showing {visible.length} of {consultations.length}, newest
                session first.
              </CardDescription>
            </div>
            <NewConsultationDialog onSaved={announceSaved} />
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
              <Label htmlFor="consultation-filter-priority">Priority</Label>
              <Select
                value={priority}
                onValueChange={(value) =>
                  setPriority(value as ConsultationPriority | "all")
                }
              >
                <SelectTrigger id="consultation-filter-priority">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All priorities</SelectItem>
                  {CONSULTATION_PRIORITIES.map((level) => (
                    <SelectItem key={level} value={level}>
                      {CONSULTATION_PRIORITY_LABELS[level]}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-1.5 sm:col-span-1 lg:col-span-2">
              <Label htmlFor="consultation-search">Search</Label>
              <Input
                id="consultation-search"
                type="search"
                value={search}
                placeholder="Student, note, or concern category"
                onChange={(event) => setSearch(event.target.value)}
              />
            </div>
          </div>

          {/*
            Polite, not `alert`: a successful save is not an interruption, and
            the reader has just moved focus back to the trigger that opened the
            dialog. Placed directly above the table it confirms, because that is
            the content that changed.
          */}
          {notice ? (
            <p role="status" className="text-sm text-muted-foreground">
              {notice}
            </p>
          ) : null}

          <div className="flex items-center gap-2">
            <input
              id="consultations-hide-completed"
              type="checkbox"
              checked={hideCompleted}
              onChange={(event) => setHidden(event.target.checked)}
              className="size-4 accent-primary"
            />
            <Label htmlFor="consultations-hide-completed">
              Hide completed (archive)
            </Label>
          </div>

          <DataTable
            caption="Consultations"
            columns={columns}
            rows={pageRows}
            rowKey={(row) => row.id}
            rowProps={(row) => ({ "data-consultation-id": row.id })}
            isLoading={consultationsQuery.isLoading}
            error={
              consultationsQuery.isError
                ? normalizeApiError(consultationsQuery.error).message
                : null
            }
            loadingLabel="Loading consultations"
            emptyMessage={
              isFiltered
                ? "No consultations match the current filters."
                : "You have not recorded any consultations yet."
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
        Consultations are private to the counselor who recorded them. The
        dashboard&apos;s pending-consultation count comes from the same scoped
        list.
      </p>
    </div>
  )
}

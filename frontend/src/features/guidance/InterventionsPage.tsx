import { ClipboardList } from "lucide-react"
import { useMemo, useState, type FormEvent } from "react"

import { EmptyState, ErrorNote } from "@/components/feedback/Feedback"
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
import { Skeleton } from "@/components/ui/skeleton"
import {
  INTERVENTION_STATUSES,
  INTERVENTION_STATUS_LABELS,
  INTERVENTION_STEP_STATUSES,
  INTERVENTION_STEP_STATUS_LABELS,
  RISK_ALERT_STATUS_LABELS,
  RISK_LEVEL_LABELS,
  countInterventionsByStatus,
  filterInterventions,
  useCreateIntervention,
  useCreateInterventionStep,
  useCreateProgressNote,
  useInterventionSteps,
  useInterventions,
  useProgressNotes,
  useRiskAlerts,
  useStudentRoster,
  useUpdateInterventionStep,
  type Intervention,
  type InterventionStatus,
  type InterventionStep,
  type InterventionStepStatus,
} from "@/features/guidance/api"
import { normalizeApiError } from "@/lib/error"
import { useHideCompleted } from "@/lib/archive"
import { consultationStatusBadgeClass } from "@/lib/status-badge"

const NO_RISK_ALERT = "none"

function PageHeading({
  title,
  description,
}: {
  title: string
  description: string
}) {
  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-3">
        <ClipboardList
          className="size-5 text-muted-foreground"
          aria-hidden="true"
        />
        <h2 className="text-2xl font-bold text-foreground">{title}</h2>
      </div>
      <p className="text-sm text-muted-foreground">{description}</p>
    </div>
  )
}

function InterventionStatusBadge({ status }: { status: InterventionStatus }) {
  return (
    <Badge
      variant="outline"
      className={consultationStatusBadgeClass(
        status === "active"
          ? "ongoing"
          : status === "cancelled"
            ? "follow_up"
            : "completed"
      )}
      data-intervention-status={status}
    >
      {INTERVENTION_STATUS_LABELS[status]}
    </Badge>
  )
}

function StepStatusBadge({ status }: { status: InterventionStepStatus }) {
  return (
    <Badge variant="secondary" data-step-status={status}>
      {INTERVENTION_STEP_STATUS_LABELS[status]}
    </Badge>
  )
}

/**
 * Status filter row with live counts.
 *
 * Counts come from the unfiltered list so the chip totals always describe the
 * whole visible set rather than collapsing as the user narrows it.
 */
function StatusFilterChips({
  counts,
  value,
  onChange,
}: {
  counts: ReturnType<typeof countInterventionsByStatus>
  value: InterventionStatus | "all"
  onChange: (next: InterventionStatus | "all") => void
}) {
  const options: ReadonlyArray<InterventionStatus | "all"> = [
    "all",
    ...INTERVENTION_STATUSES,
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
            {option === "all" ? "All" : INTERVENTION_STATUS_LABELS[option]}{" "}
            <span className="tabular-nums opacity-80">{counts[option]}</span>
          </Button>
        )
      })}
    </div>
  )
}

/**
 * `POST /guidance/interventions/` form.
 *
 * `assigned_counselor` and `status` are read-only serializer fields: the
 * viewset assigns the caller and defaults the status to `active`, so neither is
 * offered here.
 *
 * The optional `risk_alert` link is drawn from the student's own alerts rather
 * than a free UUID, which keeps the FK honest about what it points at.
 */
function NewInterventionDialog() {
  const rosterQuery = useStudentRoster()
  const alertsQuery = useRiskAlerts()
  const create = useCreateIntervention()

  const [open, setOpen] = useState(false)
  const [studentId, setStudentId] = useState("")
  const [planStartDate, setPlanStartDate] = useState("")
  const [targetReviewDate, setTargetReviewDate] = useState("")
  const [riskAlertId, setRiskAlertId] = useState<string>(NO_RISK_ALERT)

  const roster = rosterQuery.data ?? []

  const studentAlerts = useMemo(
    () =>
      (alertsQuery.data ?? [])
        .filter((alert) => alert.student === studentId)
        .slice(0, 50),
    [alertsQuery.data, studentId]
  )

  // `Intervention.clean` rejects a review date before the plan start.
  const reviewBeforeStart =
    planStartDate.length > 0 &&
    targetReviewDate.length > 0 &&
    targetReviewDate < planStartDate

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!studentId || !planStartDate || reviewBeforeStart) return
    try {
      await create.mutateAsync({
        student: studentId,
        plan_start_date: planStartDate,
        target_review_date: targetReviewDate || null,
        risk_alert: riskAlertId === NO_RISK_ALERT ? null : riskAlertId,
      })
      setStudentId("")
      setPlanStartDate("")
      setTargetReviewDate("")
      setRiskAlertId(NO_RISK_ALERT)
      setOpen(false)
    } catch {
      // Surfaced from `create.isError` below; the dialog stays open so the
      // entered values survive a failure.
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button>New intervention</Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>New intervention</DialogTitle>
          <DialogDescription>
            Open an intervention plan. The plan is assigned to you and starts
            active.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-1.5">
            {/*
              Mandatory. Marked with a visible asterisk and `aria-required`; the
              asterisk is a sibling of the label, because anything inside
              `<label>` becomes part of the control's accessible name and would be
              read as "Student *" rather than "Student, required".
            */}
            <div className="flex items-center gap-1">
              <Label htmlFor="intervention-student">Student</Label>
              <span aria-hidden="true" className="text-destructive">
                *
              </span>
            </div>
            <Select
              value={studentId}
              onValueChange={(value) => {
                setStudentId(value)
                setRiskAlertId(NO_RISK_ALERT)
              }}
              disabled={rosterQuery.isLoading || roster.length === 0}
            >
              <SelectTrigger id="intervention-student" aria-required="true">
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
              `Field` carries the required marking for the plan start date: the
              asterisk outside the label and `aria-required` on the control. It
              is fully controlled with no error state, which is the shape `Field`
              exists for.
            */}
            <Field
              label="Plan start date"
              id="intervention-start"
              type="date"
              required
              value={planStartDate}
              onChange={setPlanStartDate}
            />
            {/*
              The review date stays hand-rolled because its failure message is
              `role="alert"`: the error is announced when it appears, so the
              control has to be the thing that locates it — `aria-invalid` marks
              the field as the one at fault and `aria-describedby` makes focusing
              it read the message. `aria-describedby` is only present while the
              message is rendered, so the reference is never dangling.
            */}
            <div className="space-y-1.5">
              <Label htmlFor="intervention-review">Target review date</Label>
              <Input
                id="intervention-review"
                type="date"
                aria-invalid={reviewBeforeStart || undefined}
                aria-describedby={
                  reviewBeforeStart ? "intervention-review-error" : undefined
                }
                value={targetReviewDate}
                onChange={(event) => setTargetReviewDate(event.target.value)}
              />
              {reviewBeforeStart ? (
                <p
                  id="intervention-review-error"
                  role="alert"
                  className="text-xs text-destructive"
                >
                  The review date cannot be earlier than the plan start date.
                </p>
              ) : (
                <p className="text-xs text-muted-foreground">Optional.</p>
              )}
            </div>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="intervention-risk-alert">Linked risk alert</Label>
            <Select
              value={riskAlertId}
              onValueChange={setRiskAlertId}
              disabled={!studentId || studentAlerts.length === 0}
            >
              <SelectTrigger id="intervention-risk-alert">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={NO_RISK_ALERT}>No linked alert</SelectItem>
                {studentAlerts.map((alert) => (
                  <SelectItem key={alert.id} value={alert.id}>
                    {RISK_LEVEL_LABELS[alert.risk_level]} ·{" "}
                    {RISK_ALERT_STATUS_LABELS[alert.status]}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <p className="text-xs text-muted-foreground">
              Optional. Only this student&apos;s alerts are offered.
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
              disabled={
                create.isPending ||
                !studentId ||
                !planStartDate ||
                reviewBeforeStart ||
                roster.length === 0
              }
            >
              {create.isPending ? "Creating…" : "Create intervention"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

/** `PATCH /guidance/interventions/{id}/steps/{step_id}/` form. */
function EditStepDialog({
  interventionId,
  step,
}: {
  interventionId: string
  step: InterventionStep
}) {
  const update = useUpdateInterventionStep()

  const [open, setOpen] = useState(false)
  const [title, setTitle] = useState(step.title)
  const [description, setDescription] = useState(step.description)
  const [status, setStatus] = useState<InterventionStepStatus>(step.status)
  const [order, setOrder] = useState(String(step.order))

  const titleBlank = title.trim().length === 0
  // `InterventionStep.clean` rejects an order below 1.
  const parsedOrder = Number.parseInt(order, 10)
  const orderInvalid = !Number.isInteger(parsedOrder) || parsedOrder < 1

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (titleBlank || orderInvalid) return
    try {
      await update.mutateAsync({
        interventionId,
        stepId: step.id,
        payload: {
          title: title.trim(),
          description,
          status,
          order: parsedOrder,
        },
      })
      setOpen(false)
    } catch {
      // Surfaced from `update.isError` below.
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        {/*
          One of these per step in the plan. The bare verb repeated down a list
          gave every button the same accessible name, so the buttons could not be
          told apart; the label names the step's order and title and still
          contains the visible "Update" (WCAG 2.5.3).
        */}
        <Button
          type="button"
          size="xs"
          variant="outline"
          aria-label={`Update step ${step.order}, ${step.title}`}
        >
          Update
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Update step</DialogTitle>
          <DialogDescription>Step {step.order} of the plan.</DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4">
          <Field
            label="Title"
            id={`step-title-${step.id}`}
            required
            value={title}
            onChange={setTitle}
          />

          <div className="space-y-1.5">
            <Label htmlFor={`step-description-${step.id}`}>Description</Label>
            <textarea
              id={`step-description-${step.id}`}
              rows={3}
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-xs outline-none focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring"
            />
          </div>

          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor={`step-status-${step.id}`}>Status</Label>
              <Select
                value={status}
                onValueChange={(value) =>
                  setStatus(value as InterventionStepStatus)
                }
              >
                <SelectTrigger id={`step-status-${step.id}`}>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {INTERVENTION_STEP_STATUSES.map((option) => (
                    <SelectItem key={option} value={option}>
                      {INTERVENTION_STEP_STATUS_LABELS[option]}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              {/*
                The order is mandatory — `InterventionStep.clean()` rejects
                anything below 1 — so it carries `aria-required` alongside the
                visible marker, and its failure message is linked back to the
                control by `aria-describedby` so focusing the field reads it.
              */}
              <div className="flex items-center gap-1">
                <Label htmlFor={`step-order-${step.id}`}>Order</Label>
                <span aria-hidden="true" className="text-destructive">
                  *
                </span>
              </div>
              <Input
                id={`step-order-${step.id}`}
                type="number"
                min={1}
                aria-required="true"
                aria-invalid={orderInvalid || undefined}
                aria-describedby={
                  orderInvalid ? `step-order-${step.id}-error` : undefined
                }
                value={order}
                onChange={(event) => setOrder(event.target.value)}
              />
              {orderInvalid ? (
                <p
                  id={`step-order-${step.id}-error`}
                  role="alert"
                  className="text-xs text-destructive"
                >
                  Order must be 1 or greater.
                </p>
              ) : null}
            </div>
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
            <Button
              type="submit"
              disabled={update.isPending || titleBlank || orderInvalid}
            >
              {update.isPending ? "Saving…" : "Save step"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

/** `POST /guidance/interventions/{id}/steps/` form. */
function AddStepForm({ interventionId }: { interventionId: string }) {
  const create = useCreateInterventionStep()

  const [title, setTitle] = useState("")
  const [description, setDescription] = useState("")
  const [status, setStatus] = useState<InterventionStepStatus>("pending")
  const [order, setOrder] = useState("1")

  const titleBlank = title.trim().length === 0
  const parsedOrder = Number.parseInt(order, 10)
  const orderInvalid = !Number.isInteger(parsedOrder) || parsedOrder < 1

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (titleBlank || orderInvalid) return
    try {
      await create.mutateAsync({
        interventionId,
        payload: {
          title: title.trim(),
          description,
          status,
          order: parsedOrder,
        },
      })
      setTitle("")
      setDescription("")
      setOrder(String(parsedOrder + 1))
      setStatus("pending")
    } catch {
      // Surfaced from `create.isError` below.
    }
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="space-y-3 rounded-md border border-border p-3"
      aria-label="Add step"
    >
      <Field
        label="Step title"
        id="new-step-title"
        required
        value={title}
        onChange={setTitle}
      />

      <div className="space-y-1.5">
        <Label htmlFor="new-step-description">Description</Label>
        <textarea
          id="new-step-description"
          rows={2}
          value={description}
          onChange={(event) => setDescription(event.target.value)}
          className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-xs outline-none focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring"
        />
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        <div className="space-y-1.5">
          <Label htmlFor="new-step-status">Status</Label>
          <Select
            value={status}
            onValueChange={(value) =>
              setStatus(value as InterventionStepStatus)
            }
          >
            <SelectTrigger id="new-step-status">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {INTERVENTION_STEP_STATUSES.map((option) => (
                <SelectItem key={option} value={option}>
                  {INTERVENTION_STEP_STATUS_LABELS[option]}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1.5">
          <div className="flex items-center gap-1">
            <Label htmlFor="new-step-order">Order</Label>
            <span aria-hidden="true" className="text-destructive">
              *
            </span>
          </div>
          <Input
            id="new-step-order"
            type="number"
            min={1}
            aria-required="true"
            aria-invalid={orderInvalid || undefined}
            aria-describedby={orderInvalid ? "new-step-order-error" : undefined}
            value={order}
            onChange={(event) => setOrder(event.target.value)}
          />
          {orderInvalid ? (
            <p
              id="new-step-order-error"
              role="alert"
              className="text-xs text-destructive"
            >
              Order must be 1 or greater.
            </p>
          ) : null}
        </div>
      </div>

      {create.isError ? (
        <ErrorNote message={normalizeApiError(create.error).message} />
      ) : null}

      <Button
        type="submit"
        size="sm"
        disabled={create.isPending || titleBlank || orderInvalid}
      >
        {create.isPending ? "Adding…" : "Add step"}
      </Button>
    </form>
  )
}

/** `POST /guidance/interventions/{id}/notes/` form. */
function AddNoteForm({ interventionId }: { interventionId: string }) {
  const create = useCreateProgressNote()

  const [noteText, setNoteText] = useState("")
  const [nextFollowUp, setNextFollowUp] = useState("")

  const noteBlank = noteText.trim().length === 0

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (noteBlank) return
    try {
      await create.mutateAsync({
        interventionId,
        payload: {
          note_text: noteText.trim(),
          next_follow_up: nextFollowUp || null,
        },
      })
      setNoteText("")
      setNextFollowUp("")
    } catch {
      // Surfaced from `create.isError` below.
    }
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="space-y-3 rounded-md border border-border p-3"
      aria-label="Add progress note"
    >
      <div className="space-y-1.5">
        <div className="flex items-center gap-1">
          <Label htmlFor="new-note-text">Progress note</Label>
          <span aria-hidden="true" className="text-destructive">
            *
          </span>
        </div>
        <textarea
          id="new-note-text"
          rows={3}
          aria-required="true"
          value={noteText}
          onChange={(event) => setNoteText(event.target.value)}
          className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-xs outline-none focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring"
        />
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="new-note-follow-up">Next follow-up</Label>
        <Input
          id="new-note-follow-up"
          type="date"
          value={nextFollowUp}
          onChange={(event) => setNextFollowUp(event.target.value)}
        />
        <p className="text-xs text-muted-foreground">Optional.</p>
      </div>

      {create.isError ? (
        <ErrorNote message={normalizeApiError(create.error).message} />
      ) : null}

      <Button type="submit" size="sm" disabled={create.isPending || noteBlank}>
        {create.isPending ? "Adding…" : "Add note"}
      </Button>
    </form>
  )
}

/**
 * Per-plan workspace: steps and progress notes.
 *
 * Both endpoints return bare arrays rather than paginated envelopes, so they
 * are read with `apiClient.get` through `useInterventionSteps` /
 * `useProgressNotes` and never `fetchAllPages`.
 *
 * `risk_alert_student` is deliberately not rendered. The serializer resolves it
 * from the *linked alert's* student, which the backend does not require to match
 * this plan's student, so showing it beside `student_name` could display two
 * different names for one plan.
 */
function ManagePlanDialog({ intervention }: { intervention: Intervention }) {
  const stepsQuery = useInterventionSteps(intervention.id)
  const notesQuery = useProgressNotes(intervention.id)

  const steps = useMemo(() => stepsQuery.data ?? [], [stepsQuery.data])
  const notes = useMemo(() => notesQuery.data ?? [], [notesQuery.data])

  return (
    <Dialog>
      <DialogTrigger asChild>
        {/*
          One of these per row on a page of up to 25 plans, and the bare verb
          gave them all the same accessible name. The label names the student and
          the plan's start date and still contains the visible "Manage plan".
        */}
        <Button
          type="button"
          size="xs"
          variant="outline"
          aria-label={`Manage plan for ${intervention.student_name}, started ${intervention.plan_start_date}`}
        >
          Manage plan
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>Intervention plan</DialogTitle>
          <DialogDescription>
            {intervention.student_name} · started {intervention.plan_start_date}
            {intervention.target_review_date
              ? ` · review ${intervention.target_review_date}`
              : ""}
          </DialogDescription>
        </DialogHeader>

        <section className="space-y-3">
          <h4 className="text-sm font-semibold">Steps ({steps.length})</h4>

          {stepsQuery.isLoading ? (
            <Skeleton className="h-16 w-full" />
          ) : stepsQuery.isError ? (
            <ErrorNote message={normalizeApiError(stepsQuery.error).message} />
          ) : steps.length === 0 ? (
            <EmptyState message="This plan has no steps yet." />
          ) : (
            <ul className="space-y-2">
              {steps.map((step) => (
                <li
                  key={step.id}
                  data-step-id={step.id}
                  className="flex items-start justify-between gap-3 rounded-md border border-border p-3"
                >
                  <div className="min-w-0 space-y-1">
                    <div className="flex items-center gap-2">
                      <span className="tabular-nums text-xs text-muted-foreground">
                        #{step.order}
                      </span>
                      <span className="font-medium">{step.title}</span>
                      <StepStatusBadge status={step.status} />
                    </div>
                    {step.description ? (
                      <p className="text-sm text-muted-foreground">
                        {step.description}
                      </p>
                    ) : null}
                  </div>
                  <EditStepDialog
                    interventionId={intervention.id}
                    step={step}
                  />
                </li>
              ))}
            </ul>
          )}

          <AddStepForm interventionId={intervention.id} />
        </section>

        <section className="space-y-3">
          <h4 className="text-sm font-semibold">
            Progress notes ({notes.length})
          </h4>

          {notesQuery.isLoading ? (
            <Skeleton className="h-16 w-full" />
          ) : notesQuery.isError ? (
            <ErrorNote message={normalizeApiError(notesQuery.error).message} />
          ) : notes.length === 0 ? (
            <EmptyState message="No progress notes recorded yet." />
          ) : (
            <ul className="space-y-2">
              {notes.map((note) => (
                <li
                  key={note.id}
                  className="space-y-1 rounded-md border border-border p-3"
                >
                  <p className="text-sm">{note.note_text}</p>
                  <p className="text-xs text-muted-foreground">
                    {note.recorded_by_name}
                    {note.next_follow_up
                      ? ` · follow up ${note.next_follow_up}`
                      : ""}
                  </p>
                </li>
              ))}
            </ul>
          )}

          <AddNoteForm interventionId={intervention.id} />
        </section>
      </DialogContent>
    </Dialog>
  )
}

/** Rows per page for the counselor's plan list. */
const PAGE_SIZE = 25

/** Page sizes offered for this list. */
const PAGE_SIZE_OPTIONS = [25, 50, 100] as const

export function InterventionsPage() {
  const interventionsQuery = useInterventions()
  const rosterQuery = useStudentRoster()

  const [status, setStatus] = useState<InterventionStatus | "all">("all")
  const [search, setSearch] = useState("")
  const [sort, setSort] = useState<DataTableSort | null>(null)
  const { hideCompleted, setHidden } = useHideCompleted(
    "aegis:archive:interventions"
  )

  const interventions = useMemo(
    () => interventionsQuery.data ?? [],
    [interventionsQuery.data]
  )

  const visible = useMemo(() => {
    const filtered = filterInterventions(interventions, { status, search })
    // Archive: completed plans stay on the server; this only hides them.
    return hideCompleted
      ? filtered.filter((row) => row.status !== "completed")
      : filtered
  }, [interventions, status, search, hideCompleted])

  const counts = useMemo(
    () => countInterventionsByStatus(interventions),
    [interventions]
  )

  /**
   * Student UUID -> code.
   *
   * `InterventionSerializer` carries no student ID code, so the enrollment
   * roster is the only verified source.
   */
  const codeByStudent = useMemo(() => {
    const map = new Map<string, string>()
    for (const entry of rosterQuery.data ?? []) map.set(entry.id, entry.code)
    return map
  }, [rosterQuery.data])

  const isFiltered = status !== "all" || search.trim().length > 0

  const columns = useMemo<readonly DataTableColumn<Intervention>[]>(
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
        key: "planStart",
        header: "Plan start",
        sortValue: (row) => row.plan_start_date,
        sortTieBreak: (row) => row.student_name,
        cellClassName: "text-sm text-muted-foreground",
        cell: (row) => row.plan_start_date,
      },
      {
        key: "targetReview",
        header: "Target review",
        // No target review means "not scheduled yet", so it sinks to the bottom
        // rather than sorting as the epoch.
        sortValue: (row) => row.target_review_date,
        sortTieBreak: (row) => row.student_name,
        cellClassName: "text-sm text-muted-foreground",
        cell: (row) => row.target_review_date ?? "—",
      },
      {
        key: "status",
        header: "Status",
        sortValue: (row) => row.status,
        sortTieBreak: (row) => row.plan_start_date,
        cell: (row) => <InterventionStatusBadge status={row.status} />,
      },
      {
        key: "actions",
        header: "Actions",
        cell: (row) => <ManagePlanDialog intervention={row} />,
      },
    ],
    [codeByStudent]
  )

  /*
   * PH11.10: pagination and client-side sorting for the plan list. The server
   * returns only the counselor's own plans with no `ordering` parameter, so the
   * ordering happens here over rows already in memory.
   */
  const sorted = useMemo(
    () => orderRows(visible, sort, columns),
    [visible, sort, columns]
  )

  const { pagination, pageRows, setPageSize } = useDataTablePagination(
    sorted,
    PAGE_SIZE,
    `interventions:${status}:${search}`
  )

  return (
    <div className="space-y-6">
      <PageHeading
        title="Interventions"
        description="Intervention plans you own, with their steps and progress notes. The server returns only plans assigned to you."
      />

      <Card>
        <CardHeader>
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="space-y-1">
              <CardTitle>Plans</CardTitle>
              <CardDescription>
                Showing {visible.length} of {interventions.length}.
              </CardDescription>
            </div>
            <NewInterventionDialog />
          </div>
        </CardHeader>

        <CardContent className="space-y-4">
          <StatusFilterChips
            counts={counts}
            value={status}
            onChange={setStatus}
          />

          <div className="space-y-1.5">
            <Label htmlFor="intervention-search">Search</Label>
            <Input
              id="intervention-search"
              type="search"
              value={search}
              placeholder="Student name"
              onChange={(event) => setSearch(event.target.value)}
            />
          </div>

          <div className="flex items-center gap-2">
            <input
              id="interventions-hide-completed"
              type="checkbox"
              checked={hideCompleted}
              onChange={(event) => setHidden(event.target.checked)}
              className="size-4 accent-primary"
            />
            <Label htmlFor="interventions-hide-completed">
              Hide completed (archive)
            </Label>
          </div>

          <DataTable
            caption="Intervention plans"
            columns={columns}
            rows={pageRows}
            rowKey={(row) => row.id}
            rowProps={(row) => ({ "data-intervention-id": row.id })}
            isLoading={interventionsQuery.isLoading}
            error={
              interventionsQuery.isError
                ? normalizeApiError(interventionsQuery.error).message
                : null
            }
            loadingLabel="Loading interventions"
            emptyMessage={
              isFiltered
                ? "No interventions match the current filters."
                : "You have not opened any intervention plans yet."
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
        Plans, steps, and progress notes are private to the assigned counselor.
        Steps and notes can be created and updated; neither this page nor the
        router exposes a delete action for them, and plan status is read-only
        here.
      </p>
    </div>
  )
}

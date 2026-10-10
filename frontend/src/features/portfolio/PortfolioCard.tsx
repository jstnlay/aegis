import { useState, type FormEvent } from "react"

import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { ErrorNote } from "@/components/feedback/Feedback"
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
import { Skeleton } from "@/components/ui/skeleton"
import {
  PORTFOLIO_ACTIVITY_LABELS,
  useCreatePortfolioEntry,
  useDeletePortfolioEntry,
  usePortfolioEntries,
  useUpdatePortfolioEntry,
  type PortfolioActivityType,
  type PortfolioEntry,
} from "@/features/portfolio/api"
import { getFieldError, normalizeApiError } from "@/lib/error"

const ACTIVITY_TYPES = Object.keys(
  PORTFOLIO_ACTIVITY_LABELS
) as PortfolioActivityType[]

/**
 * Read-only portfolio list (parents, guidance, faculty).
 *
 * The entries are the student's own words about their school activities —
 * paperwork, term exams, recitations — plus an optional link to the work.
 */
export function PortfolioList({ studentId }: { studentId: string | null }) {
  const query = usePortfolioEntries(studentId)
  const entries = query.data ?? []

  if (query.isLoading) {
    return (
      <div className="space-y-2">
        <Skeleton className="h-16 w-full" />
      </div>
    )
  }
  if (query.isError) {
    return <ErrorNote message={normalizeApiError(query.error).message} />
  }
  if (entries.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">No portfolio entries yet.</p>
    )
  }
  return (
    <ul className="space-y-2">
      {entries.map((entry) => (
        <PortfolioRow key={entry.id} entry={entry} />
      ))}
    </ul>
  )
}

function PortfolioRow({ entry }: { entry: PortfolioEntry }) {
  return (
    <li className="rounded-md border border-border p-3">
      <div className="flex flex-wrap items-center gap-2">
        <p className="min-w-0 flex-1 truncate font-medium">{entry.title}</p>
        <span className="shrink-0 rounded-md bg-muted px-2 py-0.5 text-xs font-medium">
          {PORTFOLIO_ACTIVITY_LABELS[entry.activity_type] ??
            entry.activity_type}
        </span>
      </div>
      {entry.description ? (
        <p className="mt-1 text-sm whitespace-pre-line">{entry.description}</p>
      ) : null}
      {entry.link_url ? (
        <a
          href={entry.link_url}
          target="_blank"
          rel="noreferrer"
          className="mt-1 inline-block text-sm underline"
        >
          Open linked work
        </a>
      ) : null}
    </li>
  )
}

/**
 * Student-owned portfolio card: list plus add/edit/delete.
 *
 * Only the owning student ever sees the controls — the API answers 403 to
 * every other role, so no other surface imports this card.
 */
export function StudentPortfolioCard() {
  const query = usePortfolioEntries()
  const entries = query.data ?? []
  const [editing, setEditing] = useState<PortfolioEntry | null>(null)
  const [adding, setAdding] = useState(false)

  return (
    <Card>
      <CardHeader>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="space-y-1">
            <CardTitle>My portfolio</CardTitle>
            <CardDescription>
              School activities you showcase yourself — paperwork, term exams,
              recitations. {entries.length} of your entries.
            </CardDescription>
          </div>
          <Button
            type="button"
            size="sm"
            onClick={() => {
              setEditing(null)
              setAdding(true)
            }}
          >
            Add entry
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {query.isLoading ? (
          <Skeleton className="h-16 w-full" />
        ) : query.isError ? (
          <ErrorNote message={normalizeApiError(query.error).message} />
        ) : entries.length === 0 && !adding ? (
          <p className="text-sm text-muted-foreground">
            No portfolio entries yet. Add your first one above.
          </p>
        ) : (
          <ul className="space-y-2">
            {entries.map((entry) => (
              <li
                key={entry.id}
                className="rounded-md border border-border p-3"
              >
                <PortfolioRow entry={entry} />
                <div className="mt-2 flex gap-2">
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => {
                      setAdding(false)
                      setEditing(entry)
                    }}
                  >
                    Edit
                  </Button>
                  <DeleteButton entry={entry} />
                </div>
              </li>
            ))}
          </ul>
        )}

        {adding ? (
          <PortfolioForm
            key="new"
            initial={null}
            onDone={() => setAdding(false)}
          />
        ) : null}
        {editing ? (
          <PortfolioForm
            key={editing.id}
            initial={editing}
            onDone={() => setEditing(null)}
          />
        ) : null}
      </CardContent>
    </Card>
  )
}

function DeleteButton({ entry }: { entry: PortfolioEntry }) {
  const remove = useDeletePortfolioEntry()
  const [confirming, setConfirming] = useState(false)

  if (!confirming) {
    return (
      <Button
        type="button"
        variant="outline"
        size="sm"
        onClick={() => setConfirming(true)}
      >
        Delete
      </Button>
    )
  }
  return (
    <span className="flex items-center gap-2">
      <span className="text-xs text-muted-foreground">Delete this entry?</span>
      <Button
        type="button"
        variant="destructive"
        size="sm"
        disabled={remove.isPending}
        onClick={() => remove.mutate(entry.id)}
      >
        {remove.isPending ? "Deleting…" : "Confirm"}
      </Button>
      <Button
        type="button"
        variant="ghost"
        size="sm"
        onClick={() => setConfirming(false)}
      >
        Keep
      </Button>
    </span>
  )
}

function PortfolioForm({
  initial,
  onDone,
}: {
  initial: PortfolioEntry | null
  onDone: () => void
}) {
  const create = useCreatePortfolioEntry()
  const update = useUpdatePortfolioEntry(initial?.id ?? "")
  const mutation = initial ? update : create

  const [title, setTitle] = useState(initial?.title ?? "")
  const [activity, setActivity] = useState<PortfolioActivityType>(
    initial?.activity_type ?? "other"
  )
  const [description, setDescription] = useState(initial?.description ?? "")
  const [linkUrl, setLinkUrl] = useState(initial?.link_url ?? "")

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!title.trim()) return
    try {
      await mutation.mutateAsync({
        title: title.trim(),
        activity_type: activity,
        description: description.trim(),
        link_url: linkUrl.trim() === "" ? null : linkUrl.trim(),
      })
      onDone()
    } catch {
      // Surfaced from `mutation.isError` below.
    }
  }

  return (
    <form
      onSubmit={handleSubmit}
      noValidate
      className="space-y-3 rounded-md border border-border p-3"
    >
      <Field
        label="Title"
        id={
          initial ? `portfolio-edit-${initial.id}-title` : "portfolio-new-title"
        }
        required
        value={title}
        onChange={setTitle}
        error={getFieldError(mutation.error, "title")}
        placeholder="e.g. Science investigatory project"
      />
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="space-y-1.5">
          <Label
            htmlFor={
              initial
                ? `portfolio-edit-${initial.id}-activity`
                : "portfolio-new-activity"
            }
          >
            Activity type
          </Label>
          <Select
            value={activity}
            onValueChange={(value) =>
              setActivity(value as PortfolioActivityType)
            }
          >
            <SelectTrigger
              id={
                initial
                  ? `portfolio-edit-${initial.id}-activity`
                  : "portfolio-new-activity"
              }
            >
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {ACTIVITY_TYPES.map((type) => (
                <SelectItem key={type} value={type}>
                  {PORTFOLIO_ACTIVITY_LABELS[type]}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1.5">
          <Label
            htmlFor={
              initial
                ? `portfolio-edit-${initial.id}-link`
                : "portfolio-new-link"
            }
          >
            Link to the work (optional)
          </Label>
          <Input
            id={
              initial
                ? `portfolio-edit-${initial.id}-link`
                : "portfolio-new-link"
            }
            type="url"
            inputMode="url"
            value={linkUrl}
            onChange={(e) => setLinkUrl(e.target.value)}
            placeholder="https://…"
          />
        </div>
      </div>
      <div className="space-y-1.5">
        <Label
          htmlFor={
            initial
              ? `portfolio-edit-${initial.id}-description`
              : "portfolio-new-description"
          }
        >
          Description
        </Label>
        <textarea
          id={
            initial
              ? `portfolio-edit-${initial.id}-description`
              : "portfolio-new-description"
          }
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          rows={3}
          className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
          placeholder="What did you do, and what did it show?"
        />
      </div>

      {mutation.isError ? (
        <ErrorNote message={normalizeApiError(mutation.error).message} />
      ) : null}

      <div className="flex gap-2">
        <Button type="submit" size="sm" disabled={mutation.isPending}>
          {mutation.isPending
            ? "Saving…"
            : initial
              ? "Save changes"
              : "Add entry"}
        </Button>
        <Button type="button" variant="outline" size="sm" onClick={onDone}>
          Cancel
        </Button>
      </div>
    </form>
  )
}

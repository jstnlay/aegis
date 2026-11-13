import { ShieldAlert } from "lucide-react"

import {
  EmptyState,
  ErrorNote,
  LoadingState,
} from "@/components/feedback/Feedback"
import { Badge } from "@/components/ui/badge"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { normalizeApiError } from "@/lib/error"
import {
  useMyBehavioralNotes,
  type StudentBehavioralNote,
} from "@/features/student/api"

/**
 * The student's own behavioral notes and class-related concerns (2.1.3).
 *
 * The backend already served this — `BehavioralNoteViewSet` returns a student
 * only their own rows and is read-only for them — but no student screen existed,
 * so the QA checklist recorded 2.1.3 as FAILED. This is that missing surface.
 * Every mutating verb (create is faculty-only; update/delete are absent) is
 * deliberately not rendered: a control here could only produce an error.
 */

const BEHAVIORAL_NOTE_TYPE_LABELS: Record<string, string> = {
  positive: "Positive",
  warning: "Warning",
  incident: "Incident",
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

function NoteItem({ note }: { note: StudentBehavioralNote }) {
  return (
    <li
      className="student-behavioral-note rounded-md border border-border p-3"
      data-note-type={note.note_type}
    >
      <div className="flex flex-wrap items-center gap-2">
        <Badge status={note.note_type} variant="outline">
          {BEHAVIORAL_NOTE_TYPE_LABELS[note.note_type] ?? note.note_type}
        </Badge>
        <span className="text-xs text-muted-foreground">
          {formatDate(note.date_recorded)}
        </span>
        {note.recorded_by_name ? (
          <span className="text-xs text-muted-foreground">
            · {note.recorded_by_name}
          </span>
        ) : null}
      </div>
      <p className="mt-2 text-sm">{note.note_text}</p>
    </li>
  )
}

export function StudentSupportPage() {
  const notesQuery = useMyBehavioralNotes()
  const notes = notesQuery.data ?? []

  return (
    <div className="student-page student-support space-y-6">
      <div className="student-page-heading flex flex-col gap-1">
        <div className="flex items-center gap-3">
          <ShieldAlert
            className="size-5 text-muted-foreground"
            aria-hidden="true"
          />
          <h2 className="text-2xl font-bold text-foreground">
            Behavioral notes
          </h2>
        </div>
        <p className="text-sm text-muted-foreground">
          Notes your teachers have recorded about your conduct and class
          concerns. Contact your adviser or the Guidance Office if you need
          clarification about a note.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Your notes</CardTitle>
          <CardDescription>
            {notesQuery.isLoading
              ? "Loading your notes."
              : notesQuery.isError
                ? "Notes could not be loaded."
                : notes.length > 0
                  ? `${notes.length} note${notes.length === 1 ? "" : "s"} on record.`
                  : "No notes have been recorded for you."}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {notesQuery.isLoading ? (
            <LoadingState label="Loading behavioral notes" />
          ) : notesQuery.isError ? (
            <ErrorNote message={normalizeApiError(notesQuery.error).message} />
          ) : notes.length === 0 ? (
            <EmptyState message="No behavioral notes have been recorded for you." />
          ) : (
            <ul className="space-y-2">
              {notes.map((note) => (
                <NoteItem key={note.id} note={note} />
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  )
}

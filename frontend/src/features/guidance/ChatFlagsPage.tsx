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
import { ErrorNote } from "@/components/feedback/Feedback"
import { Label } from "@/components/ui/label"
import { Skeleton } from "@/components/ui/skeleton"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Textarea } from "@/components/ui/textarea"
import {
  useAcknowledgeFlag,
  useAddCaseNote,
  useAssessmentDraft,
  useChatFlag,
  useGuidanceFlags,
  useInterventionSuggestions,
  useMarkFalsePositive,
  useResolveFlag,
  type ChatFlag,
} from "@/features/chatbot/flags-api"
import { normalizeApiError } from "@/lib/error"

/**
 * The Guidance flag inbox.
 *
 * A flag is the safety workstream's unit of work: a chatbot message that the
 * screening marked sensitive, plus the clock on it. Guidance is the only role
 * that sees the message text — a faculty recipient sees severity and status
 * only — so this page is the one place the conversation is readable.
 *
 * The acknowledgment timer is the page's spine. A flag that is not
 * acknowledged inside the configured window is escalated to administrators by
 * the server, so acknowledging is the first button on a flag, not a status
 * field to edit later.
 */
export function ChatFlagsPage() {
  const [status, setStatus] = useState("")
  const [severity, setSeverity] = useState("")
  const [selectedId, setSelectedId] = useState<string | undefined>()

  const flagsQuery = useGuidanceFlags({
    status: status || undefined,
    severity: severity || undefined,
  })
  const flags = flagsQuery.data ?? []

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-2">
        <h2 className="text-2xl font-bold text-foreground">Chat Support Flags</h2>
        <p className="text-sm text-muted-foreground">
          Sensitive chatbot messages, routed by severity. Critical and high
          flags reach faculty without the message text; Guidance sees the
          conversation. Acknowledge a flag before its timer expires.
        </p>
      </div>

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Filters</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-wrap gap-3">
          <div className="space-y-1.5">
            <Label htmlFor="flag-status">Status</Label>
            <select
              id="flag-status"
              className="h-9 rounded-md border border-input bg-background px-2 text-sm"
              value={status}
              onChange={(event) => setStatus(event.target.value)}
            >
              <option value="">All</option>
              <option value="open">Open</option>
              <option value="acknowledged">Acknowledged</option>
              <option value="under_review">Under review</option>
              <option value="resolved">Resolved</option>
              <option value="false_positive">False positive</option>
            </select>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="flag-severity">Severity</Label>
            <select
              id="flag-severity"
              className="h-9 rounded-md border border-input bg-background px-2 text-sm"
              value={severity}
              onChange={(event) => setSeverity(event.target.value)}
            >
              <option value="">All</option>
              <option value="critical">Critical</option>
              <option value="high">High</option>
              <option value="medium">Medium</option>
              <option value="low">Low</option>
            </select>
          </div>
        </CardContent>
      </Card>

      {flagsQuery.isLoading ? (
        <Skeleton className="h-48 w-full" />
      ) : flagsQuery.isError ? (
        <ErrorNote message={normalizeApiError(flagsQuery.error).message} />
      ) : flags.length === 0 ? (
        <Card>
          <CardContent className="py-8 text-center text-sm text-muted-foreground">
            No flags match these filters.
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base">Inbox</CardTitle>
            <CardDescription>
              {flags.length} flag(s). Select one to review the message and act.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Table scrollLabel="Chat support flags">
              <TableHeader>
                <TableRow>
                  <TableHead>Severity</TableHead>
                  <TableHead>Student</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Source</TableHead>
                  <TableHead>Created</TableHead>
                  <TableHead>Due</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {flags.map((flag) => (
                  <TableRow key={flag.id}>
                    <TableCell>
                      <Button
                        type="button"
                        size="xs"
                        variant="link"
                        className="h-auto p-0"
                        onClick={() => setSelectedId(flag.id)}
                      >
                        <SeverityBadge severity={flag.severity} />
                      </Button>
                    </TableCell>
                    <TableCell>
                      {flag.student_name ?? "Unknown student"}
                    </TableCell>
                    <TableCell>
                      <StatusBadge status={flag.status} />
                    </TableCell>
                    <TableCell>{flag.source}</TableCell>
                    <TableCell>{formatDate(flag.created_at)}</TableCell>
                    <TableCell>
                      {flag.escalation_due_at ? formatDate(flag.escalation_due_at) : "—"}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}

      {selectedId ? (
        <FlagDetail flagId={selectedId} onClose={() => setSelectedId(undefined)} />
      ) : null}
    </div>
  )
}

function SeverityBadge({ severity }: { severity: string }) {
  if (severity === "critical" || severity === "high") {
    return <Badge variant="destructive">{severity}</Badge>
  }
  return <Badge variant="outline">{severity}</Badge>
}

function StatusBadge({ status }: { status: string }) {
  if (status === "resolved") return <Badge variant="secondary">resolved</Badge>
  if (status === "false_positive") {
    return <Badge variant="outline">false positive</Badge>
  }
  if (status === "open") return <Badge variant="default">open</Badge>
  return <Badge variant="outline">{status.replace("_", " ")}</Badge>
}

function formatDate(value: string): string {
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return value
  return parsed.toLocaleString()
}

/**
 * One flag in full: the conversation, the recipients, the action history and
 * the controls that move it forward.
 */
function FlagDetail({
  flagId,
  onClose,
}: {
  flagId: string
  onClose: () => void
}) {
  const flagQuery = useChatFlag(flagId)
  const acknowledge = useAcknowledgeFlag()
  const addNote = useAddCaseNote()
  const resolve = useResolveFlag()
  const falsePositive = useMarkFalsePositive()
  const suggestions = useInterventionSuggestions()
  const drafts = useAssessmentDraft()

  const [note, setNote] = useState("")
  const [suggestionList, setSuggestionList] = useState<string[] | null>(null)
  const [draftList, setDraftList] = useState<
    { question_text: string; question_type: string }[] | null
  >(null)

  const flag: ChatFlag | undefined = flagQuery.data

  if (flagQuery.isLoading) {
    return <Skeleton className="h-64 w-full" />
  }
  if (flagQuery.isError || !flag) {
    return (
      <ErrorNote
        message={normalizeApiError(flagQuery.error ?? new Error("Flag not found.")).message}
      />
    )
  }

  const actionError = [
    acknowledge,
    addNote,
    resolve,
    falsePositive,
    suggestions,
    drafts,
  ].find((mutation) => mutation.isError)

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div className="space-y-1">
            <CardTitle className="flex items-center gap-2 text-base">
              <SeverityBadge severity={flag.severity} />
              {flag.student_name ?? "Unknown student"}
            </CardTitle>
            <CardDescription>
              {flag.categories.length > 0 ? flag.categories.join(", ") : "No categories"}{" "}
              · detected by {flag.source}
              {flag.manual_review ? " · needs manual review" : ""}
            </CardDescription>
          </div>
          <Button type="button" size="xs" variant="ghost" onClick={onClose}>
            Close
          </Button>
        </div>
      </CardHeader>

      <CardContent className="space-y-4">
        <section className="space-y-2">
          <h3 className="text-sm font-semibold">Student message</h3>
          <p className="rounded-md bg-muted px-3 py-2 text-sm">{flag.message}</p>
          {flag.reply ? (
            <p className="rounded-md border border-border px-3 py-2 text-sm text-muted-foreground">
              {flag.reply}
            </p>
          ) : null}
        </section>

        <section className="flex flex-wrap gap-2">
          <Button
            size="sm"
            disabled={acknowledge.isPending || Boolean(flag.acknowledged_at)}
            onClick={() => void acknowledge.mutate({ flagId })}
          >
            {flag.acknowledged_at ? "Acknowledged" : "Acknowledge"}
          </Button>
          <Button
            size="sm"
            variant="outline"
            disabled={resolve.isPending}
            onClick={() => void resolve.mutate({ flagId, note })}
          >
            Resolve
          </Button>
          <Button
            size="sm"
            variant="outline"
            disabled={falsePositive.isPending}
            onClick={() => void falsePositive.mutate({ flagId, note })}
          >
            Mark false positive
          </Button>
          <Button
            size="sm"
            variant="outline"
            disabled={suggestions.isPending}
            onClick={() =>
              void suggestions
                .mutateAsync({ flagId })
                .then((result) => setSuggestionList(result.suggestions))
                .catch(() => undefined)
            }
          >
            {suggestions.isPending ? "Drafting…" : "Suggest interventions"}
          </Button>
          <Button
            size="sm"
            variant="outline"
            disabled={drafts.isPending}
            onClick={() =>
              void drafts
                .mutateAsync({ flagId })
                .then((result) => setDraftList(result.drafts))
                .catch(() => undefined)
            }
          >
            {drafts.isPending ? "Drafting…" : "Draft check-in items"}
          </Button>
        </section>

        <section className="space-y-2">
          <Label htmlFor="flag-note">Private case note</Label>
          <Textarea
            id="flag-note"
            rows={3}
            value={note}
            onChange={(event) => setNote(event.target.value)}
            placeholder="Visible to Guidance and administrators only."
          />
          <Button
            size="sm"
            variant="secondary"
            disabled={addNote.isPending || note.trim().length === 0}
            onClick={() =>
              void addNote
                .mutateAsync({ flagId, note })
                .then(() => setNote(""))
                .catch(() => undefined)
            }
          >
            {addNote.isPending ? "Saving…" : "Add case note"}
          </Button>
        </section>

        {suggestionList ? (
          <section className="space-y-1">
            <h3 className="text-sm font-semibold">Suggested interventions</h3>
            <ul className="list-disc space-y-1 pl-5 text-sm text-muted-foreground">
              {suggestionList.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </section>
        ) : null}

        {draftList ? (
          <section className="space-y-1">
            <h3 className="text-sm font-semibold">Draft check-in items</h3>
            <ol className="list-decimal space-y-1 pl-5 text-sm text-muted-foreground">
              {draftList.map((item) => (
                <li key={item.question_text}>{item.question_text}</li>
              ))}
            </ol>
            <p className="text-xs text-muted-foreground">
              These are proposals. Nothing is published — save anything worth
              keeping through the Assessments page.
            </p>
          </section>
        ) : null}

        <section className="space-y-1">
          <h3 className="text-sm font-semibold">Recipients</h3>
          <p className="text-xs text-muted-foreground">
            {flag.recipients.length === 0
              ? "No staff member was notified."
              : flag.recipients
                  .map(
                    (recipient) =>
                      `${recipient.role}${recipient.acknowledged_at ? " (acknowledged)" : ""}`
                  )
                  .join(", ")}
          </p>
        </section>

        <section className="space-y-1">
          <h3 className="text-sm font-semibold">History</h3>
          <ul className="space-y-1 text-xs text-muted-foreground">
            {flag.actions.map((action) => (
              <li key={action.id}>
                {formatDate(action.created_at)} · {action.action.replace("_", " ")}
                {action.actor_name ? ` · ${action.actor_name}` : ""}
                {action.note ? ` · ${action.note}` : ""}
              </li>
            ))}
          </ul>
        </section>

        {actionError ? (
          <ErrorNote message={normalizeApiError(actionError.error).message} />
        ) : null}
      </CardContent>
    </Card>
  )
}

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
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { MetricCard } from "@/components/ui/metric-card"
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
  useChatbotDashboard,
  useCreateKeywordTerm,
  useCreateKnowledgeDocument,
  useDeleteKeywordTerm,
  useDeleteKnowledgeDocument,
  useEscalateStaleFlags,
  useKeywordTerms,
  useKnowledgeDocuments,
  useToggleKeywordTerm,
  useUpdateKnowledgeDocument,
  type KnowledgeDocument,
} from "@/features/chatbot/flags-api"
import { normalizeApiError } from "@/lib/error"

/**
 * The administrator's chatbot safety console.
 *
 * What an administrator needs to see and be able to change:
 *
 * - **How much is being flagged**, and how fast Guidance acknowledges it.
 * - **The Layer 1 terms**, which are the screen the model does not get to
 *   change.
 * - **The knowledge corpus**, the school documents the assistant answers
 *   questions about the school itself from.
 * - **The timer.** The escalation button runs the acknowledgment timer on
 *   demand, which is how a deployment without a scheduler still escalates.
 *
 * The model status card that used to sit here was removed, along with the
 * encryption line inside it: the model, the key and SDK, the fallback list, the
 * two layers and the encryption posture are operator diagnostics, read from
 * `GET /chatbot/admin/model-status/` or `manage.py security_posture`. What
 * remains on the page is the action — the escalation timer.
 */
export function AdminChatbotPage() {
  const dashboardQuery = useChatbotDashboard()
  const escalate = useEscalateStaleFlags()

  const dashboard = dashboardQuery.data

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-2">
        <h2 className="text-2xl font-bold text-foreground">
          Chatbot Safety Console
        </h2>
        <p className="text-sm text-muted-foreground">
          Screening, routing and the acknowledgment timer for sensitive
          chatbot messages.
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <MetricCard
          title="Flags"
          hint="All time"
          isLoading={dashboardQuery.isLoading}
          isError={dashboardQuery.isError}
        >
          {dashboard?.flags.total ?? 0}
        </MetricCard>
        <MetricCard
          title="Unacknowledged"
          hint="Still inside the timer"
          isLoading={dashboardQuery.isLoading}
          isError={dashboardQuery.isError}
        >
          {dashboard?.flags.unacknowledged ?? 0}
        </MetricCard>
        <MetricCard
          title="Needs manual review"
          hint="Layer 2 did not run"
          isLoading={dashboardQuery.isLoading}
          isError={dashboardQuery.isError}
        >
          {dashboard?.flags.manual_review ?? 0}
        </MetricCard>
        <MetricCard
          title="Acknowledgment timer"
          hint={
            dashboard?.acknowledgment.average_minutes != null
              ? `Average ${dashboard.acknowledgment.average_minutes} min`
              : "Minutes before escalation"
          }
          isLoading={dashboardQuery.isLoading}
          isError={dashboardQuery.isError}
        >
          {dashboard?.acknowledgment.timer_minutes ?? "—"}
        </MetricCard>
      </div>

      {/*
        The timer action.

        The model status card is gone, and so is the encryption line that was
        inside it: the model name, the key and SDK, the fallback list, the layer
        descriptions and the encryption posture are operator diagnostics, read
        once from `GET /chatbot/admin/model-status/` or
        `manage.py security_posture` rather than repeated on every visit. The
        escalation button is not diagnostics — it is how a deployment without a
        scheduler escalates on demand.
      */}
      <div className="flex flex-wrap items-center gap-3">
        <Button
          size="sm"
          variant="outline"
          disabled={escalate.isPending}
          onClick={() => void escalate.mutate()}
        >
          {escalate.isPending ? "Running…" : "Run escalation timer"}
        </Button>
        {escalate.isSuccess ? (
          <p className="text-xs text-muted-foreground">
            Escalated {escalate.data.escalated} flag(s).
          </p>
        ) : null}
        {escalate.isError ? (
          <ErrorNote message={normalizeApiError(escalate.error).message} />
        ) : null}
      </div>

      <KeywordManager />

      <KnowledgeManager />

      <FalsePositiveFeedback />
    </div>
  )
}

/**
 * The feedback loop.
 *
 * A flag a counselor marked as a false positive is the only evidence the
 * school has that a term cries wolf. Without somewhere to read them, the
 * feedback stops at the flag and the term stays active.
 */
function FalsePositiveFeedback() {
  const dashboardQuery = useChatbotDashboard()
  const feedback = dashboardQuery.data?.false_positives

  if (dashboardQuery.isLoading || !feedback) {
    return (
      <Card>
        <CardContent className="py-6 text-sm text-muted-foreground">
          Loading false positives…
        </CardContent>
      </Card>
    )
  }

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-base">False positives</CardTitle>
        <CardDescription>
          {feedback.total} flag(s) were marked as false positives. A term that
          keeps appearing here is a term to deactivate.
        </CardDescription>
      </CardHeader>
      <CardContent>
        {feedback.recent.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No false positives recorded.
          </p>
        ) : (
          <Table scrollLabel="Recent false positives">
            <TableHeader>
              <TableRow>
                <TableHead>Severity</TableHead>
                <TableHead>Categories</TableHead>
                <TableHead>Note</TableHead>
                <TableHead>Marked</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {feedback.recent.map((row) => (
                <TableRow key={row.id}>
                  <TableCell>{row.severity}</TableCell>
                  <TableCell>{row.categories.join(", ") || "—"}</TableCell>
                  <TableCell>{row.note || "—"}</TableCell>
                  <TableCell>{new Date(row.created_at).toLocaleString()}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  )
}

/**
 * The Layer 1 term table.
 *
 * The terms are the part of the screening an administrator owns outright: the
 * model cannot lower them, and deactivating one is the fastest way to stop a
 * term that cries wolf.
 */
function KeywordManager() {
  const termsQuery = useKeywordTerms()
  const createTerm = useCreateKeywordTerm()
  const toggleTerm = useToggleKeywordTerm()
  const deleteTerm = useDeleteKeywordTerm()

  const [term, setTerm] = useState("")
  const [severity, setSeverity] = useState("medium")
  const [category, setCategory] = useState("")
  const [matchType, setMatchType] = useState<"keyword" | "phrase" | "regex">(
    "keyword"
  )

  const terms = termsQuery.data ?? []

  function handleCreate(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (term.trim().length === 0) return
    void createTerm
      .mutateAsync({
        term: term.trim(),
        severity: severity as "low" | "medium" | "high" | "critical",
        category: category.trim(),
        match_type: matchType,
        is_active: true,
        notes: "",
      })
      .then(() => {
        setTerm("")
        setCategory("")
      })
      .catch(() => undefined)
  }

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-base">Layer 1 screening terms</CardTitle>
        <CardDescription>
          {terms.length} term(s), {terms.filter((row) => row.is_active).length}{" "}
          active. A term raises the severity of a message that contains it.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <form onSubmit={handleCreate} className="flex flex-wrap items-end gap-3">
          <div className="space-y-1.5">
            <Label htmlFor="keyword-term">Term</Label>
            <Input
              id="keyword-term"
              value={term}
              className="w-56"
              onChange={(event) => setTerm(event.target.value)}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="keyword-match">Match</Label>
            <select
              id="keyword-match"
              className="h-9 rounded-md border border-input bg-background px-2 text-sm"
              value={matchType}
              onChange={(event) =>
                setMatchType(event.target.value as "keyword" | "phrase" | "regex")
              }
            >
              <option value="keyword">Whole word</option>
              <option value="phrase">Phrase</option>
              <option value="regex">Regular expression</option>
            </select>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="keyword-severity">Severity</Label>
            <select
              id="keyword-severity"
              className="h-9 rounded-md border border-input bg-background px-2 text-sm"
              value={severity}
              onChange={(event) => setSeverity(event.target.value)}
            >
              <option value="low">Low</option>
              <option value="medium">Medium</option>
              <option value="high">High</option>
              <option value="critical">Critical</option>
            </select>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="keyword-category">Category</Label>
            <Input
              id="keyword-category"
              value={category}
              className="w-40"
              onChange={(event) => setCategory(event.target.value)}
            />
          </div>
          <Button type="submit" size="sm" disabled={createTerm.isPending}>
            {createTerm.isPending ? "Adding…" : "Add term"}
          </Button>
        </form>

        {createTerm.isError ? (
          <ErrorNote message={normalizeApiError(createTerm.error).message} />
        ) : null}

        {termsQuery.isLoading ? (
          <p className="text-sm text-muted-foreground">Loading terms…</p>
        ) : termsQuery.isError ? (
          <ErrorNote message={normalizeApiError(termsQuery.error).message} />
        ) : (
          <Table scrollLabel="Layer 1 screening terms">
            <TableHeader>
              <TableRow>
                <TableHead>Term</TableHead>
                <TableHead>Match</TableHead>
                <TableHead>Severity</TableHead>
                <TableHead>Category</TableHead>
                <TableHead>Active</TableHead>
                <TableHead />
              </TableRow>
            </TableHeader>
            <TableBody>
              {terms.map((row) => (
                <TableRow key={row.id}>
                  <TableCell>{row.term}</TableCell>
                  <TableCell>{row.match_type}</TableCell>
                  <TableCell>{row.severity}</TableCell>
                  <TableCell>{row.category || "—"}</TableCell>
                  <TableCell>
                    <Badge variant={row.is_active ? "default" : "outline"}>
                      {row.is_active ? "active" : "off"}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-right">
                    <Button
                      type="button"
                      size="xs"
                      variant="outline"
                      onClick={() =>
                        void toggleTerm.mutate({
                          id: row.id,
                          payload: { is_active: !row.is_active },
                        })
                      }
                    >
                      {row.is_active ? "Deactivate" : "Activate"}
                    </Button>
                    <Button
                      type="button"
                      size="xs"
                      variant="ghost"
                      onClick={() => void deleteTerm.mutate(row.id)}
                    >
                      Delete
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  )
}

const KNOWLEDGE_CATEGORIES = [
  "handbook",
  "policy",
  "announcement",
  "resource",
  "faq",
  "other",
] as const

/**
 * The corpus the assistant answers school questions from.
 *
 * Two jobs, and they are different: adding a document (the handbook, a policy
 * PDF's text) and replacing the text of one already in use. Replacing is a
 * separate mode because a past answer cites a document by id, so fixing a typo
 * in a policy must update that document rather than add a second one.
 *
 * The chunk count is on every row on purpose. A document with zero chunks is
 * invisible to the assistant, and a title in a list is exactly where that would
 * otherwise go unnoticed.
 */
function KnowledgeManager() {
  const documentsQuery = useKnowledgeDocuments()
  const createDocument = useCreateKnowledgeDocument()
  const updateDocument = useUpdateKnowledgeDocument()
  const deleteDocument = useDeleteKnowledgeDocument()

  const [title, setTitle] = useState("")
  const [category, setCategory] = useState<string>("handbook")
  const [sourceLabel, setSourceLabel] = useState("")
  const [body, setBody] = useState("")
  const [editing, setEditing] = useState<KnowledgeDocument | null>(null)
  const [replacement, setReplacement] = useState("")

  const documents = documentsQuery.data ?? []
  const unindexed = documents.filter((row) => row.chunk_count === 0).length

  function handleCreate(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (title.trim().length === 0 || body.trim().length === 0) return
    void createDocument
      .mutateAsync({
        title: title.trim(),
        category,
        source_label: sourceLabel.trim(),
        body,
        is_active: true,
      })
      .then(() => {
        setTitle("")
        setSourceLabel("")
        setBody("")
      })
      .catch(() => undefined)
  }

  function handleReplace(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!editing || replacement.trim().length === 0) return
    void updateDocument
      .mutateAsync({ id: editing.id, payload: { body: replacement } })
      .then(() => {
        setEditing(null)
        setReplacement("")
      })
      .catch(() => undefined)
  }

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-base">Knowledge corpus</CardTitle>
        <CardDescription>
          {documents.length} document(s)
          {unindexed > 0 ? `, ${unindexed} with no text` : ""}. The assistant
          answers school questions only from these documents, and says it does
          not know when none match.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {editing ? (
          <form onSubmit={handleReplace} className="space-y-3">
            <p className="text-sm">
              Replacing the text of <strong>{editing.title}</strong>. The
              document keeps its identity, so answers that cited it stay
              correct.
            </p>
            <Textarea
              aria-label="Replacement text"
              rows={6}
              value={replacement}
              placeholder="Paste the full replacement text…"
              onChange={(event) => setReplacement(event.target.value)}
            />
            <div className="flex gap-2">
              <Button
                type="submit"
                size="sm"
                disabled={updateDocument.isPending}
              >
                {updateDocument.isPending ? "Saving…" : "Replace text"}
              </Button>
              <Button
                type="button"
                size="sm"
                variant="ghost"
                onClick={() => {
                  setEditing(null)
                  setReplacement("")
                }}
              >
                Cancel
              </Button>
            </div>
          </form>
        ) : (
          <form onSubmit={handleCreate} className="space-y-3">
            <div className="flex flex-wrap items-end gap-3">
              <div className="space-y-1.5">
                <Label htmlFor="knowledge-title">Title</Label>
                <Input
                  id="knowledge-title"
                  value={title}
                  className="w-56"
                  onChange={(event) => setTitle(event.target.value)}
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="knowledge-category">Category</Label>
                <select
                  id="knowledge-category"
                  className="h-9 rounded-md border border-input bg-background px-2 text-sm"
                  value={category}
                  onChange={(event) => setCategory(event.target.value)}
                >
                  {KNOWLEDGE_CATEGORIES.map((option) => (
                    <option key={option} value={option}>
                      {option}
                    </option>
                  ))}
                </select>
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="knowledge-label">Cited as</Label>
                <Input
                  id="knowledge-label"
                  value={sourceLabel}
                  className="w-56"
                  placeholder="Handbook 2026, p. 12"
                  onChange={(event) => setSourceLabel(event.target.value)}
                />
              </div>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="knowledge-body">Text</Label>
              <Textarea
                id="knowledge-body"
                rows={6}
                value={body}
                placeholder="Paste the document's text. Blank lines separate passages."
                onChange={(event) => setBody(event.target.value)}
              />
            </div>
            <Button type="submit" size="sm" disabled={createDocument.isPending}>
              {createDocument.isPending ? "Adding…" : "Add document"}
            </Button>
          </form>
        )}

        {createDocument.isError ? (
          <ErrorNote message={normalizeApiError(createDocument.error).message} />
        ) : null}
        {updateDocument.isError ? (
          <ErrorNote message={normalizeApiError(updateDocument.error).message} />
        ) : null}
        {deleteDocument.isError ? (
          <ErrorNote message={normalizeApiError(deleteDocument.error).message} />
        ) : null}

        {documentsQuery.isLoading ? (
          <p className="text-sm text-muted-foreground">Loading documents…</p>
        ) : documentsQuery.isError ? (
          <ErrorNote message={normalizeApiError(documentsQuery.error).message} />
        ) : documents.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No documents yet. The assistant can only answer school questions
            once the handbook or a policy is added here.
          </p>
        ) : (
          <Table scrollLabel="Knowledge corpus">
            <TableHeader>
              <TableRow>
                <TableHead>Title</TableHead>
                <TableHead>Category</TableHead>
                <TableHead>Cited as</TableHead>
                <TableHead>Passages</TableHead>
                <TableHead>Source</TableHead>
                <TableHead>Active</TableHead>
                <TableHead />
              </TableRow>
            </TableHeader>
            <TableBody>
              {documents.map((row) => (
                <TableRow key={row.id}>
                  <TableCell>{row.title}</TableCell>
                  <TableCell>{row.category}</TableCell>
                  <TableCell>{row.source_label || "—"}</TableCell>
                  <TableCell>
                    {row.chunk_count > 0 ? (
                      row.chunk_count
                    ) : (
                      <Badge variant="destructive">not indexed</Badge>
                    )}
                  </TableCell>
                  <TableCell>{row.origin}</TableCell>
                  <TableCell>
                    <Badge variant={row.is_active ? "default" : "outline"}>
                      {row.is_active ? "active" : "off"}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-right">
                    <Button
                      type="button"
                      size="xs"
                      variant="outline"
                      onClick={() => {
                        setEditing(row)
                        setReplacement("")
                      }}
                    >
                      Replace text
                    </Button>
                    <Button
                      type="button"
                      size="xs"
                      variant="outline"
                      onClick={() =>
                        void updateDocument.mutate({
                          id: row.id,
                          payload: { is_active: !row.is_active },
                        })
                      }
                    >
                      {row.is_active ? "Deactivate" : "Activate"}
                    </Button>
                    <Button
                      type="button"
                      size="xs"
                      variant="ghost"
                      onClick={() => void deleteDocument.mutate(row.id)}
                    >
                      Delete
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  )
}

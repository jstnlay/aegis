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
import {
  useChatbotDashboard,
  useCreateKeywordTerm,
  useDeleteKeywordTerm,
  useEscalateStaleFlags,
  useKeywordTerms,
  useModelStatus,
  useToggleKeywordTerm,
} from "@/features/chatbot/flags-api"
import { normalizeApiError } from "@/lib/error"

/**
 * The administrator's chatbot safety console.
 *
 * Four things an administrator needs to see and be able to change:
 *
 * - **How much is being flagged**, and how fast Guidance acknowledges it.
 * - **Whether the model is even available.** A blank API key does not fail
 *   loudly: Layer 2 simply does not run, and every message that Layer 1 missed
 *   is marked for manual review instead. That is the safe failure, but it is
 *   invisible unless somebody looks, so the status is on this page.
 * - **The Layer 1 terms**, which are the screen the model does not get to
 *   change.
 * - **The timer.** The escalation button runs the acknowledgment timer on
 *   demand, which is how a deployment without a scheduler still escalates.
 */
export function AdminChatbotPage() {
  const dashboardQuery = useChatbotDashboard()
  const statusQuery = useModelStatus()
  const escalate = useEscalateStaleFlags()

  const dashboard = dashboardQuery.data
  const status = statusQuery.data

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

      <Card>
        <CardHeader className="pb-3">
          <div className="flex flex-wrap items-start justify-between gap-2">
            <div className="space-y-1">
              <CardTitle className="text-base">Model status</CardTitle>
              <CardDescription>
                Layer 1 is the database keyword screen and always runs. Layer 2
                is Gemini classification and augments it.
              </CardDescription>
            </div>
            <div className="flex items-center gap-2">
              <Badge variant={status?.available ? "default" : "destructive"}>
                {status?.available ? "Layer 2 available" : "Layer 2 unavailable"}
              </Badge>
              <Button
                size="sm"
                variant="outline"
                disabled={escalate.isPending}
                onClick={() => void escalate.mutate()}
              >
                {escalate.isPending ? "Running…" : "Run escalation timer"}
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent className="space-y-1 text-sm text-muted-foreground">
          {statusQuery.isLoading ? (
            <p>Loading model status…</p>
          ) : statusQuery.isError ? (
            <ErrorNote message={normalizeApiError(statusQuery.error).message} />
          ) : status ? (
            <>
              <p>
                Model: <span className="font-mono">{status.model}</span> · API key{" "}
                {status.configured ? "configured" : "missing"} · SDK{" "}
                {status.sdk_installed ? "installed" : "not installed"}
              </p>
              {status.models?.length > 1 ? (
                <p className="text-xs">
                  Fallback models:{" "}
                  <span className="font-mono">
                    {status.models.slice(1).join(", ")}
                  </span>
                </p>
              ) : null}
              {status.key_count > 0 ? (
                <p>
                  {status.key_count} key(s) configured,{" "}
                  {status.keys_exhausted} spent. Timeout{" "}
                  {status.timeout_seconds}s, deadline {status.deadline_seconds}s.
                </p>
              ) : null}
              {/*
                Whether student free text is encrypted in the database. A
                deployment without a key stores disclosures in plain text, so
                this is stated rather than assumed.
              */}
              {status.encryption ? (
                <p
                  className={
                    status.encryption.enabled
                      ? "text-xs"
                      : "text-xs text-destructive"
                  }
                >
                  {status.encryption.enabled
                    ? `Student messages are encrypted at rest (${
                        status.encryption.algorithm
                      }, ${status.encryption.key_count} key(s)).`
                    : "Field encryption is OFF. Student messages are stored in plain text."}
                </p>
              ) : null}
              {status.last_failure?.reason ? (
                <p className="text-xs text-destructive">
                  Last call failed: {status.last_failure.reason}. Layer 1 is
                  screening alone and missed messages are marked for manual
                  review.
                </p>
              ) : null}
              <p>{status.layer1}</p>
              <p>{status.layer2}</p>
              <p className="text-xs">{status.privacy}</p>
            </>
          ) : null}
          {escalate.isSuccess ? (
            <p className="text-xs">
              Escalated {escalate.data.escalated} flag(s).
            </p>
          ) : null}
          {escalate.isError ? (
            <ErrorNote message={normalizeApiError(escalate.error).message} />
          ) : null}
        </CardContent>
      </Card>

      <KeywordManager />

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

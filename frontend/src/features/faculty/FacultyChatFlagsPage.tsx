import { ShieldAlert } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { ErrorNote } from "@/components/feedback/Feedback"
import { Skeleton } from "@/components/ui/skeleton"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { useFacultyFlags } from "@/features/chatbot/flags-api"
import { normalizeApiError } from "@/lib/error"

/**
 * The faculty flag feed.
 *
 * Deliberately thin, and deliberately blind. `FacultyFlagSerializer` returns
 * only `id`, `severity`, `status`, `created_at`, `acknowledged_at` and
 * `escalated_at` — there is no student field, no message field, no reply field
 * and no category field, so this page has nothing to leak even by accident.
 *
 * The copy states that plainly rather than implying the counselor's view is
 * hidden behind a toggle. A teacher who is told "a student in your class needs
 * support" learns something actionable; a teacher who is shown the transcript
 * learns something they were never asked to hold.
 */
export function FacultyChatFlagsPage() {
  const flagsQuery = useFacultyFlags()
  const flags = flagsQuery.data ?? []

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-2">
        <h2 className="text-2xl font-bold text-foreground">Support Flags</h2>
        <p className="text-sm text-muted-foreground">
          A student in one of your classes has a support flag. The conversation
          and the student's identity stay with Guidance — this feed shows the
          severity and the status so you know support is in motion.
        </p>
      </div>

      {flagsQuery.isLoading ? (
        <Skeleton className="h-40 w-full" />
      ) : flagsQuery.isError ? (
        <ErrorNote message={normalizeApiError(flagsQuery.error).message} />
      ) : flags.length === 0 ? (
        <Card>
          <CardContent className="py-8 text-center text-sm text-muted-foreground">
            No support flags involve your classes.
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base">Your classes</CardTitle>
            <CardDescription>
              {flags.length} flag(s). Guidance owns the follow-up.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Table scrollLabel="Support flags for your classes">
              <TableHeader>
                <TableRow>
                  <TableHead>Severity</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Raised</TableHead>
                  <TableHead>Acknowledged</TableHead>
                  <TableHead>Escalated</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {flags.map((flag) => (
                  <TableRow key={flag.id}>
                    <TableCell>
                      <span className="inline-flex items-center gap-1">
                        {flag.severity === "critical" ||
                        flag.severity === "high" ? (
                          <ShieldAlert
                            className="size-3.5 text-destructive"
                            aria-hidden="true"
                          />
                        ) : null}
                        <Badge
                          variant={
                            flag.severity === "critical" ||
                            flag.severity === "high"
                              ? "destructive"
                              : "outline"
                          }
                        >
                          {flag.severity}
                        </Badge>
                      </span>
                    </TableCell>
                    <TableCell>{flag.status.replace("_", " ")}</TableCell>
                    <TableCell>{formatDate(flag.created_at)}</TableCell>
                    <TableCell>
                      {flag.acknowledged_at
                        ? formatDate(flag.acknowledged_at)
                        : "—"}
                    </TableCell>
                    <TableCell>
                      {flag.escalated_at ? formatDate(flag.escalated_at) : "—"}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}
    </div>
  )
}

function formatDate(value: string): string {
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return value
  return parsed.toLocaleString()
}

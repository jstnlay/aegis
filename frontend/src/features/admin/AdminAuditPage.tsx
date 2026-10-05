import { Shield } from "lucide-react"
import { useState } from "react"

import { Badge } from "@/components/ui/badge"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { DataTable, type DataTableColumn } from "@/components/ui/data-table"
import { ErrorNote } from "@/components/feedback/Feedback"
import { useDataTablePagination } from "@/components/ui/data-table-pagination"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  AUDIT_ACTIONS,
  useAuditLogs,
  type AuditLogEntry,
} from "@/features/admin/api"
import { normalizeApiError } from "@/lib/error"

/**
 * The audit trail.
 *
 * Read-only, and not by choice of this screen: `AuditLogViewSet` is a
 * `ReadOnlyModelViewSet` whose `http_method_names` is
 * `["get", "head", "options"]`, so the router maps no write route at all. An
 * administrator cannot delete or amend an audit record through this API, and
 * that is the correct property for an append-only trail.
 *
 * Every filter here maps to a bounded query parameter the viewset implements.
 * `search` covers `model_name` and `object_repr` only — the view deliberately
 * refuses to search inside `changes`, and the placeholder says so rather than
 * implying a full-text search that does not exist.
 *
 * `changes` is rendered as the stored safe diff. It is never re-serialised or
 * dereferenced back into live domain objects, so a record for a deleted object
 * stays readable.
 */

export function AdminAuditPage() {
  const [action, setAction] = useState("all")
  const [modelName, setModelName] = useState("")
  const [search, setSearch] = useState("")
  const [startTime, setStartTime] = useState("")
  const [endTime, setEndTime] = useState("")

  const logsQuery = useAuditLogs({
    action: action === "all" ? undefined : action,
    modelName: modelName.trim() || undefined,
    search: search.trim() || undefined,
    startTime: startTime ? `${startTime}T00:00:00` : undefined,
    endTime: endTime ? `${endTime}T23:59:59` : undefined,
  })

  const entries = logsQuery.data ?? []
  const { pagination, pageRows } = useDataTablePagination(
    entries,
    20,
    `audit:${action}:${modelName}:${search}:${startTime}:${endTime}`
  )

  const columns: readonly DataTableColumn<AuditLogEntry>[] = [
    {
      key: "timestamp",
      header: "When",
      cell: (entry) => (
        <span className="whitespace-nowrap text-sm text-muted-foreground">
          {formatDateTime(entry.timestamp)}
        </span>
      ),
    },
    {
      key: "actor",
      header: "Who",
      // `user` is null for a system event, which the serializer represents
      // explicitly rather than as an empty object.
      cell: (entry) => (
        <span className="text-sm">
          {entry.user?.name ?? (
            <span className="text-muted-foreground">System</span>
          )}
        </span>
      ),
    },
    {
      key: "action",
      header: "Action",
      cell: (entry) => (
        <Badge variant="outline" data-audit-action={entry.action}>
          {entry.action}
        </Badge>
      ),
    },
    {
      key: "target",
      header: "Target",
      cell: (entry) => (
        <div className="min-w-0">
          <div className="text-sm font-medium">{entry.model_name}</div>
          <div className="max-w-60 truncate text-xs text-muted-foreground">
            {entry.object_repr}
          </div>
        </div>
      ),
    },
    {
      key: "changes",
      header: "Changes",
      cell: (entry) =>
        entry.changes ? (
          <details className="text-sm">
            <summary className="cursor-pointer text-muted-foreground">
              View diff
            </summary>
            <pre className="mt-2 max-w-md overflow-x-auto rounded-md bg-muted p-2 text-xs">
              {JSON.stringify(entry.changes, null, 2)}
            </pre>
          </details>
        ) : (
          <span className="text-muted-foreground">—</span>
        ),
    },
    {
      key: "ip",
      header: "IP address",
      cell: (entry) => (
        <span className="text-xs text-muted-foreground">
          {entry.ip_address ?? "—"}
        </span>
      ),
    },
  ]

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-1">
        <div className="flex items-center gap-3">
          <Shield className="size-5 text-muted-foreground" aria-hidden="true" />
          <h1 className="text-2xl font-bold text-foreground">Audit Logs</h1>
        </div>
        <p className="text-sm text-muted-foreground">
          Every recorded create, update, delete, login, logout, import, export
          and sensitive read. This trail is append-only — the API exposes no way
          to modify or remove a record.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Filters</CardTitle>
          <CardDescription>
            Search covers the model name and the object label only. It does not
            search inside the stored changes.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
            <div className="space-y-1.5">
              <Label htmlFor="audit-action">Action</Label>
              <Select value={action} onValueChange={setAction}>
                <SelectTrigger id="audit-action">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All actions</SelectItem>
                  {AUDIT_ACTIONS.map((value) => (
                    <SelectItem key={value} value={value}>
                      {value}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="audit-model">Model</Label>
              <Input
                id="audit-model"
                value={modelName}
                placeholder="accounts.User"
                onChange={(event) => setModelName(event.target.value)}
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="audit-search">Search</Label>
              <Input
                id="audit-search"
                type="search"
                value={search}
                placeholder="Model or object label"
                onChange={(event) => setSearch(event.target.value)}
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="audit-from">From</Label>
              <Input
                id="audit-from"
                type="date"
                value={startTime}
                onChange={(event) => setStartTime(event.target.value)}
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="audit-to">To</Label>
              <Input
                id="audit-to"
                type="date"
                value={endTime}
                onChange={(event) => setEndTime(event.target.value)}
              />
            </div>
          </div>

          {logsQuery.isError ? (
            <ErrorNote message={normalizeApiError(logsQuery.error).message} />
          ) : null}

          <DataTable
            caption="Audit log"
            columns={columns}
            rows={pageRows}
            rowKey={(entry) => entry.id}
            isLoading={logsQuery.isLoading}
            error={null}
            loadingLabel="Loading audit records"
            emptyMessage={
              action !== "all" || modelName || search || startTime || endTime
                ? "No audit records match the current filters."
                : "No audit records have been written yet."
            }
            pagination={pagination}
          />
        </CardContent>
      </Card>
    </div>
  )
}

function formatDateTime(value: string): string {
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return value
  return parsed.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  })
}

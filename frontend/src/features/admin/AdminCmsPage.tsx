import { Tabs } from "@/components/ui/tabs"
import { FileText } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { DataTable, type DataTableColumn } from "@/components/ui/data-table"
import { ErrorNote } from "@/components/feedback/Feedback"
import { useState } from "react"
import {
  ANNOUNCEMENT_PRIORITY_LABELS,
  ANNOUNCEMENT_TYPE_LABELS,
  downloadCmsResource,
  RESOURCE_TYPE_LABELS,
  useCmsAnnouncements,
  useCmsResources,
  type CmsAnnouncement,
  type CmsResource,
} from "@/features/admin/api"
import { normalizeApiError } from "@/lib/error"

/**
 * School content, read through the AEGIS CMS proxy.
 *
 * Content lives in Strapi. `CmsAnnouncementList`, `CmsResourceList` and their
 * detail routes are `ListAPIView`/`RetrieveAPIView` — read-only. The only write
 * path is `StrapiAnnouncementWebhookView`, which is `AllowAny` because Strapi
 * authenticates it separately and which is a webhook receiver, not an authoring
 * API. So there is no create, update or delete form here: the backend would
 * reject one, and offering it would misrepresent what the system can do.
 *
 * Authoring happens in Strapi. This screen shows what AEGIS is currently
 * publishing, which is the part an administrator actually needs to verify.
 *
 * Two states are kept distinct. The proxy answers 503 when Strapi is
 * unreachable, which is not the same as "there is no content" — the error path
 * says so rather than rendering an empty list that reads as an empty school.
 *
 * Resource files are downloaded through `GET /cms/resources/{id}/file/`
 * (SEC-007), the authorized proxy, never through a direct Strapi URL. PH11.10
 * corrected that download: it was a plain link, which cannot carry the bearer
 * token this app authenticates with, so it now goes through the API client.
 */

export function AdminCmsPage() {
  const [tab, setTab] = useState<"announcements" | "resources">("announcements")

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-1">
        <div className="flex items-center gap-3">
          <FileText
            className="size-5 text-muted-foreground"
            aria-hidden="true"
          />
          <h2 className="text-2xl font-bold text-foreground">Content</h2>
        </div>
        <p className="text-sm text-muted-foreground">
          Announcements and resources published to the school through the CMS.
        </p>
      </div>

      {/*
        Stated rather than hidden. An administrator looking for a "publish
        announcement" button here has no way to tell whether authoring belongs
        in this system, so the boundary is written down.
      */}
      <Card>
        <CardHeader>
          <CardTitle>Read-only view</CardTitle>
          <CardDescription>
            Content is authored in Strapi. AEGIS proxies it for display and
            applies its own access rules, and exposes no write endpoint — so
            this screen has no create, edit or delete control.
          </CardDescription>
        </CardHeader>
        <CardContent />
      </Card>

      {/*
        PH11.11: the hand-rolled tab strip is replaced by the shared `Tabs`.
        This page's tabs had no `focus-visible:` rule at all — they were plain
        `<button>`s with hand-written classes rather than the shared `Button` —
        so a keyboard user had no visible focus indicator on either state. It is
        also the only page of the three that did not use the shared `Button`.
      */}
      <Tabs
        label="Content"
        value={tab}
        onValueChange={setTab}
        items={[
          {
            id: "announcements",
            label: "Announcements",
            content: <AnnouncementsCard />,
          },
          { id: "resources", label: "Resources", content: <ResourcesCard /> },
        ]}
      />
    </div>
  )
}

function AnnouncementsCard() {
  const query = useCmsAnnouncements()

  const columns: readonly DataTableColumn<CmsAnnouncement>[] = [
    {
      key: "title",
      header: "Announcement",
      cell: (row) => (
        <div className="min-w-0">
          <div className="font-medium">{row.title}</div>
          <p className="mt-1 max-w-xl text-sm text-muted-foreground">
            {row.content}
          </p>
        </div>
      ),
    },
    {
      key: "type",
      header: "Type",
      cell: (row) => (
        <Badge
          variant="secondary"
          data-announcement-type={row.announcement_type}
        >
          {ANNOUNCEMENT_TYPE_LABELS[row.announcement_type] ??
            row.announcement_type}
        </Badge>
      ),
    },
    {
      key: "priority",
      header: "Priority",
      cell: (row) => (
        <Badge
          variant={row.priority === "urgent" ? "destructive" : "outline"}
          data-announcement-priority={row.priority}
        >
          {ANNOUNCEMENT_PRIORITY_LABELS[row.priority] ?? row.priority}
        </Badge>
      ),
    },
    {
      key: "audience",
      header: "Audience",
      cell: (row) => (
        <span className="text-sm text-muted-foreground">
          {row.target_roles.join(", ") || "—"}
        </span>
      ),
    },
    {
      key: "published",
      header: "Published",
      cell: (row) => (
        <span className="whitespace-nowrap text-sm text-muted-foreground">
          {formatDate(row.published_at)}
        </span>
      ),
    },
    {
      key: "expires",
      header: "Expires",
      cell: (row) => (
        <span className="whitespace-nowrap text-sm text-muted-foreground">
          {row.expires_at ? formatDate(row.expires_at) : "No expiry"}
        </span>
      ),
    },
  ]

  return (
    <Card>
      <CardHeader>
        <CardTitle>Announcements</CardTitle>
        <CardDescription>
          {query.data?.length ?? 0} announcement
          {query.data?.length === 1 ? "" : "s"} currently visible to you.
          Expired items are hidden from students and parents but remain visible
          to staff.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <DataTable
          caption="Announcements"
          columns={columns}
          rows={query.data ?? []}
          rowKey={(row) => row.document_id}
          isLoading={query.isLoading}
          error={query.isError ? normalizeApiError(query.error).message : null}
          loadingLabel="Loading announcements"
          emptyMessage="No announcements are currently published."
        />
      </CardContent>
    </Card>
  )
}

function ResourcesCard() {
  const query = useCmsResources()
  const download = useCmsResourceDownload()

  const columns: readonly DataTableColumn<CmsResource>[] = [
    {
      key: "title",
      header: "Resource",
      cell: (row) => (
        <div className="min-w-0">
          <div className="font-medium">{row.title}</div>
          {row.description ? (
            <p className="mt-1 max-w-xl text-sm text-muted-foreground">
              {row.description}
            </p>
          ) : null}
        </div>
      ),
    },
    {
      key: "type",
      header: "Type",
      cell: (row) => (
        <Badge variant="secondary" data-resource-type={row.resource_type}>
          {RESOURCE_TYPE_LABELS[row.resource_type] ?? row.resource_type}
        </Badge>
      ),
    },
    {
      key: "audience",
      header: "Audience",
      cell: (row) => (
        <span className="text-sm text-muted-foreground">
          {row.target_audience.join(", ") || "—"}
        </span>
      ),
    },
    {
      key: "file",
      header: "File",
      /*
       * PH11.10: this was an `<a href>` at the AEGIS proxy route (SEC-007),
       * which returned 401 — authentication here is a bearer token added by
       * the axios request interceptor, and a native anchor sends no such
       * header. The download now goes through the API client so the token and
       * the refresh path apply. The Strapi URL is still never exposed: that
       * would bypass the SEC-007 access check entirely.
       */
      cell: (row) =>
        row.file_or_url ? (
          <Button
            type="button"
            variant="link"
            size="sm"
            className="h-auto p-0"
            disabled={download.pendingId === row.document_id}
            onClick={() => download.start(row.document_id)}
          >
            {download.pendingId === row.document_id ? "Preparing…" : "Download"}
          </Button>
        ) : (
          <span className="text-muted-foreground">—</span>
        ),
    },
  ]

  return (
    <Card>
      <CardHeader>
        <CardTitle>Resources</CardTitle>
        <CardDescription>
          Only active resources targeted at your audience are returned. Files
          are downloaded through AEGIS, not from Strapi directly.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <DataTable
          caption="Resources"
          columns={columns}
          rows={query.data ?? []}
          rowKey={(row) => row.document_id}
          isLoading={query.isLoading}
          error={query.isError ? normalizeApiError(query.error).message : null}
          loadingLabel="Loading resources"
          emptyMessage="No resources are currently published."
        />
        {download.error ? <ErrorNote message={download.error} /> : null}
      </CardContent>
    </Card>
  )
}

/**
 * One download at a time, with its own error.
 *
 * The table's error prop reports the *list* query, so a failed file download
 * needs its own surface — otherwise a 401 from the proxy would look like a
 * successfully rendered table with a dead link.
 */
function useCmsResourceDownload() {
  const [pendingId, setPendingId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const start = (documentId: string) => {
    setPendingId(documentId)
    setError(null)
    void downloadCmsResource(documentId)
      .catch((caught: unknown) => {
        setError(normalizeApiError(caught).message)
      })
      .finally(() => {
        setPendingId(null)
      })
  }

  return { pendingId, error, start }
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

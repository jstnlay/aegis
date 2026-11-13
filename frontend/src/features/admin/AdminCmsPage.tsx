import { Tabs } from "@/components/ui/tabs"
import { FileText } from "lucide-react"
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
import { DataTable, type DataTableColumn } from "@/components/ui/data-table"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import { ErrorNote } from "@/components/feedback/Feedback"
import { ChoiceField, Field } from "@/components/ui/form-field"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { AnnouncementCover } from "@/features/cms/AnnouncementCover"
import {
  ANNOUNCEMENT_PRIORITY_LABELS,
  ANNOUNCEMENT_TYPE_LABELS,
  downloadCmsResource,
  RESOURCE_TYPE_LABELS,
  useCmsAnnouncements,
  useCmsResources,
  useDeleteCmsAnnouncement,
  useDeleteCmsResource,
  useSaveCmsAnnouncement,
  useSaveCmsResource,
  type CmsAnnouncement,
  type CmsAnnouncementInput,
  type CmsResource,
  type CmsResourceInput,
} from "@/features/admin/api"
import { normalizeApiError } from "@/lib/error"

/**
 * School content, authored through the AEGIS CMS proxy.
 *
 * Content lives in Strapi. Administrators create, edit and delete
 * announcements and resources here; Django validates the payload and relays
 * it with the server-side Strapi token (`/cms/.../manage/`, admin-only). No
 * Strapi credential or URL ever reaches the browser.
 *
 * Uploaded files are still attached in the Strapi admin because the content
 * API needs multipart media handling that this proxy does not expose. A
 * resource created here carries an authored URL; an existing uploaded file is
 * still listed and downloadable through the SEC-007 proxy below.
 *
 * Two states are kept distinct. The proxy answers 502 when Strapi is
 * unreachable (the CMS service is not deployed or not responding), which is
 * not the same as "there is no content" — the error path says the content
 * service is temporarily unavailable rather than rendering an empty list
 * that reads as an empty school.
 *
 * Resource files are downloaded through `GET /cms/resources/{id}/file/`
 * (SEC-007), the authorized proxy, never through a direct Strapi URL. PH11.10
 * corrected that download: it was a plain link, which cannot carry the bearer
 * token this app authenticates with, so it now goes through the API client.
 */

const AUDIENCE_OPTIONS = [
  { value: "all", label: "Everyone" },
  { value: "student", label: "Students" },
  { value: "parent", label: "Parents" },
  { value: "faculty", label: "Faculty" },
  { value: "guidance", label: "Guidance" },
  { value: "admin", label: "Administrators" },
]

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

      <Card>
        <CardHeader>
          <CardTitle>Authoring</CardTitle>
          <CardDescription>
            Create, edit and delete announcements and resources from this
            screen. A new announcement is published immediately. File uploads
            are still attached in the Strapi admin.
          </CardDescription>
        </CardHeader>
        <CardContent />
      </Card>

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
      key: "photo",
      header: "Photo",
      cell: (row) =>
        row.cover_image ? (
          <div className="w-24">
            <AnnouncementCover
              documentId={row.document_id}
              coverImage={row.cover_image}
              alt={`Cover image for ${row.title}`}
            />
          </div>
        ) : (
          <span className="text-sm text-muted-foreground">—</span>
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
          status={row.priority}
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
    {
      key: "actions",
      header: <span className="sr-only">Actions</span>,
      cell: (row) => (
        <div className="flex justify-end gap-1">
          <AnnouncementEditor announcement={row} />
          <DeleteAnnouncement row={row} />
        </div>
      ),
    },
  ]

  return (
    <Card>
      <CardHeader>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="space-y-1">
            <CardTitle>Announcements</CardTitle>
            <CardDescription>
              {query.data?.length ?? 0} announcement
              {query.data?.length === 1 ? "" : "s"} currently visible to you.
              Expired items are hidden from students and parents but remain
              visible to staff.
            </CardDescription>
          </div>
          <AnnouncementEditor />
        </div>
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
    {
      key: "actions",
      header: <span className="sr-only">Actions</span>,
      cell: (row) => (
        <div className="flex justify-end gap-1">
          <ResourceEditor resource={row} />
          <DeleteResource row={row} />
        </div>
      ),
    },
  ]

  return (
    <Card>
      <CardHeader>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="space-y-1">
            <CardTitle>Resources</CardTitle>
            <CardDescription>
              Only active resources targeted at your audience are returned.
              Files are downloaded through AEGIS, not from Strapi directly.
            </CardDescription>
          </div>
          <ResourceEditor />
        </div>
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

function RoleCheckboxes({
  idPrefix,
  value,
  onChange,
}: {
  idPrefix: string
  value: string[]
  onChange: (roles: string[]) => void
}) {
  const toggle = (role: string, checked: boolean) => {
    if (role === "all") {
      onChange(checked ? ["all"] : [])
      return
    }
    const withoutAll = value.filter((item) => item !== "all")
    onChange(
      checked
        ? [...withoutAll, role]
        : withoutAll.filter((item) => item !== role)
    )
  }

  return (
    <fieldset className="space-y-1.5">
      <legend className="text-sm font-medium">Audience</legend>
      <div className="flex flex-wrap gap-x-4 gap-y-2">
        {AUDIENCE_OPTIONS.map((option) => (
          <label
            key={option.value}
            className="flex items-center gap-2 text-sm"
            htmlFor={`${idPrefix}-${option.value}`}
          >
            <input
              id={`${idPrefix}-${option.value}`}
              type="checkbox"
              className="size-4 accent-foreground"
              checked={value.includes(option.value)}
              onChange={(event) => toggle(option.value, event.target.checked)}
            />
            {option.label}
          </label>
        ))}
      </div>
    </fieldset>
  )
}

function AnnouncementEditor({
  announcement,
}: {
  announcement?: CmsAnnouncement
}) {
  const save = useSaveCmsAnnouncement()
  const [open, setOpen] = useState(false)
  const initial = (): CmsAnnouncementInput => ({
    title: announcement?.title ?? "",
    content: announcement?.content ?? "",
    announcement_type: announcement?.announcement_type ?? "news",
    priority: announcement?.priority ?? "normal",
    target_roles: announcement?.target_roles?.length
      ? announcement.target_roles
      : ["all"],
  })
  const [form, setForm] = useState<CmsAnnouncementInput>(initial)

  const canSubmit =
    form.title.trim().length > 0 &&
    form.content.trim().length > 0 &&
    form.target_roles.length > 0

  const reset = (nextOpen: boolean) => {
    setOpen(nextOpen)
    if (nextOpen) {
      setForm(initial())
      save.reset()
    }
  }

  return (
    <Dialog open={open} onOpenChange={reset}>
      <DialogTrigger asChild>
        <Button variant={announcement ? "ghost" : "default"} size="sm">
          {announcement ? "Edit" : "New announcement"}
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>
            {announcement ? "Edit announcement" : "New announcement"}
          </DialogTitle>
          <DialogDescription>
            Saved through AEGIS and published to Strapi. Audience checkboxes
            choose which roles can see it.
          </DialogDescription>
        </DialogHeader>

        <form
          className="space-y-3"
          onSubmit={(event) => {
            event.preventDefault()
            if (!canSubmit) return
            save.mutate(
              {
                documentId: announcement?.document_id,
                payload: {
                  ...form,
                  title: form.title.trim(),
                  content: form.content.trim(),
                },
              },
              { onSuccess: () => setOpen(false) }
            )
          }}
        >
          <Field
            label="Title"
            id="cms-announcement-title"
            value={form.title}
            onChange={(value) => setForm({ ...form, title: value })}
            required
          />

          <div className="space-y-1.5">
            <Label htmlFor="cms-announcement-content">Content</Label>
            <Textarea
              id="cms-announcement-content"
              rows={4}
              value={form.content}
              required
              aria-required="true"
              onChange={(event) =>
                setForm({ ...form, content: event.target.value })
              }
            />
          </div>

          <div className="grid gap-3 sm:grid-cols-2">
            <ChoiceField
              label="Type"
              id="cms-announcement-type"
              value={form.announcement_type}
              onChange={(value) =>
                setForm({
                  ...form,
                  announcement_type:
                    value as CmsAnnouncement["announcement_type"],
                })
              }
              options={Object.entries(ANNOUNCEMENT_TYPE_LABELS).map(
                ([value, label]) => ({ value, label })
              )}
            />
            <ChoiceField
              label="Priority"
              id="cms-announcement-priority"
              value={form.priority}
              onChange={(value) =>
                setForm({
                  ...form,
                  priority: value as CmsAnnouncement["priority"],
                })
              }
              options={Object.entries(ANNOUNCEMENT_PRIORITY_LABELS).map(
                ([value, label]) => ({ value, label })
              )}
            />
          </div>

          <RoleCheckboxes
            idPrefix="cms-announcement-audience"
            value={form.target_roles}
            onChange={(roles) => setForm({ ...form, target_roles: roles })}
          />

          {save.isError ? (
            <ErrorNote message={normalizeApiError(save.error).message} />
          ) : null}

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => setOpen(false)}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={!canSubmit || save.isPending}>
              {save.isPending ? "Saving…" : "Save announcement"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

function DeleteAnnouncement({ row }: { row: CmsAnnouncement }) {
  const remove = useDeleteCmsAnnouncement()
  const [open, setOpen] = useState(false)

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="ghost" size="sm">
          Delete
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Delete announcement</DialogTitle>
          <DialogDescription>
            “{row.title}” is removed from Strapi and disappears from every
            audience. This cannot be undone.
          </DialogDescription>
        </DialogHeader>
        {remove.isError ? (
          <ErrorNote message={normalizeApiError(remove.error).message} />
        ) : null}
        <DialogFooter>
          <Button variant="outline" onClick={() => setOpen(false)}>
            Cancel
          </Button>
          <Button
            variant="destructive"
            disabled={remove.isPending}
            onClick={() =>
              remove.mutate(row.document_id, {
                onSuccess: () => setOpen(false),
              })
            }
          >
            {remove.isPending ? "Deleting…" : "Delete"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function ResourceEditor({ resource }: { resource?: CmsResource }) {
  const save = useSaveCmsResource()
  const [open, setOpen] = useState(false)
  const initial = (): CmsResourceInput => ({
    title: resource?.title ?? "",
    description: resource?.description ?? "",
    resource_type: resource?.resource_type ?? "link",
    url: resource?.file_or_url ?? "",
    target_audience: resource?.target_audience?.length
      ? resource.target_audience
      : ["all"],
    is_active: resource?.is_active ?? true,
  })
  const [form, setForm] = useState<CmsResourceInput>(initial)

  const canSubmit =
    form.title.trim().length > 0 && form.target_audience.length > 0

  const reset = (nextOpen: boolean) => {
    setOpen(nextOpen)
    if (nextOpen) {
      setForm(initial())
      save.reset()
    }
  }

  return (
    <Dialog open={open} onOpenChange={reset}>
      <DialogTrigger asChild>
        <Button variant={resource ? "ghost" : "default"} size="sm">
          {resource ? "Edit" : "New resource"}
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>
            {resource ? "Edit resource" : "New resource"}
          </DialogTitle>
          <DialogDescription>
            Authored links are published directly. To attach an uploaded file,
            use the Strapi admin.
          </DialogDescription>
        </DialogHeader>

        <form
          className="space-y-3"
          onSubmit={(event) => {
            event.preventDefault()
            if (!canSubmit) return
            save.mutate(
              {
                documentId: resource?.document_id,
                payload: {
                  ...form,
                  title: form.title.trim(),
                  description: form.description?.trim() || null,
                  url: form.url?.trim() || null,
                },
              },
              { onSuccess: () => setOpen(false) }
            )
          }}
        >
          <Field
            label="Title"
            id="cms-resource-title"
            value={form.title}
            onChange={(value) => setForm({ ...form, title: value })}
            required
          />

          <div className="space-y-1.5">
            <Label htmlFor="cms-resource-description">Description</Label>
            <Textarea
              id="cms-resource-description"
              rows={3}
              value={form.description ?? ""}
              onChange={(event) =>
                setForm({ ...form, description: event.target.value })
              }
            />
          </div>

          <div className="grid gap-3 sm:grid-cols-2">
            <ChoiceField
              label="Type"
              id="cms-resource-type"
              value={form.resource_type}
              onChange={(value) =>
                setForm({
                  ...form,
                  resource_type: value as CmsResource["resource_type"],
                })
              }
              options={Object.entries(RESOURCE_TYPE_LABELS).map(
                ([value, label]) => ({ value, label })
              )}
            />
            <ChoiceField
              label="Status"
              id="cms-resource-status"
              value={form.is_active ? "active" : "inactive"}
              onChange={(value) =>
                setForm({ ...form, is_active: value === "active" })
              }
              options={[
                { value: "active", label: "Active" },
                { value: "inactive", label: "Inactive" },
              ]}
            />
          </div>

          <Field
            label="File or URL"
            id="cms-resource-url"
            value={form.url ?? ""}
            onChange={(value) => setForm({ ...form, url: value })}
            placeholder="/uploads/handbook.pdf or https://example.com"
            hint="Leave blank for a metadata-only resource."
          />

          <RoleCheckboxes
            idPrefix="cms-resource-audience"
            value={form.target_audience}
            onChange={(roles) => setForm({ ...form, target_audience: roles })}
          />

          {save.isError ? (
            <ErrorNote message={normalizeApiError(save.error).message} />
          ) : null}

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => setOpen(false)}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={!canSubmit || save.isPending}>
              {save.isPending ? "Saving…" : "Save resource"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

function DeleteResource({ row }: { row: CmsResource }) {
  const remove = useDeleteCmsResource()
  const [open, setOpen] = useState(false)

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="ghost" size="sm">
          Delete
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Delete resource</DialogTitle>
          <DialogDescription>
            “{row.title}” is removed from Strapi and disappears from every
            audience. This cannot be undone.
          </DialogDescription>
        </DialogHeader>
        {remove.isError ? (
          <ErrorNote message={normalizeApiError(remove.error).message} />
        ) : null}
        <DialogFooter>
          <Button variant="outline" onClick={() => setOpen(false)}>
            Cancel
          </Button>
          <Button
            variant="destructive"
            disabled={remove.isPending}
            onClick={() =>
              remove.mutate(row.document_id, {
                onSuccess: () => setOpen(false),
              })
            }
          >
            {remove.isPending ? "Deleting…" : "Delete"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
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

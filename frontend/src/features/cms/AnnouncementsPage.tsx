import { Badge } from "@/components/ui/badge"
import {
  Card,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import {
  EmptyState,
  ErrorNote,
  PendingRegion,
} from "@/components/feedback/Feedback"
import { Skeleton } from "@/components/ui/skeleton"
import {
  ANNOUNCEMENT_PRIORITY_LABELS,
  ANNOUNCEMENT_TYPE_LABELS,
  useCmsAnnouncements,
  type CmsAnnouncement,
} from "@/features/admin/api"
import { AnnouncementCover } from "@/features/cms/AnnouncementCover"
import { CmsRichText } from "@/features/cms/CmsRichText"

function formatDate(value: string | null): string {
  if (!value) return ""
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return ""
  return parsed.toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  })
}

function AnnouncementCard({
  announcement,
  isPublic = false,
}: {
  announcement: CmsAnnouncement
  isPublic?: boolean
}) {
  const published = formatDate(announcement.published_at)
  return (
    <Card className="overflow-hidden">
      {announcement.cover_image ? (
        <AnnouncementCover
          documentId={announcement.document_id}
          coverImage={announcement.cover_image}
          isPublic={isPublic}
          alt={`Cover image for ${announcement.title}`}
        />
      ) : null}
      <CardHeader>
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="secondary">
            {ANNOUNCEMENT_TYPE_LABELS[announcement.announcement_type] ??
              announcement.announcement_type}
          </Badge>
          <Badge
            variant={
              announcement.priority === "urgent" ? "destructive" : "outline"
            }
          >
            {ANNOUNCEMENT_PRIORITY_LABELS[announcement.priority] ??
              announcement.priority}
          </Badge>
          {published ? (
            <span className="text-xs text-muted-foreground">{published}</span>
          ) : null}
        </div>
        <CardTitle>{announcement.title}</CardTitle>
        <CardDescription>
          <CmsRichText
            content={announcement.content}
            documentId={announcement.document_id}
            isPublic={isPublic}
            className="text-sm text-muted-foreground"
          />
        </CardDescription>
      </CardHeader>
    </Card>
  )
}

export function AnnouncementsPage() {
  const query = useCmsAnnouncements()
  const announcements = query.data ?? []

  return (
    <div className="space-y-6">
      <header className="space-y-1">
        <h2 className="text-2xl font-bold text-foreground">Announcements</h2>
        <p className="text-sm text-muted-foreground">
          School news and updates for you.
        </p>
      </header>

      {query.isLoading ? (
        <PendingRegion label="Announcements">
          <div className="grid gap-4 md:grid-cols-2">
            <Skeleton className="h-40 w-full" />
            <Skeleton className="h-40 w-full" />
          </div>
        </PendingRegion>
      ) : query.isError ? (
        <ErrorNote message="Unable to load announcements. The content service may be unavailable." />
      ) : announcements.length === 0 ? (
        <EmptyState message="No announcements yet. Check back later." />
      ) : (
        <ul className="grid gap-4 md:grid-cols-2">
          {announcements.map((announcement) => (
            <li key={announcement.document_id}>
              <AnnouncementCard announcement={announcement} />
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

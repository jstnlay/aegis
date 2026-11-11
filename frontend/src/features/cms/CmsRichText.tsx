import { API_BASE_URL } from "@/lib/api"

/**
 * CMS announcement content.
 *
 * The CMS authors content as plain text with the two pieces of markdown the
 * school actually uses: `![alt](url)` for an image and `**bold**` for
 * emphasis. Printing the raw string showed the markdown syntax to the
 * reader, so it is parsed here instead.
 *
 * A Strapi-hosted image is never fetched from the CMS origin (SEC-007): the
 * bytes come from Django's proxy for that announcement, which is the same
 * route the cover image uses. An image that cannot be fetched is hidden
 * rather than left as a broken icon.
 */

const IMAGE_PATTERN = /!\[([^\]]*)\]\(([^)\s]+)\)/g
const BOLD_PATTERN = /\*\*([^*]+)\*\*/g

type Segment =
  | { kind: "text"; text: string }
  | { kind: "image"; alt: string; src: string }

/**
 * Where the bytes for an image live.
 *
 * An absolute URL that is not a CMS upload is an authored external link
 * (a CDN, or Supabase Storage) and is used as it is. A CMS upload - a
 * path under `/uploads/` - is served by Django's proxy for that
 * announcement, because uploaded CMS media is never fetched from the CMS
 * origin directly (SEC-007).
 */
function imageSrc(
  url: string | undefined,
  documentId: string,
  isPublic: boolean
): string | null {
  if (!url) return null
  const isAbsolute = /^https?:\/\//i.test(url)
  const isCmsUpload = isAbsolute
    ? new URL(url).pathname.startsWith("/uploads/")
    : url.startsWith("/uploads/")
  if (isAbsolute && !isCmsUpload) return url
  if (!documentId) return null
  const path = isPublic
    ? `announcements/public/${encodeURIComponent(documentId)}/image/`
    : `announcements/${encodeURIComponent(documentId)}/image/`
  return `${API_BASE_URL}/cms/${path}`
}

function splitContent(
  content: string,
  documentId: string,
  isPublic: boolean
): Segment[] {
  const segments: Segment[] = []
  let cursor = 0
  for (const match of content.matchAll(IMAGE_PATTERN)) {
    const [raw, alt, url] = match
    const index = match.index ?? 0
    if (index > cursor) {
      segments.push({ kind: "text", text: content.slice(cursor, index) })
    }
    const src = imageSrc(url, documentId, isPublic)
    if (src) segments.push({ kind: "image", alt: alt || "", src })
    cursor = index + raw.length
  }
  if (cursor < content.length) {
    segments.push({ kind: "text", text: content.slice(cursor) })
  }
  return segments
}

/** `**bold**` becomes a `<strong>`, everything else stays text. */
function renderInline(text: string): React.ReactNode[] {
  const nodes: React.ReactNode[] = []
  let cursor = 0
  for (const match of text.matchAll(BOLD_PATTERN)) {
    const [raw, strong] = match
    const index = match.index ?? 0
    if (index > cursor) nodes.push(text.slice(cursor, index))
    nodes.push(<strong>{strong}</strong>)
    cursor = index + raw.length
  }
  if (cursor < text.length) nodes.push(text.slice(cursor))
  return nodes
}

export function CmsRichText({
  content,
  documentId,
  isPublic = false,
  className,
}: {
  content: string
  /** The announcement the content belongs to; its media proxy. */
  documentId: string
  /** True on the anonymous landing page. */
  isPublic?: boolean
  className?: string
}) {
  const segments = splitContent(content, documentId, isPublic)

  return (
    <div className={className}>
      {segments.map((segment, index) =>
        segment.kind === "image" ? (
          <img
            key={index}
            src={segment.src}
            alt={segment.alt}
            loading="lazy"
            className="mt-3 max-h-80 w-full rounded-sm border border-border object-cover"
            // A file that is gone (an upload from before the media moved to
            // durable storage) must not leave a broken image on the page.
            onError={(event) => {
              event.currentTarget.style.display = "none"
            }}
          />
        ) : (
          <p key={index} className="whitespace-pre-line">
            {renderInline(segment.text)}
          </p>
        )
      )}
    </div>
  )
}

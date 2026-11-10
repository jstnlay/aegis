import { useEffect } from "react"
import { useQuery } from "@tanstack/react-query"

import { API_BASE_URL, apiClient } from "@/lib/api"

/**
 * Announcement cover image.
 *
 * Three cases, and the caller does not have to know which:
 *
 * - The image is hosted by the Strapi origin: the bytes are proxied through
 *   Django, so an authenticated page fetches them with the bearer token and
 *   hands the browser an object URL.
 * - The image is hosted elsewhere (a CDN, or Supabase Storage when the CMS
 *   upload provider is configured for it): the URL is used as it is, exactly
 *   as an authored external link.
 * - The public landing page reads the anonymous proxy route, which a plain
 *   `<img>` can load directly.
 */
export function AnnouncementCover({
  documentId,
  coverImage,
  isPublic = false,
  alt,
}: {
  documentId: string
  /** The `cover_image` value from the CMS payload; a proxy path or a URL. */
  coverImage?: string | null
  isPublic?: boolean
  alt: string
}) {
  const external = coverImage?.startsWith("http") ? coverImage : null

  const query = useQuery<string | null, Error>({
    queryKey: ["cms", "announcement-image", documentId],
    enabled: !external && !isPublic && Boolean(documentId),
    queryFn: async () => {
      const response = await apiClient.get(
        `/cms/announcements/${encodeURIComponent(documentId)}/image/`,
        { responseType: "blob" }
      )
      return URL.createObjectURL(response.data as Blob)
    },
  })

  // The object URL is released when it is replaced or the page goes away;
  // without this it is retained for the lifetime of the document.
  useEffect(() => {
    const url = query.data
    return () => {
      if (url) URL.revokeObjectURL(url)
    }
  }, [query.data])

  const src =
    external ??
    (isPublic
      ? `${API_BASE_URL}/cms/announcements/public/${encodeURIComponent(
          documentId
        )}/image/`
      : (query.data ?? null))

  if (!src) return null

  return (
    <img
      src={src}
      alt={alt}
      loading="lazy"
      className="h-44 w-full rounded-t-sm object-cover"
    />
  )
}

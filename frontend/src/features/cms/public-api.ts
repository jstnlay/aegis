import { useQuery } from "@tanstack/react-query"

import type { CmsAnnouncement, CmsResource } from "@/features/admin/api"
import { fetchAllPages } from "@/lib/pagination"

/**
 * Anonymous landing-page feeds.
 *
 * `GET /cms/announcements/public/` and `/cms/resources/public/` need no
 * authentication and return only items targeted at everyone. A 502 means
 * Strapi (the CMS service) is unreachable — the landing page says so
 * honestly rather than rendering an empty list as "no announcements".
 *
 * `fetchAllPages` is the one way to read these: the views are
 * `ListAPIView`, so DRF envelopes the response as
 * `{count, next, previous, results}` and the rows live under `results`.
 */
export function usePublicAnnouncements() {
  return useQuery<CmsAnnouncement[], Error>({
    queryKey: ["cms", "public-announcements"],
    queryFn: async ({ signal }) => {
      const { results } = await fetchAllPages<CmsAnnouncement>(
        "/cms/announcements/public/",
        { signal }
      )
      return results
    },
    // One attempt only: a dead content service refuses the connection slowly,
    // so the default single retry doubles the time before the landing page
    // can say the service is unavailable.
    retry: false,
  })
}

export function usePublicResources() {
  return useQuery<CmsResource[], Error>({
    queryKey: ["cms", "public-resources"],
    queryFn: async ({ signal }) => {
      const { results } = await fetchAllPages<CmsResource>(
        "/cms/resources/public/",
        { signal }
      )
      return results
    },
    retry: false,
  })
}

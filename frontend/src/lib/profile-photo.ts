import { API_BASE_URL } from "@/lib/api"

/**
 * An absolute URL for a stored profile photo, or null when none is set.
 *
 * DRF returns an absolute URL when the request has a context; a relative
 * `/media/...` is resolved against the API origin, not the frontend origin,
 * because the file is served by Django.
 */
export function profilePhotoSrc(
  value: string | null | undefined
): string | null {
  if (!value) return null
  if (/^https?:\/\//i.test(value)) return value
  try {
    return `${new URL(API_BASE_URL).origin}/${value.replace(/^\/+/, "")}`
  } catch {
    return value
  }
}

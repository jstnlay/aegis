/** Keep upstream pagination links on the configured same-origin API proxy. */
export function rewriteProxiedApiUrl(
  url: string | undefined,
  baseUrl: string,
  upstreamUrl: string | undefined
): string | undefined {
  if (!url || !baseUrl.startsWith("/") || !upstreamUrl) return url
  try {
    const requested = new URL(url)
    const upstream = new URL(upstreamUrl)
    const prefix = upstream.pathname.replace(/\/+$/, "")
    if (
      requested.origin !== upstream.origin ||
      (requested.pathname !== prefix &&
        !requested.pathname.startsWith(`${prefix}/`))
    ) {
      return url
    }
    return `${requested.pathname.slice(prefix.length) || "/"}${requested.search}${requested.hash}`
  } catch {
    // Relative endpoints and deployments without a valid upstream stay intact.
    return url
  }
}

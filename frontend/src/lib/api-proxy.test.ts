import { describe, expect, it } from "vitest"

import { rewriteProxiedApiUrl } from "./api-proxy"

const upstream = "https://api.example.test/api/v1"

describe("same-origin API proxy routing", () => {
  it("routes absolute pagination links through the proxy and preserves the query", () => {
    expect(
      rewriteProxiedApiUrl(
        `${upstream}/guidance/students/?page=2&page_size=100&search=Ana%20Reyes`,
        "/api",
        upstream
      )
    ).toBe("/guidance/students/?page=2&page_size=100&search=Ana%20Reyes")
  })

  it.each([undefined, "/auth/login/", "/guidance/students/?page=2"])(
    "preserves relative endpoints: %s",
    (url) => {
      expect(rewriteProxiedApiUrl(url, "/api", upstream)).toBe(url)
    }
  )

  it.each([
    "https://other.example.test/api/v1/students/",
    "https://api.example.test/api/v10/students/",
    "https://api.example.test/media/photo.jpg",
  ])("preserves URLs outside the configured upstream: %s", (url) => {
    expect(rewriteProxiedApiUrl(url, "/api", upstream)).toBe(url)
  })

  it("preserves direct API deployments", () => {
    const url = `${upstream}/students/?page=2`
    expect(rewriteProxiedApiUrl(url, upstream, upstream)).toBe(url)
    expect(rewriteProxiedApiUrl(url, "/api", undefined)).toBe(url)
  })

  it("accepts an upstream with a trailing slash", () => {
    expect(
      rewriteProxiedApiUrl(
        `${upstream}/students/?page=2`,
        "/api",
        `${upstream}/`
      )
    ).toBe("/students/?page=2")
  })

  it("leaves requests intact when the upstream setting is invalid", () => {
    const url = `${upstream}/students/`
    expect(rewriteProxiedApiUrl(url, "/api", "invalid")).toBe(url)
  })
})

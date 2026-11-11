import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { CmsRichText } from "./CmsRichText"

/**
 * The CMS is authored as plain text with the two pieces of markdown the
 * school uses. Printing the raw string showed `![alt](url)` and `**bold**`
 * to the reader, so the content is parsed before it is rendered.
 */
describe("CmsRichText", () => {
  it("renders plain text as it was written", () => {
    render(
      <CmsRichText content="Class advisers upload grades." documentId="doc-1" />
    )

    expect(
      screen.getByText("Class advisers upload grades.")
    ).toBeInTheDocument()
  })

  it("renders bold text as bold, not as markdown", () => {
    render(<CmsRichText content="**Read this first.**" documentId="doc-1" />)

    expect(screen.getByText("Read this first.").tagName).toBe("STRONG")
    expect(screen.queryByText(/\*\*/)).not.toBeInTheDocument()
  })

  it("renders an external image as an image", () => {
    render(
      <CmsRichText
        content="![Poster](https://images.example.org/poster.png)"
        documentId="doc-1"
      />
    )

    const image = screen.getByRole("img", { name: "Poster" })
    expect(image).toHaveAttribute(
      "src",
      "https://images.example.org/poster.png"
    )
  })

  it("serves a CMS-hosted image through the Django proxy, never directly", () => {
    render(
      <CmsRichText
        content="![Poster](https://aegis-cms.onrender.com/uploads/poster.png)"
        documentId="doc-1"
        isPublic
      />
    )

    const image = screen.getByRole("img", { name: "Poster" })
    expect(image.getAttribute("src")).toContain(
      "/cms/announcements/public/doc-1/image/"
    )
    expect(image.getAttribute("src")).not.toContain("aegis-cms.onrender.com")
  })
})

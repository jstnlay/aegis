import type { ReactNode } from "react"
import { ArrowLeft } from "lucide-react"
import { Link } from "react-router-dom"

import { PublicFooter } from "@/components/brand/PublicFooter"
import { SchoolHeader } from "@/components/brand/SchoolHeader"
import { CONTACT, SCHOOL_NAME } from "@/lib/school-content"

/**
 * Shared chrome for the three legal pages (privacy, terms, cookies).
 *
 * They share the public header and footer but not `PublicNav`: its entries are
 * anchor links into the landing page's sections, and none of those anchors
 * exist here.
 *
 * The date is a constant rather than a build value so the school can see and
 * edit exactly what is published. It is the date the text last changed, so it
 * must be bumped whenever any of the three pages is edited.
 */
export const LEGAL_LAST_UPDATED = "October 2026"

export function LegalPageLayout({
  title,
  intro,
  children,
}: {
  title: string
  /** One-paragraph plain-language summary shown under the heading. */
  intro: string
  children: ReactNode
}) {
  return (
    <div className="min-h-svh bg-background">
      <SchoolHeader>
        <Link
          to="/"
          className="inline-flex items-center gap-1.5 text-sm text-muted-foreground transition-colors hover:text-foreground"
        >
          <ArrowLeft aria-hidden="true" className="size-4" />
          Back to the landing page
        </Link>
      </SchoolHeader>

      <main className="mx-auto w-full max-w-3xl space-y-8 px-4 py-12 lg:px-6">
        <div className="space-y-3">
          <h1 className="text-balance text-3xl font-bold tracking-tight text-primary sm:text-4xl">
            {title}
          </h1>
          <p className="text-xs text-muted-foreground">
            Last updated {LEGAL_LAST_UPDATED}
          </p>
          <p className="max-w-prose text-sm leading-relaxed text-pretty text-muted-foreground">
            {intro}
          </p>
        </div>

        <div className="space-y-6">{children}</div>

        <section
          aria-labelledby="legal-contact"
          className="space-y-3 rounded-2xl border border-border/70 bg-primary/5 p-6"
        >
          <h2 id="legal-contact" className="text-lg font-semibold text-primary">
            How to reach us about this policy
          </h2>
          <p className="text-sm leading-relaxed text-muted-foreground">
            {SCHOOL_NAME} is the personal information controller for AEGIS.
            Write to the school's Data Protection Officer through the
            registrar's office:
          </p>
          <dl className="grid gap-3 text-sm sm:grid-cols-2">
            <div className="space-y-1">
              <dt className="text-xs text-muted-foreground">Email</dt>
              <dd>
                <a
                  href={`mailto:${CONTACT.email}`}
                  className="break-all underline underline-offset-4 transition-colors hover:text-primary"
                >
                  {CONTACT.email}
                </a>
              </dd>
            </div>
            <div className="space-y-1">
              <dt className="text-xs text-muted-foreground">Address</dt>
              <dd className="text-muted-foreground">{CONTACT.address}</dd>
            </div>
          </dl>
          <p className="text-xs leading-relaxed text-muted-foreground">
            You may also lodge a complaint with the National Privacy Commission
            of the Philippines.
          </p>
        </section>
      </main>

      <PublicFooter />
    </div>
  )
}

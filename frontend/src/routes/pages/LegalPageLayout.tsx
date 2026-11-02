import { useLayoutEffect, type ReactNode } from "react"
import { ArrowLeft, X } from "lucide-react"
import { Link } from "react-router-dom"

import { PublicFooter } from "@/components/brand/PublicFooter"
import { SchoolHeader } from "@/components/brand/SchoolHeader"
import { Button } from "@/components/ui/button"
import {
  DialogClose,
  DialogDescription,
  DialogTitle,
} from "@/components/ui/dialog"
import { CONTACT, SCHOOL_NAME } from "@/lib/school-content"
import "./legal-page.css"

export const LEGAL_LAST_UPDATED = "October 2026"

export function LegalPageLayout({
  title,
  intro,
  children,
  presentation = "page",
}: {
  title: string
  intro: string
  children: ReactNode
  presentation?: "page" | "dialog"
}) {
  useLayoutEffect(() => {
    if (presentation === "page") {
      window.scrollTo({ top: 0, left: 0, behavior: "instant" })
    }
  }, [title, presentation])

  if (presentation === "dialog") {
    return (
      <div className="login-policy-document">
        <header className="login-policy-header">
          <div>
            <p className="login-policy-eyebrow">AEGIS · School policies</p>
            <DialogTitle>{title}</DialogTitle>
            <p className="login-policy-updated">
              Last updated {LEGAL_LAST_UPDATED}
            </p>
          </div>
          <DialogClose asChild>
            <Button variant="ghost" size="icon" aria-label="Close policy">
              <X aria-hidden="true" />
            </Button>
          </DialogClose>
        </header>
        <div
          className="login-policy-scroll"
          role="region"
          aria-label={`${title} document`}
          tabIndex={0}
        >
          <DialogDescription className="login-policy-intro">
            {intro}
          </DialogDescription>
          <LegalDocumentBody>{children}</LegalDocumentBody>
        </div>
        <footer className="login-policy-footer">
          <p>His Care Christian Institute</p>
          <DialogClose asChild>
            <Button>Back to sign in</Button>
          </DialogClose>
        </footer>
      </div>
    )
  }

  return (
    <div className="school-legal-page min-h-svh bg-background">
      <SchoolHeader brandPosition="end">
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

        <LegalDocumentBody>{children}</LegalDocumentBody>
      </main>

      <PublicFooter />
    </div>
  )
}

function LegalDocumentBody({ children }: { children: ReactNode }) {
  return (
    <div className="space-y-8">
      <div className="space-y-6">{children}</div>
      <section
        aria-labelledby="legal-contact"
        className="space-y-3 rounded-2xl border border-border/70 bg-primary/5 p-6"
      >
        <h2 id="legal-contact" className="text-lg font-semibold text-primary">
          How to contact the school
        </h2>
        <p className="text-sm leading-relaxed text-muted-foreground">
          {SCHOOL_NAME} is the personal information controller for AEGIS. Write
          to the school's Data Protection Officer through the registrar's
          office:
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
          You may also lodge a complaint with the National Privacy Commission of
          the Philippines.
        </p>
      </section>
    </div>
  )
}

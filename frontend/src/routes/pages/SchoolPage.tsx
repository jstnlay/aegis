import { ArrowLeft, ArrowRight } from "lucide-react"
import { Link } from "react-router-dom"

import { SchoolHeader } from "@/components/brand/SchoolHeader"
import { Reveal } from "@/components/layout/Reveal"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { ABOUT_TEXT, MISSION_TEXT, VISION_TEXT } from "@/lib/school-content"

/**
 * "Read more" destination from the landing page - the school's background
 * page the supplied reference shows: the full About text (three campuses,
 * DepEd recognitions) plus the Mission and Vision verbatim from
 * `@/lib/school-content`. Public, no sign-in.
 *
 * The reference also shows a PVMGO/Philosophy block below the Mission &
 * Vision; that copy has not been supplied, so it is deliberately absent
 * rather than invented.
 */
export function SchoolPage() {
  return (
    <div className="min-h-svh bg-background">
      <SchoolHeader>
        <Button
          asChild
          size="sm"
          className="transition-all hover:-translate-y-0.5 hover:shadow-sm"
        >
          <Link to="/login">
            Sign in <ArrowRight aria-hidden="true" className="size-4" />
          </Link>
        </Button>
      </SchoolHeader>

      <main className="mx-auto w-full max-w-5xl space-y-8 px-4 py-12 md:space-y-12 lg:px-6">
        <Reveal>
          <div className="space-y-3">
            <Link
              to="/"
              className="inline-flex items-center gap-1.5 text-sm text-muted-foreground transition-colors hover:text-foreground"
            >
              <ArrowLeft aria-hidden="true" className="size-4" />
              Back to the landing page
            </Link>
            <h1 className="text-balance text-3xl font-bold tracking-tight text-primary sm:text-4xl">
              School background
            </h1>
          </div>
        </Reveal>

        <Reveal>
          <section
            aria-labelledby="school-about"
            className="space-y-4 scroll-mt-20"
          >
            <h2
              id="school-about"
              className="text-balance text-2xl font-semibold tracking-tight text-primary"
            >
              About the school
            </h2>
            <p className="max-w-prose text-sm leading-relaxed text-pretty text-muted-foreground">
              {ABOUT_TEXT}
            </p>
          </section>
        </Reveal>

        <Reveal>
          <section
            aria-labelledby="school-mission-vision"
            className="space-y-4 rounded-2xl border border-border/70 bg-muted/50 p-6 md:p-8"
          >
            <h2
              id="school-mission-vision"
              className="text-balance text-2xl font-semibold tracking-tight text-primary"
            >
              Mission &amp; vision
            </h2>
            <div className="grid gap-4 md:grid-cols-2">
              <Card className="h-full transition-all duration-200 hover:-translate-y-0.5 hover:shadow-md hover:ring-primary/20">
                <CardHeader>
                  <CardTitle className="text-base text-primary">
                    Mission
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <p className="text-sm whitespace-pre-line leading-relaxed text-muted-foreground">
                    {MISSION_TEXT}
                  </p>
                </CardContent>
              </Card>
              <Card className="h-full transition-all duration-200 hover:-translate-y-0.5 hover:shadow-md hover:ring-primary/20">
                <CardHeader>
                  <CardTitle className="text-base text-primary">
                    Vision
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <p className="text-sm leading-relaxed text-muted-foreground">
                    {VISION_TEXT}
                  </p>
                </CardContent>
              </Card>
            </div>
          </section>
        </Reveal>
      </main>

      <footer className="border-t border-border bg-muted/30">
        <div className="mx-auto w-full max-w-5xl px-4 py-8 text-xs text-muted-foreground lg:px-6">
          <span>
            His Care Christian Institute · AEGIS school information system
          </span>
        </div>
      </footer>
    </div>
  )
}

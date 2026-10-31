import { useLayoutEffect } from "react"
import { ArrowLeft, BookOpen, Target } from "lucide-react"
import { Link } from "react-router-dom"

import { PublicFooter } from "@/components/brand/PublicFooter"
import { SchoolHeader } from "@/components/brand/SchoolHeader"
import { Reveal } from "@/components/layout/Reveal"
import { Button } from "@/components/ui/button"
import { ABOUT_TEXT, MISSION_TEXT, VISION_TEXT } from "@/lib/school-content"
import "./school-page.css"

const ABOUT_PARAGRAPHS = ABOUT_TEXT.split(
  /(?=On their 1st year|His Care Christian Institute of Tanauan|His Care Christian Institute of Santa Maria)/
)

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
  useLayoutEffect(() => {
    window.scrollTo({ top: 0, left: 0, behavior: "instant" })
  }, [])

  return (
    <div className="school-background-page min-h-svh">
      <SchoolHeader brandPosition="end">
        <Link
          to="/"
          aria-label="Back to the landing page"
          className="school-background-back"
        >
          <ArrowLeft aria-hidden="true" className="size-4" />
          <span>Back to the landing page</span>
        </Link>
        <Button asChild size="lg" className="school-background-sign-in">
          <Link to="/login">Sign in</Link>
        </Button>
      </SchoolHeader>

      <main className="school-background-main">
        <Reveal>
          <div className="school-background-title">
            <h1>School background</h1>
          </div>
        </Reveal>

        <Reveal>
          <section
            aria-labelledby="school-about"
            className="school-background-about"
          >
            <h2 id="school-about">About the school</h2>
            <div className="school-background-copy" lang="en">
              {ABOUT_PARAGRAPHS.map((paragraph) => (
                <p key={paragraph}>{paragraph.trim()}</p>
              ))}
            </div>
          </section>
        </Reveal>

        <Reveal>
          <section
            aria-labelledby="school-mission-vision"
            className="school-background-beliefs"
          >
            <h2 id="school-mission-vision">Mission &amp; vision</h2>
            <div className="school-background-belief-grid">
              <article
                className="school-background-belief"
                aria-labelledby="school-mission"
              >
                <div className="school-background-belief-heading">
                  <BookOpen aria-hidden="true" />
                  <h3 id="school-mission">Mission</h3>
                </div>
                <p
                  className="school-background-copy school-background-mission"
                  lang="en"
                >
                  {MISSION_TEXT}
                </p>
              </article>
              <article
                className="school-background-belief"
                aria-labelledby="school-vision"
              >
                <div className="school-background-belief-heading">
                  <Target aria-hidden="true" />
                  <h3 id="school-vision">Vision</h3>
                </div>
                <p className="school-background-copy" lang="en">
                  {VISION_TEXT}
                </p>
              </article>
            </div>
          </section>
        </Reveal>
      </main>

      <PublicFooter />
    </div>
  )
}

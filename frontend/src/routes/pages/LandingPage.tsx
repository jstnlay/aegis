import { useEffect, useState } from "react"
import { Link } from "react-router-dom"
import {
  ArrowRight,
  Bell,
  BookOpen,
  CalendarCheck,
  ChevronDown,
  HeartHandshake,
  HelpCircle,
} from "lucide-react"

import { PublicFooter } from "@/components/brand/PublicFooter"
import { PublicNav } from "@/components/brand/PublicNav"
import { SchoolHeader } from "@/components/brand/SchoolHeader"
import { Reveal } from "@/components/layout/Reveal"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardAction,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import {
  ANNOUNCEMENT_TYPE_LABELS,
  RESOURCE_TYPE_LABELS,
} from "@/features/admin/api"
import {
  usePublicAnnouncements,
  usePublicResources,
} from "@/features/cms/public-api"
import { normalizeApiError } from "@/lib/error"
import {
  ABOUT_EXCERPT,
  CONTACT,
  MISSION_TEXT,
  SCHOOL_CAMPUS_LINE,
  SCHOOL_NAME,
  VISION_TEXT,
} from "@/lib/school-content"
import { cn } from "@/lib/utils"

/** Hero entrance runs on the first landing visit of a session, not every one. */
const HERO_SEEN_KEY = "aegis:hero-entrance-seen"

function useHeroEntrance() {
  const [animate] = useState(() => {
    if (typeof window === "undefined") return true
    try {
      return !window.sessionStorage.getItem(HERO_SEEN_KEY)
    } catch {
      return true
    }
  })

  useEffect(() => {
    if (!animate) return
    try {
      window.sessionStorage.setItem(HERO_SEEN_KEY, "1")
    } catch {
      // Storage blocked (private mode): the entrance just replays.
    }
  }, [animate])

  return animate
}

/**
 * Public landing page - reachable by everyone, no sign-in.
 *
 * School identity first (lockup, cover-photo hero backdrop, About/Mission/Vision from
 * the school's own copy in `@/lib/school-content`), then the AEGIS product
 * sections: portal highlights, FAQ and the school CMS feed. The CMS sections
 * read the anonymous public endpoints; when Strapi is down they say the
 * content service is unavailable rather than pretending there is nothing to
 * show.
 */
export function LandingPage() {
  const animateHero = useHeroEntrance()

  return (
    <div className="min-h-svh bg-background">
      <SchoolHeader>
        <PublicNav />
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

      <main className="mx-auto w-full max-w-5xl space-y-12 px-4 py-12 md:space-y-16 lg:px-6">
        <section
          aria-labelledby="landing-hero"
          className="relative min-h-[20rem] overflow-hidden rounded-2xl border border-border bg-center bg-cover shadow-sm max-md:bg-left"
          style={{ backgroundImage: "url(/cover-photo.png)" }}
        >
          {/* Solid light veil on the left where the copy sits, opening to the
                bare campus photo on the right, per the school's reference. */}
          <div
            aria-hidden="true"
            className="absolute inset-0 bg-gradient-to-r from-background via-background/95 to-background/70 md:to-transparent"
          />
          <div
            className={cn(
              "relative z-10 flex min-h-[20rem] max-w-xl flex-col justify-center p-6 md:p-10",
              animateHero &&
                "motion-safe:animate-in motion-safe:fade-in motion-safe:slide-in-from-bottom-4 motion-safe:fill-mode-both motion-safe:duration-700"
            )}
          >
            <h1
              id="landing-hero"
              className="text-balance text-3xl font-bold tracking-tight text-primary sm:text-4xl"
            >
              {SCHOOL_NAME}
            </h1>
            <p className="mt-1 font-medium">{SCHOOL_CAMPUS_LINE}</p>
            <p className="mt-4 max-w-prose text-sm leading-relaxed text-pretty text-muted-foreground">
              {/* Verbatim from the supplied landing-page reference, keeping
                    its emphasis on the school name and founding year. */}
              <strong className="text-foreground">
                His Care Christian Institute
              </strong>{" "}
              was founded in{" "}
              <strong className="text-foreground">April 2007</strong> by Leila
              D. Paragoso and Clemente T. Paragoso. From a small preschool, it
              has grown into a school serving students from Nursery to Grade 10
              in Batangas.
            </p>
            <div className="mt-5 flex flex-wrap items-center gap-3">
              <Button
                asChild
                className="transition-all hover:-translate-y-0.5 hover:shadow-md"
              >
                <Link to="/school">
                  Read more <ArrowRight aria-hidden="true" className="size-4" />
                </Link>
              </Button>
            </div>
          </div>
        </section>

        <Reveal>
          <section
            id="about"
            aria-labelledby="landing-about"
            className="space-y-4 scroll-mt-20"
          >
            <h2
              id="landing-about"
              className="text-balance text-2xl font-semibold tracking-tight text-primary"
            >
              About the school
            </h2>
            <p className="max-w-prose text-sm leading-relaxed text-pretty text-muted-foreground">
              {ABOUT_EXCERPT}
            </p>
            <Button
              asChild
              variant="outline"
              size="sm"
              className="transition-all hover:-translate-y-0.5 hover:shadow-sm"
            >
              <Link to="/school">
                Read more <ArrowRight aria-hidden="true" className="size-4" />
              </Link>
            </Button>
          </section>
        </Reveal>

        <Reveal>
          <section
            aria-labelledby="landing-mission-vision"
            className="space-y-4 rounded-2xl border border-border/70 bg-muted/50 p-6 md:p-8"
          >
            <h2
              id="landing-mission-vision"
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

        <Reveal>
          <PortalHighlights />
        </Reveal>
        <Reveal>
          <AnnouncementsSection />
        </Reveal>
        <Reveal>
          <ResourcesSection />
        </Reveal>
        <Reveal>
          <FaqSection />
        </Reveal>

        <Reveal>
          <section
            id="contact"
            aria-labelledby="landing-contact"
            className="space-y-4 rounded-2xl border border-border/70 bg-primary/5 p-6 scroll-mt-20 md:p-8"
          >
            <h2
              id="landing-contact"
              className="text-balance text-2xl font-semibold tracking-tight text-primary"
            >
              Contact
            </h2>
            <div className="grid gap-4 sm:grid-cols-3">
              <Card className="h-full transition-all duration-200 hover:-translate-y-0.5 hover:shadow-md hover:ring-primary/20">
                <CardHeader>
                  <CardTitle className="text-base text-primary">
                    Address
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <p className="text-sm leading-relaxed text-muted-foreground">
                    {CONTACT.address}
                  </p>
                </CardContent>
              </Card>
              <Card className="h-full transition-all duration-200 hover:-translate-y-0.5 hover:shadow-md hover:ring-primary/20">
                <CardHeader>
                  <CardTitle className="text-base text-primary">
                    School ID
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <p className="text-sm leading-relaxed text-muted-foreground">
                    {CONTACT.schoolId}
                  </p>
                </CardContent>
              </Card>
              <Card className="h-full transition-all duration-200 hover:-translate-y-0.5 hover:shadow-md hover:ring-primary/20">
                <CardHeader>
                  <CardTitle className="text-base text-primary">
                    Email Address
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <a
                    href={`mailto:${CONTACT.email}`}
                    className="break-all text-sm underline transition-colors hover:text-primary"
                  >
                    {CONTACT.email}
                  </a>
                </CardContent>
              </Card>
            </div>
          </section>
        </Reveal>
      </main>

      <PublicFooter />
    </div>
  )
}

/** The three things AEGIS gives the school, one icon per module. */
const PORTAL_HIGHLIGHTS = [
  {
    icon: BookOpen,
    title: "Academics",
    body: "Grades encoded by faculty, finalized by administration, and visible to students and linked parents once finalized.",
  },
  {
    icon: CalendarCheck,
    title: "Attendance",
    body: "Daily records taken by faculty, with per-section summaries for students, parents and administrators.",
  },
  {
    icon: HeartHandshake,
    title: "Guidance",
    body: "Counseling sessions, intervention plans and wellness assessments handled by the guidance office.",
  },
] as const

function PortalHighlights() {
  return (
    <section aria-labelledby="landing-portal" className="space-y-4">
      <h2
        id="landing-portal"
        className="text-balance text-2xl font-semibold tracking-tight text-primary"
      >
        What AEGIS offers
      </h2>
      <div className="grid gap-4 md:grid-cols-3">
        {PORTAL_HIGHLIGHTS.map(({ icon: Icon, title, body }) => (
          <Card
            key={title}
            className="h-full transition-all duration-200 hover:-translate-y-0.5 hover:shadow-md hover:ring-primary/20"
          >
            <CardHeader>
              <span className="flex size-9 items-center justify-center rounded-lg bg-primary/10 text-primary">
                <Icon aria-hidden="true" className="size-5" />
              </span>
              <CardTitle className="mt-1 text-base text-primary">
                {title}
              </CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-sm leading-relaxed text-pretty text-muted-foreground">
                {body}
              </p>
            </CardContent>
          </Card>
        ))}
      </div>
    </section>
  )
}

/**
 * Announcement type chip colour, reusing the existing badge variants so the
 * four types are told apart at a glance: an alert reads as a warning, an
 * academic notice carries the school maroon.
 */
const ANNOUNCEMENT_TYPE_BADGE = {
  alert: "destructive",
  academic: "default",
  event: "secondary",
  news: "outline",
} as const

function AnnouncementsSection() {
  const query = usePublicAnnouncements()
  const items = query.data ?? []

  return (
    <section
      id="announcements"
      aria-labelledby="landing-announcements"
      className="space-y-4 scroll-mt-20"
    >
      <h2
        id="landing-announcements"
        className="flex items-center gap-2 text-balance text-2xl font-semibold tracking-tight text-primary"
      >
        <Bell aria-hidden="true" className="size-5 text-muted-foreground" />
        Announcements
      </h2>
      {query.isLoading ? (
        <div className="space-y-2">
          <Skeleton className="h-16 w-full" />
          <Skeleton className="h-16 w-full" />
        </div>
      ) : query.isError ? (
        <Card>
          <CardContent className="pt-6">
            <p
              className="text-sm leading-relaxed text-muted-foreground"
              role="alert"
            >
              The content service is temporarily unavailable (
              {normalizeApiError(query.error).message}). Please try again later.
            </p>
          </CardContent>
        </Card>
      ) : items.length === 0 ? (
        <p className="text-sm leading-relaxed text-muted-foreground">
          No announcements have been published yet.
        </p>
      ) : (
        <ul className="grid gap-4 md:grid-cols-2">
          {items.map((item) => (
            <li key={item.document_id}>
              <Card className="transition-all duration-200 hover:-translate-y-0.5 hover:shadow-md hover:ring-primary/20">
                <CardHeader>
                  <CardTitle className="text-base break-words text-primary">
                    {item.title}
                  </CardTitle>
                  <CardAction>
                    <Badge
                      variant={ANNOUNCEMENT_TYPE_BADGE[item.announcement_type]}
                    >
                      {ANNOUNCEMENT_TYPE_LABELS[item.announcement_type] ??
                        item.announcement_type}
                    </Badge>
                  </CardAction>
                </CardHeader>
                <CardContent className="space-y-2">
                  <p className="text-sm leading-relaxed whitespace-pre-line">
                    {item.content}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    Published {new Date(item.published_at).toLocaleDateString()}
                  </p>
                </CardContent>
              </Card>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}

function ResourcesSection() {
  const query = usePublicResources()
  const items = query.data ?? []

  return (
    <section
      id="resources"
      aria-labelledby="landing-resources"
      className="space-y-4 scroll-mt-20"
    >
      <h2
        id="landing-resources"
        className="flex items-center gap-2 text-balance text-2xl font-semibold tracking-tight text-primary"
      >
        <BookOpen aria-hidden="true" className="size-5 text-muted-foreground" />
        Resources
      </h2>
      {query.isLoading ? (
        <div className="space-y-2">
          <Skeleton className="h-12 w-full" />
          <Skeleton className="h-12 w-full" />
        </div>
      ) : query.isError ? (
        <Card>
          <CardContent className="pt-6">
            <p
              className="text-sm leading-relaxed text-muted-foreground"
              role="alert"
            >
              The content service is temporarily unavailable (
              {normalizeApiError(query.error).message}). Please try again later.
            </p>
          </CardContent>
        </Card>
      ) : items.length === 0 ? (
        <p className="text-sm leading-relaxed text-muted-foreground">
          No resources have been published yet.
        </p>
      ) : (
        <ul className="space-y-2">
          {items.map((item) => (
            <li
              key={item.document_id}
              className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-border bg-card p-3.5 transition-colors duration-200 hover:border-primary/40 hover:bg-muted/40"
            >
              <div className="min-w-0">
                <p className="truncate font-medium">{item.title}</p>
                {item.description ? (
                  <p className="truncate text-xs text-muted-foreground">
                    {item.description}
                  </p>
                ) : null}
              </div>
              <Badge variant="secondary" className="shrink-0">
                {RESOURCE_TYPE_LABELS[item.resource_type] ?? item.resource_type}
              </Badge>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}

const FAQS = [
  {
    q: "How do I sign in?",
    a: "Use the Sign in button above with the school account issued to you. If you must change your password, the system will ask for it right after sign-in.",
  },
  {
    q: "Where do grades appear?",
    a: "Students see finalized grades on their Academics page; linked parents see the same on theirs. Draft and submitted grades are visible only to faculty and administration.",
  },
  {
    q: "Who do I contact about counseling?",
    a: "The guidance office handles consultations, interventions and wellness assessments. Students and parents can reach them through the support pages inside the portal.",
  },
  {
    q: "Why is the content feed unavailable?",
    a: "Announcements and resources are published through the school content service. If it is down, this page says so instead of showing an empty list - try again later.",
  },
]

function FaqSection() {
  return (
    <section
      id="faq"
      aria-labelledby="landing-faq"
      className="space-y-4 scroll-mt-20"
    >
      <h2
        id="landing-faq"
        className="flex items-center gap-2 text-balance text-2xl font-semibold tracking-tight text-primary"
      >
        <HelpCircle
          aria-hidden="true"
          className="size-5 text-muted-foreground"
        />
        Frequently asked questions
      </h2>
      <div className="space-y-2">
        {FAQS.map((faq) => (
          <details
            key={faq.q}
            className="group rounded-lg border border-border bg-card transition-colors duration-200 hover:border-primary/40"
          >
            <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-4 py-3 text-sm font-medium [&::-webkit-details-marker]:hidden">
              {faq.q}
              <ChevronDown
                aria-hidden="true"
                className="size-4 shrink-0 text-muted-foreground transition-transform duration-200 group-open:rotate-180"
              />
            </summary>
            <p className="px-4 pb-4 text-sm leading-relaxed text-muted-foreground">
              {faq.a}
            </p>
          </details>
        ))}
      </div>
    </section>
  )
}

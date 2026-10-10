import { Link } from "react-router-dom"
import {
  ArrowRight,
  Bell,
  BookOpen,
  GraduationCap,
  HelpCircle,
} from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
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

/**
 * Public landing page — reachable by everyone, no sign-in.
 *
 * Splash hero, About, FAQ, and the school CMS feed (announcements the admin
 * posts plus resources), all in one scrollable page. The CMS sections read
 * the anonymous public endpoints; when Strapi is down they say the content
 * service is unavailable rather than pretending there is nothing to show.
 */
export function LandingPage() {
  return (
    <div className="min-h-svh bg-background">
      <header className="border-b border-border">
        <div className="mx-auto flex h-14 w-full max-w-5xl items-center justify-between px-4 lg:px-6">
          <span className="flex items-center gap-2 font-semibold">
            <GraduationCap aria-hidden="true" className="size-5" />
            AEGIS
          </span>
          <Button asChild size="sm">
            <Link to="/login">
              Sign in <ArrowRight aria-hidden="true" className="size-4" />
            </Link>
          </Button>
        </div>
      </header>

      <main className="mx-auto w-full max-w-5xl space-y-12 px-4 py-10 lg:px-6">
        <section aria-labelledby="landing-hero" className="text-center">
          <h1
            id="landing-hero"
            className="text-3xl font-bold tracking-tight sm:text-4xl"
          >
            Welcome to AEGIS
          </h1>
          <p className="mx-auto mt-3 max-w-2xl text-muted-foreground">
            The school&apos;s academic, attendance and guidance companion — for
            students, parents, faculty, counselors and administrators.
          </p>
          <div className="mt-5 flex flex-wrap items-center justify-center gap-2">
            <Button asChild>
              <Link to="/login">Open your dashboard</Link>
            </Button>
            <Button asChild variant="outline">
              <a href="#announcements">See announcements</a>
            </Button>
          </div>
        </section>

        <AboutSection />
        <AnnouncementsSection />
        <ResourcesSection />
        <FaqSection />
      </main>

      <footer className="border-t border-border">
        <div className="mx-auto flex w-full max-w-5xl flex-wrap items-center justify-between gap-2 px-4 py-4 text-xs text-muted-foreground lg:px-6">
          <span>AEGIS school information system</span>
          <Link to="/login" className="underline">
            Staff and student sign-in
          </Link>
        </div>
      </footer>
    </div>
  )
}

function AboutSection() {
  return (
    <section aria-labelledby="landing-about" className="space-y-3">
      <h2 id="landing-about" className="text-2xl font-semibold">
        About us
      </h2>
      <div className="grid gap-4 md:grid-cols-3">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Academics</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground">
              Grades encoded by faculty, finalized by administration, and
              visible to students and linked parents once finalized.
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Attendance</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground">
              Daily records taken by faculty, with per-section summaries for
              students, parents and administrators.
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Guidance</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground">
              Counseling sessions, intervention plans and wellness assessments
              handled by the guidance office.
            </p>
          </CardContent>
        </Card>
      </div>
    </section>
  )
}

function AnnouncementsSection() {
  const query = usePublicAnnouncements()
  const items = query.data ?? []

  return (
    <section
      id="announcements"
      aria-labelledby="landing-announcements"
      className="space-y-3"
    >
      <h2
        id="landing-announcements"
        className="flex items-center gap-2 text-2xl font-semibold"
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
            <p className="text-sm text-muted-foreground" role="alert">
              The content service is temporarily unavailable (
              {normalizeApiError(query.error).message}). Please try again later.
            </p>
          </CardContent>
        </Card>
      ) : items.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          No announcements have been published yet.
        </p>
      ) : (
        <ul className="grid gap-4 md:grid-cols-2">
          {items.map((item) => (
            <li key={item.document_id}>
              <Card>
                <CardHeader>
                  <CardTitle className="text-base">{item.title}</CardTitle>
                  <CardDescription>
                    {ANNOUNCEMENT_TYPE_LABELS[item.announcement_type] ??
                      item.announcement_type}
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-2">
                  <p className="text-sm whitespace-pre-line">{item.content}</p>
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
    <section aria-labelledby="landing-resources" className="space-y-3">
      <h2
        id="landing-resources"
        className="flex items-center gap-2 text-2xl font-semibold"
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
            <p className="text-sm text-muted-foreground" role="alert">
              The content service is temporarily unavailable (
              {normalizeApiError(query.error).message}). Please try again later.
            </p>
          </CardContent>
        </Card>
      ) : items.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          No resources have been published yet.
        </p>
      ) : (
        <ul className="space-y-2">
          {items.map((item) => (
            <li
              key={item.document_id}
              className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-border p-3"
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
    a: "Announcements and resources are published through the school content service. If it is down, this page says so instead of showing an empty list — try again later.",
  },
]

function FaqSection() {
  return (
    <section aria-labelledby="landing-faq" className="space-y-3">
      <h2
        id="landing-faq"
        className="flex items-center gap-2 text-2xl font-semibold"
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
            className="rounded-md border border-border px-3 py-2"
          >
            <summary className="cursor-pointer text-sm font-medium">
              {faq.q}
            </summary>
            <p className="pt-1 text-sm text-muted-foreground">{faq.a}</p>
          </details>
        ))}
      </div>
    </section>
  )
}

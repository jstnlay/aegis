import {
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  useSyncExternalStore,
} from "react"
import { Link } from "react-router-dom"
import {
  ArrowUpRight,
  BookOpen,
  CalendarCheck,
  ChevronDown,
  CircleHelp,
  FileText,
  Globe,
  HandHeart,
  Mail,
  MapPin,
  Megaphone,
  MessageCircle,
  Phone,
  RotateCw,
  School,
  Target,
  type LucideIcon,
} from "lucide-react"

import { PublicFooter } from "@/components/brand/PublicFooter"
import { FeaturedAnnouncement } from "@/components/brand/FeaturedAnnouncement"
import { HomepageBackground } from "@/components/brand/HomepageBackground"
import { PublicNav } from "@/components/brand/PublicNav"
import { SchoolHeader } from "@/components/brand/SchoolHeader"
import { Reveal } from "@/components/layout/Reveal"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import {
  ANNOUNCEMENT_TYPE_LABELS,
  RESOURCE_TYPE_LABELS,
} from "@/features/admin/api"
import {
  usePublicAnnouncements,
  usePublicResources,
} from "@/features/cms/public-api"
import {
  CONTACT,
  MISSION_TEXT,
  SCHOOL_CAMPUS_LINE,
  SCHOOL_NAME,
  VISION_TEXT,
} from "@/lib/school-content"
import { cn } from "@/lib/utils"
import "./landing-page.css"

/** Hero entrance runs on the first landing visit of a session, not every one. */
const HERO_SEEN_KEY = "aegis:hero-entrance-seen"

const SECTION_TITLE = "landing-section-title"

const [MISSION_INTRO, ...MISSION_POINTS] = MISSION_TEXT.split("\n")
const [CONTACT_EMAIL_NAME, CONTACT_EMAIL_DOMAIN] = CONTACT.email.split("@")
const CONTACT_FACEBOOK_PAGE = new URL(CONTACT.facebookUrl)

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

function subscribeToMissionScroll(callback: () => void) {
  window.addEventListener("scroll", callback, { passive: true })
  return () => window.removeEventListener("scroll", callback)
}

function isMissionTitleEmphasized() {
  return window.scrollY > 0
}

function getMissionTitleServerSnapshot() {
  return false
}

function MissionVisionTitle() {
  const emphasized = useSyncExternalStore(
    subscribeToMissionScroll,
    isMissionTitleEmphasized,
    getMissionTitleServerSnapshot
  )

  return (
    <h2
      id="landing-mission-vision"
      className={`${SECTION_TITLE} landing-section-title--centered landing-mission-title`}
      data-emphasized={emphasized}
    >
      Mission &amp; Vision
    </h2>
  )
}

/** Public school homepage; CMS feeds continue to use the anonymous API. */
export function LandingPage() {
  const animateHero = useHeroEntrance()
  return (
    <div className="school-homepage min-h-svh">
      <HomepageBackground />
      <SchoolHeader>
        <PublicNav />
        <Button asChild size="sm" className="landing-sign-in">
          <Link to="/login">Sign in</Link>
        </Button>
      </SchoolHeader>
      <main className="landing-main">
        <section aria-labelledby="landing-hero" className="landing-hero">
          <div className="landing-hero__media">
            <img
              src="/front%20bg.png"
              alt="Entrance gate of His Care Christian Institute"
              className="landing-hero__photo"
              decoding="async"
            />
            <div className="landing-hero__blend" aria-hidden="true" />
          </div>
          <div
            className={cn(
              "landing-hero__copy",
              animateHero &&
                "motion-safe:animate-in motion-safe:fade-in motion-safe:slide-in-from-bottom-4 motion-safe:fill-mode-both motion-safe:duration-700"
            )}
          >
            <h1 id="landing-hero">
              <span className="block">{SCHOOL_NAME.slice(0, 8)}</span>{" "}
              <span className="block">{SCHOOL_NAME.slice(9)}</span>
            </h1>
            <p className="landing-hero__campus">{SCHOOL_CAMPUS_LINE}</p>
            <p className="landing-hero__intro">
              <strong>His Care Christian Institute</strong> was founded in{" "}
              <strong>April 2007</strong> by Leila D. Paragoso and Clemente T.
              Paragoso. From a small preschool, it has grown into a school
              serving students from Nursery to Grade 12 (Senior High School) in
              Batangas.
            </p>
            <Button asChild size="sm" className="landing-hero__read-more">
              <Link to="/school">Read more</Link>
            </Button>
          </div>
        </section>
        <div className="landing-feeds">
          <AnnouncementsSection />
        </div>
        <section
          aria-labelledby="landing-mission-vision"
          className="landing-section"
        >
          <MissionVisionTitle />
          <Reveal>
            <div className="landing-beliefs">
              <article
                className="landing-belief"
                aria-labelledby="landing-mission"
              >
                <div className="landing-card-heading">
                  <IconCircle icon={BookOpen} />
                  <h3 id="landing-mission">Mission</h3>
                </div>
                <h4 className="landing-mission-intro">{MISSION_INTRO}</h4>
                <ol className="landing-mission-points">
                  {MISSION_POINTS.map((point, index) => (
                    <li key={point}>
                      <span
                        className="landing-mission-number"
                        aria-hidden="true"
                      >
                        {index + 1}
                      </span>
                      <p>{point.replace(/^\d+\.\s*/, "")}</p>
                    </li>
                  ))}
                </ol>
              </article>
              <article
                className="landing-belief landing-vision"
                aria-labelledby="landing-vision"
              >
                <div className="landing-card-heading">
                  <IconCircle icon={Target} />
                  <h3 id="landing-vision">Vision</h3>
                </div>
                <p className="landing-vision-copy">{VISION_TEXT}</p>
                <div className="landing-vision-lines" aria-hidden="true">
                  <span />
                  <span />
                  <span />
                </div>
              </article>
            </div>
          </Reveal>
        </section>
        <Reveal>
          <PortalHighlights />
        </Reveal>
        <div className="landing-feeds">
          <ResourcesSection />
        </div>
        <Reveal>
          <FaqSection />
        </Reveal>
        <Reveal className="landing-contact-reveal">
          <section
            id="contact"
            aria-labelledby="landing-contact"
            className="landing-section landing-contact"
          >
            <div className="landing-card landing-contact-panel landing-glass">
              <div className="landing-contact-heading">
                <h2
                  id="landing-contact"
                  className={`${SECTION_TITLE} landing-contact-title`}
                >
                  <Phone
                    aria-hidden="true"
                    className="size-5 shrink-0"
                    strokeWidth={1.7}
                  />
                  Contact
                </h2>
                <p className="landing-contact-intro">
                  Visit our campus, call, email, or connect with us on social
                  media for school inquiries.
                </p>
              </div>
              <div className="landing-contact-campus">
                <div className="landing-contact-row">
                  <IconCircle icon={MapPin} />
                  <div>
                    <h3>Address</h3>
                    <p>{CONTACT.address}</p>
                    <div className="landing-contact-school-id">
                      <School aria-hidden="true" className="size-4" />
                      <span>School ID</span>
                      <strong>{CONTACT.schoolId}</strong>
                    </div>
                  </div>
                </div>
              </div>
              <div className="landing-contact-channels">
                <div className="landing-contact-row">
                  <IconCircle icon={Phone} />
                  <div>
                    <h3>Phone</h3>
                    <a
                      href={`tel:${CONTACT.phone.replace(/\s/g, "")}`}
                      className="landing-contact-number"
                    >
                      {CONTACT.phone}
                    </a>
                  </div>
                </div>
                <a
                  href={`mailto:${CONTACT.email}`}
                  aria-label={CONTACT.email}
                  className="landing-contact-channel"
                >
                  <IconCircle icon={Mail} />
                  <div className="landing-contact-channel-copy">
                    <h3>Email Address</h3>
                    <p>
                      {CONTACT_EMAIL_NAME}@<wbr />
                      {CONTACT_EMAIL_DOMAIN}
                    </p>
                  </div>
                  <ArrowUpRight
                    aria-hidden="true"
                    className="landing-contact-link-arrow size-5"
                  />
                </a>
              </div>
              <div className="landing-contact-channels">
                <div className="landing-contact-channel">
                  <IconCircle icon={MessageCircle} />
                  <div className="landing-contact-channel-copy">
                    <h3>Messenger</h3>
                    <p>{CONTACT.messengerName}</p>
                  </div>
                </div>
                <a
                  href={CONTACT.facebookUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  aria-label="Facebook"
                  className="landing-contact-channel"
                >
                  <IconCircle icon={Globe} />
                  <div className="landing-contact-channel-copy">
                    <h3>Facebook</h3>
                    <p>
                      {CONTACT_FACEBOOK_PAGE.hostname.replace(/^www\./, "")}/
                      <wbr />
                      {CONTACT_FACEBOOK_PAGE.pathname.replace(/^\//, "")}
                    </p>
                  </div>
                  <ArrowUpRight
                    aria-hidden="true"
                    className="landing-contact-link-arrow size-5"
                  />
                </a>
              </div>
            </div>
          </section>
        </Reveal>
      </main>
      <PublicFooter />
    </div>
  )
}

function IconCircle({ icon: Icon }: { icon: LucideIcon }) {
  return (
    <span className="landing-icon">
      <Icon aria-hidden="true" strokeWidth={1.7} />
    </span>
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
    icon: HandHeart,
    title: "Guidance",
    body: "Counseling sessions, intervention plans and wellness assessments handled by the guidance office.",
  },
] as const

function PortalHighlights() {
  return (
    <section
      aria-labelledby="landing-portal"
      className="landing-section landing-offers"
    >
      <h2 id="landing-portal" className={SECTION_TITLE}>
        What AEGIS Offers
      </h2>
      <div className="landing-features">
        {PORTAL_HIGHLIGHTS.map(({ icon: Icon, title, body }, index) => (
          <article
            key={title}
            className={cn(
              "landing-feature",
              index % 2 === 0 && "landing-glass"
            )}
          >
            <span className="landing-feature-art" aria-hidden="true">
              <Icon strokeWidth={1.3} />
            </span>
            <span className="landing-feature-number" aria-hidden="true">
              {index + 1}
            </span>
            <h3>{title}</h3>
            <p>{body}</p>
          </article>
        ))}
      </div>
    </section>
  )
}

const ANNOUNCEMENT_TYPE_BADGE = {
  alert: "destructive",
  academic: "default",
  event: "secondary",
  news: "outline",
} as const

function FeedState({
  message,
  retry,
  fetching,
  variant = "default",
}: {
  message: string
  retry?: () => void
  fetching?: boolean
  variant?: "default" | "outline"
}) {
  return (
    <div className="landing-feed-state" role={retry ? "alert" : "status"}>
      <div className="landing-feed-art" aria-hidden="true">
        <span className="landing-feed-paper">
          <span />
          <span />
          <span />
          <span />
        </span>
      </div>
      <div className="landing-feed-message">
        <p className="font-medium text-foreground">{message}</p>
        <p className="text-muted-foreground">
          {retry
            ? "Please try again later."
            : "Check back for new school updates."}
        </p>
        {retry ? (
          <Button onClick={retry} disabled={fetching} variant={variant}>
            {fetching ? "Retrying…" : "Retry"}
            <RotateCw
              aria-hidden="true"
              className={cn("size-4", fetching && "motion-safe:animate-spin")}
            />
          </Button>
        ) : null}
      </div>
    </div>
  )
}

function FeedLoading({ label }: { label: string }) {
  return (
    <div className="landing-feed-loading" role="status" aria-label={label}>
      <Skeleton className="mx-auto h-4 w-3/4" />
      <Skeleton className="mx-auto h-4 w-1/2" />
      <span className="sr-only">{label}</span>
    </div>
  )
}

function AnnouncementsSection() {
  const query = usePublicAnnouncements()
  const items = query.data ?? []
  return (
    <section
      id="announcements"
      aria-labelledby="landing-announcements"
      className="landing-section landing-card landing-feed-panel landing-feed-announcements"
    >
      <div className="landing-feed-heading">
        <span className="landing-announcement-signal" aria-hidden="true">
          <Megaphone strokeWidth={1.6} />
        </span>
        <h2 id="landing-announcements" className="landing-feed-title">
          Announcements
        </h2>
      </div>
      <FeaturedAnnouncement />
      <div className="landing-announcement-updates">
        {query.isLoading ? (
          <FeedLoading label="Loading announcements" />
        ) : items.length > 0 ? (
          <ul className="landing-feed-list">
            {items.map((item) => (
              <li key={item.document_id} className="landing-feed-item">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <h3>{item.title}</h3>
                  <Badge
                    variant={ANNOUNCEMENT_TYPE_BADGE[item.announcement_type]}
                  >
                    {ANNOUNCEMENT_TYPE_LABELS[item.announcement_type] ??
                      item.announcement_type}
                  </Badge>
                </div>
                <p className="whitespace-pre-line">{item.content}</p>
                <p className="text-xs text-muted-foreground">
                  Published{" "}
                  <time dateTime={item.published_at}>
                    {new Date(item.published_at).toLocaleDateString()}
                  </time>
                </p>
              </li>
            ))}
          </ul>
        ) : (
          <p className="landing-announcement-end" role="status">
            That&apos;s all for now. Check back for more school announcements.
          </p>
        )}
      </div>
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
      className="landing-section landing-card landing-feed-panel landing-feed-resources"
    >
      <div className="landing-feed-heading">
        <IconCircle icon={FileText} />
        <h2 id="landing-resources" className="landing-feed-title">
          Resources
        </h2>
      </div>
      {query.isLoading ? (
        <FeedLoading label="Loading resources" />
      ) : query.isError ? (
        <FeedState
          variant="outline"
          message="Resources are temporarily unavailable."
          retry={() => {
            void query.refetch()
          }}
          fetching={query.isFetching}
        />
      ) : items.length === 0 ? (
        <FeedState message="No resources have been published yet." />
      ) : (
        <ul className="landing-feed-list">
          {items.map((item) => (
            <li key={item.document_id} className="landing-feed-item">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <h3>{item.title}</h3>
                <Badge variant="secondary">
                  {RESOURCE_TYPE_LABELS[item.resource_type] ??
                    item.resource_type}
                </Badge>
              </div>
              {item.description ? <p>{item.description}</p> : null}
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
  const [open, setOpen] = useState<number | null>(null)
  const listRef = useRef<HTMLDivElement>(null)

  useLayoutEffect(() => {
    const list = listRef.current
    const stage = list?.parentElement
    if (!list || !stage) return

    const rows = Array.from(
      list.querySelectorAll<HTMLElement>(".landing-faq-item")
    )
    const headings = Array.from(list.querySelectorAll<HTMLElement>("h3"))
    const answers = Array.from(
      list.querySelectorAll<HTMLElement>(".landing-faq-answer p")
    )

    // Reserve the tallest single answer, even while every answer is collapsed.
    const reserveAnswerSpace = () => {
      const questionHeight = headings.reduce(
        (height, heading) => height + heading.getBoundingClientRect().height,
        0
      )
      const dividerHeight = rows.reduce(
        (height, row) =>
          height + (parseFloat(getComputedStyle(row).borderTopWidth) || 0),
        0
      )
      const listStyle = getComputedStyle(list)
      const borderHeight =
        (parseFloat(listStyle.borderTopWidth) || 0) +
        (parseFloat(listStyle.borderBottomWidth) || 0)
      const answerHeight = Math.max(
        0,
        ...answers.map((answer) => answer.getBoundingClientRect().height)
      )
      stage.style.setProperty(
        "--landing-faq-reserved-height",
        `${Math.ceil(questionHeight + dividerHeight + borderHeight + answerHeight)}px`
      )
    }

    reserveAnswerSpace()
    const observer =
      typeof ResizeObserver !== "undefined"
        ? new ResizeObserver(reserveAnswerSpace)
        : null
    for (const element of [...headings, ...answers]) observer?.observe(element)
    window.addEventListener("resize", reserveAnswerSpace)

    return () => {
      observer?.disconnect()
      window.removeEventListener("resize", reserveAnswerSpace)
    }
  }, [])

  return (
    <section
      id="faq"
      aria-labelledby="landing-faq"
      className="landing-section landing-faq"
    >
      <div className="landing-faq-layout">
        <div className="landing-faq-intro">
          <div className="landing-faq-heading">
            <IconCircle icon={CircleHelp} />
            <h2 id="landing-faq">Frequently asked questions</h2>
          </div>
          <p>
            Find answers about signing in, grades, counseling, and school
            updates.
          </p>
          <Button asChild size="sm">
            <a href="#contact">
              Contact the school
              <ArrowUpRight aria-hidden="true" className="size-4" />
            </a>
          </Button>
        </div>
        <div className="landing-faq-stage">
          <div ref={listRef} className="landing-faq-list landing-glass">
            {FAQS.map((faq, index) => (
              <div
                key={faq.q}
                className="landing-faq-item"
                data-open={open === index}
              >
                <h3>
                  <button
                    type="button"
                    id={`landing-question-${index}`}
                    aria-expanded={open === index}
                    aria-controls={`landing-answer-${index}`}
                    onClick={() => setOpen(open === index ? null : index)}
                  >
                    <span className="landing-faq-number" aria-hidden="true">
                      {String(index + 1).padStart(2, "0")}
                    </span>
                    <span className="landing-faq-question">{faq.q}</span>
                    <ChevronDown
                      aria-hidden="true"
                      className="size-5 shrink-0"
                    />
                  </button>
                </h3>
                <div
                  id={`landing-answer-${index}`}
                  role="region"
                  aria-labelledby={`landing-question-${index}`}
                  aria-hidden={open !== index}
                  inert={open !== index}
                  className="landing-faq-answer"
                >
                  <div>
                    <p>{faq.a}</p>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  )
}

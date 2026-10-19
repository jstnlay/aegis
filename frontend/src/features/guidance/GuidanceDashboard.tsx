import { ClipboardList } from "lucide-react"
import { Link } from "react-router-dom"

import { NewCasesTrendChart } from "@/components/charts/NewCasesTrend"
import { RiskLevelBars } from "@/components/charts/RiskLevelBars"
import { RiskStatusDonut } from "@/components/charts/RiskStatusDonut"
import { ErrorNote, PendingRegion } from "@/components/feedback/Feedback"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { MetricCard } from "@/components/ui/metric-card"
import { Skeleton } from "@/components/ui/skeleton"
import { useAuth } from "@/features/auth/AuthContext"
import {
  CONSULTATION_PRIORITY_LABELS,
  CONSULTATION_SESSION_TYPE_LABELS,
  riskFactorLabel,
  useConsultations,
  useGuidanceStats,
  useRiskAlerts,
  type Consultation,
  type RiskAlert,
} from "@/features/guidance/api"
import { formatCount, formatPercent } from "@/lib/metric-format"
import { hasRecentCaseHistory } from "@/lib/guidance-analytics"
import {
  consultationStatusBadgeClass,
  riskLevelBadgeClass,
} from "@/lib/status-badge"

/**
 * Guidance Center — the role's landing page, rebuilt to the Dashboard
 * reference's information architecture.
 *
 * What changed and why, beyond the visual restyle:
 *
 * - The four metric tiles come from one aggregate (`useGuidanceStats`), so they
 *   can never disagree. Their states are kept apart by the shared `MetricCard`:
 *   in flight, failed, and resolved are three different stories and rendering
 *   any of them as "N/A" would report a measurement that was never made.
 * - The risk-level bars, the status donut and the monthly trend are all
 *   *derived* from alerts the page already holds. Nothing fetches for them and
 *   nothing is extrapolated: an unparseable `created_at` is skipped rather than
 *   counted as a zero month, and the trend omits itself when the data cannot
 *   support six months. Colour is never the only signal — every figure is also
 *   text.
 * - The follow-up list is a real section now. `next_session_date` was fetched
 *   and thrown away; a counselor's next action is the most useful thing the
 *   page can surface first.
 */

/** Most recent alerts first, so the card is a live feed rather than API order. */
function byGeneratedAtDesc(a: RiskAlert, b: RiskAlert): number {
  return b.generated_at.localeCompare(a.generated_at)
}

/** Soonest follow-up first — the order a counselor acts in. */
function byNextSessionAsc(a: Consultation, b: Consultation): number {
  return (a.next_session_date ?? "").localeCompare(b.next_session_date ?? "")
}

/** Newest consultation first, so the feed is chronological. */
function bySessionDateDesc(a: Consultation, b: Consultation): number {
  return b.session_date.localeCompare(a.session_date)
}

const MAX_LIST_ROWS = 5

/** Today, as the reference's date card reads it. */
function formatToday(): string {
  return new Date().toLocaleDateString(undefined, {
    month: "long",
    day: "numeric",
    year: "numeric",
  })
}

/** First name for the greeting, when the account carries one. */
function greetingName(user: { first_name?: string | null } | null): string {
  const first = user?.first_name?.trim()
  return first ? first : "there"
}

/** Two-letter initials for the reference's round consultation avatars. */
function initialsOf(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? "")
    .join("")
}

/**
 * Human labels for the backend's enum values.
 *
 * The API speaks `individual_counseling` and `follow_up`; the dashboard speaks
 * "Individual counseling" and "Follow-up". The maps already exist for session
 * type and priority, so only the two statuses need spelling out — and the
 * hyphen in "Follow-up" is deliberate, matching the reference.
 */
function consultationStatusLabel(status: Consultation["status"]): string {
  if (status === "follow_up") return "Follow-up"
  return status === "ongoing" ? "Ongoing" : "Completed"
}

/** "Active" rather than "active": a status reads as a name, not a value. */
function alertStatusLabel(status: RiskAlert["status"]): string {
  const words = status.replace(/_/g, " ")
  return words.charAt(0).toUpperCase() + words.slice(1)
}

/** "2026-10-03" → "Oct 3, 2026". Falls back to the raw value when unparseable. */
function formatSessionDate(value: string): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(value)
  if (!match) return value
  const date = new Date(
    Number(match[1]),
    Number(match[2]) - 1,
    Number(match[3])
  )
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
  })
}

/** "14:30:00" → "2:30 PM". Falls back to the raw value when unparseable. */
function formatSessionTime(value: string): string {
  const match = /^(\d{1,2}):(\d{2})/.exec(value)
  if (!match) return value
  const hours = Number(match[1])
  const minutes = match[2]
  if (hours > 23) return value
  const period = hours >= 12 ? "PM" : "AM"
  const twelve = hours % 12 === 0 ? 12 : hours % 12
  return `${twelve}:${minutes} ${period}`
}

/** Shared header treatment: title left, "View All" link right. */
function PanelHeader({
  title,
  to,
}: {
  title: string
  /** Route for the "View All" link, omitted when there is no full page yet. */
  to?: string
}) {
  return (
    <div className="flex items-center justify-between gap-2">
      <CardTitle>{title}</CardTitle>
      {to ? (
        <Link
          to={to}
          className="text-xs font-medium text-primary hover:underline"
        >
          View All
        </Link>
      ) : null}
    </div>
  )
}

export function GuidanceDashboard() {
  const { user } = useAuth()

  /*
   * One aggregate feeds all four tiles, so "Active Cases" and "At-Risk
   * Students" are derived from the same open-alert set by the same rule and
   * cannot contradict each other.
   */
  const statsQuery = useGuidanceStats()
  const riskAlertsQuery = useRiskAlerts()
  const consultationsQuery = useConsultations()

  const stats = statsQuery.data
  const alerts = (riskAlertsQuery.data ?? []).slice().sort(byGeneratedAtDesc)
  const consultations = consultationsQuery.data ?? []

  const recentAlerts = alerts.slice(0, MAX_LIST_ROWS)
  // The banner counts what is still live: resolved cases are history, and
  // folding them into "open alerts" would overstate the workload.
  const openAlerts = alerts.filter((alert) => alert.status !== "resolved")

  /*
   * A follow-up is a consultation with a next session still ahead of it.
   * Completed ones are excluded — a past date on a closed case is history, not
   * an appointment.
   */
  const upcomingFollowUps = consultations
    .filter(
      (consultation) =>
        consultation.next_session_date && consultation.status !== "completed"
    )
    .sort(byNextSessionAsc)
    .slice(0, MAX_LIST_ROWS)

  const recentConsultations = consultations
    .slice()
    .sort(bySessionDateDesc)
    .slice(0, MAX_LIST_ROWS)

  if (!user) return null

  return (
    <div className="space-y-6">
      {/* ---------------------------------------------------------------- */}
      {/* Welcome banner                                                   */}
      {/* ---------------------------------------------------------------- */}
      {/*
        Transparent on purpose: the shell already paints the school banner photo
        behind every page's title block, and this text sits on it the way the
        reference shows it — dark ink on the washed-out photo, not a second
        maroon banner under the first photo. A previous version was a solid
        `bg-primary` band here, which fought the shell photo for the same strip.
      */}
      <section
        aria-label="Guidance overview"
        className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between"
      >
        <div>
          <h2 className="text-2xl font-bold text-foreground">
            Guidance Center
          </h2>
          <p className="mt-1 max-w-prose text-sm text-muted-foreground">
            Welcome back, {greetingName(user)}! Here&apos;s an overview of the
            student support activities today.
          </p>
        </div>
        <div className="flex items-center gap-3 rounded-lg border border-border bg-card/80 px-4 py-3 shadow-sm backdrop-blur-sm">
          <ClipboardList aria-hidden="true" className="size-6 text-primary" />
          <div>
            <p className="text-sm font-semibold">{formatToday()}</p>
            <p className="text-xs text-muted-foreground">
              {formatCount(openAlerts.length)} open alert
              {openAlerts.length === 1 ? "" : "s"} on file
            </p>
          </div>
        </div>
      </section>

      {/*
        PH11.11: one note for the metric row. All four figures come from a single
        `/guidance/stats/` request, so its failure is one event, and four
        identical alerts would interrupt a screen reader four times.
      */}
      {statsQuery.isError ? (
        <ErrorNote message="Unable to load the guidance statistics. Please try again." />
      ) : null}

      {/*
        One note per failed request, never one per card that wanted the data.
        Four cards read the alerts list and two read consultations; announcing
        the same failure in each would interrupt a screen reader six times for
        one event, which is why the cards below say "unavailable" in place
        instead of repeating the alert.
      */}
      {riskAlertsQuery.isError ? (
        <ErrorNote message="Unable to load risk alerts. Please try again." />
      ) : null}
      {consultationsQuery.isError ? (
        <ErrorNote message="Unable to load consultations. Please try again." />
      ) : null}

      {/* ---------------------------------------------------------------- */}
      {/* Metric tiles                                                     */}
      {/* ---------------------------------------------------------------- */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <MetricCard
          centered
          title="Active Cases"
          hint="Open risk alerts (not yet resolved)"
          isLoading={statsQuery.isLoading}
          isError={statsQuery.isError}
        >
          {formatCount(stats?.active_cases)}
        </MetricCard>

        <MetricCard
          centered
          title="At-Risk Students"
          hint="Distinct students with an open moderate/high alert"
          isLoading={statsQuery.isLoading}
          isError={statsQuery.isError}
        >
          {formatCount(stats?.at_risk_students)}
        </MetricCard>

        <MetricCard
          centered
          title="Pending Follow-up"
          hint="Your ongoing and follow-up consultations"
          isLoading={statsQuery.isLoading}
          isError={statsQuery.isError}
        >
          {formatCount(stats?.pending_follow_up)}
        </MetricCard>

        {/*
          PH11.16: this is the only tile of the four that can legitimately be
          unmeasurable — 0 of 0 results is an undefined rate, not 0%. Its hint
          therefore names that state instead of leaving a bare "N/A" beside a
          sentence that never explains it.
        */}
        <MetricCard
          centered
          title="Assessment Completion"
          hint={
            statsQuery.isError
              ? "Could not load assessment results"
              : stats?.assessment_completion_rate == null
                ? "No assessment results yet"
                : "Completed vs started assessments"
          }
          isLoading={statsQuery.isLoading}
          isError={statsQuery.isError}
        >
          {formatPercent(stats?.assessment_completion_rate, 0)}
        </MetricCard>
      </div>

      {/* ---------------------------------------------------------------- */}
      {/* Analytics                                                        */}
      {/* ---------------------------------------------------------------- */}
      {/*
        Every chart together, directly under the figures they explain. The bars
        used to live inside the Risk Alerts card while the donut and the trend
        sat at the bottom of the page, which scattered the one glance a
        counselor needs across three places.
      */}
      <section aria-labelledby="guidance-analytics" className="space-y-4">
        <h3
          id="guidance-analytics"
          className="text-lg font-semibold tracking-tight"
        >
          Analytics
        </h3>
        <Card>
          <CardHeader>
            <PanelHeader title="Risk Level Distribution" />
          </CardHeader>
          <CardContent>
            {riskAlertsQuery.isLoading ? (
              <PendingRegion label="Risk level distribution">
                <Skeleton className="h-32 w-full" />
              </PendingRegion>
            ) : riskAlertsQuery.isError ? (
              <p className="text-sm text-muted-foreground">
                Risk levels are unavailable.
              </p>
            ) : alerts.length === 0 ? (
              <p className="text-sm text-muted-foreground">No risk alerts</p>
            ) : (
              <RiskLevelBars alerts={alerts} />
            )}
          </CardContent>
        </Card>
        <div className="grid gap-4 lg:grid-cols-2">
          <Card>
            <CardHeader>
              <PanelHeader title="Case Status Overview" />
            </CardHeader>
            <CardContent>
              {riskAlertsQuery.isLoading ? (
                <PendingRegion label="Case status overview">
                  <Skeleton className="h-32 w-full" />
                </PendingRegion>
              ) : riskAlertsQuery.isError ? (
                <p className="text-sm text-muted-foreground">
                  Case status is unavailable.
                </p>
              ) : (
                <RiskStatusDonut alerts={alerts} />
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <div className="flex items-center justify-between gap-2">
                <CardTitle>Monthly Trend</CardTitle>
                <span className="text-xs text-muted-foreground">
                  Last 6 Months
                </span>
              </div>
            </CardHeader>
            <CardContent>
              {riskAlertsQuery.isLoading ? (
                <PendingRegion label="Monthly trend">
                  <Skeleton className="h-32 w-full" />
                </PendingRegion>
              ) : riskAlertsQuery.isError ? (
                <p className="text-sm text-muted-foreground">
                  The trend is unavailable.
                </p>
              ) : hasRecentCaseHistory(alerts) ? (
                <NewCasesTrendChart alerts={alerts} />
              ) : (
                <p className="text-sm text-muted-foreground">
                  No new cases recorded in the last six months.
                </p>
              )}
            </CardContent>
          </Card>
        </div>
      </section>

      {/* ---------------------------------------------------------------- */}
      {/* Risk alerts + recent consultations                               */}
      {/* ---------------------------------------------------------------- */}
      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <PanelHeader title="Risk Alerts" to="/app/guidance/risk-alerts" />
          </CardHeader>
          <CardContent className="space-y-4">
            {riskAlertsQuery.isLoading ? (
              <PendingRegion label="Risk alerts">
                <Skeleton className="h-32 w-full" />
              </PendingRegion>
            ) : riskAlertsQuery.isError ? (
              <p className="text-sm text-muted-foreground">
                Risk alerts are unavailable.
              </p>
            ) : alerts.length === 0 ? (
              <p className="text-sm text-muted-foreground">No risk alerts</p>
            ) : (
              <ul className="space-y-2">
                {recentAlerts.map((alert) => (
                  <li
                    key={alert.id}
                    className="rounded-md border border-border p-3"
                    data-risk={alert.risk_level}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0">
                        <p className="truncate text-sm font-medium">
                          {alert.student_name}
                        </p>
                        {/*
                          `RiskAlertSerializer` exposes no student ID code, so no
                          code is rendered here — the UUID is deliberately not
                          shown as a substitute. The student profile page is the
                          place a human-facing code is available.
                        */}
                        <p className="truncate text-xs text-muted-foreground">
                          {alertStatusLabel(alert.status)}
                        </p>
                      </div>
                      <Badge
                        variant="secondary"
                        className={`shrink-0 ${riskLevelBadgeClass(alert.risk_level)}`}
                        data-risk-level={alert.risk_level}
                      >
                        {alert.risk_level.toUpperCase()}
                      </Badge>
                    </div>
                    {alert.risk_factors.length > 0 && (
                      <p className="mt-1.5 text-xs text-muted-foreground">
                        {alert.risk_factors
                          .slice(0, 2)
                          .map(riskFactorLabel)
                          .filter(Boolean)
                          .join(", ")}
                        {alert.risk_factors.length > 2 && " …"}
                      </p>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <PanelHeader
              title="Recent Consultations"
              to="/app/guidance/consultations"
            />
          </CardHeader>
          <CardContent>
            {consultationsQuery.isLoading ? (
              <PendingRegion label="Recent consultations">
                <Skeleton className="h-32 w-full" />
              </PendingRegion>
            ) : consultationsQuery.isError ? (
              <p className="text-sm text-muted-foreground">
                Consultations are unavailable.
              </p>
            ) : recentConsultations.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                No consultations recorded yet.
              </p>
            ) : (
              <ul className="space-y-2">
                {recentConsultations.map((consultation) => (
                  <li
                    key={consultation.id}
                    className="flex flex-wrap items-start justify-between gap-2 rounded-md border border-border p-3"
                  >
                    <div className="flex min-w-0 items-center gap-3">
                      <span
                        aria-hidden="true"
                        className="flex size-9 shrink-0 items-center justify-center rounded-full bg-muted text-xs font-semibold text-muted-foreground"
                      >
                        {initialsOf(consultation.student_name) || "—"}
                      </span>
                      <div className="min-w-0">
                        <p className="truncate text-sm font-medium">
                          {consultation.student_name}
                        </p>
                        <p className="truncate text-xs text-muted-foreground">
                          {
                            CONSULTATION_SESSION_TYPE_LABELS[
                              consultation.session_type
                            ]
                          }{" "}
                          · {formatSessionDate(consultation.session_date)} ·{" "}
                          {formatSessionTime(consultation.session_time)}
                        </p>
                      </div>
                    </div>
                    <div className="flex shrink-0 flex-col items-end gap-1">
                      <Badge
                        variant="secondary"
                        className={consultationStatusBadgeClass(
                          consultation.status
                        )}
                        data-consultation-status={consultation.status}
                      >
                        {consultationStatusLabel(consultation.status)}
                      </Badge>
                      <span className="text-xs text-muted-foreground">
                        {
                          CONSULTATION_PRIORITY_LABELS[
                            consultation.priority_level
                          ]
                        }{" "}
                        priority
                      </span>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
      </div>

      {/* ---------------------------------------------------------------- */}
      {/* Upcoming follow-ups                                              */}
      {/* ---------------------------------------------------------------- */}
      <Card>
        <CardHeader>
          <PanelHeader
            title="Upcoming Follow-ups"
            to="/app/guidance/consultations"
          />
        </CardHeader>
        <CardContent>
          {consultationsQuery.isLoading ? (
            <PendingRegion label="Upcoming follow-ups">
              <Skeleton className="h-24 w-full" />
            </PendingRegion>
          ) : consultationsQuery.isError ? (
            <p className="text-sm text-muted-foreground">
              Consultations are unavailable.
            </p>
          ) : upcomingFollowUps.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              No follow-ups scheduled.
            </p>
          ) : (
            <ul className="space-y-2">
              {upcomingFollowUps.map((consultation) => (
                <li
                  key={consultation.id}
                  className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-border p-3"
                >
                  <div className="flex min-w-0 items-center gap-3">
                    <span
                      aria-hidden="true"
                      className="flex size-9 shrink-0 items-center justify-center rounded-full bg-primary/10 text-xs font-semibold text-primary"
                    >
                      {initialsOf(consultation.student_name) || "—"}
                    </span>
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium">
                        {consultation.student_name}
                      </p>
                      <p className="truncate text-xs text-muted-foreground">
                        {formatSessionDate(
                          consultation.next_session_date ?? ""
                        )}
                      </p>
                    </div>
                  </div>
                  <Badge
                    variant="secondary"
                    className={consultationStatusBadgeClass(
                      consultation.status
                    )}
                  >
                    {consultationStatusLabel(consultation.status)}
                  </Badge>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  )
}

import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import {
  ErrorNote,
  PendingMetric,
  PendingRegion,
  UnavailableMetric,
} from "@/components/feedback/Feedback"
import { Skeleton } from "@/components/ui/skeleton"
import { useAuth } from "@/features/auth/AuthContext"
import {
  riskFactorLabel,
  useConsultations,
  useGuidanceStats,
  useRiskAlerts,
  type RiskAlert,
} from "@/features/guidance/api"
import { formatCount, formatPercent } from "@/lib/metric-format"
import {
  consultationStatusBadgeClass,
  riskLevelBadgeClass,
} from "@/lib/status-badge"

/** Most recent alerts first, so the card is a live feed rather than API order. */
function byGeneratedAtDesc(a: RiskAlert, b: RiskAlert): number {
  return b.generated_at.localeCompare(a.generated_at)
}

const MAX_ALERT_CARDS = 5

/**
 * One headline figure, with its three states kept distinct.
 *
 * PH11.11. All four tiles read the same `/guidance/stats/` response, so they were
 * three lines of identical markup each — and had drifted in the same way: the
 * placeholder was keyed off `isFetching`, which stays true through a background
 * refetch, so refreshing the page replaced four real counts with grey bars; and
 * no tile had a failure state, so a failed request rendered
 * `formatCount(undefined)` → "N/A", claiming the backend reported no figure
 * rather than that the figure is unknown.
 *
 * `isLoading` is `isPending && isFetching` in react-query v5, so it is true only
 * before the first result and a refetch leaves the figures already on screen
 * alone.
 */
function MetricCard({
  title,
  hint,
  isLoading,
  isError,
  children,
}: {
  title: string
  hint: string
  isLoading: boolean
  isError: boolean
  /** The formatted figure. Rendered only once the request has resolved. */
  children: React.ReactNode
}) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-sm font-medium">{title}</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="text-2xl font-bold">
          {isLoading ? (
            <PendingMetric label={title} />
          ) : isError ? (
            <UnavailableMetric />
          ) : (
            children
          )}
        </div>
        <p className="text-xs text-muted-foreground mt-1">{hint}</p>
      </CardContent>
    </Card>
  )
}

function GuidanceDashboard() {
  const { user } = useAuth()

  // One aggregate feeds all four cards, so they can never disagree:
  // in particular "Active Cases" and "At-Risk Students" are derived from the
  // same open-alert set by the same rule.
  const statsQuery = useGuidanceStats()
  const riskAlertsQuery = useRiskAlerts()
  const consultationsQuery = useConsultations()

  const stats = statsQuery.data
  const recentAlerts = (riskAlertsQuery.data ?? [])
    .slice()
    .sort(byGeneratedAtDesc)
    .slice(0, MAX_ALERT_CARDS)
  const recentConsultations = (consultationsQuery.data ?? []).slice(
    0,
    MAX_ALERT_CARDS
  )

  if (!user) return null

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-2">
        <h2 className="text-2xl font-bold text-foreground">Guidance Center</h2>
        <Badge
          variant="outline"
          className="w-max max-w-full border-border bg-maroon-100 text-maroon-800"
        >
          <span className="truncate">{user.email}</span>
        </Badge>
      </div>

      {/*
        PH11.11: one note for the metric row. All four figures come from a single
        `/guidance/stats/` request, so its failure is one event, and four
        identical alerts would interrupt a screen reader four times.
      */}
      {statsQuery.isError ? (
        <ErrorNote message="Unable to load the guidance statistics. Please try again." />
      ) : null}

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <MetricCard
          title="Active Cases"
          hint="Open risk alerts (not yet resolved)"
          isLoading={statsQuery.isLoading}
          isError={statsQuery.isError}
        >
          {formatCount(stats?.active_cases)}
        </MetricCard>

        <MetricCard
          title="At-Risk Students"
          hint="Distinct students with an open moderate/high alert"
          isLoading={statsQuery.isLoading}
          isError={statsQuery.isError}
        >
          {formatCount(stats?.at_risk_students)}
        </MetricCard>

        <MetricCard
          title="Pending Follow-up"
          hint="Your ongoing and follow-up consultations"
          isLoading={statsQuery.isLoading}
          isError={statsQuery.isError}
        >
          {formatCount(stats?.pending_follow_up)}
        </MetricCard>

        <MetricCard
          title="Assessment Completion"
          hint="Completed vs started assessments"
          isLoading={statsQuery.isLoading}
          isError={statsQuery.isError}
        >
          {formatPercent(stats?.assessment_completion_rate, 0)}
        </MetricCard>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Risk Alert Cards</CardTitle>
          </CardHeader>
          <CardContent>
            {/*
                PH11.11: `isFetching` → `isLoading`, and the failure became an
                `ErrorNote`. `isFetching` stays true through a background
                refetch, so a refresh over alerts already on screen replaced the
                list with a grey bar. The muted failure paragraph was worse still:
                it was visually identical to the "No risk alerts" line directly
                below it and announced nothing, so a failed request read as an
                empty one.
              */}
            {riskAlertsQuery.isLoading ? (
              <PendingRegion label="Risk alerts">
                <Skeleton className="h-20 w-full" />
              </PendingRegion>
            ) : riskAlertsQuery.isError ? (
              <ErrorNote message="Unable to load risk alerts. Please try again." />
            ) : recentAlerts.length > 0 ? (
              <ul className="space-y-3">
                {recentAlerts.map((alert) => (
                  <li
                    key={alert.id}
                    className="rounded-md border p-3"
                    data-risk={alert.risk_level}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0">
                        <p className="truncate font-medium">
                          {alert.student_name}
                        </p>
                        {/*
                          `RiskAlertSerializer` exposes no student ID code, so
                          no code is rendered here — the UUID is deliberately not
                          shown as a substitute. The student profile page is the
                          place a human-facing code is available.
                        */}
                        <p className="truncate text-xs text-muted-foreground">
                          {alert.status.replace(/_/g, " ")}
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
                      <div className="mt-2 space-y-1">
                        <p className="text-xs font-medium">Risk Factors:</p>
                        <p className="text-xs text-muted-foreground">
                          {alert.risk_factors
                            .slice(0, 2)
                            .map(riskFactorLabel)
                            .filter(Boolean)
                            .join(", ")}
                          {alert.risk_factors.length > 2 && " ..."}
                        </p>
                      </div>
                    )}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-muted-foreground">No risk alerts</p>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Recent Consultations</CardTitle>
          </CardHeader>
          <CardContent>
            {consultationsQuery.isLoading ? (
              <PendingRegion label="Recent consultations">
                <Skeleton className="h-16 w-full" />
              </PendingRegion>
            ) : consultationsQuery.isError ? (
              <ErrorNote message="Unable to load consultations. Please try again." />
            ) : recentConsultations.length > 0 ? (
              <ul className="space-y-3">
                {recentConsultations.map((consultation) => (
                  <li
                    key={consultation.id}
                    className="flex flex-wrap items-start justify-between gap-2 rounded-md border p-3"
                  >
                    <div className="min-w-0">
                      <p className="truncate font-medium">
                        {consultation.student_name}
                      </p>
                      <p className="truncate text-xs text-muted-foreground">
                        {consultation.session_type} •{" "}
                        {consultation.session_date}
                      </p>
                    </div>
                    <div className="flex shrink-0 flex-col items-end gap-1">
                      <Badge
                        variant="secondary"
                        className={consultationStatusBadgeClass(
                          consultation.status
                        )}
                        data-consultation-status={consultation.status}
                      >
                        {consultation.status.replace("_", " ")}
                      </Badge>
                      <span className="text-xs text-muted-foreground">
                        {consultation.priority_level} priority
                      </span>
                    </div>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-muted-foreground">
                No pending consultations
              </p>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}

export { GuidanceDashboard }

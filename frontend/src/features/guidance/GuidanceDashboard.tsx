import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { useAuth } from "@/features/auth/AuthContext"
import {
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
        <h1 className="text-2xl font-bold text-foreground">Guidance Center</h1>
        <Badge
          variant="outline"
          className="w-max max-w-full border-border bg-maroon-100 text-maroon-800"
        >
          <span className="truncate">{user.email}</span>
        </Badge>
      </div>

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Active Cases</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {statsQuery.isFetching ? (
                <Skeleton className="h-8 w-20" />
              ) : (
                formatCount(stats?.active_cases)
              )}
            </div>
            <p className="text-xs text-muted-foreground mt-1">
              Open risk alerts (not yet resolved)
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">
              At-Risk Students
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {statsQuery.isFetching ? (
                <Skeleton className="h-8 w-20" />
              ) : (
                formatCount(stats?.at_risk_students)
              )}
            </div>
            <p className="text-xs text-muted-foreground mt-1">
              Distinct students with an open moderate/high alert
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">
              Pending Follow-up
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {statsQuery.isFetching ? (
                <Skeleton className="h-8 w-20" />
              ) : (
                formatCount(stats?.pending_follow_up)
              )}
            </div>
            <p className="text-xs text-muted-foreground mt-1">
              Your ongoing and follow-up consultations
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">
              Assessment Completion
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {statsQuery.isFetching ? (
                <Skeleton className="h-8 w-20" />
              ) : (
                formatPercent(stats?.assessment_completion_rate, 0)
              )}
            </div>
            <p className="text-xs text-muted-foreground mt-1">
              Completed vs started assessments
            </p>
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Risk Alert Cards</CardTitle>
          </CardHeader>
          <CardContent>
            {riskAlertsQuery.isFetching ? (
              <div className="space-y-2">
                <Skeleton className="h-20 w-full" />
              </div>
            ) : riskAlertsQuery.isError ? (
              <p className="text-sm text-muted-foreground">
                Unable to load risk alerts. Please try again.
              </p>
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
                          {alert.risk_factors.slice(0, 2).join(", ")}
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
            {consultationsQuery.isFetching ? (
              <div className="space-y-2">
                <Skeleton className="h-16 w-full" />
              </div>
            ) : consultationsQuery.isError ? (
              <p className="text-sm text-muted-foreground">
                Unable to load consultations. Please try again.
              </p>
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

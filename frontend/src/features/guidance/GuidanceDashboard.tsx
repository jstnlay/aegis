import { useMemo } from "react"

import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { useAuth } from "@/features/auth/AuthContext"
import {
  useAssessmentCompletion,
  useAtRiskStudents,
  useConsultations,
  useRiskAlerts,
} from "@/features/guidance/api"
import { formatCount, formatPercent } from "@/lib/metric-format"
import {
  consultationStatusBadgeClass,
  riskLevelBadgeClass,
} from "@/lib/status-badge"

function GuidanceDashboard() {
  const { user } = useAuth()

  const riskAlertsQuery = useRiskAlerts()
  const atRiskQuery = useAtRiskStudents()
  const consultationsQuery = useConsultations()
  const assessmentQuery = useAssessmentCompletion()

  // `null` means the aggregate could not be measured; a real 0 (no
  // active cases, no at-risk students) is preserved and shown as "0".
  const atRiskCount = useMemo<number | null>(
    () => (Array.isArray(atRiskQuery.data) ? atRiskQuery.data.length : null),
    [atRiskQuery.data]
  )

  const pendingFollowUpCount = useMemo<number | null>(
    () => assessmentQuery.data?.pending_follow_up ?? null,
    [assessmentQuery.data]
  )

  const completionRate = useMemo<number | null>(
    () => assessmentQuery.data?.assessment_completion_rate ?? null,
    [assessmentQuery.data]
  )

  const activeCasesCount = useMemo<number | null>(
    () => riskAlertsQuery.data?.length ?? null,
    [riskAlertsQuery.data]
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
              {riskAlertsQuery.isFetching ? (
                <Skeleton className="h-8 w-20" />
              ) : (
                formatCount(activeCasesCount)
              )}
            </div>
            <p className="text-xs text-muted-foreground mt-1">
              Students with active risk alerts
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
              {atRiskQuery.isFetching ? (
                <Skeleton className="h-8 w-20" />
              ) : (
                formatCount(atRiskCount)
              )}
            </div>
            <p className="text-xs text-muted-foreground mt-1">
              Moderate to high risk level
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
              {assessmentQuery.isFetching ? (
                <Skeleton className="h-8 w-20" />
              ) : (
                formatCount(pendingFollowUpCount)
              )}
            </div>
            <p className="text-xs text-muted-foreground mt-1">
              Consultations needing follow-up
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
              {assessmentQuery.isFetching ? (
                <Skeleton className="h-8 w-20" />
              ) : (
                formatPercent(completionRate, 0)
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
            ) : riskAlertsQuery.data && riskAlertsQuery.data.length > 0 ? (
              <ul className="space-y-3">
                {riskAlertsQuery.data.map((alert, idx) => (
                  <li
                    key={alert.id || idx}
                    className="rounded-md border p-3"
                    data-risk={alert.risk_level}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0">
                        <p className="truncate font-medium">
                          {alert.student_name}
                        </p>
                        <p className="truncate text-xs text-muted-foreground">
                          {alert.student_id}
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
                    <div className="mt-2 space-y-1">
                      <p className="text-xs text-muted-foreground">
                        Status: {alert.status.replace("_", " ")}
                      </p>
                      {alert.risk_factors && alert.risk_factors.length > 0 && (
                        <div>
                          <p className="text-xs font-medium">Risk Factors:</p>
                          <p className="text-xs text-muted-foreground">
                            {alert.risk_factors.slice(0, 2).join(", ")}
                            {alert.risk_factors.length > 2 && " ..."}
                          </p>
                        </div>
                      )}
                    </div>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-muted-foreground">
                No active risk alerts
              </p>
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
            ) : consultationsQuery.data &&
              consultationsQuery.data.length > 0 ? (
              <ul className="space-y-3">
                {consultationsQuery.data
                  .slice(0, 5)
                  .map((consultation, idx) => (
                    <li
                      key={consultation.id || idx}
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

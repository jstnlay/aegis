import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { useAuth } from "@/features/auth/AuthContext"
import {
  useSchoolWideMetrics,
  useRiskDistribution,
  useLowPerformanceStudents,
} from "@/features/admin/api"
import { formatCount, formatPercent } from "@/lib/metric-format"

function AdminDashboard() {
  const { user } = useAuth()

  const metricsQuery = useSchoolWideMetrics()
  const riskDistQuery = useRiskDistribution()
  const lowPerfQuery = useLowPerformanceStudents()

  // `null` means the backend reported no data for that metric; a real 0
  // is passed through untouched and rendered as "0" / "0.00%".
  const overallGradeAvg = metricsQuery.data?.overall_grade_average ?? null
  const totalStudents = metricsQuery.data?.total_students ?? null
  const gradeLevels = metricsQuery.data?.grade_levels ?? null
  const riskDistribution = riskDistQuery.data ?? null

  if (!user) return null

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-2">
        <h1 className="text-2xl font-bold text-foreground">
          Administration Panel
        </h1>
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
            <CardTitle className="text-sm font-medium">
              Overall Grade Average
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {metricsQuery.isFetching ? (
                <Skeleton className="h-8 w-20" />
              ) : (
                formatPercent(overallGradeAvg, 2)
              )}
            </div>
            <p className="text-xs text-muted-foreground mt-1">
              School-wide academic performance
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">
              Total Students
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {metricsQuery.isFetching ? (
                <Skeleton className="h-8 w-20" />
              ) : (
                formatCount(totalStudents)
              )}
            </div>
            <p className="text-xs text-muted-foreground mt-1">
              Active student enrollments
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Grade Levels</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {metricsQuery.isFetching ? (
                <Skeleton className="h-8 w-20" />
              ) : (
                formatCount(gradeLevels)
              )}
            </div>
            <p className="text-xs text-muted-foreground mt-1">
              Active grade levels
            </p>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Risk Distribution</CardTitle>
        </CardHeader>
        <CardContent>
          {riskDistQuery.isFetching ? (
            <div className="space-y-2">
              <Skeleton className="h-8 w-3/4" />
            </div>
          ) : riskDistribution ? (
            <div className="grid gap-4 md:grid-cols-3">
              <div className="rounded-md p-3 text-center">
                <div className="text-lg font-bold text-success">
                  {formatCount(riskDistribution.low)}
                </div>
                <p className="text-xs text-success">Low Risk</p>
              </div>
              <div className="rounded-md p-3 text-center">
                <div className="text-lg font-bold text-warning-foreground">
                  {formatCount(riskDistribution.moderate)}
                </div>
                <p className="text-xs text-warning-foreground">Moderate Risk</p>
              </div>
              <div className="rounded-md p-3 text-center">
                <div className="text-lg font-bold text-destructive">
                  {formatCount(riskDistribution.high)}
                </div>
                <p className="text-xs text-destructive">High Risk</p>
              </div>
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">
              {riskDistQuery.isError
                ? "Unable to load the risk distribution. Please try again."
                : "No risk distribution data available"}
            </p>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Low-Performance Students (Top 20)</CardTitle>
        </CardHeader>
        <CardContent>
          {lowPerfQuery.isFetching ? (
            <div className="space-y-2">
              <Skeleton className="h-10 w-full" />
            </div>
          ) : lowPerfQuery.isError ? (
            <p className="text-sm text-muted-foreground">
              Unable to load low-performance students. Please try again.
            </p>
          ) : lowPerfQuery.data && lowPerfQuery.data.length > 0 ? (
            <ul className="space-y-2">
              {lowPerfQuery.data.map((student, idx) => (
                <li
                  key={idx}
                  className="flex items-center justify-between gap-2 rounded-md border p-3"
                >
                  <p className="min-w-0 truncate font-medium">
                    {student.student_name}
                  </p>
                  <span className="shrink-0 font-bold text-foreground">
                    {formatPercent(student.average, 2)}
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-muted-foreground">
              No low-performance students found
            </p>
          )}
        </CardContent>
      </Card>
    </div>
  )
}

export { AdminDashboard }

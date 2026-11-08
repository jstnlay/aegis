import { CalendarCheck } from "lucide-react"
import {
  EmptyState,
  ErrorNote,
  PendingRegion,
} from "@/components/feedback/Feedback"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { formatCount, formatPercent } from "@/lib/metric-format"
import type { FacultyAttendance } from "./api"

export function FacultyAttendancePanel({
  data,
  loading,
  error,
}: {
  data?: FacultyAttendance
  loading: boolean
  error: boolean
}) {
  const rate = data?.attendance_rate
  const validRate =
    typeof rate === "number" &&
    Number.isFinite(rate) &&
    rate >= 0 &&
    rate <= 100
  return (
    <Card data-panel="attendance" className="faculty-attendance-panel">
      <CardHeader>
        <CardTitle>
          <span className="faculty-panel-icon" aria-hidden="true">
            <CalendarCheck />
          </span>
          <span>Attendance overview</span>
        </CardTitle>
      </CardHeader>
      <CardContent>
        {loading ? (
          <PendingRegion label="Class attendance">
            <Skeleton className="h-32 w-full" />
          </PendingRegion>
        ) : error ? (
          <ErrorNote message="Unable to load attendance. Please try again." />
        ) : !data || !data.records ? (
          <EmptyState message="Your attendance overview will appear once records are available." />
        ) : !validRate ? (
          <ErrorNote message="The attendance rate is unavailable." />
        ) : (
          <div className="faculty-attendance-insight">
            <div className="faculty-attendance-headline">
              <div>
                <span className="faculty-insight-caption">Attendance rate</span>
                <strong>{formatPercent(rate, 1)}</strong>
              </div>
              <span className="faculty-insight-count">
                {formatCount(data.records)}
                <small>records</small>
              </span>
            </div>
            <div
              className="faculty-progress-track"
              role="progressbar"
              aria-label="Recorded attendance rate"
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={rate}
              aria-valuetext={`${formatPercent(rate, 1)} present or late`}
            >
              <span style={{ width: `${rate}%` }} />
            </div>
            <p className="faculty-insight-note">
              Present or late, across recorded attendance.
            </p>
            <dl className="faculty-attendance-breakdown">
              {(
                [
                  { key: "present", label: "Present", value: data.present },
                  { key: "late", label: "Late", value: data.late },
                  { key: "absent", label: "Absent", value: data.absent },
                ] as const
              ).map(({ key, label, value }) => (
                <div key={key} data-attendance={key}>
                  <dt>
                    <span aria-hidden="true" />
                    {label}
                  </dt>
                  <dd>{formatCount(value)}</dd>
                </div>
              ))}
            </dl>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

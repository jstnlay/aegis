import { GraduationCap } from "lucide-react"

import {
  EmptyState,
  ErrorNote,
  PendingRegion,
} from "@/components/feedback/Feedback"
import { Badge } from "@/components/ui/badge"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { useStudentEnrollment } from "@/features/student/api"

export function SchoolRecordCard() {
  const enrollment = useStudentEnrollment()
  const record = enrollment.data
  const fields: [string, string | number | null | undefined][] = record
    ? [
        ["Student ID", record.student_id],
        ["Year level", record.grade_level_name],
        ["Section", record.section_name],
        ["School year", record.academic_year_name],
        ["Age", record.age],
      ]
    : []

  return (
    <Card>
      <CardHeader>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <CardTitle className="flex items-center gap-2">
            <GraduationCap className="size-5 text-primary" aria-hidden="true" />
            School record
          </CardTitle>
          <Badge variant="secondary">Read only</Badge>
        </div>
        <CardDescription>
          Your enrollment details, maintained by the school.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">
        {enrollment.isLoading ? (
          <PendingRegion label="School record">
            <Skeleton className="h-32 w-full" />
          </PendingRegion>
        ) : enrollment.isError ? (
          <ErrorNote message="Unable to load your school record. Please try again." />
        ) : !record ? (
          <EmptyState message="No enrollment record yet." />
        ) : (
          <dl className="grid gap-x-6 gap-y-4 text-sm sm:grid-cols-2">
            {fields.map(([label, value]) => (
              <div
                key={label}
                className={label === "Student ID" ? "sm:col-span-2" : undefined}
              >
                <dt className="mb-1 text-xs text-muted-foreground">{label}</dt>
                <dd
                  className={
                    label === "Student ID"
                      ? "break-all font-mono font-medium"
                      : "font-medium"
                  }
                >
                  {value ?? "—"}
                </dd>
              </div>
            ))}
          </dl>
        )}
        <p className="border-t pt-4 text-sm leading-relaxed text-muted-foreground">
          Need a correction? Contact the school office. Updating your profile
          does not change your student ID or enrollment details.
        </p>
      </CardContent>
    </Card>
  )
}

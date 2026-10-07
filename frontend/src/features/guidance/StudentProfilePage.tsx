import { useMemo, type ReactNode } from "react"
import { Link, useParams } from "react-router-dom"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Separator } from "@/components/ui/separator"
import { Skeleton } from "@/components/ui/skeleton"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import {
  BEHAVIORAL_NOTE_TYPE_LABELS,
  CONSULTATION_SESSION_TYPE_LABELS,
  CONSULTATION_STATUS_LABELS,
  INTERVENTION_STATUS_LABELS,
  RISK_ALERT_SOURCE_LABELS,
  RISK_LEVEL_LABELS,
  atRiskStudentsFrom,
  riskFactorLabel,
  useBehavioralNotes,
  useConsultations,
  useConsultationsByStudent,
  useGuidanceAssessmentResults,
  useGuidanceReport,
  useGuidanceStudents,
  useInterventions,
  useRiskAlerts,
  useStudentAttendance,
  useStudentGradeRecord,
  type BehavioralNote,
  type Consultation,
  type GuidanceAssessmentResult,
  type Intervention,
  type RiskAlert,
  type RiskLevel,
} from "@/features/guidance/api"
import { normalizeApiError } from "@/lib/error"
import {
  consultationStatusBadgeClass,
  riskLevelBadgeClass,
} from "@/lib/status-badge"

/**
 * The profile surfaces many independent aggregates. Each block owns its own
 * loading/error state so one slow or failing endpoint (grades, attendance)
 * does not blank the whole profile.
 */
function BlockError({ message }: { message: string }) {
  return (
    <p role="alert" className="text-sm text-destructive">
      {message}
    </p>
  )
}

function EmptyBlock({ message }: { message: string }) {
  return <p className="text-sm text-muted-foreground">{message}</p>
}

/**
 * Identity header.
 *
 * The name and code come from the guidance-activity directory, not from an
 * enrollment roster: guidance records are the only thing that makes a student
 * part of this counselor's world, and only some of them carry a code. When no
 * record carries one, the em-dash stands in for it rather than an internal id.
 */
function StudentIdentity({
  name,
  code,
}: {
  name: string
  code: string | null
}) {
  return (
    <div className="space-y-1">
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="text-2xl font-bold text-foreground">{name}</h2>
        {code ? (
          <Badge variant="outline" className="tabular-nums">
            {code}
          </Badge>
        ) : (
          <Badge variant="outline" data-student-code="absent">
            &mdash;
          </Badge>
        )}
      </div>
    </div>
  )
}

function Section({
  title,
  description,
  children,
}: {
  title: string
  description?: string
  children: ReactNode
}) {
  return (
    <Card>
      <CardHeader>
        <div className="space-y-1">
          <CardTitle>{title}</CardTitle>
          {description ? (
            <CardDescription>{description}</CardDescription>
          ) : null}
        </div>
      </CardHeader>
      <CardContent className="space-y-3">{children}</CardContent>
    </Card>
  )
}

function RiskAlertsBlock({ alerts }: { alerts: RiskAlert[] }) {
  if (alerts.length === 0) {
    return <EmptyBlock message="No risk alerts on record." />
  }

  return (
    <ul className="space-y-2">
      {alerts.map((alert) => (
        <li
          key={alert.id}
          className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-border p-3"
        >
          <div className="min-w-0 space-y-1">
            <div className="flex flex-wrap items-center gap-2">
              <Badge
                variant="secondary"
                className={riskLevelBadgeClass(alert.risk_level)}
              >
                {RISK_LEVEL_LABELS[alert.risk_level]}
              </Badge>
              <Badge variant="outline" data-alert-status={alert.status}>
                {alert.status.replace("_", " ")}
              </Badge>
            </div>
            {alert.risk_factors.length > 0 ? (
              <p className="text-sm text-muted-foreground">
                {alert.risk_factors
                  .map(riskFactorLabel)
                  .filter(Boolean)
                  .join(" · ")}
              </p>
            ) : null}
          </div>
          <span className="text-xs text-muted-foreground">
            {RISK_ALERT_SOURCE_LABELS[alert.source]}
          </span>
        </li>
      ))}
    </ul>
  )
}

function ConsultationsBlock({
  consultations,
}: {
  consultations: Consultation[]
}) {
  if (consultations.length === 0) {
    return <EmptyBlock message="No consultations recorded by you." />
  }

  return (
    <ul className="space-y-2">
      {consultations.map((consultation) => (
        <li
          key={consultation.id}
          className="space-y-1 rounded-md border border-border p-3"
        >
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="text-sm">
              {consultation.session_date} ·{" "}
              {CONSULTATION_SESSION_TYPE_LABELS[consultation.session_type]}
            </span>
            <Badge
              variant="outline"
              className={consultationStatusBadgeClass(consultation.status)}
            >
              {CONSULTATION_STATUS_LABELS[consultation.status]}
            </Badge>
          </div>
          <p className="text-sm text-muted-foreground">
            {consultation.session_notes}
          </p>
        </li>
      ))}
    </ul>
  )
}

function InterventionsBlock({
  interventions,
}: {
  interventions: Intervention[]
}) {
  if (interventions.length === 0) {
    return <EmptyBlock message="No intervention plans you own." />
  }

  return (
    <ul className="space-y-2">
      {interventions.map((intervention) => (
        <li
          key={intervention.id}
          className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-border p-3"
        >
          <div className="space-y-1">
            <p className="text-sm">Started {intervention.plan_start_date}</p>
            <p className="text-xs text-muted-foreground">
              {intervention.target_review_date
                ? `Review ${intervention.target_review_date}`
                : "No target review date"}
            </p>
          </div>
          <Badge
            variant="outline"
            data-intervention-status={intervention.status}
          >
            {INTERVENTION_STATUS_LABELS[intervention.status]}
          </Badge>
        </li>
      ))}
    </ul>
  )
}

function BehavioralNotesBlock({ notes }: { notes: BehavioralNote[] }) {
  if (notes.length === 0) {
    return <EmptyBlock message="No behavioral notes recorded." />
  }

  return (
    <ul className="space-y-2">
      {notes.map((note) => (
        <li
          key={note.id}
          className="space-y-1 rounded-md border border-border p-3"
        >
          <div className="flex flex-wrap items-center justify-between gap-2">
            <Badge variant="outline" data-note-type={note.note_type}>
              {BEHAVIORAL_NOTE_TYPE_LABELS[note.note_type]}
            </Badge>
            <span className="text-xs text-muted-foreground">
              {note.date_recorded} · {note.recorded_by_name}
            </span>
          </div>
          <p className="text-sm">{note.note_text}</p>
        </li>
      ))}
    </ul>
  )
}

function GradesBlock({ studentId }: { studentId: string }) {
  const gradesQuery = useStudentGradeRecord(studentId)

  if (gradesQuery.isLoading) return <Skeleton className="h-20 w-full" />
  if (gradesQuery.isError) {
    return <BlockError message={normalizeApiError(gradesQuery.error).message} />
  }

  const grades = gradesQuery.data ?? []
  if (grades.length === 0) {
    return <EmptyBlock message="No finalized grades recorded." />
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Subject</TableHead>
          <TableHead>Section</TableHead>
          <TableHead>Period</TableHead>
          <TableHead>Score</TableHead>
          <TableHead>Letter</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {grades.map((grade) => (
          <TableRow key={grade.id}>
            <TableCell>
              <div className="font-medium">{grade.subjectName}</div>
              <div className="text-xs text-muted-foreground">
                {grade.subjectCode}
              </div>
            </TableCell>
            <TableCell className="text-sm text-muted-foreground">
              {grade.sectionName}
            </TableCell>
            <TableCell className="text-sm text-muted-foreground">
              {grade.gradingPeriodName ?? "—"}
            </TableCell>
            <TableCell className="tabular-nums">
              {grade.score === null ? "—" : grade.score}
            </TableCell>
            <TableCell>{grade.letterGrade ?? "—"}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}

function AttendanceBlock({ studentId }: { studentId: string }) {
  const attendanceQuery = useStudentAttendance(studentId)

  if (attendanceQuery.isLoading) return <Skeleton className="h-20 w-full" />
  if (attendanceQuery.isError) {
    return (
      <BlockError message={normalizeApiError(attendanceQuery.error).message} />
    )
  }

  const attendance = attendanceQuery.data
  if (!attendance) {
    return <EmptyBlock message="No attendance records found." />
  }

  // Counts only. The summary endpoint returns no possible-day total, so a rate
  // is not computed here.
  return (
    <div>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {(
          [
            ["Present", attendance.present],
            ["Late", attendance.late],
            ["Absent", attendance.absent],
            ["Records", attendance.total],
          ] as const
        ).map(([label, value]) => (
          <div
            key={label}
            className="rounded-md border border-border p-3 text-center"
          >
            <div className="text-xs text-muted-foreground">{label}</div>
            <div className="tabular-nums text-xl font-semibold">{value}</div>
          </div>
        ))}
      </div>
      <p className="mt-2 text-xs text-muted-foreground">
        The attendance summary endpoint returns record counts only. It does not
        report total possible school days, so no attendance rate is derived
        here.
      </p>
    </div>
  )
}

function AssessmentsBlock({
  results,
  studentId,
}: {
  results: GuidanceAssessmentResult[]
  studentId: string
}) {
  const byAssessment = useMemo(() => {
    const map = new Map<string, GuidanceAssessmentResult[]>()
    for (const result of results) {
      if (result.student !== studentId) continue
      const bucket = map.get(result.assessment)
      if (bucket) bucket.push(result)
      else map.set(result.assessment, [result])
    }
    return map
  }, [results, studentId])

  if (byAssessment.size === 0) {
    return (
      <EmptyBlock message="No assessment results on record for this student." />
    )
  }

  return (
    <ul className="space-y-2">
      {Array.from(byAssessment.entries()).map(([assessmentId, list]) => {
        const title = list.find(
          (result) => result.assessment_title
        )?.assessment_title
        return (
          <li
            key={assessmentId}
            className="rounded-md border border-border p-3"
          >
            {/* `AssessmentResultListSerializer` carries the title, so no second
                lookup against the assessment list is needed. */}
            {title ? <p className="text-sm font-medium">{title}</p> : null}
            <ul className="mt-1 space-y-1">
              {list.map((result) => (
                <li
                  key={result.id}
                  className="flex flex-wrap items-center justify-between gap-2 text-sm"
                >
                  <span>
                    {result.status === "completed"
                      ? "Completed"
                      : "In progress"}
                  </span>
                  <span className="tabular-nums text-muted-foreground">
                    {result.percentage === null
                      ? "No score"
                      : `${result.percentage}%`}
                  </span>
                </li>
              ))}
            </ul>
          </li>
        )
      })}
    </ul>
  )
}

export function StudentProfilePage() {
  const { studentId } = useParams<{ studentId: string }>()

  const studentsQuery = useGuidanceStudents()
  const reportQuery = useGuidanceReport(studentId)
  const alertsQuery = useRiskAlerts()
  const consultationsQuery = useConsultations()
  const interventionsQuery = useInterventions()
  const notesQuery = useBehavioralNotes(studentId)
  const resultsQuery = useGuidanceAssessmentResults()

  const directoryEntry = useMemo(
    () =>
      (studentsQuery.data?.students ?? []).find(
        (item) => item.id === studentId
      ) ?? null,
    [studentsQuery.data, studentId]
  )

  const consultationsByStudent = useConsultationsByStudent(
    consultationsQuery.data
  )

  const alerts = useMemo(
    () =>
      (alertsQuery.data ?? []).filter((alert) => alert.student === studentId),
    [alertsQuery.data, studentId]
  )

  const interventions = useMemo(
    () =>
      (interventionsQuery.data ?? []).filter(
        (intervention) => intervention.student === studentId
      ),
    [interventionsQuery.data, studentId]
  )

  /**
   * The caller's OWN records for this student.
   *
   * Both `useConsultations` and `useInterventions` are already scoped to the
   * signed-in counselor server-side, so these are private by construction. The
   * counts on this page come from here rather than from the guidance report,
   * whose aggregates are not counselor-scoped.
   */
  const studentConsultations = useMemo(
    () => consultationsByStudent.get(studentId ?? "") ?? [],
    [consultationsByStudent, studentId]
  )

  const studentInterventions = interventions

  /**
   * The student's at-risk level, and nothing else.
   *
   * `atRiskStudentsFrom` is the membership rule (open **and** moderate/high);
   * this only picks the label and the semantic colour. Deriving the level from
   * the same open-alert subset keeps the two from disagreeing, and it means a
   * moderate-only student is not painted with high/destructive styling.
   */
  const atRiskLevel = useMemo<RiskLevel | null>(() => {
    const openEscalating = alerts.filter(
      (alert) =>
        (alert.risk_level === "high" || alert.risk_level === "moderate") &&
        atRiskStudentsFrom(alerts).includes(alert.student)
    )
    if (openEscalating.length === 0) return null
    // `atRiskStudentsFrom` scopes to this student, so the worst open
    // moderate/high level among them is the badge level.
    return openEscalating.some((alert) => alert.risk_level === "high")
      ? "high"
      : "moderate"
  }, [alerts])

  const behaviorCounts = reportQuery.data?.behavioral_note_counts

  if (studentsQuery.isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-32 w-full" />
      </div>
    )
  }

  if (studentsQuery.isError) {
    return (
      <div className="space-y-4">
        <BlockError message={normalizeApiError(studentsQuery.error).message} />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <StudentIdentity
          name={directoryEntry?.name ?? "Student"}
          code={directoryEntry?.code ?? null}
        />
        <div className="flex items-center gap-2">
          {atRiskLevel ? (
            <Badge
              variant="secondary"
              className={riskLevelBadgeClass(atRiskLevel)}
              data-at-risk="true"
              data-at-risk-level={atRiskLevel}
            >
              At risk ({RISK_LEVEL_LABELS[atRiskLevel]})
            </Badge>
          ) : null}
          <Button asChild variant="outline" size="sm">
            <Link to="/app/students">Back to roster</Link>
          </Button>
        </div>
      </div>

      {/*
        Counts come from the caller's OWN collections, not from
        `GuidanceReportView`.

        The report filters `ConsultationRecord` / `Intervention` by
        `student` only, with no counselor scope, so its `consultation_summary
        .total` and `intervention_summary.total` include every counselor's
        records for the student. Rendering those next to a list that is provably
        the caller's own would be a self-contradiction, and would leak the
        existence of a colleague's caseload. `risk_alert_history.length` is
        still safe because risk alerts are school-wide to guidance.
      */}
      {studentConsultations.length > 0 ||
      studentInterventions.length > 0 ||
      reportQuery.data ? (
        <div className="grid gap-3 sm:grid-cols-3">
          <div className="rounded-md border border-border p-3">
            <div className="text-xs text-muted-foreground">Risk alerts</div>
            <div className="tabular-nums text-xl font-semibold">
              {reportQuery.data?.risk_alert_history.length ?? 0}
            </div>
          </div>
          <div
            className="rounded-md border border-border p-3"
            data-count-source="own-consultations"
          >
            <div className="text-xs text-muted-foreground">
              Your consultations
            </div>
            <div className="tabular-nums text-xl font-semibold">
              {studentConsultations.length}
            </div>
          </div>
          <div
            className="rounded-md border border-border p-3"
            data-count-source="own-interventions"
          >
            <div className="text-xs text-muted-foreground">
              Your interventions
            </div>
            <div className="tabular-nums text-xl font-semibold">
              {studentInterventions.length}
            </div>
          </div>
        </div>
      ) : null}
      {reportQuery.isError ? (
        <BlockError message={normalizeApiError(reportQuery.error).message} />
      ) : null}

      <div className="grid gap-6 lg:grid-cols-2">
        <Section
          title="Risk alerts"
          description="Every alert on record, including resolved ones."
        >
          {alertsQuery.isLoading ? (
            <Skeleton className="h-20 w-full" />
          ) : alertsQuery.isError ? (
            <BlockError
              message={normalizeApiError(alertsQuery.error).message}
            />
          ) : (
            <RiskAlertsBlock alerts={alerts} />
          )}
        </Section>

        <Section
          title="Consultations"
          description="Only sessions you recorded are visible."
        >
          {consultationsQuery.isLoading ? (
            <Skeleton className="h-20 w-full" />
          ) : consultationsQuery.isError ? (
            <BlockError
              message={normalizeApiError(consultationsQuery.error).message}
            />
          ) : (
            <ConsultationsBlock consultations={studentConsultations} />
          )}
        </Section>

        <Section
          title="Intervention plans"
          description="Only plans assigned to you are visible."
        >
          {interventionsQuery.isLoading ? (
            <Skeleton className="h-20 w-full" />
          ) : interventionsQuery.isError ? (
            <BlockError
              message={normalizeApiError(interventionsQuery.error).message}
            />
          ) : (
            <InterventionsBlock interventions={studentInterventions} />
          )}
        </Section>

        <Section
          title="Behavioral notes"
          description={
            behaviorCounts
              ? `Positive ${behaviorCounts.positive ?? 0} · Warning ${behaviorCounts.warning ?? 0} · Incident ${behaviorCounts.incident ?? 0}`
              : "Recorded by faculty."
          }
        >
          {notesQuery.isLoading ? (
            <Skeleton className="h-20 w-full" />
          ) : notesQuery.isError ? (
            <BlockError message={normalizeApiError(notesQuery.error).message} />
          ) : (
            <BehavioralNotesBlock notes={notesQuery.data ?? []} />
          )}
        </Section>

        <Section
          title="Finalized grades"
          description="Server-filtered to this student and to finalized grades."
        >
          <GradesBlock studentId={studentId ?? ""} />
        </Section>

        <Section
          title="Attendance"
          description="Record counts from the summary endpoint."
        >
          <AttendanceBlock studentId={studentId ?? ""} />
        </Section>

        <Section
          title="Assessments"
          description="Results on assessments you created."
        >
          {resultsQuery.isLoading ? (
            <Skeleton className="h-20 w-full" />
          ) : resultsQuery.isError ? (
            <BlockError
              message={normalizeApiError(resultsQuery.error).message}
            />
          ) : (
            <AssessmentsBlock
              results={resultsQuery.data ?? []}
              studentId={studentId ?? ""}
            />
          )}
        </Section>
      </div>

      <Separator />

      <p className="text-xs text-muted-foreground">
        Risk alerts, grades, attendance, and behavioral notes are school-wide
        surfaces. Consultations and interventions are private to you, so a
        colleague&apos;s records never appear here.
      </p>
    </div>
  )
}

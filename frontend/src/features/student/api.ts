import { useState, useMemo } from "react"
import { useQuery } from "@tanstack/react-query"
import { apiClient } from "@/lib/api"
import { fetchAllPages } from "@/lib/pagination"

/**
 * Bucket label for a finalized grade that carries no grading period.
 *
 * Used in exactly one place on both sides — building the period buckets and
 * normalizing each grade's `grading_period` — so a row can never be grouped
 * under one key and then filtered by another.
 */
const UNASSIGNED_PERIOD = "Unassigned"

export interface AttendanceSummary {
  present_days: number
  late_days: number
  absent_days: number
  total_days: number
  /**
   * `(present + late) / total_records * 100`, or `null` when the
   * backend reported no attendance records at all. `null` means "no
   * data" and must be shown as N/A — it is never a legitimate 0%.
   */
  attendance_rate: number | null
}

export interface StudentGrade {
  subject_name: string
  subject_code: string
  score: number | null
  letter_grade: string | null
  grading_period: string
}

export interface GradingPeriodProgress {
  period_name: string
  /**
   * Mean score for the period, or `null` when the period has grade rows
   * but none of them carry a score yet.
   */
  average_grade: number | null
}

interface EnrollmentRecord {
  id: string
  student: string
  student_name: string
  student_id: string
  section_name: string
  is_active: boolean
}

interface AttendanceSummaryEntry {
  student: string
  student_name: string
  student_id_code: string
  section_name: string
  present_count: number
  late_count: number
  absent_count: number
  total_records: number
}

interface GradeRecord {
  subject_name: string
  subject_code: string
  score: number | null
  letter_grade: string | null
  grading_period_name: string | null
}

interface GradingPeriodRecord {
  id: string
  name: string
  order: number
}

interface DashboardMetrics {
  student_id: string
  student_name?: string
  has_data: boolean
  overall_average?: number | null
  total_subjects?: number
}

/**
 * A grade score from the API, as a number or "no score".
 *
 * DRF serialises `Decimal` as a string, so `score` arrives as `"76.69"` even
 * though the contract types it `number | null`. Passing the string through
 * unnormalised is how a row ends up reading "N/A / Passing": `formatPercent`
 * rejects a non-number while `scoreStatus` coerces it into a pass, and the
 * period average concatenates the strings into `NaN`. A value that does not
 * parse is not a zero — it is absent.
 */
function toScore(value: unknown): number | null {
  if (value === null || value === undefined || value === "") return null
  const parsed = typeof value === "number" ? value : Number(value)
  return Number.isFinite(parsed) ? parsed : null
}

/**
 * Resolves the current student's StudentProfile UUID from their own
 * enrollments. The authenticated user's `id` is the User UUID, which is
 * NOT the StudentProfile UUID used by analytics / attendance routes.
 */
export function useStudentProfileId() {
  return useQuery<string | null, Error>({
    queryKey: ["student", "profile-id"],
    queryFn: async () => {
      const { results } = await fetchAllPages<EnrollmentRecord>(
        "/academics/enrollments/"
      )
      const active = results.find((e) => e.is_active) ?? results[0]
      return active?.student ?? null
    },
  })
}

export function useStudentDashboardData(studentId: string) {
  const [selectedPeriod, setSelectedPeriod] = useState<string>("")

  const enabled = Boolean(studentId)

  const metricsQuery = useQuery<DashboardMetrics | undefined, Error>({
    queryKey: ["student", "metrics", studentId],
    enabled,
    queryFn: async () => {
      const { data } = await apiClient.get<{
        status: string
        data: DashboardMetrics
      }>(`/analytics/students/${studentId}/metrics/`)
      return data.data
    },
  })

  const attendanceQuery = useQuery<AttendanceSummary | null, Error>({
    queryKey: ["student", "attendance", studentId],
    enabled,
    queryFn: async () => {
      const { data } = await apiClient.get<AttendanceSummaryEntry[]>(
        `/attendance/summary/${studentId ? `?student=${studentId}` : ""}`
      )
      const entry = data.find((e) => e.student === studentId) ?? data[0]
      // MUST be `null`, never `undefined`: TanStack Query v5 rejects a
      // resolved `undefined` ("Query data cannot be undefined"), which
      // would mark this query as errored and make the shared `error`
      // flag render a false "Unable to load" state on sibling cards
      // (Academic Progress / Recent Grades) even though every request
      // succeeded. `null` is the codebase's established "no data" value.
      if (!entry) return null
      const total = entry.total_records
      return {
        present_days: entry.present_count,
        late_days: entry.late_count,
        absent_days: entry.absent_count,
        total_days: total,
        // No records at all is "no data", not 0%. A genuine 0% (every
        // record absent) is preserved because `total > 0` here.
        attendance_rate:
          total > 0
            ? ((entry.present_count + entry.late_count) / total) * 100
            : null,
      }
    },
  })

  const gradesQuery = useQuery<StudentGrade[], Error>({
    queryKey: ["student", "grades", studentId],
    enabled,
    queryFn: async () => {
      const { results } = await fetchAllPages<GradeRecord>(
        `/academics/grades/${studentId ? `?status=finalized&student=${studentId}` : ""}`
      )
      return results.map((g) => ({
        subject_name: g.subject_name,
        subject_code: g.subject_code,
        // Normalised at the boundary: the API sends Decimal as a string.
        score: toScore(g.score),
        letter_grade: g.letter_grade,
        // Normalized to the same key the period buckets are built from. A row
        // with no grading period used to keep `""` here while being grouped as
        // "Unassigned", so the default period filter matched nothing and every
        // grade dropped out of the average — which is how a student with
        // finalized grades saw N/A on the dashboard while Academics listed them.
        grading_period: g.grading_period_name?.trim() || UNASSIGNED_PERIOD,
      }))
    },
  })

  const gradingPeriodsQuery = useQuery<GradingPeriodRecord[], Error>({
    queryKey: ["student", "grading-periods", studentId],
    enabled,
    queryFn: async () => {
      const { results } = await fetchAllPages<GradingPeriodRecord>(
        "/academics/grading-periods/"
      )
      return results
    },
  })

  const periods = useMemo<GradingPeriodProgress[]>(() => {
    const grades = gradesQuery.data ?? []
    const byPeriod = new Map<string, number[]>()
    for (const g of grades) {
      const key = g.grading_period || UNASSIGNED_PERIOD
      const scores = byPeriod.get(key) ?? []
      if (g.score !== null) scores.push(g.score)
      byPeriod.set(key, scores)
    }
    const orderMap = new Map(
      (gradingPeriodsQuery.data ?? []).map((p) => [p.name, p.order])
    )
    return Array.from(byPeriod.entries())
      .map(([period_name, scores]) => ({
        period_name,
        average_grade:
          scores.length > 0
            ? scores.reduce((a, b) => a + b, 0) / scores.length
            : null,
      }))
      .sort(
        (a, b) =>
          (orderMap.get(a.period_name) ?? Number.MAX_SAFE_INTEGER) -
          (orderMap.get(b.period_name) ?? Number.MAX_SAFE_INTEGER)
      )
  }, [gradesQuery.data, gradingPeriodsQuery.data])

  const effectivePeriod = selectedPeriod || periods[0]?.period_name || ""

  const filteredGrades = useMemo(() => {
    if (!effectivePeriod) return gradesQuery.data ?? []
    return (gradesQuery.data ?? []).filter(
      (g) => g.grading_period === effectivePeriod
    )
  }, [gradesQuery.data, effectivePeriod])

  const averageGrade = useMemo<number | null>(() => {
    const metrics = metricsQuery.data
    if (metrics?.has_data && metrics.overall_average != null) {
      return metrics.overall_average
    }
    const withScore = filteredGrades.filter((g) => g.score !== null)
    if (withScore.length > 0) {
      return (
        withScore.reduce((sum, g) => sum + (g.score ?? 0), 0) / withScore.length
      )
    }
    // Neither the metrics endpoint nor the finalized grades carry a
    // score. A real 0.00 average is still returned above, because it is
    // derived from actual score rows.
    return null
  }, [metricsQuery.data, filteredGrades])

  const totalSubjects = useMemo<number | null>(() => {
    const metrics = metricsQuery.data
    if (metrics?.has_data && metrics.total_subjects != null) {
      return metrics.total_subjects
    }
    const grades = gradesQuery.data ?? []
    // With no finalized grade rows there is nothing to count; showing
    // "0" would claim the student has no subjects at all.
    if (grades.length === 0) return null
    return new Set(grades.map((g) => g.subject_code).filter(Boolean)).size
  }, [metricsQuery.data, gradesQuery.data])

  return {
    attendance: attendanceQuery.data,
    /** Finalized grades scoped to the selected grading period. */
    grades: filteredGrades,
    /** Every finalized grade, independent of the selected period. */
    allGrades: gradesQuery.data ?? [],
    periods,
    selectedPeriod: effectivePeriod,
    setSelectedPeriod,
    averageGrade,
    totalSubjects,
    loading:
      !enabled ||
      attendanceQuery.isFetching ||
      gradesQuery.isFetching ||
      metricsQuery.isFetching ||
      gradingPeriodsQuery.isFetching,
    error: attendanceQuery.error || gradesQuery.error || metricsQuery.error,
  }
}

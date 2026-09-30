import { useQuery } from "@tanstack/react-query"
import { fetchAllPages } from "@/lib/pagination"

export interface RiskAlert {
  id: string
  student_id: string
  student_name: string
  risk_level: "low" | "moderate" | "high"
  risk_factors: string[]
  status: "active" | "under_monitoring" | "resolved" | "escalated"
  assigned_counselor?: string
  generated_at: string
  last_updated: string
}

export interface Consultation {
  id: string
  student_id: string
  student_name: string
  session_date: string
  session_type: string
  status: "ongoing" | "completed" | "follow_up"
  priority_level: "high" | "medium" | "low"
}

export interface AssessmentResult {
  id: string
  assessment: string
  student: string
  status: "in_progress" | "completed"
}

export interface DashboardStats {
  active_cases: number
  at_risk_students: number
  pending_follow_up: number
  /**
   * `completed / total` assessment results as a percentage, or `null`
   * when the counselor has no visible assessment results at all. `null`
   * is "no data" (0 of 0 is undefined), never a legitimate 0%.
   */
  assessment_completion_rate: number | null
}

interface RiskAlertRecord {
  id: string
  student: string
  student_name: string
  risk_level: RiskAlert["risk_level"]
  risk_factors: string[]
  status: RiskAlert["status"]
  assigned_counselor_name: string | null
  generated_at: string
  last_updated: string
}

interface ConsultationRecord {
  id: string
  student: string
  student_name: string
  session_date: string
  session_type: string
  status: Consultation["status"]
  priority_level: Consultation["priority_level"]
  created_at: string
}

interface AssessmentResultRecord {
  id: string
  assessment: string
  student: string
  status: AssessmentResult["status"]
}

const queryKeys = {
  riskAlerts: ["guidance", "risk-alerts"] as const,
  consultations: ["guidance", "consultations"] as const,
  dashboardStats: ["analytics", "guidance", "dashboard"] as const,
  assessmentResults: ["analytics", "assessment-results"] as const,
}

const ACTIVE_ALERT_STATUSES: RiskAlert["status"][] = [
  "active",
  "under_monitoring",
  "escalated",
]

export function useRiskAlerts() {
  return useQuery<RiskAlert[]>({
    queryKey: queryKeys.riskAlerts,
    queryFn: async () => {
      const { results } = await fetchAllPages<RiskAlertRecord>(
        "/guidance/risk-alerts/"
      )
      return results
        .filter((alert) => ACTIVE_ALERT_STATUSES.includes(alert.status))
        .map((alert) => ({
          id: alert.id,
          student_id: alert.student,
          student_name: alert.student_name,
          risk_level: alert.risk_level,
          risk_factors: alert.risk_factors,
          status: alert.status,
          generated_at: alert.generated_at,
          last_updated: alert.last_updated,
          ...(alert.assigned_counselor_name
            ? { assigned_counselor: alert.assigned_counselor_name }
            : {}),
        }))
    },
  })
}

export function useAtRiskStudents() {
  return useQuery<string[]>({
    queryKey: [...queryKeys.riskAlerts, "at-risk"],
    queryFn: async () => {
      const { results } = await fetchAllPages<RiskAlertRecord>(
        "/guidance/risk-alerts/"
      )
      const atRisk = results.filter((alert) =>
        ["moderate", "high"].includes(alert.risk_level)
      )
      const uniqueStudents = new Set(atRisk.map((a) => a.student))
      return Array.from(uniqueStudents)
    },
  })
}

export function useConsultations() {
  return useQuery<Consultation[]>({
    queryKey: queryKeys.consultations,
    queryFn: async () => {
      const { results } = await fetchAllPages<ConsultationRecord>(
        "/guidance/consultations/"
      )
      const filtered = results.filter((c) =>
        ["ongoing", "follow_up"].includes(c.status)
      )
      const sorted = [...filtered].sort(
        (a, b) =>
          new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
      )
      return sorted.map((c) => ({
        id: c.id,
        student_id: c.student,
        student_name: c.student_name,
        session_date: c.session_date,
        session_type: c.session_type,
        status: c.status,
        priority_level: c.priority_level,
      }))
    },
  })
}

export function useAssessmentCompletion() {
  return useQuery<DashboardStats>({
    queryKey: queryKeys.dashboardStats,
    queryFn: async () => {
      const [assessmentResults, consultations, riskAlerts] = await Promise.all([
        fetchAllPages<AssessmentResultRecord>(
          "/assessments/assessment-results/"
        ),
        fetchAllPages<ConsultationRecord>("/guidance/consultations/"),
        fetchAllPages<RiskAlertRecord>("/guidance/risk-alerts/"),
      ])

      const allResults = assessmentResults.results
      const completed = allResults.filter((r) => r.status === "completed")
      // 0 of 0 assessments is an undefined rate, not 0% — the UI must
      // show N/A. A real 0% (results exist, none completed) is preserved.
      const completionRate =
        allResults.length > 0
          ? Math.round((completed.length / allResults.length) * 100)
          : null

      const pendingFollowUp = consultations.results.filter((c) =>
        ["ongoing", "follow_up"].includes(c.status)
      ).length

      const activeCases = riskAlerts.results.filter((a) =>
        ACTIVE_ALERT_STATUSES.includes(a.status)
      ).length

      const atRiskStudents = new Set(
        riskAlerts.results
          .filter((a) => ["moderate", "high"].includes(a.risk_level))
          .map((a) => a.student)
      ).size

      return {
        active_cases: activeCases,
        at_risk_students: atRiskStudents,
        pending_follow_up: pendingFollowUp,
        assessment_completion_rate: completionRate,
      }
    },
  })
}

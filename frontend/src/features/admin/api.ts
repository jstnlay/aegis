import { useQuery } from "@tanstack/react-query"
import { apiClient } from "@/lib/api"

export interface SchoolWideMetrics {
  total_students: number
  overall_grade_average: number | null
  grade_levels: number
}

export interface RiskDistribution {
  low: number
  moderate: number
  high: number
  insufficient_data: number
}

export interface LowPerformanceStudent {
  student_id: string
  student_name: string
  average: number
}

const queryKeys = {
  schoolWide: ["analytics", "school-wide"] as const,
  riskDistribution: ["analytics", "risk-distribution"] as const,
  lowPerformance: ["analytics", "low-performance"] as const,
}

export function useSchoolWideMetrics() {
  return useQuery<SchoolWideMetrics>({
    queryKey: queryKeys.schoolWide,
    queryFn: async () => {
      const { data } = await apiClient.get<{
        status: string
        data: SchoolWideMetrics
      }>("/analytics/school-wide/")
      return data.data
    },
  })
}

export function useRiskDistribution() {
  return useQuery<RiskDistribution>({
    queryKey: queryKeys.riskDistribution,
    queryFn: async () => {
      const { data } = await apiClient.get<{
        status: string
        data: { distribution: RiskDistribution; total_with_scores: number }
      }>("/analytics/risk-distribution/")
      return data.data.distribution
    },
  })
}

export function useLowPerformanceStudents() {
  return useQuery<LowPerformanceStudent[]>({
    queryKey: queryKeys.lowPerformance,
    queryFn: async () => {
      const { data } = await apiClient.get<{
        status: string
        data: LowPerformanceStudent[]
      }>("/analytics/low-performance/")
      return data.data
    },
  })
}

import { useQuery } from "@tanstack/react-query"
import { apiClient } from "@/lib/api"
import { fetchAllPages } from "@/lib/pagination"
import type { Page } from "@/types/api"

export interface FacultyAssignment {
  id: string
  subject_name: string
  subject_code: string
  section_name: string
}

export interface FacultySection {
  id: string
  name: string
  grade_level_name: string
}

export interface DashboardStats {
  total_students: number
  pending_grades: number
  pending_submissions: number
}

interface EnrollmentRecord {
  id: string
  student: string
  student_name: string
  student_id: string
  is_active: boolean
}

interface SubjectAssignmentRecord {
  id: string
  subject_name: string
  subject_code: string
  section_name: string
}

interface SectionRecord {
  id: string
  name: string
  grade_level_name: string
}

const queryKeys = {
  subjectAssignments: ["academics", "subject-assignments"] as const,
  sections: ["academics", "sections"] as const,
  facultyEnrollments: ["enrollments", "faculty"] as const,
  dashboardStats: ["analytics", "faculty", "dashboard"] as const,
}

export function useFacultySubjectAssignments() {
  return useQuery<FacultyAssignment[]>({
    queryKey: queryKeys.subjectAssignments,
    queryFn: async () => {
      const { results } = await fetchAllPages<SubjectAssignmentRecord>(
        "/academics/subject-assignments/"
      )
      return results
    },
  })
}

export function useFacultySections() {
  return useQuery<FacultySection[]>({
    queryKey: queryKeys.sections,
    queryFn: async () => {
      const { results } = await fetchAllPages<SectionRecord>(
        "/academics/sections/"
      )
      return results
    },
  })
}

export function useFacultyDashboardStats() {
  return useQuery<DashboardStats>({
    queryKey: queryKeys.dashboardStats,
    queryFn: async () => {
      const [enrollmentsRes, gradesDraftRes, gradesSubmittedRes] =
        await Promise.all([
          fetchAllPages<EnrollmentRecord>("/academics/enrollments/"),
          apiClient.get<Page<unknown>>("/academics/grades/?status=draft"),
          apiClient.get<Page<unknown>>("/academics/grades/?status=submitted"),
        ])

      const uniqueStudents = new Set(
        enrollmentsRes.results
          .filter((e: EnrollmentRecord) => e.is_active)
          .map((e: EnrollmentRecord) => e.student)
      )

      return {
        total_students: uniqueStudents.size,
        pending_grades: gradesDraftRes.data.count,
        pending_submissions: gradesSubmittedRes.data.count,
      }
    },
  })
}

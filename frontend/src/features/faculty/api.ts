import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
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
  importJobs: ["faculty", "import-jobs"] as const,
}

/**
 * The two import types faculty may upload.
 *
 * `ALL_FACULTY_IMPORT_TYPES` in `apps/data_import/constants.py` is exactly
 * these two; `students` and `guidance_records` are admin-only. Each maps to the
 * batch-import alias that pins `import_type` server-side, so the faculty page
 * cannot post a file under the wrong type.
 */
export const FACULTY_IMPORT_TYPES = [
  { type: "grades", label: "Grades", path: "/academics/grades/batch-import/" },
  {
    type: "attendance",
    label: "Attendance",
    path: "/attendance/records/batch-import/",
  },
] as const

export type FacultyImportType = (typeof FACULTY_IMPORT_TYPES)[number]["type"]

export interface FacultyImportJob {
  id: string
  file_name: string
  import_type: string
  status: string
  total_rows: number
  processed_rows: number
  error_rows: number
  created_at: string
  completed_at: string | null
  error_log: Array<{ code: string; message: string }>
}

/**
 * This faculty's own import jobs.
 *
 * `ImportJobViewSet.get_queryset` returns only jobs the caller uploaded for a
 * faculty user, so this list is already scoped server-side.
 */
export function useFacultyImportJobs() {
  return useQuery<FacultyImportJob[], Error>({
    queryKey: queryKeys.importJobs,
    queryFn: async () => {
      const { results } =
        await fetchAllPages<FacultyImportJob>("/data-import/jobs/")
      return results
    },
  })
}

/**
 * Upload a grades or attendance file.
 *
 * The pipeline runs synchronously server-side, so this resolves only once the
 * job is terminal. It posts to the batch-import alias rather than
 * `/data-import/jobs/` so the server pins the import type.
 */
export function useFacultyImportJob() {
  const queryClient = useQueryClient()
  return useMutation<
    FacultyImportJob,
    Error,
    { file: File; importType: FacultyImportType }
  >({
    mutationFn: async ({ file, importType }) => {
      const target = FACULTY_IMPORT_TYPES.find((t) => t.type === importType)
      if (!target) {
        throw new Error(`Unsupported import type: ${importType}`)
      }
      const body = new FormData()
      body.append("file", file)
      const { data } = await apiClient.post<FacultyImportJob>(
        target.path,
        body,
        { headers: { "Content-Type": "multipart/form-data" } }
      )
      return data
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.importJobs })
    },
  })
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

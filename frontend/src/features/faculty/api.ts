import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { apiClient } from "@/lib/api"
import { IMPORT_JOB_POLL_INTERVAL_MS, isImportJobLive } from "@/lib/importJobs"
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

/** Aggregate attendance across the faculty's own sections. */
export interface FacultyAttendance {
  /** Present or late over recorded days; null when nothing is recorded. */
  attendance_rate: number | null
  present: number
  late: number
  absent: number
  records: number
}

/** One behavioral note, as the guidance endpoint returns it. */
export interface BehavioralNoteRecord {
  id: string
  student: string
  student_name: string
  note_type: "positive" | "warning" | "incident"
  note_text: string
  date_recorded: string
  recorded_by_name: string
}

export interface FacultyBehaviorNotes {
  total: number
  recent: BehavioralNoteRecord[]
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
  facultyAttendance: ["attendance", "faculty", "summary"] as const,
  facultyBehaviorNotes: ["guidance", "faculty", "behavioral-notes"] as const,
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
    // A file too large for the request finishes in a worker, so the list
    // refreshes itself while any job is still running.
    refetchInterval: (query) =>
      (query.state.data ?? []).some((job) => isImportJobLive(job.status))
        ? IMPORT_JOB_POLL_INTERVAL_MS
        : false,
  })
}

/**
 * Upload a grades or attendance file.
 *
 * A file small enough to finish inside the request resolves with a terminal
 * job; a larger one resolves with `pending`/`processing` and is finished by a
 * worker afterwards (the job list polls itself until then). It posts to the
 * batch-import alias rather than `/data-import/jobs/` so the server pins the
 * import type.
 *
 * `sheet` optionally names the XLSX worksheet to import (its title, or its
 * 1-based position among the visible sheets), so a workbook that also carries
 * a README or a second dataset can still be uploaded.
 */
export function useFacultyImportJob() {
  const queryClient = useQueryClient()
  return useMutation<
    FacultyImportJob,
    Error,
    { file: File; importType: FacultyImportType; sheet?: string }
  >({
    mutationFn: async ({ file, importType, sheet }) => {
      const target = FACULTY_IMPORT_TYPES.find((t) => t.type === importType)
      if (!target) {
        throw new Error(`Unsupported import type: ${importType}`)
      }
      const body = new FormData()
      body.append("file", file)
      if (sheet?.trim()) body.append("sheet", sheet.trim())
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

/**
 * Attendance across the faculty's own sections.
 *
 * `/attendance/summary/` is already scoped by `AttendanceRecordViewSet`: a
 * faculty user only ever receives rows for their sections. Counts are summed
 * here; the rate treats late as attended, the same formula the parent academic
 * record uses. A section with no recorded days is `null`, not 0%.
 */
export function useFacultyAttendanceSummary() {
  return useQuery<FacultyAttendance>({
    queryKey: queryKeys.facultyAttendance,
    queryFn: async () => {
      const { data } = await apiClient.get<
        Array<{
          present_count: number
          late_count: number
          absent_count: number
          total_records: number
        }>
      >("/attendance/summary/")

      const present = data.reduce((sum, row) => sum + row.present_count, 0)
      const late = data.reduce((sum, row) => sum + row.late_count, 0)
      const absent = data.reduce((sum, row) => sum + row.absent_count, 0)
      const records = data.reduce((sum, row) => sum + row.total_records, 0)

      return {
        attendance_rate:
          records > 0 ? ((present + late) / records) * 100 : null,
        present,
        late,
        absent,
        records,
      }
    },
  })
}

/**
 * Behavioral notes for the faculty's students, newest first.
 *
 * The endpoint is guidance-scoped server-side, but a faculty user may already
 * read notes for students in their sections. Five rows are fetched so the
 * dashboard can show a short list and the exact `count` in one request.
 */
export function useFacultyBehavioralNotes() {
  return useQuery<FacultyBehaviorNotes>({
    queryKey: queryKeys.facultyBehaviorNotes,
    queryFn: async () => {
      const { data } = await apiClient.get<Page<BehavioralNoteRecord>>(
        "/guidance/behavioral-notes/?page_size=5"
      )
      return { total: data.count, recent: data.results }
    },
  })
}

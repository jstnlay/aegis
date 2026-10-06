/**
 * Admin domain API (PH11.9).
 *
 * Every endpoint and field below is copied from the backend, not inferred.
 * Each section records the permission class, the query scope and the response
 * shape as verified against the source, because three of them are subtly
 * different from each other.
 *
 * ---------------------------------------------------------------------------
 * §1 Administrator authority is role-based, not is_staff-based
 * ---------------------------------------------------------------------------
 * `UserListView`, `UserDetailView` and `UserCreateView` gate on
 * `core.permissions.IsAdminUser`, which tests `role == "admin"` (NFR-011). They
 * previously used DRF's stock `IsAdminUser`, which tests `is_staff` — and
 * `provision_qa_accounts` creates every QA account through `create_user`, which
 * leaves `is_staff=False`. So the QA administrator held `role="admin"` and was
 * still refused with HTTP 403 on the endpoints it administers. Fixed in PH11.9;
 * `is_staff` remains meaningful only for the Django admin site.
 *
 * ---------------------------------------------------------------------------
 * §2 Users: list, retrieve and create only
 * ---------------------------------------------------------------------------
 * These three views are the complete user-administration contract. There is
 * **no** update, deactivate, delete, role-reassignment or password-reset route
 * anywhere in the project. The screens in this module therefore expose exactly
 * these three operations and state plainly which are unavailable, rather than
 * rendering controls that could only fail.
 *
 * `UserSerializer` also makes `email`, `role` and `is_active` read-only
 * (SEC-001), so even the create response cannot set an administrator role
 * through this endpoint.
 *
 * ---------------------------------------------------------------------------
 * §3 Attendance is read-only for admin
 * ---------------------------------------------------------------------------
 * `AttendanceRecordViewSet.get_permissions()` gates create/update/partial_update
 * and destroy on `IsFacultyUser`. An administrator holds `role="admin"`, not
 * `faculty`, so every write returns 403. The admin attendance screen is
 * therefore an oversight view and says so; no write hook is defined here.
 * `GradeViewSet` is different: its `finalize` action *is* `IsAdminUser`, so an
 * admin can finalize a submitted grade.
 *
 * ---------------------------------------------------------------------------
 * §4 NFR-010: admin analytics stay aggregated
 * ---------------------------------------------------------------------------
 * NFR-010 requires administrators to view student data in aggregated or
 * anonymised form unless explicit consent is given. The endpoints used here
 * honour that: `school-wide` returns three scalars, `risk-distribution` returns
 * four counts, `grade-levels/comparison` returns one average per grade level.
 * None returns a student identifier.
 *
 * `/analytics/low-performance/` is the one exception in the existing API: it
 * returns `student_id` and `student_name`. That is a pre-existing endpoint and
 * the existing Admin dashboard already consumes it, so it is neither extended
 * nor removed here — but **no new admin screen is built on it**, and the
 * analytics page does not call it. Building a student-level table on top of it
 * is exactly what NFR-010 rules out; see docs/PH11.9_NOTE.md.
 *
 * ---------------------------------------------------------------------------
 * §5 Data import/export
 * ---------------------------------------------------------------------------
 * `ImportJobViewSet` allows only admin and faculty (`_ALLOWED_ROLES`), and
 * `http_method_names` restricts it to get/post/head/options, so there is no
 * delete or retry route. Jobs run **synchronously**: `create` calls
 * `_run_job` inline, so a job reaches a terminal state within the request. The
 * statuses below are the real `JobStatus` choices, including `partial`.
 *
 * Exports are three separate GET endpoints returning a file, not a job list:
 * grades and attendance for staff, students admin-only. Each requires
 * `?file_format=csv|xlsx` and rejects anything else with a 400.
 *
 * ---------------------------------------------------------------------------
 * §6 Audit log is read-only
 * ---------------------------------------------------------------------------
 * `AuditLogViewSet` is a `ReadOnlyModelViewSet` with
 * `http_method_names = ["get", "head", "options"]`, so no write route is mapped.
 * Its filters are bounded and explicit: `action`, `model_name`, `user`,
 * `object_id`, `search` (model_name/object_repr only), `start_time`, `end_time`.
 * There is no `search` over `changes`.
 *
 * ---------------------------------------------------------------------------
 * §7 CMS is a read-through proxy, with no authoring surface
 * ---------------------------------------------------------------------------
 * Content lives in Strapi. `CmsAnnouncementList`, `CmsResourceList` and their
 * detail routes are `ListAPIView`/`RetrieveAPIView` — read-only. The only
 * write path is `StrapiAnnouncementWebhookView`, which is `AllowAny` because
 * Strapi authenticates it separately, and it is not a CMS authoring API. So the
 * admin content screen is a browse-and-inspect view; no create/update form is
 * built, because the backend would reject it.
 *
 * The proxy returns 503 when Strapi is unreachable, which is a distinct state
 * from "no content" and is rendered as such.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useCallback, useMemo } from "react"

import { apiClient } from "@/lib/api"
import { fetchAllPages } from "@/lib/pagination"

/* ========================================================================== */
/* §1/§2 Users                                                                */
/* ========================================================================== */

export interface AdminUser {
  id: string
  email: string
  username: string
  first_name: string
  last_name: string
  role: UserRole
  phone_number: string | null
  address: string | null
  is_active: boolean
  created_at: string
  updated_at: string
}

export type UserRole = "student" | "parent" | "faculty" | "guidance" | "admin"

export const USER_ROLE_LABELS: Record<UserRole, string> = {
  student: "Student",
  parent: "Parent",
  faculty: "Faculty",
  guidance: "Guidance Counselor",
  admin: "Administrator",
}

export const USER_ROLES: readonly UserRole[] = [
  "student",
  "parent",
  "faculty",
  "guidance",
  "admin",
]

export interface CreateUserPayload {
  email: string
  username: string
  first_name: string
  last_name: string
  role: UserRole
  password: string
}

/**
 * Every user account.
 *
 * `GET /accounts/users/`. Administrator-only by role. The paginated envelope
 * applies, so `fetchAllPages` is correct here.
 */
export function useAdminUsers() {
  return useQuery<AdminUser[], Error>({
    queryKey: ["admin", "users"],
    queryFn: async () => {
      const { results } = await fetchAllPages<AdminUser>("/accounts/users/")
      return results
    },
  })
}

/** One user account. `GET /accounts/users/{id}/`. */
export function useAdminUser(userId: string | null) {
  return useQuery<AdminUser, Error>({
    queryKey: ["admin", "user", userId],
    enabled: Boolean(userId),
    queryFn: async () => {
      const { data } = await apiClient.get<AdminUser>(
        `/accounts/users/${userId ?? ""}/`
      )
      return data
    },
  })
}

/**
 * Create a user account. `POST /accounts/users/create/`.
 *
 * The only user mutation this project exposes. Note `UserCreateSerializer` does
 * not mark `role` read-only the way `UserSerializer` does, so a role *can* be
 * chosen here — but no update route exists, so this is the only point at which
 * a role can be set.
 */
export function useCreateUser() {
  const queryClient = useQueryClient()
  return useMutation<AdminUser, Error, CreateUserPayload>({
    mutationFn: async (payload) => {
      const { data } = await apiClient.post<AdminUser>(
        "/accounts/users/create/",
        payload
      )
      return data
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["admin", "users"] })
    },
  })
}

/* ========================================================================== */
/* Academic structure — IsAdminOrReadOnly, admin has full CRUD                 */
/* ========================================================================== */

/**
 * One row of the administrator faculty roster.
 *
 * `GET /accounts/faculty-profiles/` is administrator-only and exposes the
 * profile id (the value `SubjectAssignment.faculty` and `Section.adviser` both
 * take), the display name and the employee id. No contact details.
 */
export interface FacultyProfileSummary {
  id: string
  name: string
  employee_id: string
}

/** The faculty roster, for the subject-assignment and section pickers. */
export function useFacultyProfiles() {
  return useQuery<FacultyProfileSummary[], Error>({
    queryKey: ["admin", "faculty-profiles"],
    queryFn: async () => {
      const { results } = await fetchAllPages<FacultyProfileSummary>(
        "/accounts/faculty-profiles/"
      )
      return results
    },
  })
}

export interface AcademicYear {
  id: string
  name: string
  start_date: string
  end_date: string
  is_current: boolean
  created_at: string
  updated_at: string
}

export interface GradeLevel {
  id: string
  name: string
  level_number: number
}

export interface GradingPeriod {
  id: string
  academic_year: string
  academic_year_name: string
  name: string
  order: number
  start_date: string
  end_date: string
}

export interface Section {
  id: string
  name: string
  grade_level: string
  grade_level_name: string
  academic_year: string
  adviser: string | null
  adviser_name: string | null
}

export interface Subject {
  id: string
  name: string
  code: string
  grade_level: string
  grade_level_name: string
}

export interface SubjectAssignment {
  id: string
  subject: string
  subject_name: string
  subject_code: string
  faculty: string
  faculty_name: string
  section: string
  section_name: string
  academic_year: string
  academic_year_name: string
}

export interface Enrollment {
  id: string
  student: string
  student_name: string
  student_id: string
  section: string
  section_name: string
  academic_year: string
  academic_year_name: string
  date_enrolled: string
  is_active: boolean
}

/**
 * A paginated academic-structure list, plus its create/update/delete hooks.
 *
 * Every one of these viewsets uses `IsAdminOrReadOnly`, so admin has full CRUD
 * and every other authenticated role has read-only. That makes the write hooks
 * real for an administrator, unlike attendance (§3).
 */
function useAdminResource<T>({
  resource,
  queryKey,
}: {
  resource: string
  queryKey: readonly string[]
}) {
  const queryClient = useQueryClient()

  const list = useQuery<T[], Error>({
    queryKey,
    queryFn: async () => {
      const { results } = await fetchAllPages<T>(`/academics/${resource}/`)
      return results
    },
  })

  const invalidate = useCallback(() => {
    void queryClient.invalidateQueries({ queryKey })
  }, [queryClient, queryKey])

  const create = useMutation<T, Error, Partial<T>>({
    mutationFn: async (payload) => {
      const { data } = await apiClient.post<T>(
        `/academics/${resource}/`,
        payload
      )
      return data
    },
    onSuccess: invalidate,
  })

  const update = useMutation<T, Error, { id: string; payload: Partial<T> }>({
    mutationFn: async ({ id, payload }) => {
      const { data } = await apiClient.patch<T>(
        `/academics/${resource}/${id}/`,
        payload
      )
      return data
    },
    onSuccess: invalidate,
  })

  const remove = useMutation<void, Error, string>({
    mutationFn: async (id) => {
      await apiClient.delete(`/academics/${resource}/${id}/`)
    },
    onSuccess: invalidate,
  })

  return { list, create, update, remove }
}

export function useAcademicYears() {
  return useAdminResource<AcademicYear>({
    resource: "academic-years",
    queryKey: ["admin", "academic-years"],
  })
}

export function useGradeLevels() {
  return useAdminResource<GradeLevel>({
    resource: "grade-levels",
    queryKey: ["admin", "grade-levels"],
  })
}

export function useGradingPeriods() {
  return useAdminResource<GradingPeriod>({
    resource: "grading-periods",
    queryKey: ["admin", "grading-periods"],
  })
}

export function useSections() {
  return useAdminResource<Section>({
    resource: "sections",
    queryKey: ["admin", "sections"],
  })
}

export function useSubjects() {
  return useAdminResource<Subject>({
    resource: "subjects",
    queryKey: ["admin", "subjects"],
  })
}

export function useSubjectAssignments() {
  return useAdminResource<SubjectAssignment>({
    resource: "subject-assignments",
    queryKey: ["admin", "subject-assignments"],
  })
}

export function useEnrollments() {
  return useAdminResource<Enrollment>({
    resource: "enrollments",
    queryKey: ["admin", "enrollments"],
  })
}

/* ========================================================================== */
/* Grades — admin oversight plus the finalize action                          */
/* ========================================================================== */

export interface AdminGrade {
  id: string
  student: string
  student_name: string
  student_id: string
  subject_assignment: string
  subject_name: string
  subject_code: string
  section_name: string
  grading_period: string
  grading_period_name: string | null
  /** DRF DecimalField: a JSON string unless COERCE_DECIMAL_TO_STRING is off. */
  score: string | number | null
  letter_grade: string | null
  remarks: string | null
  encoded_by: string | null
  encoded_by_name: string | null
  status: "draft" | "submitted" | "finalized"
}

export const GRADE_STATUS_LABELS: Record<AdminGrade["status"], string> = {
  draft: "Draft",
  submitted: "Submitted",
  finalized: "Finalized",
}

/**
 * Every grade. `GET /academics/grades/`.
 *
 * `GradeViewSet.get_queryset()` returns the full table for `admin`. This is
 * oversight over grade records the backend already exposes to admin, not a new
 * student-level analytics surface — see the NFR-010 note at the top of this
 * module.
 */
export function useAdminGrades() {
  return useQuery<AdminGrade[], Error>({
    queryKey: ["admin", "grades"],
    queryFn: async () => {
      const { results } = await fetchAllPages<AdminGrade>("/academics/grades/")
      return results
    },
  })
}

/**
 * Finalize a submitted grade. `POST /academics/grades/{id}/finalize/`.
 *
 * `IsAdminUser` on the `finalize` action specifically — this is the one grade
 * write an administrator actually has. The action rejects a grade that is not
 * `submitted` with a 400, and the successful path sends the GRADE_POSTED
 * notification to the student and their linked parents.
 */
export function useFinalizeGrade() {
  const queryClient = useQueryClient()
  return useMutation<AdminGrade, Error, string>({
    mutationFn: async (gradeId) => {
      const { data } = await apiClient.post<AdminGrade>(
        `/academics/grades/${gradeId}/finalize/`
      )
      return data
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["admin", "grades"] })
    },
  })
}

/* ========================================================================== */
/* §3 Attendance — read-only oversight for admin                              */
/* ========================================================================== */

export interface AdminAttendanceRecord {
  id: string
  student: string
  student_name: string
  student_id_code: string
  section: string
  section_name: string
  date: string
  status: "present" | "late" | "absent"
  recorded_by: string
  recorded_by_name: string
  created_at: string
  updated_at: string
}

/**
 * Attendance oversight. `GET /attendance/records/`.
 *
 * Read-only by design — see §3. There is deliberately no create/update/delete
 * hook in this module, because the backend would answer 403 for an admin.
 */
export function useAdminAttendanceRecords(filters?: {
  section?: string
  dateFrom?: string
  dateTo?: string
  status?: string
}) {
  return useQuery<AdminAttendanceRecord[], Error>({
    queryKey: [
      "admin",
      "attendance",
      filters?.section ?? "",
      filters?.dateFrom ?? "",
      filters?.dateTo ?? "",
      filters?.status ?? "",
    ],
    queryFn: async () => {
      const params = new URLSearchParams()
      if (filters?.section) params.set("section", filters.section)
      if (filters?.dateFrom) params.set("date_from", filters.dateFrom)
      if (filters?.dateTo) params.set("date_to", filters.dateTo)
      if (filters?.status) params.set("status", filters.status)
      const qs = params.toString()
      const { results } = await fetchAllPages<AdminAttendanceRecord>(
        `/attendance/records/${qs ? `?${qs}` : ""}`
      )
      return results
    },
  })
}

export interface AttendanceSummaryRow {
  student: string
  student_name: string
  student_id_code: string
  section_name: string
  present_count: number
  late_count: number
  absent_count: number
  total_records: number
}

/**
 * Per-student attendance counts. `GET /attendance/summary/?section=`.
 *
 * A **bare array**, not the paginated envelope. `summary` is a view-level
 * action wired at `/attendance/summary/`, so `section` is a query parameter.
 */
export function useAdminAttendanceSummary(sectionId?: string | null) {
  return useQuery<AttendanceSummaryRow[], Error>({
    queryKey: ["admin", "attendance-summary", sectionId ?? ""],
    queryFn: async () => {
      const { data } = await apiClient.get<AttendanceSummaryRow[]>(
        `/attendance/summary/${sectionId ? `?section=${sectionId}` : ""}`
      )
      return data
    },
  })
}

/* ========================================================================== */
/* §4 Analytics — aggregated only                                             */
/* ========================================================================== */

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

export interface GradeLevelComparison {
  grade_level_id: string
  grade_level_name: string
  average: number | null
  grade_count: number
}

export interface SectionPerformance {
  section_id: string
  section_name: string
  grade_level: string
  total_students: number
  grade_average: number | null
  total_grades: number
}

/** `{status, data}` envelope. `GET /analytics/school-wide/`. */
export function useSchoolWideMetrics() {
  return useQuery<SchoolWideMetrics, Error>({
    queryKey: ["analytics", "school-wide"],
    queryFn: async () => {
      const { data } = await apiClient.get<{
        status: string
        data: SchoolWideMetrics
      }>("/analytics/school-wide/")
      return data.data
    },
  })
}

/**
 * `{status, data: {distribution, total_with_scores}}`.
 * `GET /analytics/risk-distribution/`.
 *
 * `RiskScore` has no API surface, so this reports zero unless the risk engine
 * has been run out of band. The screen renders that honestly rather than
 * implying a modelled risk picture that does not exist.
 */
export function useRiskDistribution() {
  return useQuery<
    { distribution: RiskDistribution; total_with_scores: number },
    Error
  >({
    queryKey: ["analytics", "risk-distribution"],
    queryFn: async () => {
      const { data } = await apiClient.get<{
        status: string
        data: { distribution: RiskDistribution; total_with_scores: number }
      }>("/analytics/risk-distribution/")
      return data.data
    },
  })
}

/**
 * One average per grade level. `GET /analytics/grade-levels/comparison/`.
 *
 * `{status, data: {grade_levels: [...]}}` — note the data object wraps the
 * array, unlike `school-wide` whose data *is* the object.
 */
export function useGradeLevelComparison() {
  return useQuery<GradeLevelComparison[], Error>({
    queryKey: ["analytics", "grade-level-comparison"],
    queryFn: async () => {
      const { data } = await apiClient.get<{
        status: string
        data: { grade_levels: GradeLevelComparison[] }
      }>("/analytics/grade-levels/comparison/")
      return data.data.grade_levels
    },
  })
}

/**
 * One grading period's identity, for ordering a period axis.
 *
 * `/analytics/subjects/trends/` keys its periods by name, so a trend chart
 * needs the academic order from somewhere. `GradingPeriod.order` is the field
 * the rest of the app already sorts periods by.
 */
export interface GradingPeriodRef {
  id: string
  name: string
  order: number
}

/* ========================================================================== */
/* 9b PH11.10 trends — real per-period and per-day series                       */
/* ========================================================================== */

/**
 * One grading period's average for one student.
 *
 * `GET /analytics/students/{id}/academic-trend/` is what the existing metrics
 * endpoint cannot provide: `latest_period_average` there is the *overall*
 * average restated, not a per-period figure, so it cannot form a series.
 *
 * `average` is `number | null`. Null means the period has recorded grades but no
 * score on any of them, which is a gap in the record rather than a zero.
 */
export interface AcademicTrendPeriod {
  period_id: string
  period: string
  order: number
  average: number | null
  grade_count: number
}

export interface AcademicTrend {
  student_id: string
  has_data: boolean
  periods: AcademicTrendPeriod[]
}

/** Per-day attendance counts for one student, ascending by date. */
export interface AttendanceTrendDay {
  date: string
  present: number
  late: number
  absent: number
  total: number
}

export interface AttendanceTrend {
  student_id?: string
  has_data?: boolean
  days: AttendanceTrendDay[]
}

export function useStudentAcademicTrend(studentId: string | null) {
  return useQuery<AcademicTrend, Error>({
    queryKey: ["analytics", "student-academic-trend", studentId],
    enabled: Boolean(studentId),
    queryFn: async () => {
      const { data } = await apiClient.get<{
        status: string
        data: AcademicTrend
      }>(`/analytics/students/${studentId ?? ""}/academic-trend/`)
      return data.data
    },
  })
}

export function useStudentAttendanceTrend(
  studentId: string | null,
  range?: { from?: string; to?: string }
) {
  return useQuery<AttendanceTrend, Error>({
    queryKey: [
      "analytics",
      "student-attendance-trend",
      studentId,
      range?.from ?? "",
      range?.to ?? "",
    ],
    enabled: Boolean(studentId),
    queryFn: async () => {
      const params = new URLSearchParams()
      if (range?.from) params.set("date_from", range.from)
      if (range?.to) params.set("date_to", range.to)
      const query = params.toString()
      const { data } = await apiClient.get<{
        status: string
        data: AttendanceTrend
      }>(
        `/analytics/students/${studentId ?? ""}/attendance-trend/${
          query ? `?${query}` : ""
        }`
      )
      return data.data
    },
  })
}

/** Per-period averages across the school. Staff or administrator. */
export function useSchoolWideAcademicTrend(academicYearId?: string | null) {
  return useQuery<{ periods: AcademicTrendPeriod[] }, Error>({
    queryKey: ["analytics", "school-wide-academic-trend", academicYearId ?? ""],
    queryFn: async () => {
      const { data } = await apiClient.get<{
        status: string
        data: { periods: AcademicTrendPeriod[] }
      }>(
        `/analytics/academic-trend/${
          academicYearId ? `?academic_year=${academicYearId}` : ""
        }`
      )
      return data.data
    },
  })
}

/** Per-day attendance counts across the school. Administrator only. */
export function useSchoolWideAttendanceTrend(range?: {
  from?: string
  to?: string
}) {
  return useQuery<AttendanceTrend, Error>({
    queryKey: [
      "analytics",
      "school-wide-attendance-trend",
      range?.from ?? "",
      range?.to ?? "",
    ],
    queryFn: async () => {
      const params = new URLSearchParams()
      if (range?.from) params.set("date_from", range.from)
      if (range?.to) params.set("date_to", range.to)
      const query = params.toString()
      const { data } = await apiClient.get<{
        status: string
        data: AttendanceTrend
      }>(`/analytics/attendance-trend/${query ? `?${query}` : ""}`)
      return data.data
    },
  })
}

/** The grading periods, in academic order. */
export function useGradingPeriodOrder() {
  const { list } = useAdminResource<GradingPeriod>({
    resource: "grading-periods",
    queryKey: ["admin", "grading-periods"],
  })
  return useMemo(
    () =>
      (list.data ?? [])
        .map((period) => ({
          id: period.id,
          name: period.name,
          order: period.order,
        }))
        .sort((a, b) => a.order - b.order),
    [list.data]
  )
}

/**
 * Subject averages per grading period.
 * `GET /analytics/subjects/trends/`.
 *
 * `{status, data: {subject_trends: {SUBJECT_CODE: {period_name: average}}}}`.
 * Periods are keyed by name, so callers order the axis themselves.
 */
export function useSubjectTrends() {
  return useQuery<Record<string, Record<string, number>>, Error>({
    queryKey: ["analytics", "subject-trends"],
    queryFn: async () => {
      const { data } = await apiClient.get<{
        status: string
        data: { subject_trends: Record<string, Record<string, number>> }
      }>("/analytics/subjects/trends/")
      return data.data.subject_trends
    },
  })
}

/** `{status, data}` for one section. `GET /analytics/sections/{id}/performance/`. */
export function useSectionPerformance(sectionId: string | null) {
  return useQuery<SectionPerformance, Error>({
    queryKey: ["analytics", "section-performance", sectionId],
    enabled: Boolean(sectionId),
    queryFn: async () => {
      const { data } = await apiClient.get<{
        status: string
        data: SectionPerformance
      }>(`/analytics/sections/${sectionId ?? ""}/performance/`)
      return data.data
    },
  })
}

/* ========================================================================== */
/* §5 Imports and exports                                                     */
/* ========================================================================== */

export type ImportJobStatus =
  "pending" | "processing" | "completed" | "failed" | "partial"

export const IMPORT_JOB_STATUS_LABELS: Record<ImportJobStatus, string> = {
  pending: "Pending",
  processing: "Processing",
  completed: "Completed",
  failed: "Failed",
  partial: "Partially completed",
}

export type ImportType =
  "grades" | "attendance" | "students" | "guidance_records"

export const IMPORT_TYPE_LABELS: Record<ImportType, string> = {
  grades: "Grades",
  attendance: "Attendance",
  students: "Students",
  guidance_records: "Guidance Records",
}

/**
 * `guidance_records` is accepted by `ImportType` and an admin may submit it, but
 * `_dispatch_domain_processing` has no guidance importer and falls through to
 * the legacy parse-only path: rows are validated and marked successful without
 * writing any domain record. The UI labels it so an admin is not misled into
 * thinking guidance rows were imported.
 */
export const IMPORT_TYPE_PARSES_ONLY: readonly ImportType[] = [
  "guidance_records",
]

export interface ImportJobSummary {
  id: string
  uploaded_by: { id: string; name: string }
  file_name: string
  import_type: ImportType
  status: ImportJobStatus
  total_rows: number
  processed_rows: number
  error_rows: number
  created_at: string
  completed_at: string | null
  record_summary: { success: number; error: number; skipped: number }
}

export interface ImportJobDetail extends ImportJobSummary {
  file_type: string
  error_log: Array<{ code: string; message: string }>
  records: Array<{
    id: string
    row_number: number
    data: Record<string, unknown>
    status: "success" | "error" | "skipped"
    error_message: string
    mapped_to_model: string | null
    mapped_to_id: string | null
  }>
}

/** Import jobs. `GET /data-import/jobs/` (admin sees every job). */
export function useImportJobs() {
  return useQuery<ImportJobSummary[], Error>({
    queryKey: ["admin", "import-jobs"],
    queryFn: async () => {
      const { results } =
        await fetchAllPages<ImportJobSummary>("/data-import/jobs/")
      return results
    },
  })
}

/** One job with its per-row results. `GET /data-import/jobs/{id}/`. */
export function useImportJob(jobId: string | null) {
  return useQuery<ImportJobDetail, Error>({
    queryKey: ["admin", "import-job", jobId],
    enabled: Boolean(jobId),
    queryFn: async () => {
      const { data } = await apiClient.get<ImportJobDetail>(
        `/data-import/jobs/${jobId ?? ""}/`
      )
      return data
    },
  })
}

/**
 * Upload a CSV or XLSX to import.
 *
 * The server detects the real type from the file's magic bytes, not the
 * extension, and the pipeline runs synchronously — so this resolves only once
 * the job has reached a terminal state. There is no separate "run" call.
 */
export function useCreateImportJob() {
  const queryClient = useQueryClient()
  return useMutation<
    ImportJobDetail,
    Error,
    { file: File; importType: ImportType }
  >({
    mutationFn: async ({ file, importType }) => {
      const body = new FormData()
      body.append("file", file)
      body.append("import_type", importType)
      const { data } = await apiClient.post<ImportJobDetail>(
        "/data-import/jobs/",
        body,
        { headers: { "Content-Type": "multipart/form-data" } }
      )
      return data
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["admin", "import-jobs"] })
    },
  })
}

export type ExportKind = "grades" | "attendance" | "students"

/**
 * Trigger a controlled export download.
 *
 * These are three separate GET endpoints returning a **file**, not a job
 * resource, so they are a download and not a query. `?file_format` is required
 * and anything other than csv/xlsx is rejected with a 400.
 *
 * `students` is admin-only; grades and attendance are available to staff.
 */
export async function downloadExport(
  kind: ExportKind,
  format: "csv" | "xlsx"
): Promise<void> {
  const response = await apiClient.get(`/data-import/exports/${kind}/`, {
    params: { file_format: format },
    responseType: "blob",
  })

  const filename = filenameFromDisposition(
    response.headers["content-disposition"]
  )
  const blobUrl = URL.createObjectURL(response.data as Blob)
  try {
    const anchor = document.createElement("a")
    anchor.href = blobUrl
    anchor.download = filename ?? `aegis-${kind}.${format}`
    document.body.appendChild(anchor)
    anchor.click()
    anchor.remove()
  } finally {
    // Releasing the object URL is not optional: without it the downloaded blob
    // is retained for the lifetime of the document.
    URL.revokeObjectURL(blobUrl)
  }
}

/**
 * Pull the filename out of a `Content-Disposition` header.
 *
 * The backend builds it with `build_content_disposition()`, which RFC 5987
 * encodes as `filename*=UTF-8''...`. The plain `filename="..."` parameter is
 * read as a fallback for the non-ASCII case.
 */
export function filenameFromDisposition(
  header: string | undefined | null
): string | null {
  if (!header) return null

  const extended = /filename\*=UTF-8''([^;]+)/i.exec(header)
  if (extended?.[1]) {
    try {
      return decodeURIComponent(extended[1])
    } catch {
      return extended[1]
    }
  }

  const plain = /filename="([^"]+)"/i.exec(header)
  return plain?.[1] ?? null
}

/* ========================================================================== */
/* §6 Audit log — read-only                                                   */
/* ========================================================================== */

export interface AuditLogEntry {
  id: string
  timestamp: string
  /** Minimal actor identity, or null for a system event. */
  user: { id: string; name: string } | null
  action: string
  model_name: string
  object_id: string | null
  object_repr: string
  /** The PH10.2/PH10.3-safe diff, returned exactly as stored. */
  changes: Record<string, unknown> | null
  ip_address: string | null
  user_agent: string | null
}

export interface AuditLogFilters {
  action?: string
  modelName?: string
  user?: string
  objectId?: string
  search?: string
  startTime?: string
  endTime?: string
}

export const AUDIT_ACTIONS: readonly string[] = [
  "create",
  "update",
  "delete",
  "login",
  "logout",
  "import",
  "export",
  "access",
]

/**
 * The audit trail. `GET /audit/logs/` — administrator-only, read-only.
 *
 * All filters map to the bounded query parameters the viewset implements.
 * `search` covers `model_name` and `object_repr` only; the view deliberately
 * does not search inside `changes`.
 */
export function useAuditLogs(filters: AuditLogFilters = {}) {
  return useQuery<AuditLogEntry[], Error>({
    queryKey: [
      "admin",
      "audit-logs",
      filters.action ?? "",
      filters.modelName ?? "",
      filters.user ?? "",
      filters.objectId ?? "",
      filters.search ?? "",
      filters.startTime ?? "",
      filters.endTime ?? "",
    ],
    queryFn: async () => {
      const params = new URLSearchParams()
      if (filters.action) params.set("action", filters.action)
      if (filters.modelName) params.set("model_name", filters.modelName)
      if (filters.user) params.set("user", filters.user)
      if (filters.objectId) params.set("object_id", filters.objectId)
      if (filters.search) params.set("search", filters.search)
      if (filters.startTime) params.set("start_time", filters.startTime)
      if (filters.endTime) params.set("end_time", filters.endTime)
      const qs = params.toString()
      const { results } = await fetchAllPages<AuditLogEntry>(
        `/audit/logs/${qs ? `?${qs}` : ""}`
      )
      return results
    },
  })
}

/* ========================================================================== */
/* §7 CMS — read-through proxy, no authoring                                  */
/* ========================================================================== */

export interface CmsAnnouncement {
  document_id: string
  title: string
  content: string
  announcement_type: "news" | "event" | "alert" | "academic"
  priority: "normal" | "high" | "urgent"
  target_roles: string[]
  target_sections: string[]
  published_at: string
  expires_at: string | null
}

export interface CmsResource {
  document_id: string
  title: string
  description?: string | null
  resource_type: "document" | "link" | "video" | "other"
  file_or_url?: string | null
  target_audience: string[]
  is_active: boolean
}

export const ANNOUNCEMENT_TYPE_LABELS: Record<
  CmsAnnouncement["announcement_type"],
  string
> = {
  news: "News",
  event: "Event",
  alert: "Alert",
  academic: "Academic",
}

export const ANNOUNCEMENT_PRIORITY_LABELS: Record<
  CmsAnnouncement["priority"],
  string
> = {
  normal: "Normal",
  high: "High priority",
  urgent: "Urgent",
}

export const RESOURCE_TYPE_LABELS: Record<
  CmsResource["resource_type"],
  string
> = {
  document: "Document",
  link: "Link",
  video: "Video",
  other: "Other",
}

/** Announcements visible to this caller. `GET /cms/announcements/`. */
export function useCmsAnnouncements() {
  return useQuery<CmsAnnouncement[], Error>({
    queryKey: ["admin", "cms-announcements"],
    queryFn: async () => {
      const { data } = await apiClient.get<CmsAnnouncement[]>(
        "/cms/announcements/"
      )
      return data
    },
  })
}

/** Resources visible to this caller. `GET /cms/resources/`. */
export function useCmsResources() {
  return useQuery<CmsResource[], Error>({
    queryKey: ["admin", "cms-resources"],
    queryFn: async () => {
      const { data } = await apiClient.get<CmsResource[]>("/cms/resources/")
      return data
    },
  })
}

/**
 * The CMS proxy route for a Strapi-hosted resource file.
 *
 * `GET /cms/resources/{document_id}/file/` is SEC-007: it proxies the file
 * through AEGIS with the caller's own access rules rather than exposing the
 * Strapi URL. It is *not* browsable as a link target — see
 * `downloadCmsResource`.
 */
export function cmsResourceFilePath(documentId: string): string {
  return `/cms/resources/${encodeURIComponent(documentId)}/file/`
}

/**
 * Download a CMS resource file with the caller's credentials.
 *
 * PH11.10. This was previously a plain `<a href>` pointing at the proxy, which
 * returned 401: authentication in this app is a bearer token injected by the
 * axios request interceptor, and a native anchor sends no such header. The
 * correct pattern already existed for exports (`downloadExport`), so this
 * mirrors it — request through `apiClient` so the token and the 401 refresh
 * path apply, then hand the bytes to the browser as an object URL.
 *
 * Rejects with the normalized API error so the caller can show it; a failed
 * download never becomes a silent success.
 */
export async function downloadCmsResource(documentId: string): Promise<void> {
  const response = await apiClient.get(cmsResourceFilePath(documentId), {
    responseType: "blob",
  })

  const filename =
    filenameFromDisposition(response.headers["content-disposition"]) ??
    "aegis-resource"
  const blobUrl = URL.createObjectURL(response.data as Blob)
  try {
    const anchor = document.createElement("a")
    anchor.href = blobUrl
    anchor.download = filename
    document.body.appendChild(anchor)
    anchor.click()
    anchor.remove()
  } finally {
    URL.revokeObjectURL(blobUrl)
  }
}

/**
 * Attendance domain API (PH11.7).
 *
 * Verified against:
 * - `apps/attendance/serializers.py` (AttendanceRecordSerializer, summary fields)
 * - `apps/attendance/views.py` (scopes, filters, update/delete self-scoped,
 *   create future-date rejection enforced by serializer, 1/student/date)
 * - `apps/attendance/urls/attendance.py`
 *
 * No `attendance/bulk-import` endpoints are invoked. Attendance summary is a
 * bare array (no pagination) with fields: student, student_name,
 * student_id_code, section_name, present_count, late_count, absent_count,
 * total_records. Grouped by student+section.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import { apiClient } from "@/lib/api"
import { fetchAllPages } from "@/lib/pagination"

export type AttendanceStatus = "present" | "late" | "absent"

export const ATTENDANCE_STATUSES: readonly AttendanceStatus[] = [
  "present",
  "late",
  "absent",
] as const

export const ATTENDANCE_STATUS_LABELS: Record<AttendanceStatus, string> = {
  present: "Present",
  late: "Late",
  absent: "Absent",
}

export interface AttendanceRecord {
  id: string
  student: string
  student_name: string
  student_id_code: string
  section: string
  section_name: string
  date: string
  status: AttendanceStatus
  recorded_by: string
  recorded_by_name: string
  created_at: string
  updated_at: string
}

export interface AttendanceSummaryEntry {
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
 * Per-section record counts by student (array form). A multi-section student
 * produces multiple rows — the consumer must aggregate if totals are desired.
 */
export type AttendanceSummary = AttendanceSummaryEntry[]

export interface CreateAttendancePayload {
  student: string
  section: string
  date: string
  status: AttendanceStatus
}

export interface UpdateAttendancePayload {
  student?: string
  section?: string
  date?: string
  status?: AttendanceStatus
}

/**
 * Alias documenting that the attendance wire shape matches the domain type
 * exactly — unlike `Grade.score`, no decimal coercion is needed here.
 */
type AttendanceRecordWire = AttendanceRecord

function keys() {
  return {
    records: ["attendance", "records"] as const,
    summary: (studentId?: string | null) =>
      ["attendance", "summary", studentId ?? "all"] as const,
  }
}

/**
 * Attendance records visible to the caller. Scoped server-side by role
 * (faculty see only their sections, students see only themselves). Can be
 * filtered via query params; the backend supports `student`, `section`,
 * `status`, `date_from`, `date_to`. No client-side ID filtering needed.
 */
export function useAttendanceRecords(
  filters: {
    student?: string
    section?: string
    status?: AttendanceStatus
    dateFrom?: string
    dateTo?: string
  } = {}
) {
  const params = new URLSearchParams()
  if (filters.student) params.set("student", filters.student)
  if (filters.section) params.set("section", filters.section)
  if (filters.status) params.set("status", filters.status)
  if (filters.dateFrom) params.set("date_from", filters.dateFrom)
  if (filters.dateTo) params.set("date_to", filters.dateTo)
  const qs = params.toString() ? `?${params.toString()}` : ""
  return useQuery<AttendanceRecord[], Error>({
    queryKey: ["attendance", "records", filters],
    queryFn: async () => {
      const { results } = await fetchAllPages<AttendanceRecordWire>(
        `/attendance/records/${qs}`
      )
      return results
    },
  })
}

/**
 * Attendance summary. Returns a bare array (not paginated). If `studentId` is
 * provided, the backend accepts `?student=<uuid>`; the caller may also pass
 * it to scope the React Query cache key.
 */
export function useAttendanceSummary(studentId?: string | null) {
  return useQuery<AttendanceSummary, Error>({
    queryKey: keys().summary(studentId),
    queryFn: async () => {
      const qs = studentId ? `?student=${studentId}` : ""
      const { data } = await apiClient.get<AttendanceSummaryEntry[]>(
        `/attendance/summary/${qs}`
      )
      return data
    },
  })
}

export function useCreateAttendance() {
  const queryClient = useQueryClient()
  return useMutation<AttendanceRecord, Error, CreateAttendancePayload>({
    mutationFn: async (payload) => {
      const { data } = await apiClient.post<AttendanceRecordWire>(
        "/attendance/records/",
        payload
      )
      return data
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["attendance"] })
    },
  })
}

/**
 * Updates a record. Backend-enforced self-scope — see the note on
 * `useDeleteAttendance` about why PH11.7 exposes no caller for this hook.
 */
export function useUpdateAttendance(recordId: string) {
  const queryClient = useQueryClient()
  return useMutation<AttendanceRecord, Error, UpdateAttendancePayload>({
    mutationFn: async (payload) => {
      const { data } = await apiClient.patch<AttendanceRecordWire>(
        `/attendance/records/${recordId}/`,
        payload
      )
      return data
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["attendance"] })
    },
  })
}

/**
 * Deletes a record. Backend-enforced self-scope: `AttendanceRecordViewSet`
 * compares `record.recorded_by.user` with the caller and returns 403 otherwise.
 *
 * PH11.7 deliberately ships no UI caller for this hook. `recorded_by` is a
 * `FacultyProfile` UUID, and `/accounts/me/` returns only the `User`, so the
 * frontend cannot authoritatively tell which rows are the caller's own. The
 * endpoint and its guard are unchanged; only the surface is withheld.
 */
export function useDeleteAttendance(recordId: string) {
  const queryClient = useQueryClient()
  return useMutation<void, Error, void>({
    mutationFn: async () => {
      await apiClient.delete(`/attendance/records/${recordId}/`)
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["attendance"] })
    },
  })
}

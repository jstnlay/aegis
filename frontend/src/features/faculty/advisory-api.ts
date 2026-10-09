import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import type { GradeLevel } from "@/features/admin/api"
import type { Enrollment, Section } from "@/features/academics/api"
import {
  type BehavioralNote,
  type BehavioralNoteType,
} from "@/features/guidance/api"
import { apiClient } from "@/lib/api"
import { fetchAllPages } from "@/lib/pagination"

/**
 * Advisory-class API for the faculty role.
 *
 * TC-FAC-07 / TC-FAC-08: a faculty member records behavioral notes for
 * students in their own sections. The backend already implements the whole
 * contract — `BehavioralNoteViewSet` accepts POST from `IsFacultyUser` only,
 * validates section access, rejects blank text ("Note text cannot be empty."),
 * and scopes the GET list to the caller's sections — so this module is the
 * frontend half: the roster to act on and the create mutation.
 *
 * TC-FAC-03 / TC-FAC-04: the same faculty member also manages the student
 * profiles in that roster (`PATCH /academics/student-profiles/{id}/`). The
 * endpoint's write contract requires every field — grade level, section,
 * guardian contact and date of birth — so a partially-filled update is
 * rejected by the server with the same envelope the form renders.
 */

const keys = {
  /**
   * Shares the guidance cache on purpose: `BehavioralNoteViewSet.get_queryset`
   * scopes by role, so the same endpoint serves both roles and one key keeps
   * them consistent after a faculty create.
   */
  behavioralNotes: ["guidance", "behavioral-notes"] as const,
  advisoryEnrollments: ["faculty", "advisory-enrollments"] as const,
} as const

/**
 * The roster this faculty member may act on.
 *
 * `EnrollmentViewSet.get_queryset` already limits faculty to sections they
 * advise or teach, so no client-side role logic is needed here. Inactive
 * enrollments are dropped because the backend's create path requires an
 * active enrollment, and offering a student the server would reject only
 * produces a failed save.
 */
export function useAdvisoryEnrollments() {
  return useQuery<Enrollment[], Error>({
    queryKey: keys.advisoryEnrollments,
    queryFn: async () => {
      const { results } = await fetchAllPages<Enrollment>(
        "/academics/enrollments/"
      )
      return results.filter((entry) => entry.is_active)
    },
  })
}

/** The create payload of `BehavioralNoteSerializer` (write fields only). */
export interface CreateBehavioralNotePayload {
  student: string
  note_type: BehavioralNoteType
  note_text: string
  /** `YYYY-MM-DD`; the server refuses a future date. */
  date_recorded: string
}

/**
 * Record a behavioral note (`POST /guidance/behavioral-notes/`).
 *
 * The server is the authority on scope and validity: a student outside the
 * faculty's sections answers 403, blank text answers 400 with
 * `note_text: ["Note text cannot be empty."]`. Both flow to the caller
 * through `normalizeApiError`, and nothing is optimistically inserted — the
 * saved note appears only when the server returns it.
 */
export function useCreateBehavioralNote() {
  const queryClient = useQueryClient()
  return useMutation<BehavioralNote, Error, CreateBehavioralNotePayload>({
    mutationFn: async (payload) => {
      const { data } = await apiClient.post<BehavioralNote>(
        "/guidance/behavioral-notes/",
        payload
      )
      return data
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: keys.behavioralNotes,
      })
    },
  })
}

/* -------------------------------------------------------------------------- */
/* Student profile management (TC-FAC-03 / TC-FAC-04)                          */
/* -------------------------------------------------------------------------- */

/** `StudentProfileManageSerializer` — the profile form's read model. */
export interface StudentProfileDetail {
  id: string
  student_name: string
  /** School-assigned ID, read-only on the wire. */
  student_id: string
  grade_level: string
  section: string
  guardian_contact: string | null
  date_of_birth: string | null
  is_active: boolean
}

/**
 * The write contract of `StudentProfileManageSerializer`.
 *
 * Every field is required server-side: an update missing one of them is a
 * 400, not a partial save (TC-FAC-04).
 */
export interface StudentProfileUpdatePayload {
  grade_level: string
  section: string
  guardian_contact: string
  date_of_birth: string
}

/**
 * Reference data for the form's two selects.
 *
 * `StudentProfileManageSerializer` rejects a section that does not belong to
 * the chosen grade level, so the form filters the section list locally to
 * keep the two choices consistent before the request is made.
 */
export function useProfileReferenceData() {
  const gradeLevels = useQuery<GradeLevel[], Error>({
    queryKey: ["faculty", "advisory", "grade-levels"],
    queryFn: async () => {
      const { results } = await fetchAllPages<GradeLevel>(
        "/academics/grade-levels/"
      )
      return results
    },
  })
  const sections = useQuery<Section[], Error>({
    queryKey: ["faculty", "advisory", "sections"],
    queryFn: async () => {
      const { results } = await fetchAllPages<Section>("/academics/sections/")
      return results
    },
  })

  return {
    gradeLevels: gradeLevels.data ?? [],
    sections: sections.data ?? [],
    isLoading: gradeLevels.isLoading || sections.isLoading,
    error: gradeLevels.error ?? sections.error,
  }
}

/**
 * GET a student profile for the manage form.
 *
 * Disabled until `studentId` is known so closing and reopening the dialog
 * does not refetch forever. An out-of-scope student (not enrolled in this
 * faculty's sections) answers 404, which the dialog surfaces as "not found"
 * rather than silently showing another roster member's data.
 */
export function useStudentProfile(studentId: string | null) {
  return useQuery<StudentProfileDetail, Error>({
    queryKey: ["faculty", "advisory", "student-profile", studentId],
    enabled: Boolean(studentId),
    queryFn: async () => {
      const { data } = await apiClient.get<StudentProfileDetail>(
        `/academics/student-profiles/${studentId}/`
      )
      return data
    },
  })
}

/**
 * PATCH a student profile (`PATCH /academics/student-profiles/{id}/`).
 *
 * Field-level 400s (missing guardian contact, a section from the wrong grade
 * level, a future date of birth) flow back through `normalizeApiError` and
 * are rendered per field from `error.details`.
 */
export function useUpdateStudentProfile(studentId: string | null) {
  const queryClient = useQueryClient()
  return useMutation<StudentProfileDetail, Error, StudentProfileUpdatePayload>({
    mutationFn: async (payload) => {
      const { data } = await apiClient.patch<StudentProfileDetail>(
        `/academics/student-profiles/${studentId}/`,
        payload
      )
      return data
    },
    onSuccess: () => {
      // Without this the dialog reopens on the cached pre-save profile: React
      // Query serves the stale copy first, so the form would show the values
      // the save just corrected. Invalidating forces the refetch that the
      // dialog's loading state waits on.
      void queryClient.invalidateQueries({
        queryKey: ["faculty", "advisory", "student-profile", studentId],
      })
    },
  })
}

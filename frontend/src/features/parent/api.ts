import { useQuery } from "@tanstack/react-query"
import { fetchAllPages } from "@/lib/pagination"

export interface LinkedStudent {
  id: string
  student_name: string
  student_id: string
  section_name: string
}

interface EnrollmentRecord {
  id: string
  student: string
  student_name: string
  student_id: string
  section_name: string
  is_active: boolean
}

export function useLinkedStudents() {
  return useQuery<LinkedStudent[]>({
    queryKey: ["parent", "linked-students"],
    queryFn: async () => {
      const { results } = await fetchAllPages<EnrollmentRecord>(
        "/academics/enrollments/"
      )
      // Deduplicate by StudentProfile UUID (enrollment `student` field).
      // NOTE: enrollment `id` is the Enrollment PK, not the student UUID.
      const studentMap = new Map<string, LinkedStudent>()
      for (const enrollment of results) {
        if (!studentMap.has(enrollment.student)) {
          studentMap.set(enrollment.student, {
            id: enrollment.student,
            student_name: enrollment.student_name,
            student_id: enrollment.student_id,
            section_name: enrollment.section_name,
          })
        }
      }
      return Array.from(studentMap.values())
    },
  })
}

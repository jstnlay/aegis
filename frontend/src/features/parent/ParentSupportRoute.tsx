import { useState } from "react"

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { useLinkedStudents } from "@/features/parent/api"
import { ParentSupportPage } from "@/features/parent/ParentSupportPage"

/**
 * Route-level child selection for the parent support view.
 *
 * The linked children come from `/academics/enrollments/`, which
 * `EnrollmentViewSet.get_queryset()` already scopes to `ParentStudentLink`
 * children. A child therefore cannot be selected from outside the set, and no
 * child UUID is accepted from the URL.
 */
export function ParentSupportRoute() {
  const [selectedChildId, setSelectedChildId] = useState<string>("")
  const linkedQuery = useLinkedStudents()
  const linked = linkedQuery.data ?? []
  const child = linked.find((c) => c.id === selectedChildId)

  return (
    <div className="space-y-6">
      <div className="space-y-1.5">
        <label htmlFor="parent-support-child" className="text-sm font-medium">
          Student
        </label>
        <Select value={selectedChildId} onValueChange={setSelectedChildId}>
          <SelectTrigger id="parent-support-child">
            <SelectValue placeholder="Select a student" />
          </SelectTrigger>
          <SelectContent>
            {linked.map((student) => (
              <SelectItem key={student.id} value={student.id}>
                {student.student_name} — {student.section_name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {child ? (
        <ParentSupportPage child={child} />
      ) : (
        <Card>
          <CardHeader>
            <CardTitle>No student selected</CardTitle>
            <CardDescription>
              Choose a linked student above to see the Guidance Office record.
            </CardDescription>
          </CardHeader>
          <CardContent />
        </Card>
      )}
    </div>
  )
}

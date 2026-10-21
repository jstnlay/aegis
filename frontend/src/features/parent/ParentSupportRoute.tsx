import { useEffect, useState } from "react"

import { ErrorNote, LoadingState } from "@/components/feedback/Feedback"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Label } from "@/components/ui/label"
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
 *
 * PH11.11. The picker had no loading, failure or empty state. `linked` fell back
 * to `[]`, so while the request was in flight the page rendered an empty,
 * disabled-looking select and then "No student selected — choose a linked student
 * above", which is an instruction to use a control that had nothing in it. After a
 * failure it showed exactly the same thing, so a broken request read as a parent
 * with no linked children. The three states are now separated, matching
 * `ChildPicker` in `ParentAcademicsPage`.
 */
export function ParentSupportRoute() {
  const [selectedChildId, setSelectedChildId] = useState<string>("")
  const linkedQuery = useLinkedStudents()
  const linked = linkedQuery.data ?? []
  const child = linked.find((c) => c.id === selectedChildId)

  // A parent with one child should land on that child's record, not on an
  // empty picker. Runs only while nothing is selected, so a deliberate
  // choice is never overwritten.
  useEffect(() => {
    const first = linked[0]
    if (!selectedChildId && first) {
      setSelectedChildId(first.id)
    }
  }, [linked, selectedChildId])

  if (linkedQuery.isLoading) {
    return <LoadingState label="Loading linked students" />
  }

  if (linkedQuery.isError) {
    return (
      <ErrorNote message="Unable to load linked students. Please try again." />
    )
  }

  if (linked.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>No linked students</CardTitle>
          <CardDescription>
            This account has no linked children, so there is no Guidance Office
            record to show. Please contact the school office.
          </CardDescription>
        </CardHeader>
        <CardContent />
      </Card>
    )
  }

  return (
    <div className="space-y-6">
      <div className="space-y-1.5">
        {/*
          `Label` rather than a bare `<label className="text-sm font-medium">`.
          The raw element rendered the system label at the browser's default size
          and weight, so this one control looked different from every other field
          label in the app — the shared primitive is what makes it consistent.
        */}
        <Label htmlFor="parent-support-child">Student</Label>
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

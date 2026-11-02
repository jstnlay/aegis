import { ErrorNote, LoadingState } from "@/components/feedback/Feedback"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { useLinkedStudents, useSelectedChild } from "@/features/parent/api"
import { ParentSupportPage } from "@/features/parent/ParentSupportPage"
import { ParentChildSelect } from "./ParentChildSelect"
import { ParentSelectionPrompt } from "./ParentStudentContext"

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
  const linkedQuery = useLinkedStudents()
  const linked = linkedQuery.data ?? []

  const { selectedChildId, setSelectedChildId, child } =
    useSelectedChild(linked)

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
    <div className="parent-page parent-support space-y-6">
      <ParentChildSelect
        id="parent-support-child"
        linked={linked}
        selectedId={selectedChildId}
        onSelect={setSelectedChildId}
      />

      {child ? (
        <ParentSupportPage key={child.id} child={child} />
      ) : (
        <ParentSelectionPrompt />
      )}
    </div>
  )
}

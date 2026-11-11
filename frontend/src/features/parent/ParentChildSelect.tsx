import { UserRound } from "lucide-react"
import {
  EmptyState,
  ErrorNote,
  PendingRegion,
} from "@/components/feedback/Feedback"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Skeleton } from "@/components/ui/skeleton"
import type { LinkedStudent } from "./api"

export function ParentChildSelect({
  id,
  label = "Student",
  linked,
  selectedId,
  onSelect,
  isLoading = false,
  error = false,
}: {
  id: string
  label?: string
  linked: readonly LinkedStudent[]
  selectedId: string
  onSelect: (id: string) => void
  isLoading?: boolean
  error?: boolean
}) {
  if (isLoading)
    return (
      <PendingRegion label="Linked students">
        <Skeleton className="h-16 w-full" />
      </PendingRegion>
    )
  if (error)
    return (
      <ErrorNote message="Unable to load linked students. Please try again." />
    )
  if (!linked.length)
    return (
      <EmptyState message="No linked students were found. Please contact the school office." />
    )
  const child = linked.find((student) => student.id === selectedId)
  return (
    <div className="parent-child-picker">
      <span className="parent-child-picker-icon" aria-hidden="true">
        <UserRound />
      </span>
      <div className="parent-child-picker-field">
        <Label htmlFor={id}>{label}</Label>
        <Select value={selectedId} onValueChange={onSelect}>
          <SelectTrigger id={id}>
            <SelectValue placeholder="Choose a student">
              {child ? (
                <span className="parent-child-selection">
                  <span className="parent-child-selection-name">
                    {child.student_name}
                  </span>
                  <span className="parent-child-selection-section">
                    {child.section_name || "Section not assigned"}
                  </span>
                </span>
              ) : undefined}
            </SelectValue>
          </SelectTrigger>
          <SelectContent>
            {linked.map((student) => (
              <SelectItem key={student.id} value={student.id}>
                {student.student_name} — {student.section_name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <p className="parent-child-picker-hint">
          {child
            ? "This student stays selected across the parent portal."
            : "Choose a student before viewing their records."}
        </p>
      </div>
    </div>
  )
}

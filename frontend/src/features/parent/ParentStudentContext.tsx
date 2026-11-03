import { UserRound } from "lucide-react"
import type { LinkedStudent } from "./api"

export function ParentStudentContext({ child }: { child: LinkedStudent }) {
  return (
    <div
      className="parent-viewing-student"
      role="status"
      aria-live="polite"
      aria-atomic="true"
    >
      <span className="parent-viewing-icon" aria-hidden="true">
        <UserRound />
      </span>
      <div>
        <p className="parent-viewing-label">Viewing student record</p>
        <h3>{child.student_name}</h3>
        <p className="parent-viewing-details">
          <span>{child.section_name}</span>
          <span>Student ID: {child.student_id}</span>
        </p>
      </div>
    </div>
  )
}

export function ParentSelectionPrompt() {
  return (
    <div className="parent-selection-prompt">
      <UserRound aria-hidden="true" />
      <h3>Select a student to get started</h3>
      <p>
        Their grades, attendance and school support information will appear
        here.
      </p>
    </div>
  )
}

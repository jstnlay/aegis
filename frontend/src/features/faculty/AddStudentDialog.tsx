import { useState, type FormEvent } from "react"

import { ErrorNote } from "@/components/feedback/Feedback"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { ChoiceField, Field } from "@/components/ui/form-field"
import {
  useCreateStudentProfile,
  useProfileReferenceData,
} from "@/features/faculty/advisory-api"
import { getFieldErrors, normalizeApiError } from "@/lib/error"

interface NewStudentForm {
  first_name: string
  last_name: string
  email: string
  student_id: string
  grade_level: string
  section: string
  guardian_contact: string
  date_of_birth: string
}

const EMPTY_NEW_STUDENT: NewStudentForm = {
  first_name: "",
  last_name: "",
  email: "",
  student_id: "",
  grade_level: "",
  section: "",
  guardian_contact: "",
  date_of_birth: "",
}

/**
 * Add a student (FR-007 / TC-FAC-03).
 *
 * One submit creates the account, profile and enrollment server-side, so the
 * form carries the identity fields as well as the profile fields. The student
 * never gets a caller-chosen password: the server mails a set-password link.
 *
 * The same dialog serves faculty and administrators. A faculty member's
 * section list is already scoped to the sections they advise or teach; an
 * administrator receives every section. The server repeats both checks.
 */
export function AddStudentDialog({
  open,
  onClose,
  onCreated,
}: {
  open: boolean
  onClose: () => void
  onCreated: (fullName: string) => void
}) {
  const reference = useProfileReferenceData()
  const createStudent = useCreateStudentProfile()
  const [form, setForm] = useState<NewStudentForm>(EMPTY_NEW_STUDENT)

  const fieldErrors = createStudent.isError
    ? getFieldErrors(createStudent.error)
    : null

  const set = (patch: Partial<NewStudentForm>) =>
    setForm((current) => ({ ...current, ...patch }))

  const sectionOptions = reference.sections
    .filter(
      (section) => !form.grade_level || section.grade_level === form.grade_level
    )
    .map((section) => ({ value: section.id, label: section.name }))

  const onSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    createStudent.mutate(form, {
      onSuccess: (profile) => {
        setForm(EMPTY_NEW_STUDENT)
        createStudent.reset()
        onCreated(profile.student_name)
      },
    })
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) {
          createStudent.reset()
          onClose()
        }
      }}
    >
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Add student</DialogTitle>
          <DialogDescription>
            Creates the student account and enrolls them in a section. The
            student receives an email link to set their password.
          </DialogDescription>
        </DialogHeader>

        <form
          className="space-y-3"
          id="add-student-form"
          onSubmit={onSubmit}
          noValidate
        >
          <div className="grid gap-3 sm:grid-cols-2">
            <Field
              label="First name"
              id="new-student-first-name"
              required
              value={form.first_name}
              onChange={(value) => set({ first_name: value })}
              error={fieldErrors?.first_name?.[0] ?? null}
            />
            <Field
              label="Last name"
              id="new-student-last-name"
              required
              value={form.last_name}
              onChange={(value) => set({ last_name: value })}
              error={fieldErrors?.last_name?.[0] ?? null}
            />
          </div>
          <Field
            label="Email"
            id="new-student-email"
            required
            type="text"
            value={form.email}
            onChange={(value) => set({ email: value })}
            error={fieldErrors?.email?.[0] ?? null}
            hint="The set-password link is sent to this address."
          />
          <Field
            label="Student ID"
            id="new-student-id"
            required
            value={form.student_id}
            onChange={(value) => set({ student_id: value })}
            error={fieldErrors?.student_id?.[0] ?? null}
          />
          <ChoiceField
            label="Grade level"
            id="new-student-grade-level"
            required
            value={form.grade_level}
            onChange={(value) => set({ grade_level: value, section: "" })}
            options={reference.gradeLevels.map((level) => ({
              value: level.id,
              label: level.name,
            }))}
            error={fieldErrors?.grade_level?.[0] ?? null}
          />
          <ChoiceField
            label="Section"
            id="new-student-section"
            required
            value={form.section}
            onChange={(value) => set({ section: value })}
            options={sectionOptions}
            error={fieldErrors?.section?.[0] ?? null}
            hint={
              form.grade_level && sectionOptions.length === 0
                ? "No section you can add students to is open in this grade level."
                : undefined
            }
          />
          <Field
            label="Guardian contact"
            id="new-student-guardian"
            required
            value={form.guardian_contact}
            onChange={(value) => set({ guardian_contact: value })}
            error={fieldErrors?.guardian_contact?.[0] ?? null}
            placeholder="09XX-XXX-XXXX"
          />
          <Field
            label="Date of birth"
            id="new-student-date-of-birth"
            required
            type="date"
            value={form.date_of_birth}
            onChange={(value) => set({ date_of_birth: value })}
            error={fieldErrors?.date_of_birth?.[0] ?? null}
          />

          {createStudent.isError &&
          (!fieldErrors || Object.keys(fieldErrors).length === 0) ? (
            <ErrorNote
              message={normalizeApiError(createStudent.error).message}
            />
          ) : null}
        </form>

        <DialogFooter>
          <Button
            type="button"
            variant="outline"
            onClick={() => {
              createStudent.reset()
              onClose()
            }}
          >
            Cancel
          </Button>
          <Button
            type="submit"
            form="add-student-form"
            disabled={createStudent.isPending}
          >
            {createStudent.isPending ? "Adding…" : "Add student"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

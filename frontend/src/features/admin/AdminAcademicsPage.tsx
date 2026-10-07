import { ChoiceField, Field } from "@/components/ui/form-field"
import { Tabs, type TabItem } from "@/components/ui/tabs"
import { BookOpen } from "lucide-react"
import { useState } from "react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { DataTable, type DataTableColumn } from "@/components/ui/data-table"
import { useDataTablePagination } from "@/components/ui/data-table-pagination"
import { ErrorNote } from "@/components/feedback/Feedback"
import {
  useAcademicYears,
  useEnrollments,
  useGradeLevels,
  useGradingPeriods,
  useFacultyProfiles,
  useSections,
  useSubjects,
  useSubjectAssignments,
  type AcademicYear,
  type Enrollment,
  type GradeLevel,
  type GradingPeriod,
  type Section,
  type Subject,
  type SubjectAssignment,
} from "@/features/admin/api"
import { getFieldErrors, normalizeApiError } from "@/lib/error"

/**
 * Academic structure administration.
 *
 * Covers the models the backend actually supports: AcademicYear, GradeLevel,
 * Section, Subject, SubjectAssignment, GradingPeriod and Enrollment. Each is a
 * `ModelViewSet` behind `IsAdminOrReadOnly`, so an administrator has genuine
 * create/edit/delete — unlike attendance, whose write path is faculty-only.
 *
 * Enrollment sits on this page rather than having its own because it shares the
 * section and academic-year lookups and is one more row in the same structure.
 *
 * `Schedule` is deliberately absent. `ScheduleViewSet` is also
 * `IsAdminOrReadOnly`, but a timetable editor is not a requirement here and the
 * only server-side rule is start-before-end, so a form built here would offer
 * almost no validation.
 *
 * Each card owns its own form state. An earlier draft factored the fields into
 * a shared component that stashed values in hidden inputs and read them back at
 * submit time; that couples the form to the DOM and makes required-field
 * behaviour invisible, so each card keeps plain `useState` instead.
 */

type Tab =
  | "academic-years"
  | "grade-levels"
  | "sections"
  | "subjects"
  | "assignments"
  | "grading-periods"
  | "enrollments"

export function AdminAcademicsPage() {
  const [tab, setTab] = useState<Tab>("sections")

  /*
    PH11.12: id, label and content are declared once. PH11.11 introduced the
    shared `Tabs`, which needs each tab's *content* alongside its label, and the
    first draft kept the old label-only array and recovered the labels with
    `TABS.find(t => t.id === …)!.label` — seven linear scans, seven non-null
    assertions, and two places to change when a tab is added or renamed. One
    array, typed so the tab state and the panels cannot drift apart.
  */
  const tabs: readonly TabItem<Tab>[] = [
    {
      id: "academic-years",
      label: "Academic years",
      content: <AcademicYearsCard />,
    },
    { id: "grade-levels", label: "Grade levels", content: <GradeLevelsCard /> },
    { id: "sections", label: "Sections", content: <SectionsCard /> },
    { id: "subjects", label: "Subjects", content: <SubjectsCard /> },
    {
      id: "assignments",
      label: "Subject assignments",
      content: <SubjectAssignmentsCard />,
    },
    {
      id: "grading-periods",
      label: "Grading periods",
      content: <GradingPeriodsCard />,
    },
    { id: "enrollments", label: "Enrollments", content: <EnrollmentsCard /> },
  ]

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-1">
        <div className="flex items-center gap-3">
          <BookOpen
            className="size-5 text-muted-foreground"
            aria-hidden="true"
          />
          <h2 className="text-2xl font-bold text-foreground">
            Academic Structure
          </h2>
        </div>
        <p className="text-sm text-muted-foreground">
          The academic year, grade levels, sections, subjects, subject
          assignments, grading periods and enrollments. Administrators have full
          create and delete on all of these.
        </p>
      </div>

      {/* PH11.11: shared `Tabs` — adds `aria-controls`, a real `tabpanel`, and
          arrow-key roving focus across all seven tabs. See
          `components/ui/tabs.tsx`. */}
      <Tabs
        label="Academic structure"
        value={tab}
        onValueChange={setTab}
        items={tabs}
      />
    </div>
  )
}

/** Rows per page for the tables that grow without a bound. */
const PAGE_SIZE = 25

/** Page sizes offered for those tables. */
const PAGE_SIZE_OPTIONS = [25, 50, 100] as const

/**
 * Delete button plus its pending state, shared by every table's Actions column.
 *
 * `size="sm"` replaced `size="xs"` in PH11.11. `xs` is `h-6` — 24px — which is
 * below PH11.2 §16.6's stated 32px floor for buttons, before its ~44px
 * practical target is even considered, and this is the destructive control in
 * every one of these tables, where a mis-tap is not recoverable.
 *
 * Only this control is widened. PH11.4 recorded that the shared design system's
 * 36px control height is deliberately not being widened to chase a larger touch
 * target, and that decision is not this phase's to overturn; `sm` (`h-8`, 32px)
 * meets the documented minimum without touching the system.
 *
 * `aria-label` added in the same pass: the button's accessible name was the bare
 * word "Delete", repeated once per row, so a screen reader's button list read
 * "Delete, Delete, Delete…" with no way to tell the rows apart. `subject` names
 * what is being deleted.
 */
function DeleteButton({
  onDelete,
  pending,
  subject,
}: {
  onDelete: () => void
  pending: boolean
  /** Identifies the row, so the control is distinguishable from every other. */
  subject: string
}) {
  return (
    <Button
      type="button"
      variant="destructive"
      size="sm"
      disabled={pending}
      onClick={onDelete}
      aria-label={`Delete ${subject}`}
    >
      Delete
    </Button>
  )
}

function AcademicYearsCard() {
  const { list, create, remove } = useAcademicYears()
  const [form, setForm] = useState({ name: "", start_date: "", end_date: "" })
  const fieldErrors = useFieldErrors(create.error)
  const canSubmit =
    form.name.trim() !== "" && form.start_date !== "" && form.end_date !== ""

  const columns: readonly DataTableColumn<AcademicYear>[] = [
    {
      key: "name",
      header: "Name",
      cell: (row) => (
        <div className="flex items-center gap-2">
          <span className="font-medium">{row.name}</span>
          {row.is_current ? <Badge variant="secondary">Current</Badge> : null}
        </div>
      ),
    },
    {
      key: "dates",
      header: "Dates",
      cell: (row) => (
        <span className="text-sm text-muted-foreground">
          {row.start_date} → {row.end_date}
        </span>
      ),
    },
    {
      key: "actions",
      header: "Actions",
      cell: (row) => (
        <DeleteButton
          pending={remove.isPending}
          subject={row.name}
          onDelete={() => remove.mutate(row.id)}
        />
      ),
    },
  ]

  return (
    <Card>
      <CardHeader>
        <CardTitle>Academic years</CardTitle>
        <CardDescription>
          Only one year may be current — `AcademicYearSerializer` rejects a
          second with a field-level validation error.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <form
          className="space-y-3"
          onSubmit={(event) => {
            event.preventDefault()
            if (!canSubmit) return
            create.mutate(
              {
                name: form.name.trim(),
                start_date: form.start_date,
                end_date: form.end_date,
              },
              {
                onSuccess: () =>
                  setForm({ name: "", start_date: "", end_date: "" }),
              }
            )
          }}
        >
          <div className="grid gap-3 sm:grid-cols-3">
            <Field
              label="Name"
              id="new-year-name"
              required
              placeholder="SY 2026-2027"
              value={form.name}
              error={fieldErrors.name}
              onChange={(name) => setForm({ ...form, name })}
            />
            <Field
              label="Start date"
              id="new-year-start"
              type="date"
              required
              value={form.start_date}
              error={fieldErrors.start_date}
              onChange={(start_date) => setForm({ ...form, start_date })}
            />
            <Field
              label="End date"
              id="new-year-end"
              type="date"
              required
              value={form.end_date}
              error={fieldErrors.end_date}
              onChange={(end_date) => setForm({ ...form, end_date })}
            />
          </div>
          <CreateError error={create.error} fieldErrors={fieldErrors} />
          <Button type="submit" disabled={!canSubmit || create.isPending}>
            {create.isPending ? "Saving…" : "Create academic year"}
          </Button>
        </form>

        <DataTable
          caption="Academic years"
          columns={columns}
          rows={list.data ?? []}
          rowKey={(row) => row.id}
          isLoading={list.isLoading}
          error={list.isError ? normalizeApiError(list.error).message : null}
          loadingLabel="Loading academic years"
          emptyMessage="No academic years have been created."
        />
      </CardContent>
    </Card>
  )
}

function GradeLevelsCard() {
  const { list, create, remove } = useGradeLevels()
  const [form, setForm] = useState({ name: "", level_number: "" })
  const fieldErrors = useFieldErrors(create.error)
  const canSubmit = form.name.trim() !== "" && form.level_number !== ""

  const columns: readonly DataTableColumn<GradeLevel>[] = [
    {
      key: "name",
      header: "Name",
      cell: (row) => <span className="font-medium">{row.name}</span>,
    },
    {
      key: "level",
      header: "Level number",
      cell: (row) => <span>{row.level_number}</span>,
    },
    {
      key: "actions",
      header: "Actions",
      cell: (row) => (
        <DeleteButton
          pending={remove.isPending}
          subject={row.name}
          onDelete={() => remove.mutate(row.id)}
        />
      ),
    },
  ]

  return (
    <Card>
      <CardHeader>
        <CardTitle>Grade levels</CardTitle>
        <CardDescription>
          Every section, subject and academic record resolves to one of these.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <form
          className="space-y-3"
          onSubmit={(event) => {
            event.preventDefault()
            if (!canSubmit) return
            create.mutate(
              {
                name: form.name.trim(),
                level_number: Number(form.level_number),
              },
              { onSuccess: () => setForm({ name: "", level_number: "" }) }
            )
          }}
        >
          <div className="grid gap-3 sm:grid-cols-2">
            <Field
              label="Name"
              id="new-level-name"
              required
              placeholder="Grade 8"
              value={form.name}
              error={fieldErrors.name}
              onChange={(name) => setForm({ ...form, name })}
            />
            <Field
              label="Level number"
              id="new-level-number"
              type="number"
              required
              min={1}
              value={form.level_number}
              error={fieldErrors.level_number}
              onChange={(level_number) => setForm({ ...form, level_number })}
            />
          </div>
          <CreateError error={create.error} fieldErrors={fieldErrors} />
          <Button type="submit" disabled={!canSubmit || create.isPending}>
            {create.isPending ? "Saving…" : "Create grade level"}
          </Button>
        </form>

        <DataTable
          caption="Grade levels"
          columns={columns}
          rows={list.data ?? []}
          rowKey={(row) => row.id}
          isLoading={list.isLoading}
          error={list.isError ? normalizeApiError(list.error).message : null}
          loadingLabel="Loading grade levels"
          emptyMessage="No grade levels have been created."
        />
      </CardContent>
    </Card>
  )
}

function SectionsCard() {
  const { list, create, remove } = useSections()
  const { list: levels } = useGradeLevels()
  const { list: years } = useAcademicYears()
  const facultyRoster = useFacultyProfiles()

  /*
   * The adviser picker reads the same administrator-only roster as the
   * subject-assignment picker, so both name every faculty member rather than
   * only those already teaching an existing assignment.
   */
  const faculty = (facultyRoster.data ?? []).map((profile) => ({
    value: profile.id,
    label: `${profile.name} (${profile.employee_id})`,
  }))

  const [form, setForm] = useState({
    name: "",
    grade_level: "",
    academic_year: "",
    adviser: "",
  })
  const fieldErrors = useFieldErrors(create.error)
  const canSubmit =
    form.name.trim() !== "" &&
    form.grade_level !== "" &&
    form.academic_year !== ""

  const columns: readonly DataTableColumn<Section>[] = [
    {
      key: "name",
      header: "Section",
      cell: (row) => <span className="font-medium">{row.name}</span>,
    },
    {
      key: "grade_level",
      header: "Grade level",
      cell: (row) => <span>{row.grade_level_name}</span>,
    },
    {
      key: "adviser",
      header: "Adviser",
      cell: (row) => (
        <span className="text-sm text-muted-foreground">
          {row.adviser_name || "Unassigned"}
        </span>
      ),
    },
    {
      key: "actions",
      header: "Actions",
      cell: (row) => (
        <DeleteButton
          pending={remove.isPending}
          subject={row.name}
          onDelete={() => remove.mutate(row.id)}
        />
      ),
    },
  ]

  return (
    <Card>
      <CardHeader>
        <CardTitle>Sections</CardTitle>
        <CardDescription>
          A section belongs to one grade level within one academic year.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <form
          className="space-y-3"
          onSubmit={(event) => {
            event.preventDefault()
            if (!canSubmit) return
            create.mutate(
              {
                name: form.name.trim(),
                grade_level: form.grade_level,
                academic_year: form.academic_year,
                adviser: form.adviser || null,
              },
              {
                onSuccess: () =>
                  setForm({
                    name: "",
                    grade_level: "",
                    academic_year: "",
                    adviser: "",
                  }),
              }
            )
          }}
        >
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Field
              label="Name"
              id="new-section-name"
              required
              placeholder="Bonifacio"
              value={form.name}
              error={fieldErrors.name}
              onChange={(name) => setForm({ ...form, name })}
            />
            <ChoiceField
              label="Grade level"
              id="new-section-grade"
              required
              value={form.grade_level}
              error={fieldErrors.grade_level}
              onChange={(value) => setForm({ ...form, grade_level: value })}
              options={(levels.data ?? []).map((level) => ({
                value: level.id,
                label: level.name,
              }))}
            />
            <ChoiceField
              label="Academic year"
              id="new-section-year"
              required
              value={form.academic_year}
              error={fieldErrors.academic_year}
              onChange={(value) => setForm({ ...form, academic_year: value })}
              options={(years.data ?? []).map((year) => ({
                value: year.id,
                label: year.name,
              }))}
            />
            <ChoiceField
              label="Adviser"
              id="new-section-adviser"
              value={form.adviser}
              error={fieldErrors.adviser}
              onChange={(value) => setForm({ ...form, adviser: value })}
              options={faculty}
              optional
              emptyLabel={
                facultyRoster.isLoading
                  ? "Loading faculty…"
                  : facultyRoster.isError
                    ? "Faculty could not be loaded."
                    : "No faculty accounts exist yet."
              }
            />
          </div>
          <CreateError error={create.error} fieldErrors={fieldErrors} />
          <Button type="submit" disabled={!canSubmit || create.isPending}>
            {create.isPending ? "Saving…" : "Create section"}
          </Button>
        </form>

        <DataTable
          caption="Sections"
          columns={columns}
          rows={list.data ?? []}
          rowKey={(row) => row.id}
          isLoading={list.isLoading}
          error={list.isError ? normalizeApiError(list.error).message : null}
          loadingLabel="Loading sections"
          emptyMessage="No sections have been created."
        />
      </CardContent>
    </Card>
  )
}

function SubjectsCard() {
  const { list, create, remove } = useSubjects()
  const { list: levels } = useGradeLevels()
  const [form, setForm] = useState({ name: "", code: "", grade_level: "" })
  const fieldErrors = useFieldErrors(create.error)
  const canSubmit =
    form.name.trim() !== "" &&
    form.code.trim() !== "" &&
    form.grade_level !== ""

  const columns: readonly DataTableColumn<Subject>[] = [
    {
      key: "name",
      header: "Name",
      cell: (row) => <span className="font-medium">{row.name}</span>,
    },
    {
      key: "code",
      header: "Code",
      cell: (row) => <span className="text-sm">{row.code}</span>,
    },
    {
      key: "grade_level",
      header: "Grade level",
      cell: (row) => <span>{row.grade_level_name}</span>,
    },
    {
      key: "actions",
      header: "Actions",
      cell: (row) => (
        <DeleteButton
          pending={remove.isPending}
          subject={row.name}
          onDelete={() => remove.mutate(row.id)}
        />
      ),
    },
  ]

  return (
    <Card>
      <CardHeader>
        <CardTitle>Subjects</CardTitle>
        <CardDescription>
          `Subject.code` is globally unique across the whole school.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <form
          className="space-y-3"
          onSubmit={(event) => {
            event.preventDefault()
            if (!canSubmit) return
            create.mutate(
              {
                name: form.name.trim(),
                code: form.code.trim(),
                grade_level: form.grade_level,
              },
              {
                onSuccess: () =>
                  setForm({ name: "", code: "", grade_level: "" }),
              }
            )
          }}
        >
          <div className="grid gap-3 sm:grid-cols-3">
            <Field
              label="Name"
              id="new-subject-name"
              required
              placeholder="Mathematics"
              value={form.name}
              error={fieldErrors.name}
              onChange={(name) => setForm({ ...form, name })}
            />
            <Field
              label="Code"
              id="new-subject-code"
              required
              placeholder="MATH-8"
              value={form.code}
              error={fieldErrors.code}
              onChange={(code) => setForm({ ...form, code })}
            />
            <ChoiceField
              label="Grade level"
              id="new-subject-grade"
              required
              value={form.grade_level}
              error={fieldErrors.grade_level}
              onChange={(value) => setForm({ ...form, grade_level: value })}
              options={(levels.data ?? []).map((level) => ({
                value: level.id,
                label: level.name,
              }))}
            />
          </div>
          <CreateError error={create.error} fieldErrors={fieldErrors} />
          <Button type="submit" disabled={!canSubmit || create.isPending}>
            {create.isPending ? "Saving…" : "Create subject"}
          </Button>
        </form>

        <DataTable
          caption="Subjects"
          columns={columns}
          rows={list.data ?? []}
          rowKey={(row) => row.id}
          isLoading={list.isLoading}
          error={list.isError ? normalizeApiError(list.error).message : null}
          loadingLabel="Loading subjects"
          emptyMessage="No subjects have been created."
        />
      </CardContent>
    </Card>
  )
}

function SubjectAssignmentsCard() {
  const { list, create, remove } = useSubjectAssignments()
  const { list: subjects } = useSubjects()
  const { list: sections } = useSections()
  const { list: years } = useAcademicYears()
  const facultyRoster = useFacultyProfiles()

  /*
   * `SubjectAssignment.faculty` is a required foreign key. PH11.10 added
   * GET /accounts/faculty-profiles/ (administrator-only, PH11.10 test
   * `FacultyProfileListTest`), so the picker is populated from real faculty
   * records rather than omitted and left to fail as a 400.
   */
  const [form, setForm] = useState({
    subject: "",
    section: "",
    academic_year: "",
    faculty: "",
  })
  const fieldErrors = useFieldErrors(create.error)
  const canSubmit =
    form.subject !== "" &&
    form.section !== "" &&
    form.academic_year !== "" &&
    form.faculty !== ""

  const columns: readonly DataTableColumn<SubjectAssignment>[] = [
    {
      key: "subject",
      header: "Subject",
      cell: (row) => (
        <div className="min-w-0">
          <div className="font-medium">{row.subject_name}</div>
          <div className="text-xs text-muted-foreground">
            {row.subject_code}
          </div>
        </div>
      ),
    },
    {
      key: "section",
      header: "Section",
      cell: (row) => <span>{row.section_name}</span>,
    },
    {
      key: "faculty",
      header: "Faculty",
      cell: (row) => (
        <span className="text-sm text-muted-foreground">
          {row.faculty_name || "Unassigned"}
        </span>
      ),
    },
    {
      key: "actions",
      header: "Actions",
      cell: (row) => (
        <DeleteButton
          pending={remove.isPending}
          subject={`${row.subject_name} in ${row.section_name}`}
          onDelete={() => remove.mutate(row.id)}
        />
      ),
    },
  ]

  return (
    <Card>
      <CardHeader>
        <CardTitle>Subject assignments</CardTitle>
        <CardDescription>
          Which subject is taught to which section. This is what scopes a
          faculty member&apos;s grade-encoding and attendance-write access.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <form
          className="space-y-3"
          onSubmit={(event) => {
            event.preventDefault()
            if (!canSubmit) return
            create.mutate(
              {
                subject: form.subject,
                section: form.section,
                academic_year: form.academic_year,
                faculty: form.faculty,
              },
              {
                onSuccess: () =>
                  setForm({
                    subject: "",
                    section: "",
                    academic_year: "",
                    faculty: "",
                  }),
              }
            )
          }}
        >
          <div className="grid gap-3 sm:grid-cols-3">
            <ChoiceField
              label="Subject"
              id="new-assignment-subject"
              required
              value={form.subject}
              error={fieldErrors.subject}
              onChange={(value) => setForm({ ...form, subject: value })}
              options={(subjects.data ?? []).map((subject) => ({
                value: subject.id,
                label: `${subject.name} (${subject.code})`,
              }))}
            />
            <ChoiceField
              label="Section"
              id="new-assignment-section"
              required
              value={form.section}
              error={fieldErrors.section}
              onChange={(value) => setForm({ ...form, section: value })}
              options={(sections.data ?? []).map((section) => ({
                value: section.id,
                label: section.name,
              }))}
            />
            <ChoiceField
              label="Academic year"
              id="new-assignment-year"
              required
              value={form.academic_year}
              error={fieldErrors.academic_year}
              onChange={(value) => setForm({ ...form, academic_year: value })}
              options={(years.data ?? []).map((year) => ({
                value: year.id,
                label: year.name,
              }))}
            />
            <ChoiceField
              label="Faculty"
              id="new-assignment-faculty"
              required
              value={form.faculty}
              error={fieldErrors.faculty}
              onChange={(value) => setForm({ ...form, faculty: value })}
              options={(facultyRoster.data ?? []).map((profile) => ({
                value: profile.id,
                label: `${profile.name} (${profile.employee_id})`,
              }))}
              emptyLabel={
                facultyRoster.isLoading
                  ? "Loading faculty…"
                  : facultyRoster.isError
                    ? "Faculty could not be loaded, so no teacher can be chosen."
                    : "No faculty accounts exist yet."
              }
            />
          </div>
          <CreateError error={create.error} fieldErrors={fieldErrors} />
          <Button type="submit" disabled={!canSubmit || create.isPending}>
            {create.isPending ? "Saving…" : "Create assignment"}
          </Button>
        </form>

        <DataTable
          caption="Subject assignments"
          columns={columns}
          rows={list.data ?? []}
          rowKey={(row) => row.id}
          isLoading={list.isLoading}
          error={list.isError ? normalizeApiError(list.error).message : null}
          loadingLabel="Loading subject assignments"
          emptyMessage="No subject assignments have been created."
        />
      </CardContent>
    </Card>
  )
}

function GradingPeriodsCard() {
  const { list, create, remove } = useGradingPeriods()
  const { list: years } = useAcademicYears()
  const [form, setForm] = useState({
    name: "",
    order: "",
    start_date: "",
    end_date: "",
    academic_year: "",
  })
  const fieldErrors = useFieldErrors(create.error)
  const canSubmit =
    form.name.trim() !== "" &&
    form.order !== "" &&
    form.start_date !== "" &&
    form.end_date !== "" &&
    form.academic_year !== ""

  const columns: readonly DataTableColumn<GradingPeriod>[] = [
    {
      key: "name",
      header: "Name",
      cell: (row) => <span className="font-medium">{row.name}</span>,
    },
    {
      key: "year",
      header: "Academic year",
      cell: (row) => <span className="text-sm">{row.academic_year_name}</span>,
    },
    { key: "order", header: "Order", cell: (row) => <span>{row.order}</span> },
    {
      key: "dates",
      header: "Dates",
      cell: (row) => (
        <span className="text-sm text-muted-foreground">
          {row.start_date} → {row.end_date}
        </span>
      ),
    },
    {
      key: "actions",
      header: "Actions",
      cell: (row) => (
        <DeleteButton
          pending={remove.isPending}
          subject={row.name}
          onDelete={() => remove.mutate(row.id)}
        />
      ),
    },
  ]

  return (
    <Card>
      <CardHeader>
        <CardTitle>Grading periods</CardTitle>
        <CardDescription>
          A term or quarter. Both dates must sit inside the academic year, and
          the end must fall after the start — the serializer rejects anything
          else with a field-level error.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <form
          className="space-y-3"
          onSubmit={(event) => {
            event.preventDefault()
            if (!canSubmit) return
            create.mutate(
              {
                name: form.name.trim(),
                order: Number(form.order),
                start_date: form.start_date,
                end_date: form.end_date,
                academic_year: form.academic_year,
              },
              {
                onSuccess: () =>
                  setForm({
                    name: "",
                    order: "",
                    start_date: "",
                    end_date: "",
                    academic_year: "",
                  }),
              }
            )
          }}
        >
          <div className="grid gap-3 sm:grid-cols-5">
            <Field
              label="Name"
              id="new-period-name"
              required
              placeholder="First Term"
              value={form.name}
              error={fieldErrors.name}
              onChange={(name) => setForm({ ...form, name })}
            />
            <Field
              label="Order"
              id="new-period-order"
              type="number"
              required
              min={1}
              value={form.order}
              error={fieldErrors.order}
              onChange={(order) => setForm({ ...form, order })}
            />
            <Field
              label="Start date"
              id="new-period-start"
              type="date"
              required
              value={form.start_date}
              error={fieldErrors.start_date}
              onChange={(start_date) => setForm({ ...form, start_date })}
            />
            <Field
              label="End date"
              id="new-period-end"
              type="date"
              required
              value={form.end_date}
              error={fieldErrors.end_date}
              onChange={(end_date) => setForm({ ...form, end_date })}
            />
            <ChoiceField
              label="Academic year"
              id="new-period-year"
              required
              value={form.academic_year}
              error={fieldErrors.academic_year}
              onChange={(value) => setForm({ ...form, academic_year: value })}
              options={(years.data ?? []).map((year) => ({
                value: year.id,
                label: year.name,
              }))}
            />
          </div>
          <CreateError error={create.error} fieldErrors={fieldErrors} />
          <Button type="submit" disabled={!canSubmit || create.isPending}>
            {create.isPending ? "Saving…" : "Create grading period"}
          </Button>
        </form>

        <DataTable
          caption="Grading periods"
          columns={columns}
          rows={list.data ?? []}
          rowKey={(row) => row.id}
          isLoading={list.isLoading}
          error={list.isError ? normalizeApiError(list.error).message : null}
          loadingLabel="Loading grading periods"
          emptyMessage="No grading periods have been created."
        />
      </CardContent>
    </Card>
  )
}

function EnrollmentsCard() {
  const { list, create, remove } = useEnrollments()
  const { list: sections } = useSections()
  const { list: years } = useAcademicYears()

  /*
   * `Enrollment.student` is a StudentProfile UUID. There is no administrator
   * endpoint that lists student profiles — guidance can read enrollments, but
   * an admin reading its own list is the only source of these UUIDs here. So
   * the picker offers only students already present in an enrollment, and the
   * card says so when that set is empty rather than presenting an empty select
   * that cannot be used.
   */
  const students = Array.from(
    new Map(
      (list.data ?? []).map((row) => [
        row.student,
        {
          value: row.student,
          label: `${row.student_name} (${row.student_id})`,
        },
      ])
    ).values()
  )

  const [form, setForm] = useState({
    student: "",
    section: "",
    academic_year: "",
    date_enrolled: "",
  })
  const fieldErrors = useFieldErrors(create.error)
  const canSubmit =
    form.student !== "" &&
    form.section !== "" &&
    form.academic_year !== "" &&
    form.date_enrolled !== ""

  /*
   * PH11.10: enrollments is the one academic-structure table that grows without
   * a bound — one row per student per section per year — so it is paginated
   * rather than rendered in full. Not sorted: the columns here are lookups an
   * administrator scans for a specific student rather than a list they re-order.
   */
  const { pagination, pageRows, setPageSize } = useDataTablePagination(
    list.data ?? [],
    PAGE_SIZE
  )

  const columns: readonly DataTableColumn<Enrollment>[] = [
    {
      key: "student",
      header: "Student",
      cell: (row) => (
        <div className="min-w-0">
          <div className="font-medium">{row.student_name}</div>
          <div className="text-xs text-muted-foreground">{row.student_id}</div>
        </div>
      ),
    },
    {
      key: "section",
      header: "Section",
      cell: (row) => <span>{row.section_name}</span>,
    },
    {
      key: "year",
      header: "Academic year",
      cell: (row) => <span className="text-sm">{row.academic_year_name}</span>,
    },
    {
      key: "enrolled",
      header: "Enrolled on",
      cell: (row) => (
        <span className="text-sm text-muted-foreground">
          {row.date_enrolled}
        </span>
      ),
    },
    {
      key: "status",
      header: "Status",
      cell: (row) => (
        <Badge variant="outline" data-enrollment-active={String(row.is_active)}>
          {row.is_active ? "Active" : "Inactive"}
        </Badge>
      ),
    },
    {
      key: "actions",
      header: "Actions",
      cell: (row) => (
        <DeleteButton
          pending={remove.isPending}
          subject={`${row.student_name} in ${row.section_name}`}
          onDelete={() => remove.mutate(row.id)}
        />
      ),
    },
  ]

  return (
    <Card>
      <CardHeader>
        <CardTitle>Enrollments</CardTitle>
        <CardDescription>
          Enrolment is what scopes a student to a section, and through it to
          grades, attendance and guidance visibility.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {list.data && list.data.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No enrollments exist yet. Import a student roster first — the
            administrator API has no endpoint that lists unenrolled students.
          </p>
        ) : null}

        <form
          className="space-y-3"
          onSubmit={(event) => {
            event.preventDefault()
            if (!canSubmit) return
            create.mutate(
              {
                student: form.student,
                section: form.section,
                academic_year: form.academic_year,
                date_enrolled: form.date_enrolled,
                is_active: true,
              },
              {
                onSuccess: () =>
                  setForm({
                    student: "",
                    section: "",
                    academic_year: "",
                    date_enrolled: "",
                  }),
              }
            )
          }}
        >
          <div className="grid gap-3 sm:grid-cols-4">
            <ChoiceField
              label="Student"
              id="new-enrollment-student"
              required
              value={form.student}
              error={fieldErrors.student}
              onChange={(value) => setForm({ ...form, student: value })}
              options={students}
              emptyLabel="No students available"
            />
            <ChoiceField
              label="Section"
              id="new-enrollment-section"
              required
              value={form.section}
              error={fieldErrors.section}
              onChange={(value) => setForm({ ...form, section: value })}
              options={(sections.data ?? []).map((section) => ({
                value: section.id,
                label: section.name,
              }))}
            />
            <ChoiceField
              label="Academic year"
              id="new-enrollment-year"
              required
              value={form.academic_year}
              error={fieldErrors.academic_year}
              onChange={(value) => setForm({ ...form, academic_year: value })}
              options={(years.data ?? []).map((year) => ({
                value: year.id,
                label: year.name,
              }))}
            />
            <Field
              label="Date enrolled"
              id="new-enrollment-date"
              type="date"
              required
              value={form.date_enrolled}
              error={fieldErrors.date_enrolled}
              onChange={(date_enrolled) => setForm({ ...form, date_enrolled })}
            />
          </div>
          <CreateError error={create.error} fieldErrors={fieldErrors} />
          <Button type="submit" disabled={!canSubmit || create.isPending}>
            {create.isPending ? "Saving…" : "Create enrollment"}
          </Button>
        </form>

        <DataTable
          caption="Enrollments"
          columns={columns}
          rows={pageRows}
          rowKey={(row) => row.id}
          isLoading={list.isLoading}
          error={list.isError ? normalizeApiError(list.error).message : null}
          loadingLabel="Loading enrollments"
          emptyMessage="No enrollments have been recorded."
          pagination={pagination}
          pageSizeOptions={PAGE_SIZE_OPTIONS}
          onPageSizeChange={setPageSize}
        />
      </CardContent>
    </Card>
  )
}

/* ------------------------------------------------------------------ */
/* Error mapping                                                       */
/* ------------------------------------------------------------------ */

/**
 * The messages the API returned for this form, keyed by request field name.
 *
 * Returns an empty map when the failure was not a field-keyed validation error
 * (a 500, a 403, a network error), so callers always have a map to index.
 */
function useFieldErrors(error: unknown): Record<string, string> {
  const fields = getFieldErrors(error)
  if (!fields) return {}
  const out: Record<string, string> = {}
  for (const [name, messages] of Object.entries(fields)) {
    const first = messages[0]
    if (first) out[name] = first
  }
  return out
}

/**
 * The form-level banner for a failed create.
 *
 * A field-keyed 400 is already shown against each input, so repeating it here
 * would print the same sentence twice. The banner is kept for failures the
 * inputs cannot explain — a permission error, a server fault, a network drop,
 * or a `non_field_errors` entry.
 */
function CreateError({
  error,
  fieldErrors,
}: {
  error: unknown
  fieldErrors: Record<string, string>
}) {
  if (!error) return null
  const named = Object.keys(fieldErrors).filter(
    (name) => !OPAQUE_ERROR_FIELDS.has(name)
  )
  if (named.length > 0 && named.length === Object.keys(fieldErrors).length) {
    return null
  }
  return <ErrorNote message={normalizeApiError(error).message} />
}

/** DRF keys that are not a specific input, so their text needs the banner. */
const OPAQUE_ERROR_FIELDS = new Set([
  "detail",
  "non_field_errors",
  "__all__",
  "root",
])

import { Users } from "lucide-react"
import { useMemo, useState, type FormEvent } from "react"

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
import { ErrorNote } from "@/components/feedback/Feedback"
import { ChoiceField, Field } from "@/components/ui/form-field"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { SearchableSelect } from "@/components/ui/searchable-select"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Textarea } from "@/components/ui/textarea"
import type { Enrollment } from "@/features/academics/api"
import {
  BEHAVIORAL_NOTE_TYPES,
  BEHAVIORAL_NOTE_TYPE_LABELS,
  useBehavioralNotes,
  type BehavioralNote,
  type BehavioralNoteType,
} from "@/features/guidance/api"
import { useFacultyGrades } from "@/features/academics/api"
import {
  useAttendanceSummary,
  type AttendanceSummaryEntry,
} from "@/features/attendance/api"
import {
  useAdvisoryEnrollments,
  useCreateBehavioralNote,
  useProfileReferenceData,
  useStudentProfile,
  useUpdateStudentProfile,
} from "@/features/faculty/advisory-api"
import { getFieldErrors, isHttpError, normalizeApiError } from "@/lib/error"
import { downloadExport, type ExportFormat } from "@/lib/export"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"

/**
 * Advisory class surface (TC-FAC-07 / TC-FAC-08).
 *
 * A faculty member sees the students in the sections they advise or teach
 * and can record a behavioral note against one of them. The backend is the
 * authority: `BehavioralNoteViewSet` scopes both the roster and the note
 * list to the caller's sections, rejects a blank note with
 * "Note text cannot be empty.", and refuses a student outside that scope.
 * The client mirrors the blank check so the usual path shows the same
 * wording without a round trip, but a server validation error is always
 * preferred when one comes back.
 *
 * TC-FAC-03 / TC-FAC-04: the same roster can open the manage-profile form,
 * whose write contract requires every field, so a partial update is
 * rejected per-field by the server rather than saved incomplete.
 *
 * TC-FAC-17 / TC-FAC-20: the class summary collapses profile, attendance and
 * grade data for every student on this page, and the same figures are
 * downloadable through the server's own aggregate export.
 */

/** Today's date as `YYYY-MM-DD` in the browser's local zone. */
function today(): string {
  const now = new Date()
  const month = String(now.getMonth() + 1).padStart(2, "0")
  const day = String(now.getDate()).padStart(2, "0")
  return `${now.getFullYear()}-${month}-${day}`
}

function formatDate(value: string): string {
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return value
  return parsed.toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  })
}

const NOTE_TYPE_BADGE: Record<
  BehavioralNoteType,
  "default" | "secondary" | "destructive"
> = {
  positive: "default",
  warning: "secondary",
  incident: "destructive",
}

interface StudentProfileForm {
  grade_level: string
  section: string
  guardian_contact: string
  date_of_birth: string
}

const EMPTY_PROFILE_FORM: StudentProfileForm = {
  grade_level: "",
  section: "",
  guardian_contact: "",
  date_of_birth: "",
}

export function FacultyAdvisoryPage() {
  const [managing, setManaging] = useState<Enrollment | null>(null)

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-1">
        <div className="flex items-center gap-3">
          <Users className="size-5 text-muted-foreground" aria-hidden="true" />
          <h2 className="text-2xl font-bold text-foreground">Advisory class</h2>
        </div>
        <p className="text-sm text-muted-foreground">
          The students in the sections you advise or teach: their profiles and
          the behavioral notes you record for them.
        </p>
      </div>

      <RosterCard onManageProfile={setManaging} />
      <NotesCard />
      <ClassSummaryCard />

      <ManageProfileDialog
        enrollment={managing}
        onClose={() => setManaging(null)}
      />
    </div>
  )
}

function RosterCard({
  onManageProfile,
}: {
  onManageProfile: (enrollment: Enrollment) => void
}) {
  const rosterQuery = useAdvisoryEnrollments()
  const [search, setSearch] = useState("")

  const rows = useMemo(() => {
    const q = search.trim().toLowerCase()
    const all = rosterQuery.data ?? []
    if (!q) return all
    return all.filter(
      (entry) =>
        entry.student_name.toLowerCase().includes(q) ||
        entry.student_id.toLowerCase().includes(q) ||
        entry.section_name.toLowerCase().includes(q)
    )
  }, [rosterQuery.data, search])

  const columns: readonly DataTableColumn<Enrollment>[] = [
    {
      key: "student_name",
      header: "Student",
      cell: (entry) => (
        <span className="font-medium">{entry.student_name}</span>
      ),
    },
    {
      key: "student_id",
      header: "Student ID",
      cell: (entry) => (
        <span className="font-mono text-sm">{entry.student_id}</span>
      ),
    },
    {
      key: "section_name",
      header: "Section",
      cell: (entry) => entry.section_name,
    },
    {
      key: "actions",
      header: "Profile",
      headerClassName: "whitespace-nowrap",
      cell: (entry) => (
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => onManageProfile(entry)}
        >
          Manage profile
        </Button>
      ),
    },
  ]

  return (
    <Card>
      <CardHeader>
        <CardTitle>Students in your class</CardTitle>
        <CardDescription>
          Enrolled students in the sections you advise or teach. The server
          keeps this list scoped to your own sections.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="mb-3 space-y-1.5">
          <Label htmlFor="advisory-roster-search">Search students</Label>
          <Input
            id="advisory-roster-search"
            type="search"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Name, ID or section"
          />
        </div>
        <div className="max-h-[28rem] overflow-y-auto">
          <DataTable
            caption="Students in your advisory class"
            columns={columns}
            rows={rows}
            rowKey={(entry) => entry.id}
            isLoading={rosterQuery.isLoading}
            error={
              rosterQuery.isError
                ? normalizeApiError(rosterQuery.error).message
                : null
            }
            loadingLabel="Loading your class list"
            emptyMessage={
              search.trim()
                ? "No students match the current search."
                : "No students are enrolled in your sections yet."
            }
          />
        </div>
      </CardContent>
    </Card>
  )
}

/**
 * One-page advisory class summary (TC-FAC-17).
 *
 * Every figure comes from the same role-scoped endpoints the rest of the
 * page uses, so the numbers are the student's real records rather than a
 * placeholder: the roster is the faculty enrollment scope, the attendance
 * counts come from `/attendance/summary/` (scoped to the caller's
 * sections), and the grades come from the faculty grade queryset.
 *
 * An average over no scored grades is shown as "—", never as 0: a student
 * with nothing recorded has no average. Attendance totals are record counts
 * (the API defines no "school days" denominator), and the card says so.
 */
function ClassSummaryCard() {
  const rosterQuery = useAdvisoryEnrollments()
  const attendanceQuery = useAttendanceSummary()
  const gradesQuery = useFacultyGrades()
  const [downloading, setDownloading] = useState<ExportFormat | null>(null)
  const [exportError, setExportError] = useState<string | null>(null)

  const attendanceByStudent = useMemo(() => {
    const map = new Map<string, AttendanceSummaryEntry>()
    for (const entry of attendanceQuery.data ?? []) {
      const previous = map.get(entry.student)
      if (!previous) {
        map.set(entry.student, { ...entry })
        continue
      }
      // A student enrolled in two of this faculty's sections has two summary
      // rows; the class summary reports their combined totals.
      map.set(entry.student, {
        ...previous,
        present_count: previous.present_count + entry.present_count,
        late_count: previous.late_count + entry.late_count,
        absent_count: previous.absent_count + entry.absent_count,
        total_records: previous.total_records + entry.total_records,
      })
    }
    return map
  }, [attendanceQuery.data])

  const gradesByStudent = useMemo(() => {
    const totals = new Map<string, { recorded: number; sum: number }>()
    for (const grade of gradesQuery.data ?? []) {
      const current = totals.get(grade.student) ?? { recorded: 0, sum: 0 }
      current.recorded += 1
      if (grade.score !== null) current.sum += grade.score
      totals.set(grade.student, current)
    }
    return totals
  }, [gradesQuery.data])

  const rows = useMemo(
    () =>
      (rosterQuery.data ?? []).map((entry) => {
        const attendance = attendanceByStudent.get(entry.student)
        const grades = gradesByStudent.get(entry.student)
        const scored = grades && grades.recorded > 0
        return {
          key: entry.id,
          student: entry.student,
          student_name: entry.student_name,
          student_id: entry.student_id,
          section_name: entry.section_name,
          present: attendance?.present_count ?? 0,
          late: attendance?.late_count ?? 0,
          absent: attendance?.absent_count ?? 0,
          total: attendance?.total_records ?? 0,
          gradesRecorded: grades?.recorded ?? 0,
          average: scored && grades ? grades.sum / grades.recorded : null,
        }
      }),
    [rosterQuery.data, attendanceByStudent, gradesByStudent]
  )

  const loading =
    rosterQuery.isLoading || attendanceQuery.isLoading || gradesQuery.isLoading
  const error =
    rosterQuery.error ?? attendanceQuery.error ?? gradesQuery.error ?? null

  const download = async (format: ExportFormat) => {
    setDownloading(format)
    setExportError(null)
    try {
      await downloadExport("advisory", format)
    } catch (caught) {
      setExportError(normalizeApiError(caught).message)
    } finally {
      setDownloading(null)
    }
  }

  const columns: readonly DataTableColumn<(typeof rows)[number]>[] = [
    {
      key: "student_name",
      header: "Student",
      cell: (row) => <span className="font-medium">{row.student_name}</span>,
    },
    {
      key: "student_id",
      header: "Student ID",
      cell: (row) => (
        <span className="font-mono text-sm">{row.student_id}</span>
      ),
    },
    {
      key: "section_name",
      header: "Section",
      cell: (row) => row.section_name,
    },
    {
      key: "present",
      header: "Present",
      cell: (row) => row.present,
    },
    {
      key: "late",
      header: "Late",
      cell: (row) => row.late,
    },
    {
      key: "absent",
      header: "Absent",
      cell: (row) => row.absent,
    },
    {
      key: "total",
      header: "Total",
      cell: (row) => row.total,
    },
    {
      key: "gradesRecorded",
      header: "Grades",
      cell: (row) => row.gradesRecorded,
    },
    {
      key: "average",
      header: "Average",
      headerClassName: "whitespace-nowrap",
      cell: (row) =>
        row.average === null ? (
          <span className="text-muted-foreground">&mdash;</span>
        ) : (
          <span className="tabular-nums">{row.average.toFixed(2)}%</span>
        ),
    },
  ]

  return (
    <Card>
      <CardHeader>
        <CardTitle>Advisory class summary</CardTitle>
        <CardDescription>
          Profiles, attendance and grades for your class on one page. Counts are
          attendance records taken, not a rate over school days, and an average
          over no recorded grades is shown as a dash.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {exportError ? <ErrorNote message={exportError} /> : null}

        <DataTable
          caption="Advisory class summary: attendance records and grade averages per student"
          columns={columns}
          rows={rows}
          rowKey={(row) => row.key}
          isLoading={loading}
          error={error ? normalizeApiError(error).message : null}
          loadingLabel="Loading your class summary"
          emptyMessage="No students are enrolled in your sections yet."
        />

        <div className="flex flex-wrap items-center gap-2">
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={downloading !== null}
            onClick={() => void download("csv")}
          >
            {downloading === "csv" ? "Preparing…" : "Download summary (CSV)"}
          </Button>
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={downloading !== null}
            onClick={() => void download("xlsx")}
          >
            {downloading === "xlsx" ? "Preparing…" : "Download summary (Excel)"}
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}

function NotesCard() {
  const rosterQuery = useAdvisoryEnrollments()
  const notesQuery = useBehavioralNotes()
  const createNote = useCreateBehavioralNote()
  const [student, setStudent] = useState("")
  const [noteType, setNoteType] = useState<BehavioralNoteType>("positive")
  const [dateRecorded, setDateRecorded] = useState(today())
  const [noteText, setNoteText] = useState("")
  const [blankRejected, setBlankRejected] = useState(false)

  const fieldErrors = createNote.isError
    ? getFieldErrors(createNote.error)
    : null
  // A named field error beats the envelope's generic summary: the serializer
  // refuses a blank note or a future date with its own wording, and that is
  // what the reader needs to act on.
  const serverFieldError = fieldErrors
    ? (fieldErrors.note_text?.[0] ?? Object.values(fieldErrors)[0]?.[0] ?? null)
    : null
  const serverError = createNote.isError
    ? (serverFieldError ?? normalizeApiError(createNote.error).message)
    : null
  const validationError =
    serverError ??
    (blankRejected && !noteText.trim() ? "Note text cannot be empty." : null)

  const resetMessage = () => {
    setBlankRejected(false)
    if (createNote.isError || createNote.isSuccess) createNote.reset()
  }

  const onSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!noteText.trim()) {
      // Same wording the server returns for a blank note (TC-FAC-08), so the
      // rejection is shown whether the round trip happens or not.
      setBlankRejected(true)
      return
    }
    createNote.mutate(
      {
        student,
        note_type: noteType,
        note_text: noteText,
        date_recorded: dateRecorded,
      },
      {
        onSuccess: () => {
          setNoteText("")
          setBlankRejected(false)
        },
      }
    )
  }

  const roster = rosterQuery.data ?? []

  const columns: readonly DataTableColumn<BehavioralNote>[] = [
    {
      key: "date_recorded",
      header: "Date",
      cell: (note) => formatDate(note.date_recorded),
    },
    {
      key: "student_name",
      header: "Student",
      cell: (note) => note.student_name,
    },
    {
      key: "note_type",
      header: "Type",
      cell: (note) => (
        <Badge variant={NOTE_TYPE_BADGE[note.note_type] ?? "secondary"}>
          {BEHAVIORAL_NOTE_TYPE_LABELS[note.note_type] ?? note.note_type}
        </Badge>
      ),
    },
    {
      key: "note_text",
      header: "Note",
      cell: (note) => (
        <span className="whitespace-normal">{note.note_text}</span>
      ),
    },
  ]

  return (
    <Card>
      <CardHeader>
        <CardTitle>Behavioral notes</CardTitle>
        <CardDescription>
          Notes are saved to the student&apos;s record and become visible to the
          guidance counselor. They cannot be edited or deleted after saving.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <form className="space-y-3" onSubmit={onSubmit} noValidate>
          <div className="grid gap-3 sm:grid-cols-3">
            <div className="space-y-1.5">
              <Label htmlFor="behavioral-note-student">Student</Label>
              <SearchableSelect
                id="behavioral-note-student"
                label="Student"
                value={student}
                onChange={(value) => {
                  setStudent(value)
                  resetMessage()
                }}
                options={roster.map((entry) => ({
                  value: entry.student,
                  label: `${entry.student_name} (${entry.student_id})`,
                }))}
                placeholder="Select a student"
                searchPlaceholder="Search students"
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="behavioral-note-type">Type</Label>
              <Select
                value={noteType}
                onValueChange={(value) => {
                  setNoteType(value as BehavioralNoteType)
                  resetMessage()
                }}
              >
                <SelectTrigger id="behavioral-note-type">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {BEHAVIORAL_NOTE_TYPES.map((type) => (
                    <SelectItem key={type} value={type}>
                      {BEHAVIORAL_NOTE_TYPE_LABELS[type]}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="behavioral-note-date">Date recorded</Label>
              <Input
                id="behavioral-note-date"
                type="date"
                value={dateRecorded}
                max={today()}
                onChange={(event) => {
                  setDateRecorded(event.target.value)
                  resetMessage()
                }}
              />
            </div>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="behavioral-note-text">Note</Label>
            <Textarea
              id="behavioral-note-text"
              value={noteText}
              rows={3}
              placeholder="What did you observe?"
              onChange={(event) => {
                setNoteText(event.target.value)
                resetMessage()
              }}
            />
          </div>

          {validationError ? <ErrorNote message={validationError} /> : null}
          {createNote.isSuccess ? (
            <p role="status" className="text-sm text-muted-foreground">
              Behavioral note saved to the student&apos;s record.
            </p>
          ) : null}

          <Button
            type="submit"
            disabled={createNote.isPending || roster.length === 0}
          >
            {createNote.isPending ? "Saving…" : "Save behavioral note"}
          </Button>
        </form>

        <DataTable
          caption="Behavioral notes you have recorded"
          columns={columns}
          rows={notesQuery.data ?? []}
          rowKey={(note) => note.id}
          isLoading={notesQuery.isLoading}
          error={
            notesQuery.isError
              ? normalizeApiError(notesQuery.error).message
              : null
          }
          loadingLabel="Loading behavioral notes"
          emptyMessage="You have not recorded a behavioral note yet."
        />
      </CardContent>
    </Card>
  )
}

/**
 * Manage-profile dialog (TC-FAC-03 / TC-FAC-04).
 *
 * The server's write contract requires all four fields, so the form keeps a
 * single enabled submit and lets the response speak: a 400 returns
 * `error.details` keyed by field name, and each message lands on its control
 * through `Field`'s `error` prop. Emptiness is not faked into a client-side
 * rule — the same serializer message ("Guardian contact may not be blank.")
 * is what the reader sees either way.
 */
function ManageProfileDialog({
  enrollment,
  onClose,
}: {
  enrollment: Enrollment | null
  onClose: () => void
}) {
  const profileQuery = useStudentProfile(enrollment?.student ?? null)
  const reference = useProfileReferenceData()
  const updateProfile = useUpdateStudentProfile(enrollment?.student ?? null)

  const profile = profileQuery.data
  const [form, setForm] = useState<StudentProfileForm>(EMPTY_PROFILE_FORM)

  // The query resolves after mount (it is disabled until the dialog opens),
  // so the saved values are folded in once — and re-folded if a different
  // student's dialog replaces this one.
  //
  // The seed is deliberately held until the query is idle: React Query
  // returns cached data first and revalidates after, so seeding on the
  // cached copy would show the pre-save values for a moment (and, without a
  // re-seed once the fresh copy arrives, for as long as the dialog stays
  // open). `isFetching` is true for exactly that window.
  const loadedId = profileQuery.data?.id
  const [seededId, setSeededId] = useState<string | null>(null)
  if (profile && loadedId !== seededId && !profileQuery.isFetching) {
    setSeededId(loadedId ?? null)
    setForm({
      grade_level: profile.grade_level,
      section: profile.section,
      guardian_contact: profile.guardian_contact ?? "",
      date_of_birth: profile.date_of_birth ?? "",
    })
  }

  const fieldErrors = updateProfile.isError
    ? getFieldErrors(updateProfile.error)
    : null

  const set = (patch: Partial<StudentProfileForm>) =>
    setForm((current) => ({ ...current, ...patch }))

  const onSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    updateProfile.mutate(
      {
        grade_level: form.grade_level,
        section: form.section,
        guardian_contact: form.guardian_contact,
        date_of_birth: form.date_of_birth,
      },
      {
        onSuccess: () => {
          // The saved profile is the form's new starting point.
          setSeededId(null)
          onClose()
        },
      }
    )
  }

  const open = enrollment !== null
  const saving = updateProfile.isPending
  // The section list follows the chosen grade level, matching the server's
  // own cross-field rule before the request is made.
  const sectionOptions = reference.sections
    .filter(
      (section) => !form.grade_level || section.grade_level === form.grade_level
    )
    .map((section) => ({ value: section.id, label: section.name }))

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) onClose()
      }}
    >
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Manage profile</DialogTitle>
          <DialogDescription>
            {enrollment
              ? `${enrollment.student_name} (${enrollment.student_id})`
              : null}
          </DialogDescription>
        </DialogHeader>

        {/*
          `isFetching`, not `isLoading`: a reopened dialog already has cached
          data, so `isLoading` is false while the fresh copy is still in
          flight. Rendering the form then would seed stale values, which is
          exactly what a save just corrected.
        */}
        {profileQuery.isFetching ? (
          <p className="text-sm text-muted-foreground" role="status">
            Loading the student&apos;s profile…
          </p>
        ) : profileQuery.isError ? (
          <ErrorNote
            message={
              // 404 means the student left the faculty's scope between opening
              // the roster and the dialog; say so instead of showing a raw
              // transport error.
              isHttpError(profileQuery.error, 404)
                ? "That student profile is not available to you any more."
                : normalizeApiError(profileQuery.error).message
            }
          />
        ) : (
          <form
            className="space-y-3"
            id="manage-profile-form"
            onSubmit={onSubmit}
            noValidate
          >
            <ChoiceField
              label="Grade level"
              id="profile-grade-level"
              required
              value={form.grade_level}
              onChange={(value) => set({ grade_level: value })}
              options={reference.gradeLevels.map((level) => ({
                value: level.id,
                label: level.name,
              }))}
              error={fieldErrors?.grade_level?.[0] ?? null}
            />
            <ChoiceField
              label="Section"
              id="profile-section"
              required
              value={form.section}
              onChange={(value) => set({ section: value })}
              options={sectionOptions}
              error={fieldErrors?.section?.[0] ?? null}
              hint={
                reference.sections.length === 0
                  ? "No sections are available yet. Ask an administrator to set up the current academic year."
                  : undefined
              }
            />
            <Field
              label="Guardian contact"
              id="profile-guardian-contact"
              required
              value={form.guardian_contact}
              onChange={(value) => set({ guardian_contact: value })}
              error={fieldErrors?.guardian_contact?.[0] ?? null}
              placeholder="09XX-XXX-XXXX"
            />
            <Field
              label="Date of birth"
              id="profile-date-of-birth"
              required
              type="date"
              value={form.date_of_birth}
              onChange={(value) => set({ date_of_birth: value })}
              error={fieldErrors?.date_of_birth?.[0] ?? null}
            />

            {updateProfile.isError &&
            (!fieldErrors || Object.keys(fieldErrors).length === 0) ? (
              <ErrorNote
                message={normalizeApiError(updateProfile.error).message}
              />
            ) : null}
          </form>
        )}

        <DialogFooter>
          <Button type="button" variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button
            type="submit"
            form="manage-profile-form"
            disabled={saving || profileQuery.isLoading || profileQuery.isError}
          >
            {saving ? "Saving…" : "Save profile"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

# Grade collection flow (teacher → adviser)

Answers the question in `NEED-TO-APPLY-AND-CHECK-May-Addition.md` §3: how
advisers collect grades from subject teachers, and whether a per-section grade
export exists.

## The flow

1. **Subject teacher encodes grades.** `POST /api/v1/academics/grades/encode/`
   creates a `Grade` row in `draft` state for one student, one subject
   assignment, one grading period. The teacher can revise the score, letter
   grade and remarks of their own rows; the lifecycle (`draft → submitted →
   finalized`) is not theirs. Finalizing is `POST /grades/{id}/finalize/`, an
   administrator action, and it notifies the student and the linked parents.

2. **Subject teacher bulk-imports instead.** `POST
   /api/v1/academics/grades/batch-import/` accepts CSV or XLSX and pins
   `import_type="grades"` server-side, so the file cannot arrive under another
   import type. Import writes the `Grade` rows directly; the uploaded file is
   kept for the job record but is never re-read afterwards.

3. **Adviser reads the advisees' grades.** `GET /api/v1/academics/grades/`
   returns, for a faculty member, the grades they encoded **plus** every
   subject grade of the students in the sections they advise
   (`Q(subject_assignment__faculty=fp) | Q(student__section__adviser=fp)`).
   A teacher who is not the adviser of a section does not see that section's
   grades, so the widening is limited to the advisory relationship.

4. **Adviser exports the section file.** `GET
   /api/v1/data-import/exports/grades/` accepts `file_format`, `schema` and
   the optional filters `section`, `subject` and `grading_period`. The
   filters narrow the caller's already-authorized queryset, so a filter can
   never widen access. `schema=reimport` renders exactly the columns of the
   grades import template, so the downloaded file can be uploaded unchanged.

## Excel-style template

There is **no** formula-driven gradebook workbook. The import template ships
headers only (`GET /api/v1/data-import/templates/{type}/`), and the XLSX
reader does not evaluate formulas. A template that computed the general
average itself was not built; the "Excel-style template that computes results
automatically" is an open item for the school to confirm.

## Where the code lives

| Concern | File |
|---|---|
| Grade encoding, finalizing, scoped reads | `backend/aegis_backend/apps/academics/views.py` |
| Export scope per role | `backend/aegis_backend/apps/data_import/exports.py` |
| Export filters | `backend/aegis_backend/apps/data_import/views.py` (`ExportViewMixin._apply_filters`) |
| Faculty export UI | `frontend/src/features/faculty/FacultyImportPage.tsx` |

# Data import: what happens to an uploaded file

Answers `NEED-TO-APPLY-AND-CHECK-May-Addition.md` §10 ("will the data be
inserted directly, or fetched from the files the admin imports?").

## The answer

**Inserted directly.** An import writes the domain records — `Grade`,
`AttendanceRecord`, `StudentProfile`, guidance records — into the database as
it parses the file. The uploaded file is never read again.

## The path a file takes

1. **Type detection from the bytes**, not from the extension: the view reads
   the file's magic bytes to tell CSV from XLSX (`apps/data_import/views.py`).
2. **An `ImportJob` is created** with the type the endpoint pinned. The
   batch-import aliases (`/academics/grades/batch-import/`,
   `/attendance/records/batch-import/`) pin the type server-side, so a grades
   file cannot arrive under the attendance type whatever the form sends.
3. **The file is parsed and validated.** Every row becomes an `ImportRecord`
   holding that row's JSON, so a failed row can be explained and a job can be
   audited.
4. **The domain importer writes the rows.** Each row is validated and saved
   with `full_clean()`; a finalized grade is never overwritten by an import.
5. **The counters are recomputed** from the real record statuses, so the job
   summary reflects the database rather than the file.

Files under ~200 rows finish inside the request; larger jobs run in an
in-process worker. The file itself is kept on the job record for the audit
trail, but no code path reads it a second time — the records are the truth.

## What can be imported

| Type | Who may upload |
|---|---|
| `grades` | faculty, admin |
| `attendance` | faculty, admin |
| `students` | admin |
| `guidance_records` | admin |

The templates (`GET /api/v1/data-import/templates/{type}/`) return the column
guide only — headers, required flags and hints. They carry no rows and no
formulas; the XLSX reader does not evaluate formulas either.

Related: `GRADE_COLLECTION_FLOW.md` for the teacher-to-adviser side of the
same data.

# Import test files (manual QA)

Files for the import cases that Cycle 2 could not run: TC-ADM-03 (grades),
TC-ADM-04 (attendance), TC-ADM-05 (guidance records), TC-ADM-18 (malformed
file). Faculty uploads, TC-FAC-13 to TC-FAC-16, use the same two attendance
files and the same grades file through the faculty page.

## No setup needed

The files name records the way a school does: `section` is
`Grade 8 - Bonifacio`, `subject_code` is `ENG-8`, `grading_period` is
`Term 3`. No UUID has to be copied from anywhere. Upload each file as it
ships.

A bare section name (`Bonifacio`) works too. If a name matches more than one
section, the row is rejected and the message asks for the full form or the
UUID; the importer never guesses.

## Files

| File | Steps | Expected result |
| --- | --- | --- |
| `attendance-import.xlsx` | Import type **Attendance**, sheet `Valid Attendance` (5 rows) | Job completed, 5 of 5 rows stored, 0 failed |
| `attendance-import.xlsx` | Same file, **no sheet named** | Job failed with `MULTIPLE_WORKSHEETS`, listing all three sheets |
| `attendance-import.xlsx` | Sheet `Malformed Attendance` (5 rows) | 0 stored, 5 failed, each row with its own reason |
| `attendance-import.xlsx` | Import `Valid Attendance` twice | Second run: 5 rows stored again, each updating the existing record in place |
| `attendance-valid.csv` | Import type **Attendance** | 5 of 5 stored, 0 failed (same data through the CSV pipeline) |
| `attendance-malformed.csv` | Import type **Attendance** | 0 stored, 5 failed |
| `grades-import.xlsx` | Import type **Grades** | 2 of 2 stored (students `AEGIS-QA-S0026`, `AEGIS-QA-S0027`) |
| `grades-import.xlsx` | Import it a second time, after changing both scores | 2 of 2 stored; the two grades are updated, not duplicated |
| `guidance-import.xlsx` | Import type **Guidance records** | 3 of 3 stored |
| `guidance-import.xlsx` | Import it a second time, after editing a note | 3 of 3 stored; the sessions are updated in place |

The workbook carries three sheets on purpose. It is the shape a school export
really arrives in (data, a second dataset, a README), and it is what the
`Sheet` field on the import form exists for. Leave the field blank to see the
old rejection.

## Re-uploading corrects a record

A second upload of the same record updates it instead of failing:

- attendance is keyed by student and date; the new status replaces the old.
- grades are keyed by student, subject assignment and grading period; the new
  score replaces the old one and the grade returns to `draft` for re-review.
  A **finalized** grade is locked and rejected, because it is a signed record:
  reopen it in the app before importing a change.
- guidance sessions are keyed by student, date and time; the new content
  replaces the old and the original counselor is kept.

The students import follows the same rule for the enrolled profile, but never
touches account identity: a roster file cannot change an account's email,
role or password.

## Large files

A file with more than 200 rows is not finished while the upload page waits.
The upload returns immediately and the job keeps running on the server; the
job list on the page refreshes itself until the status is completed, failed or
partial. The files above are all small, so they finish before the response.
If a job ever stays "processing" after a redeploy or a restart, just upload the
same file again: re-uploading is safe, and it corrects the same records.

## What each malformed row proves

| Row | Value | Expected message |
| --- | --- | --- |
| 1 | `AEGIS-QA-S9999` | No student found with that student_id |
| 2 | `status` = `maybe` | status must be one of: absent, late, present |
| 3 | `date` = `2027-01-04` | Attendance date cannot be in the future |
| 4 | `date` = `06/15/2026` | date format rejected (needs `YYYY-MM-DD`) |
| 5 | `section` blank | section is required |

## Why these dates and this grading period

- Attendance dates sit in June 2026, well outside the three seeded school
  weeks, so a valid import cannot collide with seeded records. If the app
  shows a different status afterwards, that student and date was already on
  record and the upload updated it.
- Grades use **Term 3**, which starts 2027-01-04. Term 1 and Term 2 already
  hold a grade for every student and subject, so a Term 3 file creates new
  records and a second run proves the update path.
- Guidance sessions use students `AEGIS-QA-S0026`, `S0027` and `S0003`, all of
  whom carry a seeded risk alert. The importer attributes the session to the
  student's assigned counselor and rejects the row when no counselor is on
  record, which is why the other 97 students are not used. A re-upload keeps
  the counselor already on the record, so it needs no alert.

## Exports (TC-FAC-18 to TC-FAC-20)

Nothing to prepare. Downloads are built server-side from the caller's own
queryset, so the check is that the file matches the rows on screen (grades,
attendance, advisory class summary) and that an empty scope answers with a
message instead of an empty file.

Export columns are not import columns: an attendance export carries the
section *name*, a student name and other report columns, so an exported file
is a report rather than a round-trip file (the extra columns are rejected as
unknown).

# Import test files (manual QA)

Files for the import cases that Cycle 2 could not run: TC-ADM-03 (grades),
TC-ADM-04 (attendance), TC-ADM-05 (guidance records), TC-ADM-18 (malformed
file). Faculty uploads, TC-FAC-13 to TC-FAC-16, use the same two attendance
files and the same grades file through the faculty page.

## Before you upload: replace the placeholders

The files name the records to import by UUID. Nothing in the app displays a
UUID, so copy the three values once and replace every occurrence
(Excel: `Ctrl+H`; Notepad: `Ctrl+H`).

| Placeholder | Value to use |
| --- | --- |
| `REPLACE_WITH_SECTION_UUID` | Section **Grade 8 - Bonifacio** (student `AEGIS-QA-S0026` is enrolled there) |
| `REPLACE_WITH_ASSIGNMENT_UUID` | Any subject assignment whose section is that same Bonifacio section |
| `REPLACE_WITH_GRADING_PERIOD_UUID` | Grading period **Term 3** |

Where to copy them from, easiest first:

1. Supabase dashboard -> Table Editor: `academics_section` (copy the `id` of
   the Bonifacio row), `academics_subjectassignment` (a row whose `section`
   equals that id), `academics_gradingperiod` (the `Term 3` row).
2. Django admin (`/admin/`), if a staff login exists: open the record and read
   the UUID from the address bar.
3. Browser DevTools -> Network, on the Admin Academics or the attendance
   screen: the list response for `/api/v1/academics/sections/` carries each
   `id`.

The attendance files need only the section UUID. The grades file needs the
assignment and the period UUID. The guidance file needs none.

## Files

| File | Steps | Expected result |
| --- | --- | --- |
| `attendance-import.xlsx` | Import type **Attendance**, sheet `Valid Attendance` (5 rows) | Job completed, 5 of 5 rows stored, 0 failed |
| `attendance-import.xlsx` | Same file, **no sheet named** | Job failed with `MULTIPLE_WORKSHEETS`, listing all three sheets |
| `attendance-import.xlsx` | Sheet `Malformed Attendance` (5 rows) | 0 stored, 5 failed, each row with its own reason |
| `attendance-import.xlsx` | Import `Valid Attendance` twice | Second run: 5 failed, "already exists" per student and date |
| `attendance-valid.csv` | Import type **Attendance** | 5 of 5 stored, 0 failed (same data through the CSV pipeline) |
| `attendance-malformed.csv` | Import type **Attendance** | 0 stored, 5 failed |
| `grades-import.xlsx` | Import type **Grades** | 2 of 2 stored (students `AEGIS-QA-S0026`, `AEGIS-QA-S0027`) |
| `guidance-import.xlsx` | Import type **Guidance records** | 3 of 3 stored |

The workbook carries three sheets on purpose. It is the shape a school export
really arrives in (data, a second dataset, a README), and it is what the
`Sheet` field on the import form exists for. Leave the field blank to see the
old rejection.

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
  weeks, so a valid import cannot collide with seeded records. If a row still
  reports "already exists", that student and date is on record: change the
  date.
- Grades use **Term 3**, which starts 2027-01-04. Every student already has a
  grade for each subject in Term 1 and Term 2, so importing those would
  report "a grade already exists" for every row.
- Guidance sessions use students `AEGIS-QA-S0026`, `S0027` and `S0003`, all of
  whom carry a seeded risk alert. The importer attributes the session to the
  student's assigned counselor and rejects the row when no counselor is on
  record, which is why the other 97 students are not used.

## Exports (TC-FAC-18 to TC-FAC-20)

Nothing to prepare. Downloads are built server-side from the caller's own
queryset, so the check is that the file matches the rows on screen (grades,
attendance, advisory class summary) and that an empty scope answers with a
message instead of an empty file.

Export columns are not import columns: an attendance export carries the
section *name* and no UUIDs, so an exported file cannot be fed back into
import. Verify it as a report, not as a round trip.

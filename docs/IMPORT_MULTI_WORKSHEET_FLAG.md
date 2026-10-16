# Flag — XLSX import rejects workbooks with more than one worksheet

**Status: FIXED** (2026-10-16). The import request now accepts an optional
`sheet` field — a worksheet title, or its 1-based position among the visible
worksheets — and `_select_worksheet` resolves it. Without the field the old
rule stands: one visible worksheet only, and the rejection message now names
the visible worksheets. New error code `WORKSHEET_NOT_FOUND` for a name that
matches nothing. The frontend import forms (admin and faculty) carry the
optional Sheet input. Test files for the manual retest live in
`docs/test-data/`.

Reported 2026-10-16 during the Cycle-2 import retest. The design notes below
are kept as the record of why the fix looks the way it does.

Observed error, verbatim:

    MULTIPLE_WORKSHEETS: The workbook contains 3 visible worksheets
    (Valid Attendance, Malformed Attendance, README). Only a single
    worksheet is allowed.

Source: `backend/aegis_backend/apps/data_import/xlsx_pipeline.py:235`
`_select_worksheet`. The rule is deliberate, not accidental. Its own
docstring says why: "one import file represents one dataset, so sheets are
never merged or guessed at". A workbook is ambiguous input when the data
sheet is not named, and guessing wrong imports the wrong sheet silently.

What the rule is NOT: a size limit. A single worksheet holds 1,048,576
rows, so "big data" is not the constraint. The reported workbook is a test
fixture: one data sheet, one malformed sheet, one README sheet. The README
sheet alone is enough to force the rejection even though the data sheet is
obvious to a human. That is the real gap — a caption/instructions sheet
makes a valid import impossible.

Why "just import all sheets" is not the fix: this very file carries both
`Valid Attendance` and `Malformed Attendance`. Merging every visible sheet
would import rows from the malformed sheet, and a workbook with one sheet
per section or per grading period would collide on the same student/date
keys. Merging turns a clear rejection into a guessing game with duplicate
entities.

Recommended minimal change, no guessing:

- Accept an optional `sheet` parameter on the import request: worksheet
  name, or 1-based index. Pass it through
  `validate_raw_xlsx`/`parse_xlsx_bytes` into `_select_worksheet`.
- Hidden sheets stay ignored, exactly as now.
- Unknown name or index -> new `WORKSHEET_NOT_FOUND` error, message
  listing the visible sheet names.
- `sheet` omitted and more than one visible worksheet -> keep
  `MULTIPLE_WORKSHEETS`, but the message must list the sheet names (it
  currently truncates at five and never says what to send back).
- Frontend: one optional "Sheet" field on the Import screen, shown only for
  `.xlsx` uploads.

Scope check, so the fix lands complete:

- `apps/data_import/xlsx_pipeline.py` — selection + error code.
- `apps/data_import/constants.py` — add `WORKSHEET_NOT_FOUND`.
- `apps/data_import/tests.py:1005` and `:1323` — both assert the current
  rejection; they need a no-`sheet` case plus a with-`sheet` case.
- `frontend` import form — optional sheet field.

Half-measures that look like this fix but are not:

- Auto-picking the first visible sheet. That would have imported this
  workbook's `Malformed Attendance` sheet.
- Auto-picking by header match. Smarter, still a guess, and more code.
- Silently skipping sheets named README/Instructions. A naming convention
  enforced by code, and it fails the moment a sheet is spelled differently.

Relationship to the test log: this is the blocker behind TC-ADM-04 and
TC-ADM-05 (attendance and guidance import), which Cycle 2 recorded as
"Test File not available. Could not be tested". The import pipeline itself
works; only the sheet selection rule stops these files.

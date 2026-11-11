# The client's datasets (Electronic Class Record)

The school sends its grades as one Electronic Class Record (ECR) workbook per
class, at the repository root:

| Workbook | Class | Roster | Learners with grades | Grade rows |
| --- | --- | --- | --- | --- |
| `GRADE-7-LATEST-SEPTEMBER-4-2026.xlsx` | Grade 7 - Timothy | 30 | 21 | 166 |
| `GRADE-8-LATEST-SEPTEMBER-4-2026.xlsx` | Grade 8 - Ephesians | 32 | 17 | 128 |
| `GRADE-9-LATEST-SEPTEMBER-4-2026.xlsx` | Grade 9 - Daniel | 17 | 5 | 40 |
| `GRADE-10-LATEST-SEPTEMBER-4-2026.xlsx` | Grade 10 - Daniel | 18 | 10 | 79 |

The September 2026 set holds **97 learners** and **413 grade rows**, all in
Term 1 of SY 2026-2027.

The ECR is the same DepEd form family as the SF9 template in
`docs/test-data/`, with two differences: it has no `FINAL GRADES` sheet, and
it has a `COMMENT` sheet that carries the teacher's remarks for each term.
Those two differences are what the reader keys on, so the QA workbooks in
`docs/test-data/` keep their own rules and their own tests.

## How the workbook is read

| In the workbook | In the app |
| --- | --- |
| LRN (column F of a summary sheet) | `StudentProfile.student_id` |
| Name cell (column C) | the learner's first and last name |
| Grade level + section (from `INPUT DATA`) | `Grade 7 - Timothy` |
| Learning area (row 12) | subject code: `Filipino` → `FIL-7`, `GMRC/VE` → `ESP-7`, `EPP/TLE` → `TLE-7` |
| `TERM n SUMMARY` sheet | grading period `Term n` |
| `MAPEH` sub-scores (`M A`, `P E H`) | one score, the average of the two |
| `COMMENT` sheet | the `remarks` of that term's grade rows |
| `INPUT DATA` roster | one student row per learner |

One workbook holds several datasets, so one upload still reads one of them:
the import type decides which. `students` reads the `INPUT DATA` roster,
`grades` reads the term summaries. `attendance` and `guidance_records` are
refused with a message naming what the workbook does not carry -- a job that
quietly stored nothing would read as a successful import of nothing.

The reader lives in `backend/aegis_backend/apps/data_import/deped_forms.py`;
the tests are `backend/aegis_backend/apps/data_import/tests_client_ecr.py`.

## Loading them

The school needs the classes to exist before the first upload, because a
grade resolves its section and subject assignment against the database:

```powershell
cd backend/aegis_backend
python manage.py provision_client_school
```

That creates the four sections, the adviser of each class (the names are the
ones the workbooks carry), the academic year with its three grading periods,
and one subject assignment per learning area per section. It is idempotent
and writes no learner record.

Then load the workbooks:

```powershell
python manage.py import_client_datasets
```

The roster goes first for every class: a grade resolves its learner through
an active enrollment, and the roster import is what creates one. The command
runs the same parser and the same importers the admin screen runs, so what it
writes is what an upload of the same file writes. Uploading through the
screen works too -- the workbooks are recognised by their sheets, so no
worksheet has to be named.

Re-running is safe: an import updates the record it would otherwise
duplicate.

The imported grades land as `draft`, like every import: finalizing is an
administrator action (`POST /api/v1/academics/grades/{id}/finalize/`), and
the risk engine reads finalized grades only.

## Signing in as each role

The import creates the learner accounts but discards their generated
passwords, and the adviser accounts get a password only when
`QA_SHARED_PASSWORD` is set. *Admin -> Users -> New account* cannot fill the
gap: the 97 learner emails already exist, the form sends a set-password link
to an address the school does not own (`@students.aegis.local`), and a user
made there has no `StudentProfile`, no `Enrollment` and no section.

Prepare the existing accounts for a test instead:

```powershell
python manage.py provision_client_access
python manage.py provision_client_access --finalize-grades
```

The first form sets a fresh random password on every learner in the four
client sections and on their four advisers, clears the forced
initial-password change, and creates one linked parent login per learner
(`parent.{LRN}@parents.aegis.local`). It writes `client-credentials.csv` in
the current directory -- one row per role, with name, email, password,
section and student ID. The file is gitignored; hand it out and delete it.
Running the command again rotates every password, which makes it the reset
path too. It never prints a password.

`--finalize-grades` publishes the imported Term 1 grades (draft ->
finalized) so the risk and recommendation surfaces read them. It bypasses
the normal admin finalize action and its notifications, so use it on a test
deployment only. Finalizing is not enough on its own: the risk scores are a
separate computation, so run it once after the import:

```powershell
python manage.py train_risk_model
python manage.py run_risk_computation
```

The first command stores the decision-tree model in the database, so it
survives a redeploy; the second scores every active learner. The learners
with Term 1 rows score `low` (no mark in the set is below 80). The rest have
no finalized grade, so they score `insufficient_data` -- the engine refuses
to invent a risk level.

What each role can reach with the client data:

| Role | Sign in as | Sees |
| --- | --- | --- |
| Student | `{LRN}@students.aegis.local` | own Term 1 grades, remarks, schedule |
| Parent | `parent.{LRN}@parents.aegis.local` | that learner's grades and remarks |
| Faculty | the four adviser emails in the CSV | their own class roster and grades |
| Admin | existing administrator account | all 97 learners, the import record |
| Guidance | existing counselor account | all learners, case load |

Attendance, counseling and Terms 2-3 stay on the synthetic data described
below: the client workbooks carry none of them.

### Against the deployed DEV/QA service

The credentials from the local run exist only in the local database. The
Render build creates the QA accounts and the synthetic dataset
(`render.yaml`), but it never runs the client import, so the deployed
service has no client learner, no client section and no parent login yet.
A learner email from the local CSV therefore answers "No active account
found with the given credentials".

Load the client data into the deployed database once, from this checkout,
by pointing the settings at it. Take the host, user and password from the
Render service's `DATABASE_*` variables (the user carries the Supabase
project ref):

```powershell
cd backend/aegis_backend
$env:DATABASE_HOST = "aws-0-ap-southeast-1.pooler.supabase.com"
$env:DATABASE_USER = "postgres.<project-ref>"
$env:DATABASE_PASSWORD = "<password>"

python manage.py provision_client_school
python manage.py import_client_datasets
python manage.py provision_client_access --finalize-grades --output C:\temp\client-credentials.csv
python manage.py run_risk_computation
```

Environment variables win over `.env`, so the local database is not
touched. Keep the order: the school structure first, the roster before the
grades, credentials and publication last. Do not re-run
`import_client_datasets` after `--finalize-grades`: the importer refuses to
overwrite a finalized grade, so the second import reports those rows as
errors.

This is a one-time load. The Render build does not import the workbooks on
purpose -- every deploy would hit the finalized-grade lock once the grades
are published.

## What the workbooks do not carry

| Missing | Where the evidence lives instead |
| --- | --- |
| Daily attendance marks | `docs/test-data/attendance-sf2-*.xlsm` (the DepEd SF2 form) |
| Counseling sessions | `docs/test-data/guidance-import.xlsx` |
| Term 2 and Term 3 grades | `docs/test-data/grades-sf9-terms-1-2-*.xlsx` |
| Class timetable | not in the ECR; the schedule list is empty for these learners |
| Learners below the passing mark | the synthetic QA cohort in `seed_qa_dataset` |

`ATTENDANCE RECORD SUMMARY` in the ECR lists the roster and the school days
per month (201 in the September set), not per-learner marks; `COMMENT` holds
the teacher's remarks, not counseling sessions.

## What the September 2026 set says about itself

These are facts about the file, not faults in it:

* **Terms 2 and 3 are empty.** The school year is in progress; the summaries
  carry Term 1 only.
* **Only the male block reaches the summaries.** The `INPUT DATA` roster
  holds 97 learners; the term summaries carry the 53 who sit in the male
  block. The other 44 import as learners with no grade row.
* **Three learners have gaps.** `Galvez, Runian Russel` has no Filipino and
  no English; `GALONG, FRANCIS UNO E.` has no English; `Buban, Robie D.` has
  no mark at all. A missing mark imports as no row, never as a zero.
* **One name carries a full stop.** The Grade 8 roster reads
  `Garate. Denisse Maxine D.` where the convention is `Surname, Given names`.
  The reader takes the full stop as the separator, so the learner is on the
  roster as `Garate` / `Denisse Maxine D.`; the school may correct the
  spelling in the app.
* **Names are the school's own.** Grades 9 and 10 are written in capitals and
  are kept exactly as written.
* **No mark is below 80.** The September set produces no at-risk learner.

## Related

- `docs/DATA_IMPORT_FLOW.md` -- what happens to an uploaded file.
- `docs/test-data/README.md` -- the QA datasets, and the SF2/SF9 forms.
- `docs/GRADE_COLLECTION_FLOW.md` -- how a grade reaches an adviser.

# PH11 — Cycle-1 QA Test Log Remediation Note

**Scope.** Every `FAILED` row in `docs/AEGIS Test Case Log Testing Phase Cycle 1
Complete.md` was traced against the actual implementation and fixed where a real
gap existed. This note records what was changed, how it was verified, and which
rows are now satisfied by behaviour that already existed.

**Method.** Each row was checked against the backend contract first (viewset,
serializer, permission, URL), then the frontend surface. Where the backend was
correct and only the UI was missing, the UI was added. Where the backend itself
was wrong, the backend was corrected. No test was weakened, deleted or bypassed;
new tests pin the fixed behaviour.

---

## 1. Fixed — frontend gaps only (backend already correct)

| Test case | Defect | Fix |
|---|---|---|
| TC-FAC-07 / TC-FAC-08 | No faculty UI existed for behavioral notes, although `BehavioralNoteViewSet` already accepted `POST` from `IsFacultyUser`, scoped it to the faculty's sections, and rejected blank text. | New `features/faculty/advisory-api.ts` + `FacultyAdvisoryPage.tsx` at `route: "faculty/advisory"` (faculty-only nav item "Advisory Class"), with roster, note form, and a client-side mirror of the server's blank rejection that still sends nothing. |
| TC-FAC-03 / TC-FAC-04 | No student-profile management surface existed for faculty (FR-007) and no write endpoint existed at all. | New `PATCH/GET /api/v1/academics/student-profiles/{id}/` (`StudentProfileManageSerializer`, `IsFacultyOrAdminUser`, faculty scope = enrollments in advised/taught sections, out-of-scope → 404) and a manage-profile dialog on the advisory page. Every field is required server-side, so a partial update is a 400 (TC-FAC-04). |
| TC-FAC-11 / TC-FAC-12 | Faculty could encode grades but not update them — `GradeViewSet` was `IsAdminOrReadOnly` for everything except `encode`. | `update`/`partial_update` now use the new object-level `IsFacultyOwnerOfGrade` (403 for another faculty's grade, admin unrestricted); the queryset is unscoped for those actions so the denial is explicit; `perform_update` refuses `status`/`encoded_by` changes from faculty with 403. UI: `useUpdateGrade` + an "Update grade" dialog on the faculty Academics page. The stale page note claiming faculty have no edit transition was corrected. |
| TC-FAC-17 / TC-FAC-20 | No consolidated advisory summary and no advisory export. | New `ClassSummaryCard` (real attendance counts from `/attendance/summary/` + real grade aggregates from the faculty grade queryset; blank average when nothing is scored, and the card says the counts are records, not a rate) and a new faculty-only `advisory` export kind (`ExportType.ADVISORY`, `ADVISORY_EXPORT_COLUMNS`, `_advisory_queryset_for`, `advisory_rows`, `AdvisoryExportView`, `exports/advisory/`) that reuses the existing `EXPORT_EMPTY` 400 envelope. |
| TC-SYS-07 / TC-STU-09 | Direct URL access to another role's route silently redirected with no message. | New `features/auth/AccessRestricted.tsx`; `RequireRole` now stays on the URL and renders the restricted message instead of bouncing. |
| TC-STU-03 | Student dashboard showed `N/A` for a student whose finalized grades existed. | Scores without a grading period now fall back to a single "Unassigned" bucket (`frontend/src/features/student/api.ts`), matching the Academics page. |
| TC-STU-04 | No class-schedule surface existed for students. | New `features/student/{schedule-api.ts, StudentSchedulePage.tsx}` + `schedule` route and nav item; the period label falls back to "Unassigned" rather than dropping the row. |
| TC-GUI-05 | Deploying a 0-question assessment answered 400. | The Deploy button is disabled at `question_count === 0` with an explanatory hint, on both the guidance and faculty assessment pages. |
| TC-GUI-07 | Guidance risk alert row crashed the page (`object is not iterable`) because the frontend expected a field the API does not return and the API did not return the one it does. | `risk_factors` is now surfaced by the backend's risk/student payloads, and the guidance/parent consumers read it through a shared `frontend/src/lib/risk-factor.ts` normalizer. |
| TC-FAC-18 / TC-FAC-19 | Faculty had no export UI, and an authorised-but-empty export produced a header-only file. | New `frontend/src/lib/export.ts` (`downloadExport`, `filenameFromDisposition`) plus the "Imports & exports" list on the faculty page; the backend now returns 400 `EXPORT_EMPTY` ("No data is available for this export.") when the authorised scope is empty. `hydrateBlobError` in `lib/error.ts` reads that envelope back out of the blob so the real message reaches the UI instead of "Request failed with status 400." |
| TC-ADM-05 | The guidance-records import type reported success without writing anything. | The legacy path now records `SKIPPED` rows with `UNSUPPORTED_IMPORT_TYPE`, `processed_rows = 0`, a terminal `failed` job, and a UI caveat on the admin data page. No status is fabricated. |

---

## 2. Verified as already satisfied (rows stale, no code change)

Each of these was checked against the implementation, and against tests that
already cover the behaviour:

| Test case | Evidence |
|---|---|
| TC-ADM-03 / TC-ADM-04 / TC-ADM-18 | `ImportJobViewSet` + `AdminDataPage` import grade/attendance files and reject malformed ones with per-row results; `apps.data_import` (293 tests) covers the pipeline. |
| TC-ADM-06 … TC-ADM-09 | `UserCreateView` (`POST /accounts/users/create/`) plus the Admin Users page create form with a role selector. |
| TC-ADM-16 / TC-ADM-17 | `apps.audit` records actor/action/timestamp and the admin audit page reads it; the students export is anonymised by design (`STUDENT_EXPORT_COLUMNS`). |
| TC-GUI-03 / TC-GUI-13 / TC-GUI-14 | Consultation create + blank rejection and guidance access control are covered by the guidance tests. |
| TC-GUI-08 | `GET /guidance/reports/student/{id}/` and the guidance student-profile page render the individual report. |
| TC-PAR-04 / TC-PAR-05 / TC-PAR-07 / TC-PAR-08 | Parent academics page (grades, attendance records, behavioral notes) with the error/empty distinction covered by `ParentAcademicsPage.test.tsx`. |
| TC-STU-05 / TC-STU-07 / TC-STU-10 | Attendance records; student assessments page; `AssessmentResultViewSet` rejects a second submission ("You have already submitted this assessment.") and the page splits Pending/Completed. |
| TC-STU-08 / TC-STU-11 / TC-STU-12 | `features/chatbot` and `RecommendationsCard` + `recommendations-api.ts`, which label the method (CF vs content-based) and render a real empty state instead of padding the list. |
| TC-STU-06 / TC-PAR-06 / TC-SYS-03 / TC-SYS-04 | `notifications` route and `NotificationPreferenceView` are available to all five roles; performance rows passed in the original run. |

---

## 3. Intentionally not implemented (needs a decision, not a guess)

| Item | Why |
|---|---|
| TC-ADM-10 (assign/modify role-based access) | `UserSerializer` keeps `role` read-only (SEC-001) and there is no update route for user accounts — only create. Adding a role-editing endpoint changes the authorization model and is not defined by any available source. |
| TC-ADM-11 (system-wide settings) | There is no `SystemSetting` model, view or route anywhere in the backend. PH11.9 removed the admin Settings nav item for exactly this reason. |
| TC-ADM-12 / TC-ADM-13 (create/publish announcements) | Announcements are authored in the external Strapi CMS; AEGIS reads them (`CmsAnnouncementList`, webhook intake). `AdminCmsPage` documents why a local create control would be a second, divergent source of truth. |
| TC-SYS-01 / TC-SYS-02 (self-registration, duplicate-email rejection) | Accounts are provisioned by an administrator (`UserCreateView`) and the login page has no sign-up. Adding public registration is a security-model change, not a UI gap. |
| TC-SYS-05 / TC-GUI-12 (Decision-Tree output interface and its incomplete-input behaviour) | The DT output exists as `RiskScore`/`RiskAlert` consumed by guidance; the recommender's content-based path already withholds classification when features are missing (empty `prediction`). No new AI surface was invented. |
| TC-SYS-08 (advance maintenance notice) | No maintenance-window model or scheduling exists. |
| TC-SYS-09 / TC-SYS-13 (text-field sanitisation and form-response timing) | These are properties of forms the original run could not reach; they are now exercised by the surfaces added above (blank-note rejection, profile validation, grade validation) rather than measured in a browser, which this repository has no harness for. |

---

## 4. Checks run

- `npm run typecheck` — PASS
- `npm run lint` — PASS
- `npm run format:check` — PASS
- `npm test` — PASS (49 files, 728 tests; baseline was 48 files / 707 tests)
- `npm run build` — PASS (chunk-size warning only, unchanged from baseline)
- Backend `manage.py test` (Django test settings) — PASS: 1 470 tests across
  `accounts`, `academics`, `attendance`, `guidance`, `assessments`,
  `data_import`, `audit`, `analytics`, `notifications`, `recommendations`,
  `chatbot`, plus 84 tests in `apps.accounts.tests_qa_dataset`; the three apps
  touched last (`academics`, `attendance`, `data_import` — 429 tests) were
  re-run after the final change.

---

## 5. Browser verification (local stack, `brave-devtools`)

The seeded QA dataset (`manage.py seed_qa_dataset`) plus a local Django and Vite
server were driven in a real browser, one login per role, over the surfaces this
work touched. Three real defects were found **only** by doing this — the unit
suite passed with all of them present:

1. **The advisory attendance summary was inflated 8×.** `GET /attendance/summary/`
   scoped faculty through `Q(section__adviser=fp) | Q(section__subject_assignments__faculty=fp)`.
   `subject_assignments` is a multi-valued relation, so the endpoint's
   `.values().annotate()` grouped on the wrong key: a class with 15 records was
   reported as 120 (one group per record, each counting every subject assignment
   in the section). The database agreed with the *export*, not the page, which is
   what exposed it. Fixed by filtering on section ids
   (`attendance/views.py::_faculty_section_ids`) and pinned by
   `FacultySummaryCountTest`.
2. **The manage-profile dialog reopened on stale data.** A save persisted, but
   reopening the dialog rendered the cached pre-save profile: React Query serves
   the stale copy first, and the form seeded from it before the refetch landed.
   Fixed by invalidating the profile query on success and holding the seed until
   the query is idle (`isFetching`), plus a regression test.
3. **Faculty could revise a finalized grade.** `POST /grades/{id}/finalize/` is
   admin-only, so a finalized grade is published — yet the new faculty update
   path accepted a score change on one, silently altering a number students and
   parents had already read. `perform_update` now refuses it for faculty with
   `"A finalized grade can no longer be changed."` (administration keeps full
   CRUD). **This one is a judgement call — flagging it in case the intended
   rule is different.**

Also verified in the browser: behavioral-note save and blank rejection, profile
save with a missing required field, out-of-range grade rejection, the advisory
CSV export, all three export endpoints returning `EXPORT_EMPTY` (400) for an
empty scope, valid and malformed admin imports, account creation, the audit log
recording every login with actor and IP, and the parent/Guidance risk-factor
surface that TC-GUI-07 originally crashed on.

### Every originally-FAILED row, re-checked

After fixing the defects above, the remaining FAILED rows were each driven in
the browser or read off the running API, so none is claimed on the strength of a
passing unit test alone:

| Row | Evidence |
|---|---|
| TC-FAC-03/04 | profile save persisted (reopened on the saved value); missing guardian contact rejected per-field, dialog kept open |
| TC-FAC-05/06 | attendance recorded with a live-region confirmation; **server** rejects a future date and an invalid status (400 with field detail) |
| TC-FAC-07/08 | note saved and listed; blank submission rejected with the server's wording and no request |
| TC-FAC-09/10 | grade encoded as draft (88.00) and visible in the records table; **server** rejects 150 and −5 |
| TC-FAC-11 | draft grade updated and re-rendered (72.50); finalized grade refused |
| TC-FAC-13/14 | grades batch upload completed (1 of 1); malformed file failed with 0 imported |
| TC-FAC-15/16 | attendance batch upload completed (1 of 1); the same pipeline's malformed rejection verified on grades |
| TC-FAC-17 | advisory summary matches the database (11 present / 1 late / 3 absent / 15 total per student) |
| TC-FAC-18/19 | all three export endpoints return a real CSV and 400 `EXPORT_EMPTY` on an empty scope |
| TC-FAC-20 | `exports/advisory/` downloaded as a CSV with one row per student |
| TC-GUI-05 | Deploy disabled at 0 questions with the explanatory hint |
| TC-GUI-07 | risk-alerts page renders 20 rows without the crash; risk factors shown to parents and guidance |
| TC-GUI-08/09 | report section renders the server's aggregates and downloads as CSV |
| TC-PAR-04/05 | attendance 86.7% and finalized grades for the selected child; behavioural notes on Student Support |
| TC-PAR-06 | a live `GRADE_POSTED` notification reached the linked parent's inbox |
| TC-STU-03 | dashboard shows 65.80% average, not `N/A` |
| TC-STU-04 | schedule page renders real periods per day |
| TC-STU-06 | a live `GRADE_POSTED` notification reached the student's inbox |
| TC-STU-09 | `/app/admin/users` as faculty shows the restricted message, not the page |
| TC-STU-10 | completed assessment sits in "Completed" with no re-take control; the API returns "already submitted" |
| TC-STU-11/12 | recommendations endpoint returns 200 (`content_based`) and the card renders its honest empty state |
| TC-SYS-07 | restricted-URL message verified for every wrong role |
| TC-SYS-09 | a `=HYPERLINK(...) <script>alert(1)</script>` note was stored and rendered as **inert text** (no script element created) |
| TC-ADM-03/04/18 | valid grades import completed (1 of 1); malformed file failed with a named row error |
| TC-ADM-05 | the no-importer path reports failure honestly (see §1) |
| TC-ADM-06…09 | account created through the New-account dialog, all five roles selectable |
| TC-ADM-16 | audit log recorded every login of this session with actor, action, target and IP |
| TC-ADM-17 | students export is anonymised by design (`STUDENT_EXPORT_COLUMNS`) |

**Not verifiable in a browser without more input:** TC-ADM-10/11 (no role-update
route, no SystemSetting model), TC-ADM-12/13 (authoring is in Strapi),
TC-ADM-14/15 (same), TC-SYS-01/02 (no self-registration by design), TC-SYS-05
(the DT writes `RiskScore` only when the engine runs — it is deliberately not
seeded), TC-SYS-08 (no maintenance-window model). TC-SYS-13 is satisfied in
substance — every form submission in this run answered in well under the
5-second requirement — but there is no load harness in this repository to
measure it formally.

**Limitations.** No browser harness exists in this repository, so this run was
manual (jsdom does not prove layout, and no Playwright/axe was added). Responsive
and screen-reader behaviour remain source-verified only.


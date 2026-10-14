# PH11 — Cycle-2 QA Test Log Remediation Note

**Scope.** Every `FAILED` row in `docs/AEGIS Test Case Log Testing Phase Cycle 2
Complete.md` (dated October 9, 2026) was traced against the current source.
Rows that are genuinely still failing were fixed where the gap was frontend; the
rest are classified as stale, test-data gaps, infrastructure, or real gaps that
need a decision rather than a guess.

**Method.** Same order as the Cycle-1 note: the row's requirement, then the
backend contract (viewset, serializer, permission, URL), then the frontend
surface. No test was weakened, deleted or bypassed; new tests pin the fixes.

---

## 0. The log is dated against a build older than HEAD

This matters for reading the whole file, because **28 of the 48 `FAILED` rows
describe surfaces that already exist at HEAD** (all 18 Faculty rows plus 10
other rows — see §3):

| Commit    | Date         | What landed                                      |
| --------- | ------------ | ------------------------------------------------ |
| `0bd89b7` | Oct 9, 2026  | Cycle-1 QA failures across all five roles        |
| `b036b5f` | Oct 11, 2026 | PH11.15 manual-QA UX overhaul                    |
| `55b24aa` | Oct 11, 2026 | Retired duplicated nav and stale entry points    |
| `feb643b` | Oct 11, 2026 | Replaced the last hairline bars with real charts |

The log was filed the same day the Cycle-1 remediation commit landed. Rows
logged as "Not implemented yet" for work committed hours earlier are stale
relative to the tree, not evidence of a regression.

---

## 1. Real defect found and fixed

### TC-GUI-05 — "the Counselor and Student accounts combine without authentication"

This was the most serious row in the log and it was **real**. Verbatim:

> Notice shows "I don't have permission" to create assessment. Note: The
> Counselor account and Student account combines without authentication. It auto
> change account login even, without proper sign authentication.

**Not a permission bug.** `CanCreateAssessment`
(`apps/assessments/permissions.py:53-70`) explicitly allows `role in
["faculty","guidance"]`, `IsAssessmentCreator` gates deploy on ownership only,
and the frontend posts to the right endpoints
(`guidance/api.ts:1423-1437`, `:1448-1462`). Guidance creating an assessment
returns 201 in the backend's own tests.

**It was a frontend session-identity defect.** `tokenStorage` holds one bearer
pair per browser origin under two fixed keys (`lib/auth-storage.ts`), so a
sign-in on any tab overwrites the session for every tab. A tab that was
mid-task kept rendering the first account's React state and cached rows while
every request it issued carried the second account's token — so the counselor's
create call was genuinely the student's request, and the backend was right to
refuse it. Three compounding paths:

1. **`login()` never cleared the react-query cache.** `logout()` and the
   session-expiry path both called `queryClient.clear()`; `login()` did not, so
   a second account was served the first account's dashboards for up to
   `staleTime` (60 s) and `AccountSettingsPage` was seeded from their cached
   `/accounts/me/` profile. Every query key is role-scoped but not user-scoped,
   so they collide between accounts. The hazard was already documented in the
   session-expiry comment at `AuthContext.tsx` — this path was simply missed.
2. **No signal that the slot changed hands.** Nothing listened for the swap, so
   a stale tab kept acting as an identity it no longer was.
3. **No way to tell "expired" from "replaced."** Both collapse to
   `unauthenticated`, so the sign-in page could only offer one sentence.

**Fix (frontend only, no API change):**

| File                            | Change                                                                                                                                                                                                                                                                                                                                                                                                                                                              |
| ------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `lib/auth-storage.ts`           | `accessTokenAccountId()` reads `user_id` from the token it already holds, plus `ACCESS_TOKEN_STORAGE_KEY`. Authorises nothing; it only lets a tab compare "the account I am" with "the account now in storage."                                                                                                                                                                                                                                                     |
| `features/auth/AuthContext.tsx` | A `storage` listener: when another tab writes a _different_ account's token, this tab gives up its own view of the session. `endSession()` clears the query cache and React state, and **deliberately does not clear `tokenStorage`** — the pair now belongs to the account that just signed in, and removing it would sign _them_ out. Same-subject writes (a silent refresh) are ignored, so a normal token rotation cannot sign a user out of their own session. |
| `features/auth/AuthContext.tsx` | `login()` now calls `queryClient.clear()` once the new tokens are stored — after, so a _rejected_ sign-in leaves the still-valid account's cache intact.                                                                                                                                                                                                                                                                                                            |
| `routes/pages/LoginPage.tsx`    | New `sessionEndedBy` reason: `"other-account"` renders "A different account signed in on this browser, so this session ended." `"expiry"` keeps the PH11.11 wording.                                                                                                                                                                                                                                                                                                |

**Pinned by 15 new tests** (`lib/auth-storage.test.ts`, plus sections 8–9 of
`AuthContext.test.tsx`): the takeover signs the tab out while leaving the other
account's pair alone; rotation does _not_; a cleared pair does; an unreadable
token does nothing rather than guessing; an unrelated key does nothing; an
unauthenticated tab is untouched; `login()` clears the cache and a failed
`login()` does not.

---

## 2. Second real defect found and fixed

**Dashboard hint contradicted its own failure state.** On `ParentDashboard` and
`StudentDashboard`, the `Attendance Rate` tile correctly headline "Unavailable"
when the request fails — but the hint beneath was computed independently from
`attendance`, so a failed request still read "No attendance records." That
asserts a measurement nobody made. The hint now distinguishes all three states
("Could not load attendance records" / "12 present, 0 absent" / "No attendance
records").

This is the same class of defect PH11.11 wave 4 called out, and it was invisible
to the unit suite because the hint was never asserted.

---

## 3. Stale rows — already satisfied at HEAD

Checked against source, not against the log's verdict.

### All 18 Faculty rows (TC-FAC-03 … TC-FAC-20)

Every one says "Not implemented yet." All exist, are role-gated to `faculty`,
and have tests:

| Rows                                             | Surface                                                                                                               |
| ------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------- |
| 03/04 (profiles + required-field rejection)      | `FacultyAdvisoryPage` manage-profile dialog → `PATCH /academics/student-profiles/{id}/`, out-of-scope → 404           |
| 05/06 (attendance + invalid date/status)         | `AttendancePage` faculty form, `max={today}` and a 3-option status select, server rejects a future date               |
| 07/08 (notes + blank rejection)                  | `FacultyAdvisoryPage` note form, client mirror fires no request                                                       |
| 09/10 (encode + out-of-range)                    | `AcademicsPage` `GradeEncodeForm`, `min=0 max=100`, server `validate_score`                                           |
| 11/12 (update + cross-advisory denial)           | `GradeEditDialog` → `PATCH`, `IsFacultyOwnerOfGrade` 403, edit list scoped by the backend                             |
| 13/14/15/16 (grades + attendance CSV, malformed) | `FacultyImportPage` → `/academics/grades/batch-import/`, `/attendance/records/batch-import/`                          |
| 17 (one-page summary)                            | `ClassSummaryCard` from `/attendance/summary/` + faculty grades                                                       |
| 18/19/20 (reports, export, empty scope)          | Export list `kind: "grades"` → `Subject performance report`, `downloadExport("advisory")`, backend `EXPORT_EMPTY` 400 |

Routes: `faculty/advisory`, `faculty/import`, `faculty/assessments`,
`academics`, `attendance`, `reports` — all registered, all `available`.

### Guidance / Parent / Student / System

| Row                                    | Status at HEAD                                                                                                                                               |
| -------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| TC-GUI-07 (`object is not iterable`)   | **Fixed.** `lib/risk-factor.ts` accepts both shapes; backend surfaces `risk_factors`; all four consumers read through it.                                    |
| TC-GUI-08 / 09 (guidance report + CSV) | **Resolved in this pass — see §9 (WP-8).** Was: `GuidanceReportSection` rendered `GET /guidance/reports/student/{id}/` with a *client-side* CSV that rebuilt a shorter report in the browser. The endpoint now serves `?file_format=csv|xlsx` from the same `report_data`, and the page calls it |
| TC-GUI-12 (incomplete-input)           | `risk_scorer.py` returns `risk_level: None`; `risk_service.py` stores the score but creates **no** alert; chart keeps `insufficient_data` as its own segment |
| TC-PAR-04 (attendance)                 | `ParentAcademicsPage` — summary card + day-by-day table with a status filter                                                                                 |
| TC-PAR-05 (behavioural concerns)       | `ParentSupportPage` — behavioural notes, risk alerts, counselling sessions with concerns                                                                     |
| TC-PAR-06 (notifications)              | `/app/notifications` is ungated for all five roles; header bell for every role                                                                               |
| TC-STU-04 (class schedule)             | `StudentSchedulePage` + student-only route + nav item, added for this row in Cycle 1                                                                         |
| TC-SYS-07 (wrong-role URL)             | `RequireRole` stays on the URL and renders `AccessRestricted`; `routes.test.tsx:165-233`                                                                     |
| TC-SYS-09 (malicious text)             | **Zero** `dangerouslySetInnerHTML` in `frontend/src`; React escapes; `lib/export.ts` guards formula injection                                                |
| TC-ADM-10's evidence                   | The quoted footer _"Not available through this API"_ was **removed on Oct 11** (`b036b5f`) and pinned by `routes.test.tsx:518`                               |

---

## 4. Not testable as written — test-data and tooling gaps

No code defect; these rows say so themselves.

- **TC-ADM-03 / 04 / 18** — "Test File not available. Could not be tested."
  The import UI exists (`AdminDataPage`, `<input type="file"
accept=".csv,.xlsx">` → `POST /data-import/jobs/`) and the pipeline runs. Needs
  a fixture file, not a fix.
- **TC-SYS-03 / 04** — "Load testing is needed" / "ML model testing is needed."
  No load harness exists in the repository (no k6/locust/artillery/jmeter). The
  only `benchmark.py` is the ML model-comparison harness.

---

## 5. Real gaps that need a decision, not a fix

| Row                   | Reality                                                                                                                                                                                                                                 | Why not fixed here                                                                                                                                                                                                                                                                                                                                                          |
| --------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| ~~TC-ADM-10~~         | **Resolved in this pass — see §9 (WP-4).** `PATCH /accounts/users/{id}/` now accepts exactly `role` and `is_active`, admin-only, with a self-lockout guard and an audit-log entry carrying the diff                                                                                                                            | Was: no role-update endpoint existed (`accounts/urls` had create/list/detail only) and `role` read-only by SEC-001. SEC-001 governs *self*-service, not the administrator surface, so the route does not weaken it                                                                                                                                                    |
| ~~TC-ADM-11~~         | **Resolved in this pass — see §9 (WP-5).** `SystemSetting` model (`apps/cms/models.py`, spec §E.6) with an admin-only `GET/PATCH /cms/settings/` surface, seeded by data migration. The attendance absence threshold is now read at the moment of the write, so a change applies to the very next absence with no restart | Was: no `SystemSetting` model/view/route anywhere; the PH11.9 nav removal was correct at the time, because the entry would have pointed at a page that could not exist |
| TC-ADM-12/13/14/15    | `AdminCmsPage` is "Read-only view" by design — content is authored in Strapi, AEGIS only proxies (`cms/views.py` has list/detail/download only)                                                                                         | CMS authoring is a Strapi/infrastructure concern; the 502 is `StrapiUnavailableError` (`_cms_unavailable_response`) because no Strapi instance is provisioned, and no write path exists in AEGIS to fix                                                                                                                                                                     |
| **TC-ADM-17**         | **`AdminGradesPage` shows identifiable `student_name` / `student_id` / score per student.** NFR-010 reads _"Admins shall view student data in aggregated/anonymized form **unless consent is given**"_ (`BACKEND_SPECIFICATION.md:133`) | **Needs a decision.** The repo reads NFR-010 as applying to _analytics_ (the low-performance card was removed for exactly this reason) and the grades page as ordinary oversight. There is **no consent model in the codebase** (`data_import/constants.py:234`). Either the admin grade view aggregates, or a consent model is added — both are product/architecture calls |
| ~~TC-GUI-04~~ | **AI question generation now exists — see §9 (WP-1).** `POST /assessments/question-drafts/` drafts self-report items for a counselor-supplied topic, and the chatbot's own intent classifier chooses which item bank drafts first. Was: no endpoint and no UI control.                                                                                  | Resolved in this pass. The row's other two notes (see §6) remain stale                                                                                                                                                                                                                                                                                    |
| TC-SYS-01/02          | No public registration endpoint by design; accounts are admin-provisioned                                                                                                                                                               | Security-model change                                                                                                                                                                                                                                                                                                                                                       |
| ~~TC-SYS-08~~         | **Resolved in this pass — see §9 (WP-13).** `MaintenanceWindow` + `POST /notifications/maintenance/` (admin-only) dispatches `MAINTENANCE_NOTICE` to every active user, and `clean()` refuses any window starting inside 24 hours | Was: no maintenance-window model, scheduler or notification type anywhere. The row's own "Actual Result" text (*"Duplicate email validation… registration is unavailable"*) is offset — that belongs to TC-SYS-01/02 |
| ~~TC-SYS-05~~         | **Determinism now pinned by test — see §9 (WP-12).** `RiskScorerTest.test_identical_input_produces_identical_classification` runs two independent train/predict cycles over one feature vector and compares level, score and probability vector                                                                                                                            | The row's actual-result text is misaligned (see §6); the property itself is now guarded rather than merely asserted                                                                                                                                                                                                                                                          |
| TC-SYS-10             | NFR-014 requires Chrome, Firefox, Edge; all real-browser evidence here is Chromium/Edge only, Firefox never exercised                                                                                                                   | Needs a browser matrix, not a code change                                                                                                                                                                                                                                                                                                                                   |

---

## 6. Problems with the log itself

Reported separately because they affect how much the file can be trusted.

1. **Five System rows have the wrong "Actual Results" text** — clear
   copy-paste misalignment:

   | Row       | Expected              | Actual as written                                             | That text actually belongs to |
   | --------- | --------------------- | ------------------------------------------------------------- | ----------------------------- |
   | TC-SYS-05 | DT consistency        | "Maintenance notifications are not sent 24 hours in advance." | TC-SYS-08                     |
   | TC-SYS-07 | Wrong-role URL        | "Register option is missing."                                 | TC-SYS-01                     |
   | TC-SYS-08 | Maintenance notice    | "Duplicate email validation cannot be tested…"                | TC-SYS-02                     |
   | TC-SYS-09 | Malicious input       | "Load testing is needed."                                     | TC-SYS-03                     |
   | TC-SYS-10 | Browser compatibility | "ML model testing is needed."                                 | TC-SYS-04                     |

   So 5 of 13 System rows carry a verdict whose stated reason is not about the
   row. Three of them (07, 09, 10) are recorded `FAILED` against text that
   describes something else entirely.

2. **Two TC-GUI-04 notes are contradicted by other rows in the same file:**
   "Add question shows in the sidebar" and "UI can't adopt when different
   sizes, some buttons can't click" — yet TC-SYS-11 (interface usable at
   320px and 1920px) is `PASSED`. Source agrees with TC-SYS-11: `AddQuestionForm`
   renders in main content inside a `<details>` disclosure, inputs are `w-full`,
   grids collapse at `sm:`. No page form renders in the sidebar (the sidebar is
   a nav drawer).
   "Chat bot in student portal, not implemented" — but TC-STU-08 (chatbot
   returns a relevant response) is `PASSED`. The assistant renders for all five
   roles from `AppShell`.

---

## 7. Checks run

- `npx tsc -b --force` (`npm run typecheck`) — **PASS**
- `npm run lint` (eslint) — **PASS**
- `npm run format:check` (prettier) — **PASS**
- `npm test` — **PASS**: 53 files / 767 tests (baseline 52 / 748; +15 tests for
  the session-identity fix, +4 for the FR-027 AI draft control)
- `npm run build` (`tsc -b && vite build`) — **PASS** (chunk-size warning only,
  unchanged from baseline)
- `manage.py test apps.analytics apps.chatbot apps.assessments
  --settings=config.settings.test` — **PASS**: 207 tests
- `manage.py test apps.accounts apps.audit --settings=config.settings.test` —
  **PASS**: 705 tests
- `manage.py test apps.data_import --settings=config.settings.test` — **PASS**:
  322 tests
- `manage.py test ai_engine --settings=config.settings.test` — **PASS**: 58
  tests

---

## 8. Limitations

- **No browser harness exists in this repository**, so the cross-tab takeover
  fix is covered by jsdom tests that dispatch `StorageEvent` directly. The
  `storage` event's real cross-tab delivery (browsers only fire it in _other_
  tabs) is not proven by any test here — it is a browser guarantee, not one of
  ours. jsdom does not prove layout.
- No Playwright/axe/browser tooling was added, per the execution contract.
- Responsive, screen-reader, cross-browser (Firefox) and load behaviour remain
  source-verified only.
- The stale rows in §3 were verified against source and the existing test
  suite, not re-driven in a browser against a deployed instance.

---

## 9. Remediation work completed in this pass

Work packages are numbered as agreed in the remediation plan. Each entry records
what was actually built, what was deliberately *not* built, and the tests that
pin it. Nothing below was committed — all changes are uncommitted in the working
tree, alongside unrelated pre-existing work that this pass did not touch.

### WP-12 — TC-SYS-05: Decision Tree determinism (done)

`RiskScorerTest.test_identical_input_produces_identical_classification` builds
the feature vector once, runs two independent train/predict cycles, and compares
level, score and the probability vector. `ai_engine`: 58 tests OK.

### WP-2 — TC-ADM-03/04/18: import templates (done)

`GET /data-import/templates/<type>/` returns the exact header row for each
import type. Templates ship **headers only**: an example row would have to invent
`student_id` values and scores, and a fixture that *looks* like data is worse
than no fixture. `IMPORT_TYPE_PARSES_ONLY` is gone from the frontend; the
`TemplateGuide` on the admin data page now names the real endpoint instead.

### WP-3 — TC-ADM-05: guidance-records importer (done)

New `importers/guidance.py` imports `ConsultationRecord` only (not
`BehavioralNote` — different app, different owner). Attribution is
server-controlled: `counselor` and `recorded_by` are forbidden columns; the
row's counselor is resolved from the student's `RiskAlert.assigned_counselor`,
else `Intervention.assigned_counselor`, else the row is rejected with
`NO_COUNSELOR`. The role matrix is unchanged (FR-012/FR-013): only admin may
submit `guidance_records`. `apps.data_import`: 322 tests OK.

### WP-4 — TC-ADM-10: role assignment (done)

`PATCH /accounts/users/{id}/` accepts exactly `role` and `is_active`.
Admin-only (`IsAdminUser`), `http_method_names` limited to get/patch/head/options
so `put` cannot reach the read-oriented `UserSerializer`, a self-lockout guard,
and an `audit_account_access_change()` hook. `accounts.User` was added to the
audit `MODEL_ALLOWLISTS` as exactly `("role", "is_active")` so the change is
diffed — which required retargeting three audit tests that had used
`accounts.User` as their "unallowlisted model" example to
`accounts.FacultyProfile`. The property they pin is unchanged; the new entry is
pinned separately, including that identity and credential fields are still never
serialized.

Frontend: `useUpdateUser` and an "Edit access" dialog on the admin users page,
disabled for the signed-in administrator's own row. The "Not available through
this API" card is gone, and the route-level test that asserted its absence now
asserts the reason it can be absent.

### WP-9 — N/A honesty (done)

**Backend.** Three aggregates reported a genuine 0 average as "no data", because
they used truthiness instead of an explicit null check:

| Where                                   | Was                            | Now                             |
| --------------------------------------- | ------------------------------ | ------------------------------- |
| `analytics.services.school_wide_aggregates` | `if avg_grade else None`    | `if avg_grade is not None`      |
| `analytics.services.section_performance`    | `if stats["avg"] else None` | `if stats["avg"] is not None`   |
| `analytics.services.grade_level_comparison` | `if avg else None`          | `if avg is not None`            |
| `chatbot.service.get_student_grade_summary` | `if avg else None`          | `if avg is not None`            |

This is the same lie `formatPercent` exists to prevent, committed one layer below
where the frontend cannot catch it: a school, section, grade level or student
whose finalized grades average 0 was shown as "N/A". `null` still means "nothing
to measure" — `Avg()` over an empty queryset is `None` and is unchanged.

**Frontend.** The dashboards already rendered `null` as N/A with distinct
loading and error states (PH11.11/PH11.16). What was missing was the *why*:
"Average Grade / Overall academic performance" said nothing about why the figure
was N/A. The hints are now state-aware on the student, parent and guidance
dashboards — "No finalized grades yet" / "No attendance records" / "Could not
load finalized grades" — the way the attendance tile already was.

### WP-1 — TC-GUI-04: AI chatbot-assisted question generation (done)

FR-027 in `Final_Revision.pdf` reads *"The system shall allow counselors to
create student assessments with AI chatbot assistance for question generation."*
It is a genuine requirement and it did not exist.

New `POST /assessments/question-drafts/` (guidance only), backed by
`apps/chatbot/question_generator.py`. Two decisions carry its honesty:

- **The chatbot's own model picks the item bank.** The counselor's topic is
  classified with the same intent classifier the student chatbot uses,
  phrased the way a student would say it (a bare noun phrase is out of
  distribution for a model trained on chat utterances). The intent selects which
  bank drafts first; an unconfident prediction falls back to the general bank,
  and the confidence is returned so the caller can see how much weight the
  selection carried.
- **Every draft is a self-report stem, never a fact.** A generator can honestly
  produce statements *about the respondent*; it cannot produce statements *about
  the world* and stand behind them. `true_false` is refused by name
  (`QUESTION_TYPE_UNSUPPORTED`) rather than half-supported, and no answer key is
  invented — a self-report item has none.

Nothing is persisted: the endpoint returns proposals, the form is filled, and a
question only exists once it has been back through
`POST /assessments/assessment-questions/` and `AssessmentQuestion.clean()`.

Frontend: an "AI draft (FR-027)" row on the counselor's add-question form. The
button stays enabled for `true_false` so the server's reason reaches the
counselor instead of being a control that silently does nothing.

15 backend tests and 4 frontend tests pin this, including that a draft survives
`AssessmentQuestion.clean()` — otherwise "AI-generated questions included" would
end at the proposal.

### WP-5 — TC-ADM-11: system-wide settings (done)

FR-034 (_"Admin shall manage system-wide settings"_) is in
`BACKEND_SPECIFICATION.md:105`, and the entity is specified in §E.6 with the
fields `key` (unique), `value` (text), `description`, `updated_by`. It had no
model, no view and no route — PH11.9 had removed the nav entry rather than ship
a link to a page that could not exist.

`SystemSetting` now lives in `apps/cms`, which is where §E.6 places it. It is
**not** part of the deferred Strapi work package: the model is ordinary Django,
and nothing here touches `strapi_client`, the webhook or the proxies.

Two decisions carry it:

- **The registry, not the table, knows the type.** `value` is text per spec.
  `apps/cms/settings_registry.py` is the single place that says what a setting
  means, so an unregistered key raises rather than reading as free text.
- **The reader degrades, it does not raise.** The serializer refuses a
  non-integer on the way in; `get_int_setting` is the runtime floor. A mistyped
  threshold falls back to the registered default of 3 — a fallback of 0 would
  alert on the first absence, which is the opposite of the intended effect.

Seeding is a data migration (`0004`), not a write inside the list endpoint. A
GET that inserts rows is a side effect waiting to surprise someone.

The "applied across the system" half of the test row is the part worth being
suspicious of. `ABSENCE_THRESHOLD = 3` in `apps/attendance/views.py` was a
module constant read once at import. It is now read at the moment of the write,
so an administrator's change takes effect on the very next absence with no
restart — and five tests in `AttendanceThresholdChangeTest` pin the direction
that matters operationally: raising the threshold must stop alerts that used to
fire, and lowering it must start alerts that did not.

Frontend: `AdminSettingsPage` at `admin/settings`. Each row states where the
setting bites, because "applied across the system" means nothing to someone
deciding whether to raise a threshold.

### WP-13 — TC-SYS-08: advance notice of scheduled maintenance (done)

NFR-012 reads *"Users shall be notified at least 24 hours in advance of
scheduled maintenance."* The repo has no task scheduler — no Celery, no cron,
no beat — so that guarantee could not be a job that fires later, and it could
not be tested against a clock that has not advanced yet.

It is enforced structurally instead, in two halves that are only the
requirement together:

- **A window may not start sooner than 24 hours from now.** `clean()` holds
  the rule, so every caller is covered — the API, the Django admin, a future
  management command.
- **The notice is issued when the window is created**, not in advance of it
  somewhere else. Both land in one transaction, so a dispatch that fails
  leaves no window either. A half-scheduled window whose notice never went out
  is precisely the state NFR-012 forbids, and leaving it behind to be noticed
  later would be leaving it behind.

The boundary fails safe: a window chosen at *exactly* T+24h is refused,
because the notice goes out an instant after the admin's timestamp and would
deliver 23.9999 hours. Accepting it would mean promising 24 and delivering
slightly less. `test_a_window_at_exactly_24_hours_is_refused` documents this
rather than hiding it.

The notice states its own lead time in hours. That is not decoration — NFR-012
is a claim about elapsed time, and putting the measured number in the artifact
is what makes the claim checkable from the recipient's side and not only from
a test's.

One existing test changed, and it got stricter:
`test_all_ten_types_exist` asserted `len(choices) == 10`, which passes if a
type is *renamed or swapped* — it only ever caught additions and removals. It
is now `test_the_notification_types_are_exactly_these`, asserting the explicit
set. A bare count is the weaker property of the two.

Deliberately not built: a background scheduler that re-sends a reminder, and
an admin UI for scheduling. The row asks that users *receive* the notice; the
API plus the existing notifications surface delivers that, and a scheduler is
infrastructure this repo does not have. Scheduling is reachable through
`POST /notifications/maintenance/` and the Django admin, both of which route
through the same service so the guarantee holds either way.

### WP-8 — TC-GUI-08/09: guidance report + export (done)

Both rows read "Not Implemented Yet", and half of that was already false. The
JSON report existed, was wired to a URL, and was rendered on
`StudentProfilePage` — FR-032's "generate an individual student guidance
report" was in the codebase.

The genuine gap was TC-GUI-09, and it was subtler than "missing". A CSV
download *did* exist: `downloadCsv()` in `lib/export.ts`, with a docstring
naming TC-GUI-09. But it built its rows **in the browser**, from a hardcoded
list that repeated `student_id` and `student_name` on every row and simply did
not include consultations-by-priority, interventions completed/cancelled, or
any risk-alert detail. The counselor looking at a seven-section report and
downloading a five-metric file were looking at two different documents. That
is why the row still read as failed: a file that downloads is not the same as
a report that was exported.

So the fix is deletion plus one parameter:

- `GET /guidance/reports/student/{id}/` gained `?file_format=csv|xlsx`,
  rendering **the same `report_data` dict** the JSON branch serializes. The
  rows cannot drift from the screen because they are the screen's data.
- The ~50 lines of client-side row building are gone. The endpoint now reuses
  the controlled-export machinery (`build_export_payload`,
  `build_content_disposition`, `safe_export_filename`, the EXPORT audit event,
  the `EXPORT_EMPTY` rule from TC-FAC-19).
- `downloadGuidanceReport()` replaces `downloadCsv` at that call site.
  `downloadCsv` itself stays — `AdminDataPage` still uses it for import
  templates, which are genuinely client-held rows with no server export.

`ExportType.GUIDANCE_REPORT` is deliberately **outside `ExportType.ALL`**, the
same way `ADVISORY` is: `ALL` is the administrator authority list, and a
per-student guidance report means nothing to an administrator.

Empty sections say so. A report with no risk alerts carries
"No risk alerts recorded", because a report that silently drops a section
looks identical to one from a system that does not track that thing at all,
and those mean very different things to a counselor.

### Still open

| Package | Rows            | Status                                                          |
| ------- | --------------- | --------------------------------------------------------------- |
| WP-6    | TC-ADM-12..15   | **Deferred by decision.** No Strapi instance is provisioned     |
| WP-7    | TC-ADM-17       | Not started. Needs the consent-model decision recorded in §5    |
| WP-10   | TC-SYS-01/02    | Not started. Invite-code registration + school-email domain     |
| WP-11   | TC-SYS-03/04    | Not started. Dependency-free load harness (Node 20 `fetch`)     |
| WP-0    | 29 stale rows   | Blocked on a running local stack (Django + Postgres + Vite)     |
| WP-14   | TC-SYS-10       | Blocked. Chromium/Edge verifiable here; Firefox only if needed  |

### Completed

| Package | Rows      | What landed                                                                                                              |
| ------- | --------- | ------------------------------------------------------------------------------------------------------------------------ |
| WP-5    | TC-ADM-11 | `SystemSetting` + `settings_registry`, admin-only `GET/PATCH /cms/settings/`, seed migration `0004`, attendance threshold now read per-write, `AdminSettingsPage` |
| WP-13   | TC-SYS-08 | `MaintenanceWindow` (24h rule in `clean()`), `MaintenanceWindowList` admin-only, `MAINTENANCE_NOTICE`, notice states its own lead time, Django admin routed through the same service |
| WP-8    | TC-GUI-08/09 | Report endpoint gained `?file_format=csv|xlsx` over the same `report_data`; client-side row rebuild deleted; `downloadGuidanceReport` |

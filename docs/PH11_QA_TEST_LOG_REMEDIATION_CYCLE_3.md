# PH11 — Cycle-3 QA Test Log Remediation Plan

**Scope.** Every `FAILED` row in `AEGIS Test Case Log Testing Phase Cycle 3 Complete.md`
(dated October 9, 2026), traced against current HEAD. Three buckets:

1. **Real defect in code** — fix listed with files.
2. **Stale row** — feature already exists at HEAD; only fix is a re-test with the right data/account.
3. **Test-harness / decision gap** — needs a tool, a decision, or the log itself corrected.

Method mirrors Cycle 1/2: requirement → backend contract → frontend surface. No test weakened.

---

## 1. Attachment bug first: several rows are copy-paste errors in the log

These rows have *Actual Results* that do not belong to their test objective
(paste residue from neighboring rows). Fix the log before re-testing, otherwise
the next cycle inherits wrong evidence:

| Row | Objective | Pasted-in actual result (wrong) |
| --- | --- | --- |
| TC-FAC-01 | Faculty login | "adding a student profile is not functional" |
| TC-FAC-19 | Export report with no data | "adding a student profile is not functional" |
| TC-FAC-20 | Advisory summary export | "guardian contact numbers containing letters…" |
| TC-FAC-02 | Login negative test | guardian-contact validation finding (belongs to TC-FAC-01's module flow) |

---

## 2. Data import/export round-trip (FR-037) — TC-ADM-03, TC-ADM-04, TC-ADM-05

Root cause is verified: **exporters and importers disagree on headers.**
Export columns: `data_import/exports.py:42-74`. Import schemas: `data_import/importers/base.py:33-103`.

| Error in log | Verified cause |
| --- | --- |
| Grades import: missing `subject_assignment` | Header policy in `importers/base.py:36-46` vs exporter's `GRADE_EXPORT_COLUMNS` (`exports.py:42`) disagree on required/allowed set |
| Student import: missing `email, first_name, last_name` | `STUDENT_EXPORT_COLUMNS` (`exports.py:67-74`) is the anonymized set by design (`exports.py:66`), but `STUDENT_REQUIRED_COLUMNS` (`base.py:68-74`) needs identity columns |
| Attendance import: unknown `recorded_by, student_name` | Exporter emits both (`exports.py:57-64`); importer forbids `recorded_by` (`base.py:52`) and allows only the four required columns (`base.py:55`) |

**Plan (fix at the exporter, keep importer strict — strict unknown-column policy is deliberate anti-forgery, keep it):**

1. Add round-trip column sets in `exports.py`, one per importer schema, matching `base.py` exactly:
   - `GRADE_ROUNDTRIP_COLUMNS` = required + optional grades columns only (drop `student_name`, `grade_level`, `letter_grade`, `remarks`, `status`, `encoded_by`).
   - `ATTENDANCE_ROUNDTRIP_COLUMNS` = `student_id, section, date, status` (drop `recorded_by`, `student_name`).
   - `STUDENT_ROUNDTRIP_COLUMNS` = `STUDENT_REQUIRED + STUDENT_OPTIONAL` (adds `email, first_name, last_name`; see consent note below).
2. Expose them: either a `?schema=reimport` query param on each `*ExportView` (`data_import/views.py:446-472`) or new admin-only roundtrip views registered in `data_import/urls.py:34-53`. Keep the existing human-readable exports untouched.
3. Columns that are anonymized on purpose (student identity) may only appear in the admin round-trip export when the viewer is admin **and** the consent/visibility rules behind TC-ADM-17 are honored — implement behind the same guard `ExportsViewMixin` already uses for admin-only `/students`.
4. TC-ADM-05: `/exports/guidance/` does not exist (only per-student guidance report at `data_import/urls.py:41` + `GUIDANCE_REPORT_COLUMNS`). Add `GuidanceExportView` with `GUIDANCE_ROUNDTRIP_COLUMNS` matching the guidance import schema (`base.py:106+`), reusing `ExportViewMixin`.
5. Acceptance: **every round-trip export re-imports with 100% rows OK**, same file, no edits. Backend integration test per type in `apps/data_import/tests*.py`. This single acceptance covers TC-ADM-03, TC-ADM-04, and (once implemented) TC-ADM-05.

---

## 3. Announcements & CMS resources (FR-033, FR-035) — TC-ADM-12/13/14/15

Verified: all four endpoints (`apps/cms/views.py:186-379`) are **read-only Strapi proxies by design**; authoring lives in Strapi (`cms/src/api/announcement/…`, `cms/src/api/resource/…`). `StrapiUnavailableError → 502` (`apps/cms/services/strapi_client.py:281`) explains the 502s: **Strapi was not reachable during the test.** "Read-only view Implementation" is not a code string; it is the intended architecture (`AdminCmsPage.tsx:31-48`).

**Plan — decision + two small fixes:**

1. **Decision needed from the team:** either (a) authoring stays in Strapi and the test is executed against the live Strapi admin (update Condition/Expected in the log), or (b) build admin authoring inside AEGIS (new write-proxy in `apps/cms` + UI in `AdminCmsPage.tsx`). Option (a) is a config/re-test; option (b) is a feature. Recommend (a) for Cycle 4.
2. Fix the 502 UX either way: catch `StrapiUnavailableError` in the frontend admin API layer (`features/admin/api.ts:91-98`) and render "Content service unavailable — CMS backend not reachable" instead of a raw 502 error.
3. For TC-ADM-15 (invalid resource type rejection): validation lives Strapi-side (`cms/src/api/resource/...`). Re-test by uploading an unsupported MIME through Strapi admin; if it accepts, tighten `schema.json`/upload provider config there.

---

## 4. Grades: 409 on draft encode, batch import failures (FR-010–FR-012) — TC-FAC-07/08/10/11/12/13/14

1. **409 is correct behavior**, not a bug: `apps/academics/views.py:678` returns 409 when a grade already exists for (student, subject_assignment, period). The defect is the UX — the tester saw a raw "Request Failed with status 409".
   - Fix: map that 409 in the faculty grade UI (`frontend/src/features/faculty/…`) to "A grade for this student/subject/period already exists — open the existing grade to update it", and offer the update path (deep link or inline switch to update mode).
   - This unblocks TC-FAC-08 (invalid-grade validation) which was blocked by the raw 409.
2. **TC-FAC-11 (update grade) / TC-FAC-13 (batch grades Excel):** both funnel through `apps/academics/views.py:748-766 → apps/data_import/importers/grades.py`. After the §2 round-trip alignment, regenerate the test-grade Excel from the new export and re-test. If a real parse failure remains, capture `ImportJob` error rows — the runner already stores per-row errors (`runner.py`).
3. **TC-FAC-12/14 ("failed to import, 0 of 0 rows", no clear validation error):** empty/invalid-header files produce an aggregate failure with no actionable message. Fix in `data_import/importers/base.py` + `runner.py`: when zero rows are processed or headers are missing, the import-error payload must list the offending column names / reason, surfaced verbatim in the faculty import UI (Neg tests TC-FAC-14 and TC-ADM-18 expect named-column messages).
4. **TC-FAC-10 (BLOCKED, access control):** no code change known; re-test with two faculty accounts, one outside the section. If update outside advisory class succeeds, enforce in `apps/academics` update view the same advisory-class queryset filter used by fetch.

---

## 5. Guardian contact validation — TC-FAC-01/02 residual

Verified: `guardian_contact` is a plain `CharField(max_length=255)` (`apps/accounts/models.py:77`); only max length enforced on the edit path (`apps/academics/serializers.py:171-172`).

**Plan:**
1. Add validation: strip `+`, spaces, dashes; remaining chars must be digits only, length 7–15 (PH convention ≤ 11-digit local). Implement once in `accounts` (serializer used by both admin create and faculty edit), not per-page.
2. Frontend mirror: same rule as zod schema in the faculty profile form and admin forms.
3. Backend test: letters rejected, >11 digits (beyond bound) rejected, valid numbers pass.

---

## 6. "No data available" handling (FR-014, FR-015) — TC-FAC-17/19

Analytics services return empty aggregates (`apps/analytics/services.py:290-453`). Gap: the subject performance table/report renders empty with no empty-state message.

**Plan:** in `frontend/src/features/reports/ReportsPage.tsx` (and the faculty summary the tester saw), render a standard "No data available yet for this subject/period" empty state when aggregate rows are empty, including on the downloadable export (export with zero rows → file with headers only + aFlashless "no data" notice at generation time). Approximately 3 small UI changes + 1 service guard returning an explicit `empty: true` rather than zero rows.

---

## 7. Guidance module — TC-GUI-04/05/07/08/12

1. **TC-GUI-04 (AI question generation, FR-027): implemented at HEAD** — `apps/chatbot/question_generator.py:239` + `apps/assessments/views.py:315-338`. Likely tested on a stale build or behind a disabled toggle. Re-test first; if still inactive, check the feature flag/env the assessments view expects, not new implementation.
2. **TC-GUI-05 ("I don't have permission" + account blending):** permission design is correct (`assessments/permissions.py:53-70` allows guidance to create; deploy is owner-only). The account-blending symptom was diagnosed and **fixed in Cycle 2** (per-tab token storage, `lib/auth-storage.ts`). If symptoms reappear, check for a regression in that fix; else the button the tester hit was *deploy/update* on an assessment created by someone else — owner-only is intended; re-test with the counselor who created it.
3. **TC-GUI-07/12 (at-risk alert crash, FR-030/NFR-007): real bug, verified.** `ai_engine/risk_service.py:161-217` writes `risk_factors` as dicts/objects while counselors' alerts store strings; `apps/guidance/serializers.py:131` emits both unchecked and something iterates them → `object is not iterable` crash.
   - Fix (recommended once at the boundary): normalize `RiskAlert.risk_factors` to strings in the serializer and in `risk_service.py` (dict → "factor: description" string), so every consumer gets one shape. Optional hardening: a data migration normalizing existing rows.
   - TC-GUI-12 additionally needs the incomplete-input guard: `RiskService` should skip-with-flag insufficient-data cases instead of classifying (log `RISK_ALERT_COMPUTATION.md` behavior). Add test: incomplete records → no alert, or alert explicitly marked `incomplete_data`.
4. **TC-GUI-08 (individual guidance report, FR-032): implemented at HEAD** — `guidance.py:41` (`name="guidance-report"`) + `GUIDANCE_REPORT_COLUMNS` (`exports.py:102`). Tester note even says the download works for CSV/Excel. Verify the UI exposes the button; if UI is present, log as stale and re-test.

---

## 8. Parent portal — TC-PAR-04/05/06

1. **TC-PAR-04 (child attendance, FR-025): queries already exist** (`features/parent/api.ts:150-224`) but no dedicated attendance route (`routes/routes.tsx:254-273`). Surface it: add `parent/attendance` route + page using existing queries (or a clearly-labeled attendance card/section if the design intends embedding — pick per design language PH11.2).
2. **TC-PAR-05 (child behavioral concerns, FR-026): exists** (`ParentSupportPage.tsx:73-418`, `api.ts:401-450`). Re-test; additionally fix the responsive layout note (sidebar interaction at small sizes — same UI fix as SYS-12's caveat).
3. **TC-PAR-06 (parent notifications, FR-020–022):** backend covers student notifications only. Extend: when a risk alert / behavioral note / attendance event concerns a linked child, emit a notification for parent accounts too (guard: only the linked parent, reusing the FR-020 pipeline in `apps/notifications/events.py`), respecting TC-ADM-17/NFR-010 (no behavioral detail beyond what consent allows).

---

## 9. Notifications UX (TC-STU-08 note, TC-PAR-06 pop-up)

Inbox exists (`features/notifications/NotificationsPage.tsx`) with mark-as-read and click-through links.

**Plan:**
1. Make rows clickable → navigate to `resolveNotificationHref` target, then auto mark-as-read (call the existing mark endpoint on open). One mutation call added to the click handler.
2. Full-message view: clicking a notification opens its complete message (route to detail or modal pop-up) instead of truncating — satisfies "view the notification in full message just like a pop-up".

---

## 10. Registration (FR-001, NFR-006) — TC-SYS-01/02

Verified: registration exists at HEAD — `/register` route (`frontend/src/routes/routes.tsx:82`), link on the login page (`LoginPage.tsx:257`), backend flow `apps/accounts/registration.py:56-98`, zod schema `RegisterPage.tsx:30`.

1. TC-SYS-01: **stale row — re-test on the current build.**
2. TC-SYS-02 (duplicate email): the backend deliberately answers identically for taken emails (anti-enumeration, `models.py:292-348`). Conflict: the test expects an explicit "email already in use" message. Reconcile at design level — either relax the enumeration defense (test passes, security weaker) or update the test's Expected Results to "same neutral message as a new email, no account created" (keep NFR-006 intent: no duplicate registration). Neither code nor log changed unilaterally; decide in Cycle-4 intake.

---

## 11. Test tooling — TC-SYS-03 (NFR-004), TC-SYS-05 (NFR-007)

No load harness exists (`backend/scripts/` has no k6/locust/pyperf script).

1. **Load test:** add a k6 (or locust) script in `backend/scripts/` hitting: login → role dashboards (per TC-SYS-04 fixtures), one read-heavy page per role, and one write action; run at the reduced-concurrency scale SQAP Section 14.6 defines. Record baseline vs N-user latency; store the result doc next to QA notes. Then re-test TC-SYS-03 with numbers.
2. **ML consistency (TC-SYS-05):** verification already exists backend-side — `ai_engine/benchmark.py`, `ai_engine/validation.py`, `ai_engine/tests.py`, `train_risk_model.py`, `run_risk_computation.py`. Procedure: seed `seed_qa_dataset.py`, run computation twice on identical inputs, diff `risk_factors`/`classified` outputs, attach the two dumps as evidence. Do not attempt to verify through the student UI.

---

## 12. PASSED-with-caveats (no failure, tracked only)

| Row | Caveat | Follow-up |
| --- | --- | --- |
| TC-ADM-17 | Consent not verifiable | Ship the consent flag source of truth (see §2 item 3) and re-derive the anonymization evidence |
| TC-SYS-12 | Sidebar responsive at 320px | CSS-only fix in shared sidebar component; keep fixed while scrolling |
| TC-GUI-04/UI notes, TC-PAR-05 note | Responsive sizing gaps | Sidebar/modal breakpoint pass (same PR as SYS-12) |
| TC-GUI-13 note | Past date/time accepted in consultation | Optional: add past-datetime validation if SRS requires |

---

## 13.1 Status at end of the Cycle-3 remediation sprint

| Failed row | Disposition |
| --- | --- |
| TC-ADM-03, TC-ADM-04, TC-ADM-05 | **FIXED** — code landed (round-trip export `?schema=reimport` + guidance-records export); tests green. QA re-test owed. |
| TC-FAC-02, TC-FAC-07, TC-FAC-08, TC-FAC-11, TC-FAC-12, TC-FAC-14 | **FIXED** — code landed (guardian-contact validator, DRF `{detail}` error surfacing, `error_log` in history); tests green. QA re-test owed. |
| TC-GUI-04, TC-GUI-07, TC-GUI-08, TC-SYS-01, TC-SYS-02 | **STALE** — feature verified present at HEAD; no code change needed. QA re-test owed. |
| TC-ADM-12, TC-ADM-13, TC-ADM-14, TC-ADM-15 | **DECISION** — CMS authoring stays in Strapi; 502 was Strapi unreachable during the test run. |
| TC-SYS-03, TC-SYS-05, TC-FAC-10 | **CANNOT DO TODAY** — load harness, backend ML evidence, two-account access-control check. |
| TC-FAC-17, TC-FAC-19, TC-FAC-20, TC-PAR-04, TC-PAR-05 | **LIKELY STALE / ALREADY HANDLED** — ChartState empty states and `EXPORT_EMPTY` exist; confirm in re-test. |
| TC-PAR-06 (parent notifications) | **OPEN** — backend emits student notifications only; needs parent fan-out. |
| TC-ADM-17 (consent caveat) | **DEFERRED** — no consent model; walked with the student round-trip export. |

Verification run for this status: backend `apps.data_import` 348 tests OK, `apps.academics` 100 tests OK; frontend `error`/`export`/`admin api`/`faculty` 48 tests OK; `tsc --noEmit` clean; `manage.py check` clean.

## 13. Execution order for Cycle 4

| # | Work | Rows cleared | Type |
| --- | --- | --- | --- |
| 1 | Risk-alert `risk_factors` shape fix (§7.3) | GUI-07, GUI-12 | crash fix |
| 2 | Import/export round-trip (§2) | ADM-03, ADM-04, ADM-05 | feature |
| 3 | 409 UX + import error-message clarity (§4.1, §4.3) | FAC-07, FAC-08, FAC-12, FAC-14 | defect |
| 4 | Guardian contact validation (§5) | FAC-01/02 residual | defect |
| 5 | No-data empty states (§6) | FAC-17, FAC-19 | defect |
| 6 | Parent attendance route + notifications (§8.1, §9) | PAR-04, PAR-06, STU-08 note | feature |
| 7 | CMS decision + 502 UX (§3) | ADM-12/13/14/15 | decision + small fix |
| 8 | Load-test script + ML evidence (§11) | SYS-03, SYS-05 | tooling |
| 9 | Duplicate-email decision (§10.2) | SYS-02 | decision |
| 10 | Re-tests of stale rows: SYS-01, GUI-04, GUI-05, GUI-08, PAR-05, FAC-10/11/13, FAC-20 | — | re-test |
| 11 | Log corrections (§1) + caveats (§12) | — | hygiene |

Rows 1–6 are the code sprint (~all deliverable in one cycle); rows 7 and 9 need a decision; row 10 is pure re-testing once 1–6 land.

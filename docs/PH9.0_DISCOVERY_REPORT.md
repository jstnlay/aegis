# AEGIS PH9.0 AI / ANALYTICS DISCOVERY + ARCHITECTURE REPORT

**Generated:** 2026-09-01
**Git Checkpoint:** `1f723289d1c0ee4cdbaead54e46e78e482baf997`
**Status:** Discovery/design only — no code modified.
**Python:** 3.14.0 (64-bit) | **Django:** 6.1 | **DB:** PostgreSQL

---

## Table of Contents

1. [Source-of-Truth Findings](#1-source-of-truth-findings)
2. [Confirmed Requirements](#2-confirmed-requirements)
3. [Explicitly Unapproved Decisions](#3-explicitly-unapproved-decisions)
4. [NLP / Chatbot Boundary](#4-nlp--chatbot-boundary)
5. [Current Repository State](#5-current-repository-state)
6. [Data Readiness Matrix](#6-data-readiness-matrix)
7. [Decision Tree Feasibility](#7-decision-tree-feasibility)
8. [Collaborative Filtering Feasibility](#8-collaborative-filtering-feasibility)
9. [Analytics / Visual Reporting Scope](#9-analytics--visual-reporting-scope)
10. [RiskAlert Integration Delta](#10-riskalert-integration-delta)
11. [Privacy / Security Gate](#11-privacy--security-gate)
12. [External AI Boundary](#12-external-ai-boundary)
13. [Free / No-Recurring-Cost Technology Evaluation](#13-free--no-recurring-cost-technology-evaluation)
14. [Technology Recommendation Matrix](#14-technology-recommendation-matrix)
15. [Total Cost / Free-Tier Assessment](#15-total-cost--free-tier-assessment)
16. [Performance / Deployment Assessment](#16-performance--deployment-assessment)
17. [Architecture Options](#17-architecture-options)
18. [Recommended Architecture](#18-recommended-architecture)
19. [Model/Data Feasibility Status](#19-modeldata-feasibility-status)
20. [Decision Register](#20-decision-register)
21. [Proposed PH9 Sub-Phase Structure](#21-proposed-ph9-sub-phase-structure)
22. [Risks / Blockers](#22-risks--blockers)
23. [Questions Requiring Our Discussion](#23-questions-requiring-our-discussion)
24. [Recommended Next Action](#24-recommended-next-action)

---

## 1. Source-of-Truth Findings

### Priority Order Applied

| Priority | Document | Location | Status |
|----------|----------|----------|--------|
| 1 | Final_REvision.pdf | `docs/capstone/Final_REvision.pdf` (163 pages, 3.9 MB) | Primary source |
| 2 | Panel corrections / commentary-notes.pdf | `docs/capstone/commentary-notes.pdf` (188 KB) | Adopted into BACKEND_SPECIFICATION.md §B |
| 3 | BACKEND_SPECIFICATION.md | `docs/BACKEND_SPECIFICATION.md` (1497 lines, 68 KB) | v2.0, traces all decisions to sources |
| 4 | AEGIS Development Checkpoint | Git log + Obsidian notes | Phase 8 frozen at `1f72328` |
| 5 | Existing Phase 1–8 implementation | `backend/aegis_backend/apps/*` | Verified against spec |
| 6 | Security notes | Security sections in spec §J | Phase 8 export security confirmed |
| 7 | Git history | 9 commits, `78ccdf8` → `1f72328` | Clean, checkpointed |

### Key Source-of-Truth Findings

**Final_REvision.pdf** is the capstone thesis document (Batangas State University). It defines:
- All functional requirements (FR-001 through FR-040) and non-functional requirements (NFR-001 through NFR-015)
- Six dashboard wireframes: Home/Student (Figure 11), Academic Assessment (12–13), Student Academic Reports (14), Parent (18–20), Faculty (22–24), Guidance Counselor (27–32), Admin (35–37)
- AI Academic Insights and Learning Recommendations sections on the student dashboard (Figure 13–14)
- AI Risk Alert Cards on the guidance dashboard (Figure 27, items 16–17) showing risk factors and recommended actions
- AI Risk Alerts detail page (Figure 32) showing risk score percentage, progress bar, and AI Recommendation Section
- Detailed text descriptions of every dashboard element in the document body

**BACKEND_SPECIFICATION.md §I** explicitly marks the following as UNAPPROVED with the header: *"Everything in this section is [UNAPPROVED] unless marked otherwise."* (line 1299). This is the definitive record of what has and has not been approved.

**Conflict identified:** The PDF wireframes show a "numerical risk score percentage" and "AI Recommendation Section" as concrete UI elements. The backend specification marks the underlying computation parameters (features, weights, thresholds, score meaning) as UNAPPROVED. **Resolution:** The UI elements are confirmed in the source-of-truth PDF. The computation that populates them is UNAPPROVED. The UI can be built as a placeholder; the data source cannot.

**Chatbot / NLP reconciliation:** Final_REvision.pdf defines FR-031 ("The system shall flag and escalate AI Chatbot interactions that indicate student concerns requiring counselor follow-up.") and describes the AI Chatbot Engine (Objective 6.3) as a confirmed system capability. BACKEND_SPECIFICATION.md §I.6 deferred chatbot code from the **initial backend** — that is an implementation-timing constraint, not evidence that the chatbot is removed from the AEGIS system. See §4 for the full distinction, and §20 D16, D23–D30 for the open Phase 9 decisions.

---

## 2. Confirmed Requirements

These are drawn from BACKEND_SPECIFICATION.md §A, traced to Final_REvision.pdf.

### A.7 — Analytics Functional Requirements (PH9 scope)

| ID | Requirement | Source |
|----|-------------|--------|
| FR-030 | The system shall generate AI-driven at-risk student alerts based on academic performance patterns using a Decision Tree algorithm. | Final_REvision FR-030 |
| FR-039 | The system shall produce AI-driven recommendations using Collaborative Filtering. | Final_REvision FR-039 |
| FR-040 | The system shall produce AI-driven recommendations using Decision Tree algorithms. | Final_REvision FR-040 |
| FR-ANALYTICS-VISUAL | The system shall provide visual reports and graphs on school-wide academic performance and attendance trends. | Final_REvision Objective 6.1 |

### A.9 — Chatbot Functional Requirement (PH9 scope)

| ID | Requirement | Source |
|----|-------------|--------|
| FR-031 | The system shall flag and escalate AI Chatbot interactions that indicate student concerns requiring counselor follow-up. | Final_REvision FR-031 (Guidance Module) |

> **Reconciliation note:** FR-031 originates in Final_REvision.pdf (Guidance Module). It is NOT catalogued in BACKEND_SPECIFICATION.md §A, which deferred chatbot code from the initial backend (§I.6). This report therefore treats FR-031 as a confirmed system capability (§4) whose implementation phase remains a Phase 9 approval decision (§20 D16, D23–D30).

### A.8 — Relevant Non-Functional Requirements

| ID | Requirement | Relevance to PH9 |
|----|-------------|-------------------|
| NFR-003 | Any user action shall complete within 5 seconds under normal conditions. | ML inference must not breach this |
| NFR-004 | System shall support up to 500 concurrent users without >2s degradation. | Batch precompute recommended |
| NFR-005 | Dashboard shall load all data within 5 seconds of login. | Analytics queries must be cached/precomputed |
| NFR-007 | Decision Tree shall produce consistent outputs given the same input. | Requires deterministic model (same seed, same input → same output) |
| NFR-009 | Students shall only view/modify their own data. | Risk scores visible to student only for their own profile |
| NFR-010 | Admins shall view student data in aggregated/anonymized form unless consent is given. | Admin analytics must be aggregated |
| NFR-011 | RBAC shall ensure users access only data/features for their role. | All AI endpoints need permission scoping |

### UI Elements Confirmed in PDF Wireframes (Student-Facing)

| Element | Dashboard | Description |
|---------|-----------|-------------|
| "AI Academic Insights Section" | Student (Figure 13–14) | AI-generated summary: strengths, areas needing improvement, behavioral recommendations |
| "Learning Recommendations Section" | Student (Figure 13–14) | Personalized study activities from performance data |
| "AI Assistant Button" | Student hamburger menu (Figure 14) | Navigates to AI-powered academic assistant (chatbot — confirmed capability; implementation deferred from initial backend — see §4) |

### UI Elements Confirmed in PDF Wireframes (Guidance-Facing)

| Element | Dashboard | Description |
|---------|-----------|-------------|
| "At-Risk Students Card" | Guidance (Figure 27, item 10) | Count of flagged students |
| "AI Risk Alert Card — High Risk" | Guidance (Figure 27, item 16) | Student name, grade/section, detected factors, recommended actions |
| "AI Risk Alert Card — Moderate Risk" | Guidance (Figure 27, item 17) | Student name, grade/section, factors, recommended actions |
| Risk Alert List Panel | AI Risk Alerts page (Figure 32) | Scrollable list: photo, name, grade, section, risk badge, numerical risk score % |
| Student Risk Detail Panel | AI Risk Alerts page (Figure 32) | Photo, name, risk badge, visual risk score progress bar, status, assigned counselor, timestamp |
| "AI Recommendation Section" | AI Risk Alerts page (Figure 32) | AI-generated intervention suggestions |

### Notification Events Confirmed

| Event | Trigger | Recipients |
|-------|---------|------------|
| EVT-07: RISK_ALERT_GENERATED | Risk computation flags a student | Guidance Counselor; if HIGH: Adviser + Parent |
| NotificationType.RISK_ALERT_GENERATED | Already defined in `notifications/models.py:14` | Choice exists, dispatch not yet wired for AI source |

---

## 3. Explicitly Unapproved Decisions

All drawn from BACKEND_SPECIFICATION.md §I.4 and §I.5.

### Decision Tree (§I.4)

| Decision | Status | Evidence |
|----------|--------|----------|
| Which features to include in risk scoring | **UNAPPROVED** | §I.4, §I.3 illustrative draft explicitly says "NOT APPROVED" |
| Feature weights or tree structure | **UNAPPROVED** | §I.4 |
| Risk level thresholds (low/moderate/high boundaries) | **UNAPPROVED** | §I.4 |
| Training data requirements | **UNAPPROVED** | §I.4 |
| Fallback when insufficient data for ML | **UNAPPROVED** | §I.4 |
| Risk computation trigger schedule | **UNAPPROVED** | §I.4 |

The illustrative draft (§I.3, lines 1324–1353) proposes:
```
risk_score = (w1 × grade_factor) +
             (w2 × attendance_factor) +
             (w3 × behavioral_factor) +
             (w4 × consultation_factor)
```
This is marked **"ILLUSTRATIVE ONLY — NOT APPROVED"** and **"DO NOT IMPLEMENT"**. The 40/30/20/10 weights and <30/30–69/≥70 thresholds are NOT approved.

### Collaborative Filtering (§I.5)

| Decision | Status |
|----------|--------|
| Similarity metric | **UNAPPROVED** |
| Minimum data threshold | **UNAPPROVED** |
| Recommendation types and sources | **UNAPPROVED** |

### RiskAlert Model Fields

The existing `RiskAlert` model (`guidance/models.py:156`) has:
- `risk_level` (char: low/moderate/high) — **exists**
- `risk_factors` (JSONField, default=list) — **exists**
- `source` (char, choices only: MANUAL) — **exists, but DECISION_TREE choice not added**
- `generated_at` (DateTimeField) — **exists**

**NOT on the model but shown in PDF wireframes:**
- Numeric risk score (percentage) — **does NOT exist**
- AI-generated recommendations — **not stored on RiskAlert; only `ConsultationRecord.recommendations` (manual text) exists**

These represent schema additions that require unapproved design decisions before implementation.

### Panel Correction #2

The panel explicitly requested: *"Computation of Risk and prioritization — need explicit process/formula."* This means:
- The computation MUST be documented and explainable
- The panel wants to SEE how risk is calculated
- Specific weights, thresholds, and features were NOT approved

---

## 4. NLP / Chatbot Boundary

### What the Documentation Says

Final_REvision.pdf Objective 6.3 describes an AI Chatbot Engine using Botpress or Rasa integrated with Gemini API, capable of:
- NLP-based query understanding and classification
- Urgency classification
- Routing concerns to appropriate modules/personnel
- Academic resource recommendations
- Guidance counselor assessment question generation
- Personalized responses by user role

Final_REvision.pdf FR-031 (Guidance Module):
> "The system shall flag and escalate AI Chatbot interactions that indicate student concerns requiring counselor follow-up."

### NLP / Chatbot Status

**SYSTEM CAPABILITY: CONFIRMED**

The AEGIS thesis explicitly includes an AI Chatbot Engine and FR-031, making chatbot/NLP a confirmed **major system capability**. The chatbot is not removed from the AEGIS system; it is an inherent part of the thesis scope.

**INITIAL BACKEND IMPLEMENTATION: DEFERRED**

The engineering specification deferred chatbot code from the initial backend. This is an **implementation-timing constraint**, not evidence that the chatbot is removed from the system.

**PH9 STATUS: REQUIRES ARCHITECTURE / SCOPE APPROVAL**

The Phase 9 plan must determine:
- whether chatbot implementation occurs within Phase 9
- which implementation stage it belongs to
- which free/local technology is appropriate
- privacy boundaries
- NLP architecture
- escalation workflow
- role-specific behavior

**Correction of prior wording.** The previous PH9.0 wording "NLP/chatbot = deferred" was too broad and could be misread as "the chatbot is not part of Phase 9 / not a required system capability." "Deferred" refers to implementation timing in the initial backend, NOT to removal of the chatbot from the AEGIS system. None of the implementation decisions above are already approved — they all remain open (§20 D16, D23–D30).

### Confirmed Functional Capability

- NLP-based query understanding
- query/topic classification
- urgency classification
- routing
- academic resource suggestions
- guidance-assessment assistance
- role-aware responses
- concern detection and counselor escalation via FR-031

### Deferred Initial-Backend Components

- Botpress/Rasa integration
- Gemini endpoint
- conversation model
- chatbot privacy implementation

### Still Requiring Phase 9 Design Decision

- exact chatbot architecture
- chatbot framework
- local LLM/runtime
- NLP implementation strategy
- model selection
- intent taxonomy
- urgency taxonomy
- concern detection process
- escalation rules
- data available to the chatbot
- role-specific chatbot permissions
- conversation storage/retention
- external AI usage
- free/no-recurring-cost approach
- implementation timing within Phase 9

### PH9 Design Requirement

Determine the safest practical architecture for implementing this capability with **zero required recurring AI/API cost**.

### What PH9.0 Must Do

- Treat chatbot/NLP as a confirmed system capability and a planned Phase 9 workstream (§20 D16, D23–D30)
- Inspect repository for stubs/hooks (found: `apps/guidance/urls.py` has no chatbot endpoints; `ai_engine/__init__.py` is empty)
- Identify future integration boundaries
- Evaluate technologies only (§13–§14)

### What PH9.0 Must NOT Do

- Implement chatbot, NLP, or any conversational AI
- Install Botpress, Rasa, or Gemini SDK
- Create chat models or chatbot endpoints
- Connect any external LLM
- Send any AEGIS data to an external AI service
- Claim that any chatbot/NLP implementation decision is already approved

### Future Integration Boundary (§I.6)

```
Planned endpoints (NOT implemented):
  POST /api/v1/guidance/risk-alerts/    (for chatbot escalation)
  POST /api/v1/notifications/           (for chatbot-triggered alerts)
  Chat conversation model (not implemented)
```

---

## 5. Current Repository State

### Structure Overview

```
AEGIS/
├── backend/
│   ├── aegis_backend/
│   │   ├── apps/
│   │   │   ├── accounts/      # ACTIVE — User, profiles, RBAC, JWT auth
│   │   │   ├── academics/     # ACTIVE — Years, grades, subjects, enrollments
│   │   │   ├── attendance/    # ACTIVE — Daily attendance records
│   │   │   ├── guidance/      # ACTIVE — Behavioral, consultations, risk alerts, interventions
│   │   │   ├── assessments/   # ACTIVE — Assessment CRUD, questions, results
│   │   │   ├── notifications/ # ACTIVE — In-app notifications, dispatch_event
│   │   │   ├── data_import/   # ACTIVE — CSV/XLSX import + controlled export (PH8)
│   │   │   └── cms/           # ACTIVE — Strapi adapter (PH7)
│   │   ├── ai_engine/         # EMPTY PLACEHOLDER — only __init__.py (empty)
│   │   ├── core/              # ACTIVE — permissions, pagination, exceptions
│   │   ├── config/            # ACTIVE — settings, urls, wsgi, asgi
│   │   └── templates/         # Email templates (empty/minimal)
│   ├── requirements/          # base.txt, development.txt, production.txt
│   ├── scripts/               # provision_cms_database.py, seed_phase7_e2e.py
│   └── .venv/                 # Python 3.14.0
├── cms/                       # Strapi 5 CMS (separate service)
├── docs/                      # BACKEND_SPECIFICATION.md, Final_REvision.pdf, etc.
└── frontend/                  # EMPTY — no files tracked in git
```

### App Status Audit

| App | Status | Notes |
|-----|--------|-------|
| `accounts` | ACTIVE | User model (role-based), 5 profile types, parent-student link, JWT auth, onboarding gate |
| `academics` | ACTIVE | Full schema: AcademicYear, GradeLevel, Section, Subject, SubjectAssignment, Schedule, GradingPeriod, Enrollment, Grade |
| `attendance` | ACTIVE | AttendanceRecord (student + date unique) |
| `guidance` | ACTIVE | BehavioralNote, ConsultationRecord, RiskAlert (manual only), Intervention, InterventionStep, ProgressNote |
| `assessments` | ACTIVE | Assessment (academic/wellness/behavioral), AssessmentQuestion, AssessmentResult |
| `notifications` | ACTIVE | NotificationType (10 types including RISK_ALERT_GENERATED), Notification, NotificationPreference, dispatch_event |
| `data_import` | ACTIVE | ImportJob, ImportRecord, CSV/XLSX pipeline, grade/attendance/student importers, export views |
| `cms` | ACTIVE | Strapi integration adapter: webhook receiver, read-through proxy, resource download proxy |
| `analytics` | DOES NOT EXIST | Commented out in `settings/base.py:45` (`# "apps.analytics"`). No directory, no models, no views. |
| `ai_engine` | EMPTY | `__init__.py` (0 lines). Placeholder only. No modules. |
| `audit` | DOES NOT EXIST | Commented out in `settings/base.py:49` (`# "apps.audit"`). No directory. |
| `frontend/` | EMPTY | Directory exists but contains no files. No `package.json`, no React project. |

### Installed Dependencies (from venv)

| Package | Version | Relevance |
|---------|---------|-----------|
| Django | 6.1 | Core framework |
| djangorestframework | 3.18.0 | REST API |
| djangorestframework-simplejwt | 5.5.1 | JWT auth |
| django-cors-headers | 4.9.0 | CORS |
| psycopg2-binary | 2.9.12 | PostgreSQL |
| python-decouple | 3.8+ | Config |
| Pillow | 12.3.0 | Image handling |
| openpyxl | 3.1.x | XLSX import/export |
| PyJWT | 2.13.0 | JWT |

**NOT installed (ML/AI):** numpy, pandas, scikit-learn, scipy, implicit, matplotlib, plotly, recharts, torch, tensorflow, rasa, ollama, llama.cpp, transformers, lightfm, surprise.

**Available on PyPI for Python 3.14 (verified):**
- scikit-learn 1.9.0
- numpy 2.5.2
- pandas 3.0.5
- scipy 1.18.1
- implicit 0.7.3

### Test Suite

| App | Test Methods |
|-----|-------------|
| data_import | 285 |
| guidance | 78 |
| accounts | 73 |
| cms | 69 |
| academics | 67 |
| assessments | 65 |
| attendance | 46 |
| notifications | 37 |
| **Total** | **720** |

All tests use SQLite in-memory (`config.settings.test`). No ML-related tests exist.

### Scripts

| Script | Purpose | Modifies Data? |
|--------|---------|----------------|
| `provision_cms_database.py` | One-time Strapi DB provisioning | Yes (creates Postgres role/db) |
| `seed_phase7_e2e.py` | Creates demo users + minimal academics (1 AcademicYear, 1 GradeLevel, 1 Section, 2 Students, 1 Enrollment) | Yes (creates records) |

**No bulk seed/demo-data scripts exist for grades, attendance, or guidance records.**

### Migrations

All schema-only. **No data migrations** exist (no `RunPython`, no `objects.create` in any migration file). Guidance has 2 migrations (the second adds `risk_factors` JSONField). All other apps have 1 migration.

### Media/Imports

`backend/aegis_backend/media/imports/` contains **3,078 uploaded CSV/XLSX files** from previous import job API usage. These are actual uploaded data payloads (student IDs, grades, attendance) that could theoretically be mined for analytics training data, but no code currently consumes them for ML purposes.

---

## 6. Data Readiness Matrix

### ACADEMICS

| Model | Fields (key) | Exists | Populated | ML-Suitable | Notes |
|-------|-------------|--------|-----------|-------------|-------|
| AcademicYear | name, start_date, end_date, is_current | ✅ | ❌ (empty in dev) | ✅ | Reference data; seedable |
| GradeLevel | name, level_number | ✅ | ❌ | ✅ | Reference data |
| Section | name, grade_level, academic_year, adviser | ✅ | ❌ | ✅ | Groups students |
| Subject | name, code, grade_level | ✅ | ❌ | ✅ | Reference data |
| SubjectAssignment | subject, faculty, section, academic_year | ✅ | ❌ | ✅ | Links teachers to sections |
| GradingPeriod | academic_year, name, order, start_date, end_date | ✅ | ❌ | ✅ | Time periods for grades |
| Enrollment | student, section, academic_year, date_enrolled, is_active | ✅ | ❌ | ✅ | Student-section link |
| Grade | student, subject_assignment, grading_period, score (0-100), letter_grade, status | ✅ | ❌ | ✅ **primary feature source** | Score is the most important ML feature |

### ATTENDANCE

| Model | Fields (key) | Exists | Populated | ML-Suitable | Notes |
|-------|-------------|--------|-----------|-------------|-------|
| AttendanceRecord | student, section, date, status (present/late/absent) | ✅ | ❌ | ✅ **primary feature source** | Unique on (student, date) |

### GUIDANCE

| Model | Fields (key) | Exists | Populated | ML-Suitable | Notes |
|-------|-------------|--------|-----------|-------------|-------|
| BehavioralNote | student, recorded_by, note_type, note_text, date_recorded | ✅ | ❌ | ⚠️ Partial | Counts by type are features; text is privacy-sensitive |
| ConsultationRecord | student, counselor, session_date, concern_categories, status, priority_level | ✅ | ❌ | ⚠️ Partial | Active count is a feature; notes are privacy-sensitive |
| RiskAlert | student, risk_level, risk_factors, source, status, assigned_counselor | ✅ | ❌ | ⚠️ No history | Manual only; no AI-generated alerts yet |
| Intervention | student, risk_alert, assigned_counselor, plan_start_date, status | ✅ | ❌ | ⚠️ | Linked to risk alerts |
| ProgressNote | intervention, note_text, recorded_by | ✅ | ❌ | ❌ | Privacy-sensitive |

### ASSESSMENTS

| Model | Fields (key) | Exists | Populated | ML-Suitable | Notes |
|-------|-------------|--------|-----------|-------------|-------|
| Assessment | title, assessment_type, creator_role, target_sections, quarter | ✅ | ❌ | ✅ | Assessment metadata |
| AssessmentResult | assessment, student, answers, score, total_possible, percentage, status | ✅ | ❌ | ✅ **secondary feature source** | assessment scores are ML features |

### ACCOUNTS

| Model | Fields (key) | Exists | Populated | ML-Suitable | Notes |
|-------|-------------|--------|-----------|-------------|-------|
| User | role (5 types), email | ✅ | Minimal | ✅ | Role-based feature scoping |
| StudentProfile | student_id, grade_level, section, date_of_birth, enrollment_date, is_active | ✅ | Minimal | ✅ | Student demographics |
| FacultyProfile | employee_id, department, is_adviser, advisory_section | ✅ | Minimal | ✅ | For faculty-scoped analytics |

### Data Quality Summary

| Assessment Area | Current State | Historical Depth | Row Volume (Expected) |
|----------------|---------------|-------------------|-----------------------|
| Grade records | Empty | 0 terms | 100–300 students × 6–8 subjects × 4 quarters = 2,400–9,600 |
| Attendance records | Empty | 0 days | 100–300 students × 180 school days = 18,000–54,000 |
| Behavioral notes | Empty | 0 records | 50–200 notes (estimated) |
| Consultation records | Empty | 0 records | 20–100 records (estimated) |
| Risk alerts | Empty | 0 records | Unknown (depends on computation) |
| Assessments | Empty | 0 results | 100–300 students × 5–10 assessments = 500–3,000 |

**Critical finding:** The database is empty of production data. The 3,078 uploaded import files in `media/imports/` represent actual data that was uploaded through the import API, but these records were not persisted to the domain models (they were likely development/test uploads). A data seed strategy is required before any ML model can be trained.

---

## 7. Decision Tree Feasibility

### Target Prediction

**At-risk student classification** — binary or multi-class:
- Input: student's academic and behavioral features
- Output: risk level (low / moderate / high) mapped to RiskAlert

### Is the Target Historically Labeled?

**NO.** There are zero historical risk labels in the system. `RiskAlert.Source` only has `MANUAL` — no AI-generated alerts exist. There is no historical record of which students were previously classified as at-risk by any method.

### Can a Valid Supervised Model Currently Be Trained?

**NO** — not without one of:
1. Historical labeled data from a previous system or manual annotation
2. A rule-based labeling system that generates initial labels
3. Synthetic labels (violates PH9.0 no-fabrication rule)

### What Data is Missing

1. **Labels:** No at-risk / not-at-risk target variable exists
2. **Features (grades):** Grade records are empty — no score history
3. **Features (attendance):** Attendance records are empty
4. **Features (behavioral):** Behavioral notes are empty
5. **Features (consultations):** Consultation records are empty
6. **Feature engineering definitions:** UNAPPROVED per §I.4

### Minimum Dataset Needed

For a basic Decision Tree classifier on student risk:
- **Minimum labeled examples:** ~50–100 students with known at-risk status (at least 10–15 per class for 3 classes)
- **Minimum features per student:** At least one complete term of grades, attendance, and behavioral data
- **Minimum feature records:** ~500–1,000 grade records + ~5,000–10,000 attendance records for meaningful feature engineering

For the target school (estimated 100–300 students), after one full academic term with populated data:
- Grades: 800–2,400 records (sufficient)
- Attendance: 18,000–54,000 records (sufficient)
- Behavioral notes: 50–200 records (marginal but usable as counts)
- **Labels:** Still missing — requires manual annotation or rule-based generation

### How Can Deterministic Output Be Guaranteed (NFR-007)?

Decision Tree classifiers from scikit-learn are deterministic when:
1. `random_state` is fixed (same seed → same tree)
2. Input data is identical (same feature values → same path through tree)
3. No online learning / incremental updates during inference

This is naturally satisfied by training a model once, serializing it with `joblib`/`pickle`, and loading the same model for all inference calls.

### How Will Model Output Map to RiskAlert?

```
DT prediction → risk_level (low|moderate|high)
DT feature_importances_ → risk_factors (JSON array)
DT predict_proba → risk_score (0-100 mapped from probability)
```

This mapping requires:
- `RiskAlert.source` to gain a `decision_tree` choice
- `RiskAlert.risk_factors` to be populated by the model
- A new field for numeric risk score (not currently on the model)

### What Can Honestly Be Demonstrated

1. **A trained Decision Tree** with simulated/seed data
2. **Deterministic output** for identical inputs
3. **Explainable predictions** via feature_importances_ and decision path visualization
4. **Integration with RiskAlert** via API endpoint

What CANNOT be demonstrated without labeled data:
- Actual predictive accuracy on real at-risk students
- Clinical validity of the model

---

## 8. Collaborative Filtering Feasibility

### What Exactly is Being Recommended?

Per Final_REvision.pdf (student dashboard Figure 13–14):
- **"Learning Recommendations Section"** — personalized study activities (e.g., "practice algebra exercises", "review science vocabulary", "continue reading activities")
- Per BACKEND_SPECIFICATION.md §E.5: `Recommendation` model with `recommendation_type` (resource|activity|intervention)

### Who Receives Recommendations?

- **Students** — on their dashboard (Figure 13, item 5)
- Potentially **guidance counselors** — for intervention strategies (§I.3 mentions "recommend intervention strategies for guidance counselors")

### What User-Item Interactions Exist?

| Interaction Type | Model | Exists | Data |
|-----------------|-------|--------|------|
| Student takes assessment | AssessmentResult | ✅ | Empty |
| Student receives grades | Grade | ✅ | Empty |
| Student attendance pattern | AttendanceRecord | ✅ | Empty |
| Student reads recommendations | (not tracked) | ❌ | N/A |
| Student clicks on resources | (not tracked) | ❌ | N/A |

### Is There Sufficient Interaction Data?

**NO.** Zero interactions exist. Even if data were populated, CF requires:
- A matrix of user-item interactions (student × assessment/subject)
- Sufficient density (>1-5% of cells filled for implicit CF)
- Multiple students with overlapping items

### The Cold-Start Problem

For any new student with no interaction history, CF cannot make recommendations. This is a fundamental limitation. Mitigation:
1. Use only content-based features (grades, attendance) for cold-start students
2. Use popularity-based fallback until enough interactions accumulate
3. Use hybrid CF + content-based approach

### Can Meaningful CF Be Demonstrated?

With seed/simulated data: **YES** — a CF model can be trained and produce recommendations.
With real empty data: **NO** — there is nothing to train on.

### Minimum-Data Rule Required

- **Minimum students:** ~20–30 with overlapping interactions
- **Minimum interactions per student:** ~3–5 (grades in different subjects)
- **Minimum item coverage:** ~5–10 subjects/assessments with student responses
- Total minimum: ~100–150 interaction records across 20–30 students

### Which Similarity Method Options Are Viable

| Method | Pros | Cons | Free? |
|--------|------|------|-------|
| Alternating Least Squares (ALS) via `implicit` | Fast, handles implicit feedback, mature | Requires scipy/numpy | ✅ |
| Cosine similarity (pure Python/numpy) | Simple, explainable, no new dep | Less powerful for sparse data | ✅ |
| LightFM (hybrid) | Handles cold-start via features | Heavier dependency, more complex | ✅ |
| Surprise (SVD) | Classic explicit ratings | Designed for explicit feedback (star ratings), not grade scores | ✅ |

**Recommendation:** ALS via `implicit` library for the core engine; cosine similarity as a fallback/explainable alternative.

---

## 9. Analytics / Visual Reporting Scope

### Recovered Requirement (Final_REvision Objective 6.1)

> "Provide visual reports and graphs on school-wide academic performance and attendance trends based on imported data."

### Required Academic Metrics (from wireframes)

| Metric | Dashboard | Wireframe Reference |
|--------|-----------|---------------------|
| GPA (per student) | Student (Fig 13, item 3), Parent (Fig 18, item 2) | Percentage display |
| GPA trend over time | Student (Fig 13, item 4), Parent (Fig 18, item 4) | Line graph across quarters/months |
| Subject performance | Student (Fig 13, item 2) | Per-subject breakdown |
| Assessment scores | Student (Fig 13, item 3) | Scores out of 10 |
| Total students | Faculty (Fig 22, item 7), Admin (Fig 35, item 1) | Card count |
| Attendance today | Faculty (Fig 22, item 8) | Count / total |
| Pending grades | Faculty (Fig 22, item 9) | Card count |
| Active cases | Guidance (Fig 27, item 9) | Card count |
| At-risk student count | Guidance (Fig 27, item 10) | Card count |
| User distribution by role | Admin (Fig 35, item 5) | Donut chart |

### Required Attendance Metrics

| Metric | Aggregation | Role |
|--------|-------------|------|
| Present/Late/Absent counts | Per student, per section, per day | Faculty, Guidance, Admin |
| Attendance rate % | Per student, per section, per grading period | Faculty, Guidance, Admin |
| Absence threshold flag | Configurable threshold (see ASM-05) | Parent notification trigger |

### Aggregation Levels

- **Per student:** Individual performance, attendance, risk score
- **Per section:** Class average, attendance rate, risk distribution
- **Per grade level:** Cross-section comparison
- **Per subject:** Subject performance trends
- **Per grading period:** Quarter-over-quarter trends
- **School-wide:** Overall statistics, user distribution

### Role Visibility

| Role | What They See | Source |
|------|---------------|--------|
| Student | Own GPA, grades, attendance, recommendations, risk status | NFR-009 |
| Parent | Child's GPA, grades, attendance, risk status | FR-024/025/026 |
| Faculty | Advisory class summary, own subject performance | `view_analytics` (own subjects) |
| Guidance | All students' risk scores, alerts, intervention status | `view_analytics` (all) |
| Admin | Aggregated/anonymized school-wide statistics | `view_analytics` (all, aggregated per NFR-010) |

### NFR-010 Impact

Admin analytics must be:
- Aggregated (not individual student data)
- Anonymized (no student names in school-wide charts)
- Unless explicit consent is given

This means the admin dashboard's "System Overview Chart" (Fig 35, item 5) showing user role distribution is fine, but any "school-wide academic performance" chart must aggregate scores into distributions, not individual data points.

### Backend Responsibilities

1. **Aggregation endpoints** — serve precomputed/cached JSON data
2. **Feature computation** — transform raw records into ML features
3. **Model inference** — run DT and CF, store results
4. **Report generation** — JSON reports (already exists for guidance)

### Frontend Responsibilities

1. **Chart rendering** — display data from backend JSON
2. **Dashboard layout** — implement wireframe UIs
3. **Role-based routing** — show correct dashboard per role
4. **Real-time data** — fetch from backend APIs

### Current Frontend State

**The `frontend/` directory is completely empty.** No React app, no package.json, no component code. The planned Vite frontend (origin `localhost:5173` in `.env.example`) has not been created. All dashboard work must be done from scratch.

---

## 10. RiskAlert Integration Delta

### ALREADY EXISTS (Phase 5)

| Feature | Location | Status |
|---------|----------|--------|
| `RiskAlert` model with `risk_level` (low/moderate/high) | `guidance/models.py:156` | ✅ Active |
| `RiskAlert.risk_factors` JSONField | `guidance/models.py:184` | ✅ Active |
| `RiskAlert.source` (MANUAL only) | `guidance/models.py:189` | ✅ Active |
| `RiskAlert.status` (active/under_monitoring/resolved/escalated) | `guidance/models.py:192` | ✅ Active |
| `RiskAlert.assigned_counselor` FK | `guidance/models.py:199` | ✅ Active |
| `RiskAlert.generated_at` DateTimeField | `guidance/models.py:206` | ✅ Active |
| RiskAlert CRUD + status transitions (acknowledge/escalate/resolve) | `guidance/views.py:432` | ✅ Active |
| Scoped queryset per role (guidance all, faculty advisory, student own, parent linked) | `guidance/views.py:453` | ✅ Active |
| `NotificationType.RISK_ALERT_GENERATED` choice | `notifications/models.py:14` | ✅ Defined |
| Intervention linked to RiskAlert | `guidance/models.py:240` | ✅ Active |

### CONFIRMED FOR PH9 (Requires Implementation)

| Feature | What Changes |
|---------|-------------|
| `RiskAlert.source` gains `decision_tree` choice | New choice in Source.TextChoices |
| `RiskAlert.risk_factors` populated by DT | Change from `default=list` to AI-generated JSON content |
| New: `RiskAlert.risk_score` numeric field | DecimalField (0–100) for the numerical risk score percentage |
| New: `RiskAlert.recommendations` or related model | AI-generated recommendation text/JSON |
| Risk computation trigger | New endpoint: `POST /api/v1/analytics/risk-scores/compute/` |
| Risk computation dispatches RISK_ALERT_GENERATED | New `dispatch_event` call for EVT-07 |
| HIGH risk → Adviser + Parent notifications | Extends guidance-only recipients per §G.7 |
| Recommendation model (§E.5) | New `Recommendation` model: student, type, content, generated_at |
| Analytics aggregation endpoints | New views for dashboard data (academic, attendance, school-wide) |

### UNAPPROVED (Cannot Be Implemented Yet)

| Item | Why It's Blocked |
|------|------------------|
| What triggers the computation (manual, scheduled, both) | §I.4 UNAPPROVED |
| What thresholds determine low/moderate/high | §I.4 UNAPPROVED |
| What features the DT uses | §I.4 UNAPPROVED |
| What the numeric risk_score means or how it's computed | §I.4 UNAPPROVED |
| What content the AI recommendations contain | §I.5 UNAPPROVED |
| Who can see the AI-generated risk scores | Privacy — requires approval |
| Whether students see their own risk classification | Privacy — wireframes show it, but needs confirmation |

### RiskAlert Model Schema Changes Required

```python
# Current model fields (guidance/models.py:156-222):
# student, risk_level, risk_factors (JSON), source, status,
# assigned_counselor, generated_at, last_updated

# PH9 additions needed:
risk_score = DecimalField(max_digits=5, decimal_places=2, null=True, blank=True,
    help_text="Numeric risk score 0-100. AI-generated when source=decision_tree.")
# Source choices: add DECISION_TREE = "decision_tree", "Decision Tree AI"
# risk_factors: populated with DT feature importances / detected factors
# recommendations: AI-generated (or separate Recommendation model)
```

---

## 11. Privacy / Security Gate

### NFR-009: Students Only See Their Own Data

Currently enforced in `guidance/views.py:478-482` via queryset scoping. For AI features:
- Students should see their own risk score and risk factors
- Students should see their own recommendations
- Students should NOT see other students' risk classifications
- The PDF wireframes show students seeing their own "AI Academic Insights" and "Learning Recommendations" — this is consistent with NFR-009

### NFR-010: Admins See Aggregated/Anonymized Data

Admin analytics must aggregate:
- School-wide GPA distribution (histogram, not individual GPAs)
- School-wide attendance rates (section-level, not student-level)
- Risk distribution (count of low/moderate/high, not student names)
- Unless explicit consent is given for individual data

The admin dashboard wireframe (Fig 35) only shows:
- Total Students count
- Active User count
- Pending Imports count
- Announcements count
- User distribution donut chart (by role)
- Recent Announcements

No individual student data is shown on the admin dashboard — this is already NFR-010 compliant.

### NFR-011: Role-Based Access Control

Current RBAC (`core/permissions.py`) provides role-level gates. For PH9:

| AI Feature | Who May Trigger | Who May View Results |
|-----------|-----------------|---------------------|
| Risk computation | Admin, Guidance | Guidance (all), Faculty (advisory), Student (own), Parent (linked child) |
| Risk scores | — | Same as RiskAlert viewing |
| Risk factors | — | Same as RiskAlert viewing |
| Recommendations | — | Student (own), Guidance (all) |
| Analytics dashboards | — | Faculty (own subjects), Guidance (all), Admin (aggregated) |

### What Guidance Data Should NEVER Become an ML Feature

- **ConsultationRecord.session_notes** — free-text counseling notes
- **ConsultationRecord.recommendations** — counselor recommendations
- **ProgressNote.note_text** — intervention progress notes
- **BehavioralNote.note_text** — detailed behavioral descriptions

These contain sensitive student information that should not be fed into ML models. Only **aggregate counts** (number of consultations, number of behavioral notes by type) are safe to use as features.

### What Data Should NEVER Leave the AEGIS Environment

Per SEC-PRIVACY (RA 10173 compliance):
- All student PII (names, student IDs, DOB, grades, attendance, behavioral records)
- All guidance/counseling records
- All risk classifications

This means:
- **No student data to Cloudflare Workers AI** (or any external service) for PH9
- **No student data to OpenRouter** or any cloud LLM
- All ML inference must run locally within the Django process
- The only acceptable external calls would be for development/prototyping with synthetic data, never production data

### Privacy Risk: AI Leakage

Risk of AI leakage in the current architecture:
- Risk scores stored in DB → protected by Django ORM + RBAC → **LOW risk**
- Risk factors (JSON) in DB → same protection → **LOW risk**
- Recommendations in DB → same protection → **LOW risk**
- If external LLM is used for NLP/chatbot → **HIGH risk** if student data is sent
- If recommendations are cached in browser → **MEDIUM risk** (depends on frontend implementation)

### Key Privacy Questions for Approval

1. Should students see their own risk classifications? (PDF wireframes show yes for student profile, but not prominently on main dashboard)
2. Should parents see risk scores for their children? (PDF parent dashboard Fig 18–20 does NOT show risk score)
3. Should faculty see risk scores for their advisory students? (PDF faculty dashboard Fig 22–24 does NOT show risk scores)
4. Who may trigger the risk computation? (Admin only? Guidance only? Both?)

---

## 12. External AI Boundary

### LOCAL (Required for Core System)

| Component | Purpose | Cost |
|-----------|---------|------|
| Django + Python | Application server + ML inference host | $0 (open source) |
| scikit-learn | Decision Tree, feature engineering | $0 (BSD license) |
| numpy | Numerical computation | $0 (BSD license) |
| pandas | Data aggregation, feature engineering | $0 (BSD license) |
| scipy | Statistical functions | $0 (BSD license) |
| implicit | Collaborative filtering (ALS) | $0 (MIT license) |

### OPTIONAL EXTERNAL (For NLP/Chatbot Implementation Only)

| Service | Free Allocation | Payment Required? | Privacy Implications | Data Retention | Suitability for Student Data |
|---------|----------------|-------------------|---------------------|----------------|------------------------------|
| Cloudflare Workers AI | 10,000 Neurons/day free | No (free tier sufficient for light usage) | **Data sent to Cloudflare edge** | Cloudflare's standard retention | **NOT suitable for student data** — violates SEC-PRIVACY/RA 10173 |
| OpenRouter (free models) | Varies by model | No (free tier) | **Data sent to OpenRouter + model provider** | Provider-dependent | **NOT suitable for student data** |
| Ollama (local) | Unlimited | No | **Fully local** — no data leaves machine | N/A (local) | **Suitable** — but requires local hardware (8GB+ RAM) |
| Rasa (self-hosted) | Unlimited | No | **Fully local** when self-hosted | N/A (local) | **Suitable** — but heavy infrastructure (Redis, etc.) |
| Gemini API | Free tier available | Potentially | **Data sent to Google** | Google's retention policy | **NOT suitable for student data** |

### Recommendation

**For PH9 core AI features (DT + CF + analytics):**
- 100% local. No external services needed. $0 cost.
- All inference runs inside Django as Python functions.

**For NLP/chatbot (PH9.8 implementation phase):**
- **Ollama** is the best option for privacy (fully local)
- **Cloudflare Workers AI** is acceptable ONLY for development/prototyping with synthetic data, NOT for production student data
- **Never send student data to any external AI service** in production

---

## 13. Free / No-Recurring-Cost Technology Evaluation

### Decision Tree — Technology Options

| Technology | License | Python 3.14 | Deps | Free? | Notes |
|-----------|---------|-------------|------|-------|-------|
| scikit-learn `DecisionTreeClassifier` | BSD | ✅ (1.9.0) | numpy, scipy | ✅ Fully | Industry standard, deterministic, explainable |
| scikit-learn `RandomForestClassifier` | BSD | ✅ | numpy, scipy | ✅ Fully | Ensemble of DTs, more accurate but less interpretable |
| XGBoost | Apache 2.0 | ✅ | numpy, scipy | ✅ Fully | Powerful but heavier; more complex to explain |
| Custom Python DT | N/A | ✅ | None | ✅ Fully | Maximum control but reinvents the wheel |

**Best choice: scikit-learn DecisionTreeClassifier**
- Deterministic with `random_state` (satisfies NFR-007)
- Explainable via `feature_importances_`, `decision_path()`, `export_text()`
- Lightest dependency footprint (numpy already a transitive dep)
- Well-documented, mature, battle-tested

### Collaborative Filtering — Technology Options

| Technology | License | Python 3.14 | Deps | Free? | Notes |
|-----------|---------|-------------|------|-------|-------|
| `implicit` library (ALS, BPR) | MIT | ✅ (0.7.3) | numpy, scipy, cython | ✅ Fully | Designed for implicit feedback (grades, attendance patterns) |
| LightFM | MIT | ✅ | numpy, scipy | ✅ Fully | Hybrid CF + content-based; handles cold-start better |
| Surprise (SVD, KNN) | MIT | ✅ | numpy | ✅ Fully | Designed for explicit ratings (not ideal for AEGIS) |
| Pure numpy cosine similarity | BSD | ✅ | numpy | ✅ Fully | Simplest, most explainable, no new dep |

**Best choice: `implicit` library (ALS)**
- Fast, handles the student × subject interaction matrix naturally
- Works with implicit signals (grades as "engagement" rather than explicit ratings)
- Produces user/item factors that can be used for similarity-based recommendations

**Alternative: numpy cosine similarity**
- If CF feasibility proves marginal (few students), a simple cosine similarity matrix is more explainable and lighter

### NLP / Chatbot — Technology Options (PH9 Architecture Decision)

The chatbot/NLP evaluation is **not merely future research** — it is now a Phase 9 architecture decision. The candidates below are evaluated against actual AEGIS constraints: $0 acquisition cost, $0 recurring runtime cost, privacy, hardware, Windows/local development practicality, deployment complexity, NLP quality, intent classification, urgency classification, conversation handling, role-aware responses, escalation support (FR-031), Django integration, testing, maintainability, reproducibility, English capability, Filipino/Taglish practicality, model size, and offline capability. **No software was installed; this is evaluation only.**

#### Candidate 1 — Rasa + local NLU

| Criterion | Assessment |
|-----------|------------|
| License / cost | Apache-2.0. $0 acquisition, $0 recurring. Fully self-hosted. |
| Privacy | Fully local; no student data leaves the machine when local NLU is used. |
| Hardware | CPU-only is acceptable at capstone scale; no GPU required. |
| Windows / local dev practicality | Supported, though production deployment typically targets Linux/Docker; local Windows dev usually via WSL. |
| Deployment complexity | **High** — separate Rasa server, training pipeline, custom action server, and (in production) Redis. Overkill for targeted campus Q&A. |
| NLP quality | Strong supervised NLU (DIET intent classifier) once sufficient training data exists. |
| Intent classification | Supported via custom intents + training data. |
| Urgency classification | Not pre-built — must be trained/configured as intents or rules. |
| Conversation handling | Full dialogue management, slots, forms. |
| Role-aware responses | Achievable via custom actions calling the backend RBAC service. |
| Escalation support (FR-031) | Achievable via custom action calling the §I.6 future-boundary endpoints (risk-alert / notification). |
| Django integration | Via REST/HTTP connector (separate service, not in-process). |
| Testing / maintainability | Built-in test framework; higher infrastructure upkeep. |
| Reproducibility | Reproducible with pinned versions + fixed seeds. |
| English / Filipino-Taglish | English strong; Taglish not pre-trained — requires custom Taglish training data and evaluation. |
| Model size / offline | Moderate runtime footprint; fully offline. |
| Python 3.14 risk | **Real risk** — Rasa 3.x pins older dependency ranges; verify compatibility before selection. |

#### Candidate 2 — Custom Django chatbot + local LLM

| Criterion | Assessment |
|-----------|------------|
| License / cost | Own code + MIT local-LLM runtime (Ollama / llama.cpp). $0 acquisition, $0 recurring. |
| Privacy | Local inference; nothing leaves the AEGIS machine. |
| Hardware | CPU runs 3B-class models in 4–8 GB RAM; 7B+ models raise RAM and latency. |
| Windows / local dev practicality | Practical — Ollama and llama.cpp run natively on Windows. |
| Deployment complexity | **Low–Medium** — runs inside/next to the Django process; no separate NLU framework. |
| NLP quality | Depends entirely on the local model; 3B-class output quality is limited, improving at 7B+ (higher hardware cost). |
| Intent classification | Prompt-based; not deterministic; harder to audit for FR-031 escalation. |
| Urgency classification | Prompt-based; drift and auditability concerns. |
| Conversation handling | Hand-built dialogue state management. |
| Role-aware responses | Implementable via Django RBAC + strict context controls (no unnecessary profile injection). |
| Escalation support (FR-031) | Implementable via Django code calling the future-boundary escalation endpoints. |
| Django integration | Native / in-process. |
| Testing / maintainability | Same Django suite; LLM output non-deterministic → needs golden-question / fixed-temperature strategies. Maintainability high. |
| Reproducibility | Moderate — fix temperature/sampling seed; residual non-determinism in generation. |
| English / Filipino-Taglish | English OK at 3B+; Taglish weaker at small sizes — requires prompt design and evaluation. |
| Model size / offline | 1B–70B depending on model; fully offline when local runtime used. |

#### Candidate 3 — spaCy intent classifier + local LLM response generator

| Criterion | Assessment |
|-----------|------------|
| License / cost | MIT (spaCy) + MIT local-LLM runtime. $0 acquisition, $0 recurring. |
| Privacy | Fully local; classifier and generator stay on-box. |
| Hardware | Very light classifier + local LLM runtime (4–8 GB RAM for small models). |
| Windows / local dev practicality | spaCy works on Windows; local-LLM runtimes do too. |
| Deployment complexity | **Medium** — two in-process Python components. |
| NLP quality | Strong supervised intent classification (deterministic/auditable); LLM reserved for free-form response generation. |
| Intent classification | Deterministic classifier → clean rules, ideal for FR-031 escalation thresholds. |
| Urgency classification | Deterministic classifier + rules, not LLM judgment. |
| Conversation handling | Custom dialogue state required. |
| Role-aware responses | Via Django RBAC at the service layer. |
| Escalation support (FR-031) | **Strong** — escalation fires from deterministic classification + explicit rules. |
| Django integration | Native in-process Python. |
| Testing / maintainability | Intents unit-testable; classifier deterministic; LLM responses tested with golden sets / low temperature. |
| Reproducibility | High for the classifier; generation portion moderate (low temperature / fixed seed). |
| English / Filipino-Taglish | spaCy English models strong; no official Filipino model — requires custom Taglish text-classifier training + evaluation. |
| Model size / offline | Small classifier + chosen LLM (1–3B candidate). Fully offline. |

#### Candidate 4 — Other genuinely free / self-hosted alternatives (evidence-supported)

- **Hybrid rule-based classifier + local LLM (in Django):** keyword/pattern rules (optionally NLTK) for intent and urgency classification, local LLM for generation. Fully deterministic escalation rules for FR-031, $0, lowest model dependence, no Python-version framework risk. Weak on unseen phrasings.
- **NLTK (Apache-2.0, $0):** evidence-supported baseline for tokenization/pattern rules; limited ML classification without training data.
- **Rasa-NLU-only (stripped):** Rasa's NLU without the full dialogue-management stack; Apache-2.0; lighter than full Rasa but retains Rasa pipeline / Python-version constraints.
- **Not selected on evidence:** Snips NLU (discontinued); Botpress Community self-host (oriented to the Botpress visual platform; license/self-host terms changed across versions — verify before selection); Gemini API cloud (external — not suitable for student data).

**Recommendation for this section:** No final framework/NLP choice is made here. All candidates remain **under evaluation** and are subject to the Phase 9 architecture/approval gate (§20 D24–D26). This preserves the requirement that implementation decisions are not pre-approved.

### Local LLM Runtime — Technology Options (PH9 Architecture Decision)

| Technology | License | Free | GPU Required? | RAM (3B-class) | Windows / Local Dev | Deployment Complexity | Offline | Privacy |
|-----------|---------|------|---------------|----------------|----------------------|------------------------|---------|---------|
| Ollama | MIT | ✅ $0 | Optional (faster with) | 4–8 GB | Easiest; native Windows (`ollama run llama3.2:3b`) | Low | ✅ | Fully local |
| llama.cpp | MIT | ✅ $0 | Optional | 4–8 GB (GGUF quantized) | Native Windows; lower-level (`main` CLI / server) | Medium (manual build/config) | ✅ | Fully local |
| Other evidence-supported | Jan (Apache-2.0), LM Studio (free local use — verify license for commercial deployment) | ✅ $0 | Optional | 4–8 GB | GUI launchers; simplest for evaluation | Low | ✅ | Fully local |

**Model note:** English capability is strong at the 3B class; Filipino/Taglish requires evaluation and typically improves with 7B-class or tuned/multilingual models. Model selection is an open Phase 9 decision (D25/D26), not pre-approved.

### Optional Cloud Fallback — Technology Options

| Service | Free Tier | Rate Limits | Privacy | Best For |
|---------|-----------|-------------|---------|----------|
| Cloudflare Workers AI | 10,000 Neurons/day | ~hundreds of small LLM calls/day | Data sent to edge | Development/prototyping only |
| OpenRouter free models | Varies | Model-dependent | Data sent to provider | Development/prototyping only |

**Best choice: Cloudflare Workers AI (development only)**
- Useful for testing chatbot integration during development
- Never for production student data
- Sufficient free tier for a capstone demo

### Analytics / Visualization — Technology Options

| Technology | Location | License | Free? | Notes |
|-----------|----------|---------|-------|-------|
| Recharts | Frontend (React) | MIT | ✅ | Composable React chart components (line, bar, pie, area) |
| Chart.js + react-chartjs-2 | Frontend (React) | MIT | ✅ | Simpler, fewer features than Recharts |
| Victory | Frontend (React) | MIT | ✅ | Good for dashboards; smaller community |
| Django + pandas + matplotlib | Backend (server-side) | BSD | ✅ | Generate charts as images; less interactive |
| Django + numpy aggregation | Backend (JSON API) | BSD | ✅ | Backend aggregates; frontend renders charts |

**Best choice: Recharts (frontend) + Django JSON API (backend)**
- Backend serves aggregated JSON data via DRF endpoints
- Frontend renders interactive charts with Recharts
- Clean separation of concerns
- Recharts v3.3.0 is current and well-maintained

**Alternative (no frontend): Django + reportlab/weasyprint**
- Generate PDF reports server-side
- Not interactive; not what the wireframes show

---

## 14. Technology Recommendation Matrix

### Decision Tree
- **Best choice:** scikit-learn `DecisionTreeClassifier`
- **Alternative:** scikit-learn `RandomForestClassifier` (if DT accuracy is insufficient)
- **Why:** Deterministic (NFR-007), fully explainable, zero new runtime deps beyond numpy/scipy, mature, $0

### Collaborative Filtering
- **Best choice:** `implicit` library (ALS)
- **Alternative:** numpy cosine similarity matrix (simpler, more explainable)
- **Why:** Handles implicit feedback naturally; fast; if data is too sparse, cosine similarity is a lighter fallback

### NLP
- **Best choice:** TO BE SELECTED THROUGH PH9 ARCHITECTURE DECISION (D25)
- **Candidates (evaluated in §13):** spaCy intent classification / rule-based classifier / local LLM / hybrid
- **Why:** NLP is a confirmed system capability (thesis AI Chatbot Engine, FR-031). §I.6 deferred only the initial-backend code. The NLP strategy must be selected at the Phase 9 architecture/approval gate, not pre-decided.

### Chatbot Framework
- **Best choice:** TO BE SELECTED THROUGH PH9 ARCHITECTURE DECISION (D24)
- **Candidates (evaluated in §13):** Rasa + local NLU / custom Django chatbot + local LLM / spaCy intent classifier + local LLM / other self-hosted hybrid
- **Why:** Rasa and custom-Django must NOT be chosen merely because one is simpler. Selection must be based on actual AEGIS constraints: FR-031 escalation, role-aware access, privacy (RA 10173), $0 recurring AI/API cost, local inference, Python 3.14 / Windows practicality, and Filipino/Taglish capability.

### Local LLM Runtime
- **Best choice:** TO BE SELECTED THROUGH PH9 ARCHITECTURE DECISION (D26)
- **Candidates (evaluated in §13):** Ollama / llama.cpp / other evidence-supported runtime
- **Why:** All are $0 and fully local. Selection follows the chatbot/NLP architecture choice and available hardware; it is not pre-decided.

### Optional Cloud Fallback
- **Best choice:** Cloudflare Workers AI (development/prototyping only)
- **Alternative:** OpenRouter free models
- **Why:** 10K Neurons/day free; sufficient for dev testing; never for production student data

### Analytics / Visualization
- **Best choice:** Recharts (React frontend) + Django JSON API (backend)
- **Alternative:** Chart.js (simpler) or server-side matplotlib (PDF reports)
- **Why:** Matches wireframe requirements (interactive charts); clean backend/frontend separation; MIT license

---

## 15. Total Cost / Free-Tier Assessment

### Recommended Architecture: Option A (Local-First)

| Component | Initial Cost | Recurring Cost | Notes |
|-----------|-------------|----------------|-------|
| scikit-learn | $0 | $0 | BSD license, fully open source |
| numpy | $0 | $0 | BSD license |
| pandas | $0 | $0 | BSD license |
| scipy | $0 | $0 | BSD license |
| implicit | $0 | $0 | MIT license |
| Recharts | $0 | $0 | MIT license |
| Django + DRF | $0 | $0 | Already installed |
| PostgreSQL | $0 | $0 | Already in use |
| **Total Core System** | **$0** | **$0** | **Fully free** |

### Optional Components (Future)

| Component | Initial Cost | Recurring Cost | Notes |
|-----------|-------------|----------------|-------|
| Ollama (local LLM) | $0 | $0 | MIT license; requires 8GB+ RAM on server |
| Cloudflare Workers AI (dev only) | $0 | $0 (within free tier) | 10K Neurons/day; not for production student data |
| Rasa (if chatbot implemented) | $0 | $0 | Apache 2.0; requires Redis + training infra |

### Dependency Summary Table

| Technology | Currently Installed? | Free? | New Dependency? | Runtime/Dev | Privacy | Complexity |
|-----------|---------------------|-------|----------------|-------------|---------|------------|
| scikit-learn | ❌ | ✅ | Yes | Runtime | Full (local) | Low |
| numpy | ❌ | ✅ | Yes | Runtime | Full (local) | Low (transitive) |
| pandas | ❌ | ✅ | Yes | Runtime | Full (local) | Low |
| scipy | ❌ | ✅ | Yes | Runtime | Full (local) | Low (transitive) |
| implicit | ❌ | ✅ | Yes | Runtime | Full (local) | Medium |
| Recharts | ❌ | ✅ | Yes | Frontend only | N/A | Low |
| Ollama | ❌ | ✅ | Yes (optional) | Runtime | Full (local) | Medium |
| Cloudflare Workers AI | ❌ | ⚠️ Free tier | Yes (optional) | External API | Partial | Low |

---

## 16. Performance / Deployment Assessment

### NFR-003: 5-Second User Action

ML inference costs for the target scale (100–300 students):
- **Decision Tree prediction:** ~1ms per student (scikit-learn DT is extremely fast)
- **Batch prediction (all students):** ~10–50ms for 300 students
- **Feature engineering (grade averages, attendance rates):** ~50–200ms depending on DB query complexity
- **Total risk computation for all students:** ~100–500ms (synchronous, within 5s budget)

**Conclusion:** Synchronous computation is feasible for the target school size. No async infrastructure needed for v1.

### NFR-004: 500 Concurrent Users

Risk computation is not a per-request operation — it is triggered periodically or on-demand by admin/guidance. The computation runs once and stores results. Subsequent reads are normal DB queries with DRF pagination.

- **Compute triggers:** ~1–5 per day (admin or guidance initiated)
- **Concurrent reads of risk data:** Standard DRF queryset performance; paginated at 20 items/page
- **No per-request ML inference** = no scaling concern from ML

### NFR-005: Dashboard Loads Within 5 Seconds

Dashboard data requires aggregation queries (count of risk alerts, average grades, attendance rates). For 100–300 students:
- **Aggregation query cost:** ~50–200ms per metric
- **Dashboard with 6–10 metrics:** ~300ms–2s total (including DB round-trips)
- **Caching opportunity:** Precomputed aggregation results stored in DB (AnalyticsReport model) or Django cache framework

**Recommendation:** Cache aggregation results. Recompute on risk computation trigger or on a configurable schedule.

### NFR-007: Deterministic DT Output

Satisfied by:
1. Training once, serializing model with `joblib.dump()`
2. Loading same model file for all inference calls
3. Setting `random_state` parameter during training
4. Identical input features → identical prediction

### Model Inference Cost Summary

| Operation | Frequency | Time Cost | Resource |
|-----------|-----------|-----------|----------|
| DT training | On-demand (retrain) | ~1–5 seconds | CPU only |
| DT prediction (single student) | Per-request | ~1ms | CPU only |
| DT prediction (batch, all students) | Per computation trigger | ~10–50ms | CPU only |
| CF model training | On-demand (retrain) | ~1–10 seconds | CPU only |
| CF recommendation (single student) | Per-request | ~5–20ms | CPU only |
| Feature engineering (full dataset) | Per computation trigger | ~100–500ms | CPU + DB |
| Dashboard aggregation | Per page load | ~50–200ms | DB |

**All operations are CPU-only.** No GPU required. No external API calls. Synchronous processing is fully practical.

### Deployment Implications

- **No new infrastructure required** for core ML features
- Model files (serialized Decision Tree, CF model) stored on filesystem: `ai_engine/models/`
- Computation runs inside Django process (no Celery, no Redis, no background worker)
- Same PostgreSQL database stores features and results
- Same Docker/deployment process as current backend

---

## 17. Architecture Options

### OPTION A: Local-First Python ML + Django

```
┌──────────────────────────────────────────────────────────┐
│  FRONTEND (React + Recharts)  [NOT YET CREATED]         │
│  Role-based dashboards, charts, risk views              │
└─────────────────┬────────────────────────────────────────┘
                  │ HTTPS / REST (JSON)
┌─────────────────▼────────────────────────────────────────┐
│  DJANGO REST FRAMEWORK                                   │
│  New app: apps/analytics (endpoints, views, serializers) │
│  Modified: apps/guidance (RiskAlert source扩展, dispatch) │
└─────────────────┬────────────────────────────────────────┘
                  │ Python function calls
┌─────────────────▼────────────────────────────────────────┐
│  ai_engine/  (Pure Python module)                        │
│  ├── risk_scorer.py   (scikit-learn DecisionTree)        │
│  ├── recommender.py   (implicit ALS or cosine sim)       │
│  ├── feature_engine.py (numpy/pandas transformations)    │
│  └── models/          (serialized .joblib model files)   │
└──────────────────────────────────────────────────────────┘
                  │ Django ORM queries
┌─────────────────▼────────────────────────────────────────┐
│  PostgreSQL (existing)                                   │
│  All existing tables + new analytics tables              │
└──────────────────────────────────────────────────────────┘
```

**Pros:**
- Simplest architecture — no new services
- Zero recurring cost
- Full privacy (all local)
- Easiest to test and debug
- Synchronous processing practical for 100–300 students
- Matches existing code patterns (Django apps + pure Python module)

**Cons:**
- Computation runs in Django process (blocks request thread during inference)
- No NLP/chatbot capability in this option
- Frontend must be created from scratch (empty `frontend/` directory)

**Implementation cost:** Medium (new app + ai_engine modules + frontend)
**Recurring cost:** $0
**Privacy:** Full (all local)
**Deployment:** Same as current (Django + PostgreSQL)
**Hardware:** Standard server (no GPU)
**Maintainability:** High (standard Django patterns)
**Testing:** High (scikit-learn models testable with unit tests)
**Reproducibility:** High (deterministic with fixed random_state)
**Explainability:** High (DT export_text, feature_importances_)
**Performance:** Excellent for target scale
**Student/capstone practicality:** High
**Chatbot compatibility:** Low (no NLP layer)
**Frontend compatibility:** High (JSON API for any frontend)

---

### OPTION B: Local ML + Optional Free-Tier Cloud Fallback

```
┌──────────────────────────────────────────────────────────┐
│  FRONTEND (React + Recharts)                             │
└─────────────────┬────────────────────────────────────────┘
                  │ HTTPS / REST
┌─────────────────▼────────────────────────────────────────┐
│  DJANGO REST FRAMEWORK                                   │
│  apps/analytics + apps/guidance modifications            │
└─────────────────┬────────────────────────────────────────┘
         ┌────────┴────────┐
         │                 │
┌────────▼────────┐ ┌──────▼─────────────────────────────┐
│  ai_engine/     │ │  Optional: Cloudflare Workers AI    │
│  (local ML)     │ │  (dev/prototyping only; NOT runtime │
│  DT + CF        │ │   for student data)                 │
└─────────────────┘ └────────────────────────────────────┘
         │
┌────────▼────────────────────────────────────────────────┐
│  PostgreSQL (existing)                                   │
└──────────────────────────────────────────────────────────┘
```

**Pros:**
- Same as Option A for core features
- Cloud fallback available for development/testing
- Cloudflare free tier allows experimenting with LLM without local GPU

**Cons:**
- Adds external dependency complexity
- Cloudflare free tier has daily limits (10K Neurons)
- Privacy risk if student data ever sent to cloud (must be prevented by architecture)
- Overkill for the actual use case (local inference is fast enough)

**Implementation cost:** Medium-High (same as A + cloud integration layer)
**Recurring cost:** $0 (within free tier)
**Privacy:** Partial (local primary; cloud has privacy risk)
**Deployment:** Same + Cloudflare account
**Chatbot compatibility:** Medium (cloud LLM available for dev)

---

### OPTION C: Hybrid with Dedicated Local AI/Runtime Layer

```
┌──────────────────────────────────────────────────────────┐
│  FRONTEND (React + Recharts)                             │
└─────────────────┬────────────────────────────────────────┘
                  │ HTTPS / REST
┌─────────────────▼────────────────────────────────────────┐
│  DJANGO REST FRAMEWORK                                   │
│  apps/analytics + apps/guidance modifications            │
└─────────────────┬────────────────────────────────────────┘
                  │ Internal API / function calls
┌─────────────────▼────────────────────────────────────────┐
│  ai_engine/  (Dedicated AI service module)               │
│  ├── services.py       (unified AI interface)            │
│  ├── risk_scorer.py    (scikit-learn DT)                 │
│  ├── recommender.py    (implicit ALS)                    │
│  ├── feature_engine.py (numpy/pandas)                    │
│  ├── nlp_engine.py     (future: spaCy / Ollama)          │
│  ├── model_manager.py  (training, serialization, cache)  │
│  ├── cache.py          (precomputed results)             │
│  └── models/           (serialized .joblib files)        │
└──────────────────────────────────────────────────────────┘
                  │
┌─────────────────▼────────────────────────────────────────┐
│  PostgreSQL + optional: Ollama (local LLM)               │
└──────────────────────────────────────────────────────────┘
```

**Pros:**
- Clean separation between Django app logic and AI logic
- `model_manager.py` provides unified model loading, versioning, retraining
- `cache.py` handles precomputed results (solves NFR-005)
- `nlp_engine.py` ready for future chatbot integration
- Ollama integration ready for future local LLM needs

**Cons:**
- More modules to build and maintain
- Over-engineered for the current scope (PH9 doesn't include NLP)
- More testing surface area

**Implementation cost:** High (more modules, more abstraction)
**Recurring cost:** $0
**Privacy:** Full (all local)
**Deployment:** Same + optional Ollama
**Chatbot compatibility:** High (dedicated NLP slot)

---

### OPTION D: Staged Hybrid (Recommended — See §18)

Start with Option A for PH9.0–PH9.7, with an architecture that allows upgrading to Option C for the PH9.8 NLP + AI Chatbot implementation.

```
PH9.0–PH9.7: Option A (simple, fast, minimal)
  └── ai_engine/ with risk_scorer.py, recommender.py, feature_engine.py
  └── apps/analytics with DRF views + serializers

PH9.8 (NLP + AI Chatbot Implementation): Upgrade to Option C structure
  └── Add nlp_engine.py, model_manager.py, cache.py
  └── Add Ollama integration
```

**This avoids over-engineering while preserving the migration path.**

---

## 18. Recommended Architecture

### **OPTION A (Local-First Python ML + Django) with staged upgrade path**

**Rationale:**

1. **Zero cost.** All components are open source, BSD/MIT licensed. No recurring fees.
2. **Maximum privacy.** No student data leaves the Django process. Full RA 10173 compliance.
3. **Matches existing patterns.** The repository already uses Django apps + pure Python modules. `ai_engine/` was designed as a pure Python module (§D.2).
4. **Practical for capstone.** Simple to explain, demonstrate, and defend. No external service accounts to set up.
5. **Deterministic.** scikit-learn DecisionTreeClassifier with fixed `random_state` satisfies NFR-007.
6. **Explainable.** `export_text()`, `feature_importances_`, decision paths all built-in. The panel wants to SEE how risk is computed.
7. **Synchronous is fine.** 100–300 students, <500ms full batch computation. No Celery/Redis needed.
8. **Frontend-agnostic backend.** JSON API works with any frontend (React, Vue, or even server-rendered).

### Recommended Stack

| Layer | Technology | Version | License |
|-------|-----------|---------|---------|
| Backend framework | Django + DRF | 6.1 + 3.18 | BSD |
| ML (Decision Tree) | scikit-learn | 1.9.0 | BSD |
| ML (Feature engineering) | numpy + pandas | 2.5.2 + 3.0.5 | BSD |
| ML (Collaborative Filtering) | implicit | 0.7.3 | MIT |
| Frontend charting | Recharts | 3.3.0 | MIT |
| Frontend framework | React + Vite | TBD | MIT |
| Database | PostgreSQL | Existing | — |
| Model serialization | joblib (bundled with scikit-learn) | — | BSD |

### Implementation Architecture (Files to Create/Modify)

**New files:**
```
backend/aegis_backend/ai_engine/
├── __init__.py              # (already exists, currently empty)
├── risk_scorer.py           # DecisionTreeClassifier wrapper
├── recommender.py           # ALS/cosine CF engine
├── feature_engine.py        # Grade/attendance/behavioral feature extraction
├── config.py                # ML configuration (thresholds, features — after approval)
└── models/                  # Serialized model files (.joblib)

backend/aegis_backend/apps/analytics/
├── __init__.py
├── apps.py
├── models.py                # RiskScore, Recommendation, AcademicReport
├── serializers.py
├── views.py                 # Compute trigger, dashboard aggregation
├── urls.py
├── admin.py
├── tests.py
└── migrations/
    └── 0001_initial.py
```

**Modified files:**
```
backend/aegis_backend/config/settings/base.py    # Uncomment "apps.analytics"
backend/aegis_backend/config/api_v1.py           # Add analytics URL routing
backend/aegis_backend/apps/guidance/models.py    # Add DECISION_TREE source, risk_score field
backend/aegis_backend/apps/guidance/views.py     # Populate AI-generated RiskAlert fields
backend/aegis_backend/apps/notifications/events.py  # Wire RISK_ALERT_GENERATED dispatch for AI
backend/requirements/base.txt                    # Add scikit-learn, numpy, pandas, scipy, implicit
```

---

## 19. Model/Data Feasibility Status

### GREEN / YELLOW / RED Gate

| Feature | Status | Reason |
|---------|--------|--------|
| **Decision Tree risk detection** | 🟡 YELLOW | Technically implementable with scikit-learn. Data schema exists. BUT: no historical labels, no populated data. Requires seed data + approved feature/threshold definitions before training a meaningful model. |
| **Collaborative Filtering** | 🟡 YELLOW | Technically implementable with implicit library. BUT: requires populated student×subject interaction matrix. Zero current data. Minimum ~20–30 students with grades needed. Cold-start problem for new students. |
| **AI recommendations (FR-040)** | 🟡 YELLOW | Decision Tree can generate recommendations based on feature importance. Same data dependency as DT risk detection. |
| **NLP** | 🟡 YELLOW | Confirmed system capability (thesis AI Chatbot Engine), but implementation architecture and privacy/design decisions remain unresolved. No implementation in PH9.0. Phase 9 must resolve the architecture before coding (D25). |
| **Chatbot** | 🟡 YELLOW | Confirmed system capability (FR-031 counselor escalation), but implementation was deferred from the initial backend and architecture/privacy decisions are open (D16, D23–D30). |
| **Visual analytics (FR-ANALYTICS-VISUAL)** | 🟡 YELLOW | Backend aggregation endpoints are straightforward. Frontend `frontend/` directory is empty — React app must be created from scratch. Requires both backend JSON APIs AND frontend chart implementation. |

**Why NLP/Chatbot moved from RED to YELLOW:**

- **FR-031 confirms the required capability** — "The system shall flag and escalate AI Chatbot interactions that indicate student concerns requiring counselor follow-up."
- **The initial backend deferred the implementation** (§I.6) — an implementation-timing constraint, not removal from the system.
- **Phase 9 must resolve the implementation architecture before coding** (D16, D23–D30).
- **No external student data may be sent during discovery/design** (SEC-PRIVACY / RA 10173).

### What Must Be True Before GREEN

| Prerequisite | For Feature | Status |
|-------------|-------------|--------|
| Seed data script populating grades, attendance, behavioral notes | DT, CF | Not yet created |
| Approved feature definitions (which fields, how computed) | DT | UNAPPROVED |
| Approved risk thresholds (low/moderate/high boundaries) | DT | UNAPPROVED |
| Approved training data strategy (historical labels or rule-based) | DT | UNAPPROVED |
| Approved CF interaction matrix design | CF | UNAPPROVED |
| RiskAlert model extended with risk_score + decision_tree source | DT | Not yet implemented |
| apps/analytics created with models + views | All | Not yet implemented |
| Frontend React app created | Analytics UI | Not yet implemented |

---

## 20. Decision Register

| # | Decision | Status | Evidence | Recommendation | Owner Approval Needed |
|---|----------|--------|----------|----------------|----------------------|
| D1 | Decision Tree target variable | UNAPPROVED | §I.4 | Risk level (low/moderate/high) for each student | ✅ YES |
| D2 | DT feature set | UNAPPROVED | §I.4 | Grades (avg, trend), Attendance (rate, counts), Behavioral (counts by type), Consultations (active count) | ✅ YES |
| D3 | DT feature definitions | UNAPPROVED | §I.4 | Feature engineering formulas per feature | ✅ YES |
| D4 | DT training data strategy | UNAPPROVED | §I.4 | Rule-based initial labels → manual refinement | ✅ YES |
| D5 | DT model configuration | UNAPPROVED | §I.4 | max_depth, min_samples_split, criterion (gini/entropy) | ✅ YES |
| D6 | DT risk thresholds | UNAPPROVED | §I.4, §L-OQ1 | Specific score ranges for low/moderate/high | ✅ YES |
| D7 | DT fallback (insufficient data) | UNAPPROVED | §I.4 | Return "low" or "insufficient_data" | ✅ YES |
| D8 | Risk computation trigger | UNAPPROVED | §I.4 | Manual trigger via admin/guidance endpoint | ✅ YES |
| D9 | Risk score numeric meaning | UNAPPROVED | §I.3 | Probability mapping (0–100%) | ✅ YES |
| D10 | CF similarity metric | UNAPPROVED | §I.5 | ALS (implicit library) or cosine similarity | ✅ YES |
| D11 | CF minimum interaction threshold | UNAPPROVED | §I.5 | Minimum 3–5 interactions per student | ✅ YES |
| D12 | CF recommendation types | UNAPPROVED | §I.5 | resource, activity, intervention | ✅ YES |
| D13 | CF recommendation sources | UNAPPROVED | §I.5 | Student performance patterns + similar profiles | ✅ YES |
| D14 | AI result visibility by role | PARTIALLY DEFINED | §F.2, PDF wireframes | Students: own score/factors/recommendations; Guidance: all; Faculty: advisory; Admin: aggregated | ✅ YES |
| D15 | Student sees own risk classification | CONFIRMED IN UI | PDF Figure 29 (AI Risk Alerts page) shows student profile with risk badge | But approval still needed for guidance-level visibility | ✅ YES |
| D16 | NLP/Chatbot capability | CONFIRMED SYSTEM REQUIREMENT / IMPLEMENTATION ARCHITECTURE OPEN | Final_REvision FR-031; AI Chatbot Engine (Objective 6.3); BACKEND_SPECIFICATION.md §I.6 | Treat chatbot/NLP as a Phase 9 planned workstream while preserving the initial-backend deferral as historical context | ✅ YES |
| D17 | Local vs cloud architecture | RECOMMENDED | §17-18 | Local-first (Option A) | ✅ YES |
| D18 | External AI/data boundary | DEFINED | §12 | No student data to external services | ✅ YES |
| D19 | Free-stack technology selection | RECOMMENDED | §13-14 | scikit-learn + implicit + Recharts | ✅ YES |
| D20 | Frontend framework | UNDECIDED | — | React + Vite (implied by .env.example CORS config) | ✅ YES |
| D21 | RiskAlert schema changes | BLOCKED | §10 | Add risk_score field, decision_tree source choice | Pending D1, D9 |
| D22 | Intervention escalation steps | OPEN | §L-OQ4 | School-specific steps needed | ✅ YES |
| D23 | Chatbot implementation phase | OPEN | FR-031 + §I.6 | Plan implementation within PH9 after architecture approval | ✅ YES |
| D24 | Chatbot framework | OPEN | FR-031 + §I.6 | Candidates: Rasa / custom Django / other self-hosted option | ✅ YES |
| D25 | NLP strategy | OPEN | FR-031 + §I.6 | Candidates: spaCy intent classification, rule-based classifier, local LLM, hybrid | ✅ YES |
| D26 | Local LLM runtime | OPEN | FR-031 + §I.6 | Candidates: Ollama / llama.cpp / other evidence-supported runtime | ✅ YES |
| D27 | Chatbot escalation model | OPEN | FR-031 | Must satisfy FR-031 without exposing unnecessary sensitive guidance data | ✅ YES |
| D28 | Conversation persistence | OPEN | §I.6, SEC-CHAT-PRIVACY | Determine whether conversations are stored, what data is retained, retention period, access control, and privacy impact | ✅ YES |
| D29 | External AI usage | OPEN | SEC-PRIVACY | Recommendation: no student/guidance data to external AI services | ✅ YES |
| D30 | Filipino/Taglish support | OPEN | FR-031 + §I.6 | Evaluate actual capability of selected local NLP/LLM stack | ✅ YES |

---

## 21. Proposed PH9 Sub-Phase Structure

### PH9.0 — Source-of-Truth + Repository Audit ✅ (This Document)
- Complete repository audit
- Source-of-truth analysis
- Technology evaluation
- Architecture options
- Decision register
- **No code changes**

### PH9.1 — Data Readiness + Seed Data
- Create seed data script for academics, attendance, guidance records
- Populate realistic demo data (100–300 students across 3–4 grade levels, 2 terms)
- Verify data populates all feature sources
- **Depends on:** Approved data scope (how many students, terms)
- **Gate:** Must have populated data before DT/CF training

### PH9.2 — Risk Computation Specification + Approval
- Document proposed feature definitions (formulas, computation)
- Document proposed thresholds
- Document proposed training data strategy
- Present for approval
- **Depends on:** D1–D9 decisions approved
- **Gate:** Cannot proceed to PH9.3 without approval

### PH9.3 — Decision Tree Implementation
- Implement `ai_engine/risk_scorer.py`
- Implement `ai_engine/feature_engine.py`
- Extend RiskAlert model (risk_score field, decision_tree source)
- Create DT training pipeline
- Unit tests for determinism (NFR-007)
- Unit tests for explainability
- **Depends on:** PH9.1 (data), PH9.2 (approved spec)

### PH9.4 — RiskAlert + Notification Integration
- Wire `dispatch_event(RISK_ALERT_GENERATED)` for AI-generated alerts
- Implement HIGH risk → Adviser + Parent notification routing
- Integration tests for end-to-end risk computation → alert → notification
- **Depends on:** PH9.3

### PH9.5 — Collaborative Filtering
- Implement `ai_engine/recommender.py`
- Build student × subject interaction matrix from grades/assessments
- Implement cold-start fallback
- Unit tests for recommendations
- **Depends on:** PH9.1 (data), D10–D13 approved

### PH9.6 — AI Recommendations
- Implement Recommendation model (§E.5)
- Wire DT-based recommendations (FR-040)
- Wire CF-based recommendations (FR-039)
- API endpoints for recommendations
- **Depends on:** PH9.3, PH9.5

### PH9.7 — Analytics / Visual Reporting
- Create `apps/analytics` with models, views, serializers
- Implement dashboard aggregation endpoints (academic metrics, attendance, school-wide)
- Admin analytics (aggregated per NFR-010)
- Faculty subject analytics
- Guidance risk overview analytics
- **Depends on:** PH9.1 (data), PH9.3 (DT results)

### PH9.8 — NLP + AI Chatbot Implementation
- chatbot architecture
- conversation model (if approved)
- intent/query classification
- urgency classification
- role-aware routing
- academic-resource assistance
- guidance-assessment assistance
- concern detection
- FR-031 counselor escalation
- local/self-hosted inference
- security/privacy controls
- chatbot tests
- **Depends on:** architecture approval, free-stack selection, privacy approval, escalation rules, conversation data policy
- **Do NOT implement this in PH9.0.**

### PH9.9 — Security / Privacy / Model Validation
- Verify all AI endpoints have RBAC (§F.2)
- Verify NFR-009 (student data scoping)
- Verify NFR-010 (admin aggregated data)
- Model validation: deterministic output tests
- Privacy audit: no student data leakage
- **Depends on:** PH9.3, PH9.6, PH9.7

### PH9.10 — Full Integration + Regression
- Run full test suite (existing 720 + new PH9 tests)
- End-to-end integration testing
- Performance testing (NFR-003, NFR-005)
- **Depends on:** All prior sub-phases

### PH9.11 — Git Checkpoint
- Commit all PH9 changes
- Tag checkpoint
- **Depends on:** PH9.10

### PH9.12 — Obsidian Checkpoint + Learning Note
- Update Obsidian documentation
- Create PH9 learning note
- **Depends on:** PH9.11

---

## 22. Risks / Blockers

| Risk | Severity | Mitigation |
|------|----------|------------|
| No historical risk labels exist | HIGH | PH9.2 must define a rule-based labeling strategy |
| Database is empty of production data | HIGH | PH9.1 must create comprehensive seed data |
| Risk computation parameters unapproved (§I.4) | HIGH | PH9.2 must get explicit approval before PH9.3 |
| Frontend directory is empty — React app not started | HIGH | Frontend work is a parallel workstream; does not block backend AI |
| Python 3.14 is very new — library compatibility risk | MEDIUM | Verified: scikit-learn 1.9.0, numpy 2.5.2, pandas 3.0.5 all confirmed on 3.14 |
| Cold-start problem for CF | MEDIUM | Content-based fallback for new students |
| RiskAlert model schema change needed | MEDIUM | Migration required; backward-compatible (nullable new fields) |
| Admin NFR-010 aggregated data requirement | MEDIUM | Requires careful queryset scoping for admin analytics |
| Intervention escalation steps undefined (§L-OQ4) | LOW | Can be deferred; guidance manually defines steps |
| Chatbot is a confirmed system capability but its implementation was deferred from the initial backend. Phase 9 must resolve the architecture, privacy, free-stack, and escalation design before implementation. | HIGH | FR-031 requires concern detection and counselor escalation, making chatbot behavior security/privacy-sensitive. |

---

## 23. Questions Requiring Our Discussion

These are the important choices that must be discussed before PH9 implementation begins.

### Decision Tree Design

1. **What should the DT predict?** The documentation says "at-risk student alerts based on academic performance patterns." Does this mean:
   - A 3-class classification (low/moderate/high)?
   - A binary classification (at-risk / not at-risk)?
   - A numeric risk score (0–100) that is then binned into categories?

2. **Which features should the DT use?** The illustrative draft (§I.3) suggests:
   - Grade average + trend
   - Attendance rate + late count
   - Behavioral note counts by type
   - Active consultation count
   - Are all of these approved? Are there others?

3. **How should thresholds work?** For example:
   - Risk score < 30 → low, 30–69 → moderate, ≥ 70 → high?
   - Or: DT leaf nodes directly map to risk levels?
   - The specific numbers need your approval.

### Training Data

4. **How do we get labeled training data?** Options:
   - **Rule-based labeling:** Define rules (e.g., avg grade < 75 AND absence > 20% → "at-risk") to generate initial labels, then train DT on those labels
   - **Manual labeling:** Guidance counselors manually classify 50–100 students, then train DT on those labels
   - **Hybrid:** Start with rules, then refine with manual labels
   - Which approach do you prefer?

5. **How much seed data should we create?** Options:
   - Minimal (50 students, 1 term) — enough to demonstrate
   - Moderate (150 students, 2 terms) — enough to train
   - Full (300 students, 4 terms) — production-realistic

### Collaborative Filtering

6. **What exactly should CF recommend?** The documentation says "personalized academic recommendations" and "personalized list of suggested study activities." What concrete recommendation types do you envision?
   - Study activity suggestions (e.g., "practice algebra exercises")?
   - Subject-specific resource links?
   - Intervention strategies for guidance?

7. **Is CF meaningful at this school's scale?** With 100–300 students and 6–8 subjects, the interaction matrix is small. Simple content-based recommendations (based on the student's own weak subjects) might be more practical than true collaborative filtering. Do you want to proceed with CF, or substitute a simpler approach?

### Free-Stack Choice

8. **Do you approve the recommended stack:** scikit-learn + implicit + Recharts?
    - All are $0, fully open source, MIT/BSD licensed
    - No vendor lock-in
    - Full local execution
    - Python 3.14 compatible (verified)

### Privacy Boundary

9. **Should students see their own risk scores?** The PDF wireframes (Figure 29) show a risk score on the AI Risk Alerts page. But this is in the guidance counselor's view, not necessarily the student's view. Should students see:
    - Their own risk level (low/moderate/high)?
    - Their own numeric risk score?
    - Their own detected risk factors?
    - Their own AI recommendations?

10. **Should parents see risk scores?** The PDF parent dashboard (Figures 18–20) does NOT show risk scores. Should parents see risk information for their children, or is this guidance-only?

11. **Should faculty see risk scores for their advisory students?** The PDF faculty dashboard (Figures 22–24) does NOT show risk scores. Should faculty see this, or is it guidance-only?

### NLP / Chatbot

12. **Confirm that FR-031 requires chatbot implementation as part of the completed AEGIS system.**

13. **Should chatbot implementation occur during PH9?**

14. **Should the architecture be local-first?**

15. **Rasa vs custom Django + local LLM vs hybrid?**

16. **What local model/runtime best supports English + Filipino/Taglish?**

17. **What intents/categories should be supported?**

18. **How should urgency be classified?**

19. **What exactly triggers FR-031 counselor escalation?**

20. **What chatbot data may be accessed from AEGIS?**

21. **Should conversation history be stored?**

22. **If stored, who may access it and how long is it retained?**

23. **What information must NEVER be passed to an LLM?**

24. **Is cloud AI completely prohibited for student data?**

25. **What should happen when the chatbot cannot confidently classify a concern?**

26. **What should happen when local model hardware is unavailable?**

---

## 24. Recommended Next Action

**Hold an architecture discussion meeting** to resolve the questions in §23 — the risk-computation/training-data/CF set, the privacy boundaries, and the NLP/Chatbot set — particularly:

1. **D1–D6:** Decision Tree target, features, definitions, thresholds (blocks PH9.2–PH9.3)
2. **Training data strategy:** Rule-based vs manual labeling (blocks PH9.1 and PH9.3)
3. **CF scope:** Full CF or simplified content-based alternative (blocks PH9.5)
4. **Privacy boundaries:** Who sees risk scores (blocks PH9.4 and PH9.9)
5. **Free-stack approval:** scikit-learn + implicit + Recharts (blocks PH9.3 and PH9.7)
6. **NLP/Chatbot architecture approval:** FR-031 confirmation, implementation phase, framework, NLP strategy, local LLM runtime, escalation model, conversation persistence, and the no-external-AI boundary (D16, D23–D30; gates PH9.8)

Once the risk/analytics decisions are resolved, PH9.1 (seed data) and PH9.2 (risk computation specification) can begin in parallel. The NLP/Chatbot decisions gate the PH9.8 implementation phase.

---

**PH9.0 COMPLETE — DESIGN BLOCKED UNTIL THE IDENTIFIED APPROVAL DECISIONS ARE RESOLVED.**

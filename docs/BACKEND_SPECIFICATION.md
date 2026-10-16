# AEGIS Backend Implementation Specification

**Version:** 2.1
**Date:** 2026-08-19
**Status:** APPROVED BASELINE — Ready for Implementation

> **This is a planning document. No code, models, migrations, or packages
> should be created from this document until it is explicitly approved.**

> Source documents: Final\_REvision.pdf (capstone document),
> commentary-notes.pdf (panel corrections), SAD\_Diagram.png.

> **Legend used throughout this document:**
> - **\[CONFIRMED\]** — Supported by the source documents or panel comments
> - **\[PROPOSED\]** — Architectural proposal requiring confirmation before implementation
> - **\[ASSUMPTION\]** — Implementation assumption that must be confirmed
> - **\[UNAPPROVED\]** — Draft idea not yet approved by anyone

---

## Table of Contents

1. [Confirmed Requirements](#a-confirmed-requirements)
2. [Panel Corrections](#b-panel-corrections)
3. [Proposed Architecture](#c-proposed-architecture)
4. [Proposed Django Modules](#d-proposed-django-modules)
5. [Database Entities and Relationships](#e-database-entities-and-relationships)
6. [Role/Permission Matrix](#f-rolepermission-matrix)
7. [Backend Workflows](#g-backend-workflows)
8. [API Boundaries](#h-api-boundaries)
9. [AI/ML Boundary](#i-aiml-boundary)
10. [Security and Privacy Requirements](#j-security-and-privacy-requirements)
11. [Explicit Assumptions](#k-explicit-assumptions)
12. [Decisions Still Requiring Approval](#l-decisions-still-requiring-approval)

---

## A. Confirmed Requirements

These are drawn directly from the Final\_REvision.pdf and
commentary-notes.pdf. Each entry cites its source.

### A.1 System Identity

| ID | Requirement | Source |
|----|-------------|--------|
| CR-001 | AEGIS is a **web-based** platform (browser-only). No native mobile application. | Final\_REvision §Scope; user instruction |
| CR-002 | The five user roles are: Student, Parent, Faculty, Guidance Counselor, Administrator. | Final\_REvision FR-001 through FR-006 |
| CR-003 | The system targets the **high school department** of HIS CARE CHRISTIAN INSTITUTE, Santa Maria, Sto. Tomas, Batangas. | Final\_REvision §Scope |
| CR-004 | The system does **not** cover financial management, tuition, or library management. | Final\_REvision §Scope |

### A.2 Functional Requirements — Faculty Module

| ID | Requirement | Source |
|----|-------------|--------|
| FR-007 | Faculty shall create and manage advisory class records including student profiles. | Final\_REvision FR-007 |
| FR-008 | Faculty shall record and monitor attendance. | Final\_REvision FR-008 |
| FR-009 | Faculty shall record behavioral notes (positive, warning, incident). | Final\_REvision FR-009 |
| FR-010 | Faculty shall encode student grades. | Final\_REvision FR-010 |
| FR-011 | Faculty shall update student grades. | Final\_REvision FR-011 |
| FR-012 | Faculty shall batch-upload grades via CSV or Excel. | Final\_REvision FR-012 |
| FR-013 | Faculty shall batch-upload attendance via CSV or Excel. | Final\_REvision FR-013 |
| FR-014 | Faculty shall view a consolidated advisory class summary. | Final\_REvision FR-014 |
| FR-015 | Faculty shall generate and export subject performance reports. | Final\_REvision FR-015 |
| FR-016 | Faculty shall generate and export advisory summaries. | Final\_REvision FR-016 |
| FR-FAC-ASSESS | **Faculty shall create, manage, and deploy academic assessments** for their students. | Panel correction #1; Panel #8 |

### A.3 Functional Requirements — Student Module

| ID | Requirement | Source |
|----|-------------|--------|
| FR-017 | Students shall view their grades. | Final\_REvision FR-017 |
| FR-018 | Students shall view their class schedule. | Final\_REvision FR-018 |
| FR-019 | Students shall view their attendance records. | Final\_REvision FR-019 |
| FR-020 | Students shall receive announcements and notifications about grades. | Final\_REvision FR-020 |
| FR-021 | Students shall receive announcements and notifications about attendance. | Final\_REvision FR-021 |
| FR-022 | Students shall receive announcements and notifications about concerns. | Final\_REvision FR-022 |
| FR-023 | Students shall take assessments deployed to them through the platform. | Final\_REvision FR-023 |

### A.4 Functional Requirements — Parent Module

| ID | Requirement | Source |
|----|-------------|--------|
| FR-024 | Parents shall view their child's academic performance in real time. | Final\_REvision FR-024 |
| FR-025 | Parents shall view their child's attendance in real time. | Final\_REvision FR-025 |
| FR-026 | Parents shall view their child's behavioral concerns in real time. | Final\_REvision FR-026 |
| FR-PARENT-NOTIFY | **Parents shall be notified when assessments are deployed to their child.** | Panel correction #3, #10 |

### A.5 Functional Requirements — Guidance Module

| ID | Requirement | Source |
|----|-------------|--------|
| FR-GUID-CONSULT | Guidance counselors shall manage student consultation records (session logs, history). | Final\_REvision FR-027 area; Objective 4.1 |
| FR-GUID-BEHAVIORAL | Guidance counselors shall view and track behavioral incident records. | Final\_REvision Objective 4.1.2 |
| FR-GUID-WELLNESS | **Guidance counselors shall create, manage, and deploy wellness/behavioral assessments** (not academic). | Panel correction #1; distinct from FR-FAC-ASSESS |
| FR-GUID-INTERVENTION | Guidance counselors shall create and manage intervention plans for at-risk students. | Final\_REvision Objective 4.3; Panel #9 |
| FR-GUID-REPORTS | Guidance counselors shall generate individual student guidance reports. | Final\_REvision FR-032 |
| FR-GUID-ALERTS | Guidance counselors shall receive AI-generated alerts for at-risk students. | Final\_REvision FR-030 |

### A.6 Functional Requirements — Admin Module

| ID | Requirement | Source |
|----|-------------|--------|
| FR-033 | Admin shall manage a Content Management System for school announcements. | Final\_REvision FR-033 |
| FR-034 | Admin shall manage system-wide settings. | Final\_REvision FR-034 |
| FR-035 | Admin shall manage school resources. | Final\_REvision FR-035 |
| FR-036 | Admin shall manage user accounts across all roles. | Final\_REvision FR-036 |
| FR-037 | Admin shall upload and process CSV/Excel data imports. | Final\_REvision FR-037 |
| FR-038 | The system shall maintain audit logs of system-wide activities and administrative actions. | Final\_REvision FR-038 |

### A.7 Functional Requirements — Analytics

| ID | Requirement | Source |
|----|-------------|--------|
| FR-030 | The system shall generate AI-driven at-risk student alerts based on academic performance patterns using a Decision Tree algorithm. | Final\_REvision FR-030 |
| FR-039 | The system shall produce AI-driven recommendations using Collaborative Filtering. | Final\_REvision FR-039 |
| FR-040 | The system shall produce AI-driven recommendations using Decision Tree algorithms. | Final\_REvision FR-040 |
| FR-ANALYTICS-VISUAL | The system shall provide visual reports and graphs on school-wide academic performance and attendance trends. | Final\_REvision Objective 6.1 |

### A.8 Non-Functional Requirements

| ID | Requirement | Source |
|----|-------------|--------|
| NFR-001 | Consistent layout and navigation across all pages. | Final\_REvision NFR-001 |
| NFR-002 | Clear error messages indicating what went wrong and how to correct it. | Final\_REvision NFR-002 |
| NFR-003 | Any user action shall complete within 5 seconds under normal conditions. | Final\_REvision NFR-003 |
| NFR-004 | System shall support up to 500 concurrent users without >2s degradation. | Final\_REvision NFR-004 |
| NFR-005 | Dashboard shall load all data within 5 seconds of login. | Final\_REvision NFR-005 |
| NFR-006 | System shall prevent duplicate registration using the same email. | Final\_REvision NFR-006 |
| NFR-007 | Decision Tree shall produce consistent outputs given the same input. | Final\_REvision NFR-007 |
| NFR-008 | All user passwords shall be stored securely using one-way hashing (not reversible encryption). | Final\_REvision NFR-008 |
| NFR-009 | Students shall only view/modify their own data. | Final\_REvision NFR-009 |
| NFR-010 | Admins shall view student data in aggregated/anonymized form unless consent is given. | Final\_REvision NFR-010 |
| NFR-011 | Role-based access control shall ensure users access only data/features for their role. | Final\_REvision NFR-011 |
| NFR-012 | Users shall be notified at least 24 hours in advance of scheduled maintenance. | Final\_REvision NFR-012 |
| NFR-013 | System shall use modular code with separate files for frontend, backend, and database logic. | Final\_REvision NFR-013 |
| NFR-014 | System shall function on latest Chrome, Firefox, and Edge. | Final\_REvision NFR-014 |
| NFR-015 | System shall be responsive on screens from 320px (mobile) to 1920px (desktop). | Final\_REvision NFR-015 |

### A.9 Scope Limitations (from Final\_REvision)

- Single institution only (HIS CARE CHRISTIAN INSTITUTE high school).
- No offline access.
- Data import supports CSV and Excel only; no live LMS integration.
- AI accuracy depends on data completeness and correctness.
- Chatbot responses limited to CMS-managed content scope.
- Internet connection required at all times.

---

## B. Panel Corrections

Each correction from `commentary-notes.pdf` with its implementation
status.

| # | Panel Comment | Status | Notes |
|---|--------------|--------|-------|
| 1 | **Academic Assessment should be given by Faculty, not Guidance.** | **ADOPTED** | Restructures assessment ownership. Faculty owns academic assessments. Guidance owns wellness/behavioral assessments. See §G.5, §H. |
| 2 | **Computation of Risk and prioritization — need explicit process/formula.** | **NOTED — UNAPPROVED** | The panel wants an explicit, documented computation. The v1.0 draft proposed specific weights/thresholds which are **NOT approved**. The computation flow and parameters must be defined before implementation. See §I. |
| 3 | **Parent Account and Notification.** | **ADOPTED** | Parent accounts exist. Notifications to parents on key events defined in §G.7. |
| 4 | **Privacy on chat.** | **DEFERRED** | Chatbot is deferred. When implemented, chat data must be private and encrypted. |
| 5 | **Behavioral notes should be sent to the Guidance Counselor.** | **ADOPTED** | Behavioral notes of type "warning" or "incident" trigger a notification to the guidance counselor. See §G.3. |
| 6 | **Assessment timing — is it per quarter? When to take?** | **OPEN** | The documents do not specify a fixed quarterly cadence. See §L-OQ2. |
| 7 | **Assessment delivery — take home or at school?** | **OPEN** | Backend provides the API. Delivery context is a school policy / frontend concern. See §L-OQ3. |
| 8 | **Be specific on grades — how and who takes the assessment.** | **ADOPTED** | Faculty creates/loads academic assessments. Students take them via the platform. See §G.5. |
| 9 | **If high risk, what intervention is done first?** | **NOTED** | The panel wants a documented intervention escalation flow. The documents describe this generally. See §G.6. Specific escalation steps are an open decision. See §L-OQ4. |
| 10 | **Assessment notification UI — where does the parent see it?** | **ADOPTED** | When an assessment is deployed, parents of target students receive a notification. |
| 11 | **Data pre-defined, privacy policy, agreement.** | **ADOPTED** | Users must accept a privacy policy upon registration. See §J. |
| 12 | **Gemini endpoint.** | **DEFERRED** | Chatbot integration is deferred. Gemini endpoint is a future integration boundary. See §I. |
| 13 | **Psychometrician.** | **OPEN** | Unclear if this is a separate role or a specialization within Guidance. See §L-OQ5. |
| 14 | **Language barrier checkbox.** | **OPEN** | Unclear priority and implementation scope. See §L-OQ6. |
| 15 | **Behavior notes direct to Guidance Counselor — all data should trigger direct notifications.** | **INTERPRETED CAREFULLY** | Does NOT mean every database change triggers a notification. Means that relevant domain events (behavioral incidents, grade postings, etc.) should notify the appropriate parties. See §G.7 for the definitive event list. |
| 16 | **Push notification — what is needed and applicable.** | **OPEN** | Feasibility of web push notifications is a deployment decision. See §L-OQ7. |

---

## C. Proposed Architecture

> **\[PROPOSED\]** — This architecture is a proposal. It must be reviewed
> before implementation.

### C.1 High-Level Structure

```
┌─────────────────────────────────────────────────────────────┐
│  CLIENT LAYER                                               │
│  React SPA — five role-specific portals (web-only)          │
│  (Student | Parent | Faculty | Guidance | Admin)            │
└──────────────────┬──────────────────────────────────────────┘
                   │ HTTPS / REST (JSON)
┌──────────────────▼──────────────────────────────────────────┐
│  SECURITY LAYER                                             │
│  [CONFIRMED] JWT auth, RBAC, password hashing               │
│  [PROPOSED]  HTTPS/TLS, input validation, audit trail       │
├─────────────────────────────────────────────────────────────┤
│  REST API GATEWAY                                           │
│  Django REST Framework — ViewSets, Routers, Serializers     │
├─────────────────────────────────────────────────────────────┤
│  DJANGO APPLICATION LAYER                                   │
│  accounts | academics | attendance | guidance | analytics   │
│  cms | data_import | notifications | audit                  │
├─────────────────────────────────────────────────────────────┤
│  AI/ANALYTICS ENGINE                                        │
│  Python services (scikit-learn)                             │
│  [CONFIRMED]  Decision Tree, Collaborative Filtering        │
│  [DEFERRED]   NLP / Chatbot                                 │
├─────────────────────────────────────────────────────────────┤
│  DATABASE LAYER                                             │
│  PostgreSQL                                                  │
│  [PROPOSED]   Hosted via Supabase                           │
│  Single database, tables namespaced by Django app label      │
├─────────────────────────────────────────────────────────────┤
│  INFRASTRUCTURE                                             │
│  [PROPOSED] Nginx reverse proxy (production)                │
│  [PROPOSED] File storage for uploads and exports            │
│  [PROPOSED] Email service for notifications                 │
└─────────────────────────────────────────────────────────────┘
```

### C.2 Key Architectural Decisions

| Decision | Status | Rationale |
|----------|--------|-----------|
| Single PostgreSQL database with app-namespaced tables | **\[PROPOSED\]** | The SAD shows 5 separate databases. A single DB with logical separation via Django app labels is more practical for a capstone project and simplifies cross-module queries. Requires confirmation. |
| CMS built with native Django models | **\[PROPOSED\]** | The SAD references Strapi. Strapi is a separate Node.js service. For a single small school, native Django models are simpler. **Requires confirmation — see §L-OQ8.** |
| Chatbot fully deferred | **\[CONFIRMED\]** | Botpress/Rasa/Gemini are NOT installed or implemented. API hooks are left for future integration. |
| No Nginx during development | **\[PROPOSED\]** | Django's dev server is sufficient for development. Nginx is for production deployment only. |
| Synchronous processing for v1 | **\[CONFIRMED\]** | No Celery or Redis. Risk computation runs synchronously. A small data import finishes inside the request; a file above 200 rows is finished by a bounded worker pool in the same process and polled — no queue service is added (see §G.8). |

---

## D. Proposed Django Modules

> **\[PROPOSED\]** — App boundaries are proposals that must be confirmed.

### D.1 Project Structure

```
aegis_backend/
├── manage.py
├── config/
│   ├── settings/
│   │   ├── base.py
│   │   ├── development.py
│   │   └── production.py
│   ├── urls.py
│   └── wsgi.py
│
├── apps/
│   ├── accounts/          # User model, profiles, auth, RBAC
│   ├── academics/         # Subjects, schedules, grades, enrollments
│   ├── attendance/        # Daily attendance records
│   ├── guidance/          # Consultations, behavioral notes, interventions, risk alerts
│   ├── assessments/       # Assessment CRUD, questions, deployment, submissions, results
│   ├── analytics/         # Risk scoring, recommendations, reports
│   ├── cms/               # Announcements, resources, system settings
│   ├── data_import/       # CSV/Excel upload, parsing, validation
│   ├── notifications/     # In-app notifications, email dispatch
│   └── audit/             # Audit trail logging
│
├── core/
│   ├── models.py          # Abstract base models
│   ├── permissions.py     # Custom DRF permission classes
│   ├── pagination.py
│   ├── exceptions.py
│   └── utils.py
│
├── ai_engine/             # ML services (pure Python, not a Django app)
│   ├── risk_scorer.py
│   └── recommender.py
│
├── templates/             # Email templates
└── requirements/
    ├── base.txt
    ├── development.txt
    └── production.txt
```

### D.2 Module Responsibilities

| App | Responsibility | Notes |
|-----|---------------|-------|
| `accounts` | User model (custom, extends AbstractUser), role field, profile models per role, parent-student linking, authentication endpoints | Single User model with role discriminator, not separate user tables |
| `academics` | Academic years, grade levels, sections, subjects, subject assignments, schedules, grading periods, enrollments, grades | Faculty-facing grade encoding lives here |
| `attendance` | Daily attendance records per student per date | Faculty records; students/parents view |
| `guidance` | Behavioral notes, consultation records, intervention plans, intervention steps, progress notes, risk alerts | Faculty records behavioral notes here; Guidance manages consultations and interventions |
| `assessments` | Assessment creation, question management, deployment, student submission, results | Faculty manages academic assessments; Guidance manages wellness/behavioral; Students take assessments. Ownership enforced by `creator_role` and permission classes (see §D.3) |
| `analytics` | Risk score computation, collaborative filtering recommendations, report generation | Uses `ai_engine` for ML; stores results in `analytics` models |
| `cms` | Announcements, resources, system settings | Admin-managed content |
| `data_import` | File upload handling, CSV/Excel parsing, row-level validation, import job tracking | Faculty can import grades and attendance; Admin can import all types including students (see §G.8) |
| `notifications` | Notification model, creation logic per domain event, user preferences, email dispatch | Triggered by explicit domain events (see §G.7) |
| `audit` | Audit log model, middleware/signals for activity tracking | Records who did what, when, on which object |
| `core` | Shared base models, permission classes, pagination, exception handling, utilities | No user-facing models |
| `ai_engine` | Decision Tree risk scoring, Collaborative Filtering recommendations | Pure Python module; reads from Django models, writes results back |

### D.3 Assessment Ownership — Module Split

**This is a direct implementation of Panel Correction #1.**

| Assessment Type | Created By | App | API Namespace | Deployed To |
|----------------|-----------|-----|---------------|-------------|
| Academic (e.g., Mathematics exam, Science quiz) | Faculty | `assessments` | `/api/v1/assessments/` | Students in target sections |
| Wellness (e.g., Emotional Wellness Assessment) | Guidance Counselor | `assessments` | `/api/v1/assessments/` | Students in target sections |
| Behavioral (e.g., behavioral screening) | Guidance Counselor | `assessments` | `/api/v1/assessments/` | Students in target sections |

The `Assessment` model lives in the **`assessments`** app and uses a
`creator_role` field and an `assessment_type` field to distinguish
ownership and access control:

- Faculty can CRUD assessments where `creator_role="faculty"` and
  `assessment_type="academic"`.
- Guidance can CRUD assessments where `creator_role="guidance"` and
  `assessment_type` is `"wellness"` or `"behavioral"`.
- Students take any published assessment assigned to them.
- The `assessments` app depends on `accounts` and `academics` for
  user/section references.

---

## E. Database Entities and Relationships

> **\[PROPOSED\]** — All models are proposals. They must be confirmed
> before Django model code is written.

### E.1 accounts

```
User (extends AbstractUser)
├── id               UUID PK
├── email            char, unique
├── first_name       char
├── last_name        char
├── role             char (student|parent|faculty|guidance|admin)
├── is_active        bool
├── profile_photo    image, nullable
├── phone_number     char, nullable
├── address          char, nullable
├── language_preference  char, nullable          [ASSUMPTION — §L-OQ6]
├── privacy_policy_accepted  bool
├── privacy_policy_accepted_at  datetime, nullable
├── created_at       datetime
└── updated_at       datetime

StudentProfile
├── id               UUID PK
├── user             FK → User (unique)
├── student_id       char, unique (school-assigned ID)
├── grade_level      FK → GradeLevel
├── section          FK → Section
├── date_of_birth    date, nullable
├── guardian_contact char, nullable
├── enrollment_date  date
├── is_active        bool
├── created_at       datetime
└── updated_at       datetime

ParentProfile
├── id               UUID PK
├── user             FK → User (unique)
├── relationship_to_student  char
├── created_at       datetime
└── updated_at       datetime

ParentStudentLink
├── id               UUID PK
├── parent           FK → ParentProfile
├── student          FK → StudentProfile
├── is_primary       bool
└── UNIQUE(parent, student)

FacultyProfile
├── id               UUID PK
├── user             FK → User (unique)
├── employee_id      char, unique
├── department       char, nullable
├── is_adviser       bool
├── advisory_section FK → Section, nullable
├── created_at       datetime
└── updated_at       datetime

GuidanceProfile
├── id               UUID PK
├── user             FK → User (unique)
├── employee_id      char, unique
├── specialization   char, nullable
├── license_number   char, nullable
├── created_at       datetime
└── updated_at       datetime

AdminProfile
├── id               UUID PK
├── user             FK → User (unique)
├── admin_level      char (superadmin|admin)
├── created_at       datetime
└── updated_at       datetime
```

### E.2 academics

```
AcademicYear
├── id               UUID PK
├── name             char (e.g., "2025-2026")
├── start_date       date
├── end_date         date
└── is_current       bool

GradeLevel
├── id               UUID PK
├── name             char (e.g., "Grade 7")
└── level_number     int

Section
├── id               UUID PK
├── name             char (e.g., "Einstein")
├── grade_level      FK → GradeLevel
├── academic_year    FK → AcademicYear
├── adviser          FK → FacultyProfile, nullable
└── UNIQUE(name, grade_level, academic_year)

Subject
├── id               UUID PK
├── name             char
├── code             char, unique
└── grade_level      FK → GradeLevel

SubjectAssignment
├── id               UUID PK
├── subject          FK → Subject
├── faculty          FK → FacultyProfile
├── section          FK → Section
├── academic_year    FK → AcademicYear
└── UNIQUE(subject, section, academic_year)

Schedule
├── id               UUID PK
├── subject_assignment  FK → SubjectAssignment
├── day_of_week      char (mon|tue|wed|thu|fri)
├── start_time       time
├── end_time         time
└── room             char, nullable

GradingPeriod
├── id               UUID PK
├── academic_year    FK → AcademicYear
├── name             char (e.g., "1st Quarter")
├── order            int
├── start_date       date
└── end_date         date

Enrollment
├── id               UUID PK
├── student          FK → StudentProfile
├── section          FK → Section
├── academic_year    FK → AcademicYear
├── date_enrolled    date
├── is_active        bool
└── UNIQUE(student, section, academic_year)

Grade
├── id               UUID PK
├── student          FK → StudentProfile
├── subject_assignment  FK → SubjectAssignment
├── grading_period   FK → GradingPeriod
├── score            decimal(5,2), nullable
├── letter_grade     char, nullable
├── remarks          char, nullable
├── encoded_by       FK → FacultyProfile
├── status           char (draft|submitted|finalized)
├── created_at       datetime
├── updated_at       datetime
└── UNIQUE(student, subject_assignment, grading_period)
```

### E.3 attendance

```
AttendanceRecord
├── id               UUID PK
├── student          FK → StudentProfile
├── date             date
├── status           char (present|late|absent)
├── recorded_by      FK → FacultyProfile
├── section          FK → Section
├── created_at       datetime
├── updated_at       datetime
└── UNIQUE(student, date)
```

### E.4 guidance

```
BehavioralNote
├── id               UUID PK
├── student          FK → StudentProfile
├── recorded_by      FK → FacultyProfile
├── note_type        char (positive|warning|incident)
├── note_text        text
├── date_recorded    date
├── created_at       datetime
└── updated_at       datetime

ConsultationRecord
├── id               UUID PK
├── student          FK → StudentProfile
├── counselor        FK → GuidanceProfile
├── session_date     date
├── session_time     time
├── session_type     char (individual_counseling|group|parent_conference|follow_up)
├── concern_categories  JSON (array of: academic, behavioral, emotional, family, bullying, other)
├── session_notes    text
├── recommendations  text, nullable
├── next_session_date  date, nullable
├── priority_level   char (high|medium|low)
├── status           char (ongoing|completed|follow_up)
├── created_at       datetime
└── updated_at       datetime

Assessment
├── id               UUID PK
├── title            char
├── description      text, nullable
├── assessment_type  char (academic|wellness|behavioral)
├── creator_role     char (faculty|guidance)
├── created_by       FK → User (FacultyProfile.user or GuidanceProfile.user)
├── target_sections  M2M → Section
├── target_students  M2M → StudentProfile, nullable (null = all in sections)
├── quarter          FK → GradingPeriod, nullable
├── time_limit_minutes  int, nullable
├── is_published     bool
├── published_at     datetime, nullable
├── deadline         datetime, nullable
├── created_at       datetime
└── updated_at       datetime

AssessmentQuestion
├── id               UUID PK
├── assessment       FK → Assessment
├── question_text    text
├── question_type    char (multiple_choice|likert|true_false|essay)
├── options          JSON, nullable (for MC/true_false)
├── correct_answer   char, nullable
└── order            int

AssessmentResult
├── id               UUID PK
├── assessment       FK → Assessment
├── student          FK → StudentProfile
├── answers          JSON (question_id → answer mapping)
├── score            decimal, nullable
├── total_possible   decimal, nullable
├── percentage       decimal, nullable
├── status           char (in_progress|completed)
├── started_at       datetime
├── completed_at     datetime, nullable
├── created_at       datetime
├── updated_at       datetime
└── UNIQUE(assessment, student)

Intervention
├── id               UUID PK
├── student          FK → StudentProfile
├── risk_alert       FK → RiskAlert, nullable
├── assigned_counselor  FK → GuidanceProfile
├── plan_start_date  date
├── target_review_date  date, nullable
├── status           char (active|completed|cancelled)
├── created_at       datetime
└── updated_at       datetime

InterventionStep
├── id               UUID PK
├── intervention     FK → Intervention
├── title            char
├── description      text
├── status           char (pending|in_progress|completed|scheduled)
├── order            int
├── created_at       datetime
└── updated_at       datetime

ProgressNote
├── id               UUID PK
├── intervention     FK → Intervention
├── note_text        text
├── recorded_by      FK → GuidanceProfile
├── next_follow_up   datetime, nullable
└── created_at       datetime

RiskAlert
├── id               UUID PK
├── student          FK → StudentProfile
├── risk_level       char (low|moderate|high)
├── risk_score       decimal(5,2) (0-100) [UNAPPROVED — see §I]
├── risk_factors     JSON (array of factor descriptions)
├── source           char (decision_tree|chatbot_escalation|manual)
├── status           char (active|under_monitoring|resolved|escalated)
├── assigned_counselor  FK → GuidanceProfile, nullable
├── ai_recommendation   text, nullable
├── generated_at     datetime
├── last_updated     datetime
├── created_at       datetime
└── updated_at       datetime
```

### E.5 analytics

```
RiskScore
├── id               UUID PK
├── student          FK → StudentProfile
├── academic_year    FK → AcademicYear
├── grading_period   FK → GradingPeriod, nullable
├── overall_score    decimal [UNAPPROVED — see §I]
├── grade_component  decimal [UNAPPROVED — see §I]
├── attendance_component  decimal [UNAPPROVED — see §I]
├── behavioral_component  decimal [UNAPPROVED — see §I]
├── risk_level       char (low|moderate|high) [UNAPPROVED — see §I]
├── computed_at      datetime
└── (These fields are illustrative. The actual computation parameters
     are UNAPPROVED. See §I.)

Recommendation
├── id               UUID PK
├── student          FK → StudentProfile
├── recommendation_type  char (resource|activity|intervention)
├── content          text
├── generated_at     datetime
└── is_read          bool

AcademicReport
├── id               UUID PK
├── student          FK → StudentProfile
├── report_type      char (subject_performance|class_summary|advisory|
│                          parent_performance|guidance_report)
├── generated_by     FK → User
├── data             JSON
├── file_path        char, nullable
└── created_at       datetime
```

### E.6 cms

```
Announcement
├── id               UUID PK
├── title            char
├── content          text
├── announcement_type  char (news|event|alert|academic)
├── priority         char (normal|high|urgent)
├── target_roles     JSON (array of role strings, or "all")
├── target_sections  M2M → Section, nullable (null = all)
├── is_published     bool
├── published_at     datetime, nullable
├── expires_at       datetime, nullable
├── created_by       FK → User
├── created_at       datetime
└── updated_at       datetime

Resource
├── id               UUID PK
├── title            char
├── description      text, nullable
├── resource_type    char (document|link|video|other)
├── file_or_url      char
├── target_audience  JSON (array of roles)
├── is_active        bool
├── created_by       FK → User
├── created_at       datetime
└── updated_at       datetime

SystemSetting
├── id               UUID PK
├── key              char, unique
├── value            text
├── description      text, nullable
├── updated_by       FK → User
└── updated_at       datetime
```

### E.7 data\_import

```
ImportJob
├── id               UUID PK
├── uploaded_by      FK → User
├── file             FileField
├── file_type        char (csv|xlsx|xls)
├── import_type      char (grades|attendance|students|guidance_records)
│                      # grades, attendance: Faculty + Admin
│                      # students, guidance_records: Admin only
├── status           char (pending|processing|completed|failed|partial)
├── total_rows       int
├── processed_rows   int
├── error_rows       int
├── error_log        text, nullable
├── created_at       datetime
└── completed_at     datetime, nullable

ImportRecord
├── id               UUID PK
├── job              FK → ImportJob
├── row_number       int
├── data             JSON (parsed row)
├── status           char (success|error|skipped)
├── error_message    text, nullable
├── mapped_to_model  char, nullable
└── mapped_to_id     char, nullable
```

### E.8 notifications

```
Notification
├── id               UUID PK
├── recipient        FK → User
├── sender           FK → User, nullable (null = system-generated)
├── notification_type  char (see §G.7 for valid types)
├── title            char
├── message          text
├── link             char, nullable (frontend route)
├── is_read          bool
├── read_at          datetime, nullable
└── created_at       datetime

NotificationPreference
├── id               UUID PK
├── user             FK → User (unique)
├── email_enabled    bool
├── in_app_enabled   bool
├── quiet_hours_start  time, nullable
└── quiet_hours_end  time, nullable
```

### E.9 audit

```
AuditLog
├── id               UUID PK
├── user             FK → User, nullable (null = system events)
├── action           char (create|update|delete|login|logout|import|export|access)
├── model_name       char
├── object_id        char, nullable
├── object_repr      char
├── changes          JSON, nullable (before/after diff)
├── ip_address       GenericIPAddress, nullable
├── user_agent       text, nullable
└── timestamp        datetime
```

### E.10 Entity Relationship Summary

```
User ─────┬──── StudentProfile ──── Enrollment ──── Section
          ├──── ParentProfile ───── ParentStudentLink
          ├──── FacultyProfile ──── SubjectAssignment
          ├──── GuidanceProfile ─── ConsultationRecord
          └──── AdminProfile       Intervention
                                    RiskAlert

Section ── GradeLevel
         └─ Schedule → SubjectAssignment → Subject

Grade ──── StudentProfile
         └─ SubjectAssignment → GradingPeriod

AttendanceRecord ── StudentProfile
                  └─ FacultyProfile → Section

BehavioralNote ──── StudentProfile → FacultyProfile

Assessment ──────── User (created_by)
              ├──── AssessmentQuestion
              ├──── AssessmentResult → StudentProfile
              ├──── M2M → Section
              └──── M2M → StudentProfile (target, nullable)

Intervention ────── StudentProfile → GuidanceProfile → RiskAlert
            ├──── InterventionStep
            └──── ProgressNote → GuidanceProfile

RiskScore ── StudentProfile → GradingPeriod

ImportJob ── ImportRecord
           └─ uploaded_by → User

Notification ── recipient → User
              └─ sender → User (nullable)

AuditLog ── user → User (nullable)
```

---

## F. Role/Permission Matrix

### F.1 Permission Codes

| Code | Description |
|------|-------------|
| `view_own_profile` | View own profile and account settings |
| `edit_own_profile` | Edit own profile information |
| `view_own_grades` | View own grades (student) |
| `view_child_records` | View linked child's records (parent) |
| `view_student_records` | View student academic records |
| `encode_grades` | Encode and submit grades |
| `batch_import_grades` | Import grades via CSV/Excel |
| `record_attendance` | Record and edit attendance |
| `batch_import_attendance` | Import attendance via CSV/Excel |
| `record_behavioral_note` | Record behavioral notes for students |
| `view_behavioral_notes` | View behavioral notes |
| `manage_advisory_class` | CRUD advisory class roster |
| `view_subject_schedule` | View subjects and schedules |
| `generate_reports` | Generate and export reports |
| `create_academic_assessment` | Create academic assessments (faculty) |
| `create_wellness_assessment` | Create wellness/behavioral assessments (guidance) |
| `deploy_assessment` | Publish assessments to students |
| `view_assessment_results` | View assessment results |
| `take_assessment` | Take deployed assessments (student) |
| `manage_consultation_records` | CRUD consultation records |
| `manage_interventions` | Create/manage intervention plans |
| `receive_risk_alerts` | Receive AI-generated risk alerts |
| `manage_users` | CRUD all user accounts |
| `assign_roles` | Assign/change user roles |
| `manage_announcements` | CRUD announcements |
| `manage_resources` | CRUD resources |
| `manage_system_settings` | View/edit system settings |
| `manage_data_imports` | Upload and process import jobs (scope varies by role — see §G.8) |
| `view_audit_logs` | View audit trail |
| `view_analytics` | View analytics and charts |
| `view_notifications` | View own notifications |

### F.2 Matrix

| Permission | Student | Parent | Faculty | Guidance | Admin |
|-----------|:-------:|:------:|:-------:|:--------:|:-----:|
| `view_own_profile` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `edit_own_profile` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `view_own_grades` | ✓ | — | — | — | — |
| `view_child_records` | — | ✓ | — | — | — |
| `view_student_records` | — | — | ✓ (own advisory) | ✓ (all) | ✓ (aggregated*) |
| `encode_grades` | — | — | ✓ | — | — |
| `batch_import_grades` | — | — | ✓ | — | ✓ |
| `record_attendance` | — | — | ✓ | — | — |
| `batch_import_attendance` | — | — | ✓ | — | ✓ |
| `record_behavioral_note` | — | — | ✓ | — | — |
| `view_behavioral_notes` | — | ✓ (child only) | ✓ (own advisory) | ✓ (all) | — |
| `manage_advisory_class` | — | — | ✓ | — | — |
| `view_subject_schedule` | ✓ | ✓ (child) | ✓ | ✓ | ✓ |
| `generate_reports` | — | — | ✓ | ✓ | ✓ |
| `create_academic_assessment` | — | — | ✓ | — | — |
| `create_wellness_assessment` | — | — | — | ✓ | — |
| `deploy_assessment` | — | — | ✓ | ✓ | — |
| `view_assessment_results` | ✓ (own) | ✓ (child) | ✓ (own subject) | ✓ (all) | — |
| `take_assessment` | ✓ | — | — | — | — |
| `manage_consultation_records` | — | — | — | ✓ | — |
| `manage_interventions` | — | — | — | ✓ | — |
| `receive_risk_alerts` | — | — | ✓ (advisory) | ✓ (all) | — |
| `manage_users` | — | — | — | — | ✓ |
| `assign_roles` | — | — | — | — | ✓ |
| `manage_announcements` | — | — | — | — | ✓ |
| `manage_resources` | — | — | — | — | ✓ |
| `manage_system_settings` | — | — | — | — | ✓ |
| `manage_data_imports` | — | — | ✓ (grades, attendance) | — | ✓ (all types) |
| `view_audit_logs` | — | — | — | — | ✓ |
| `view_analytics` | — | — | ✓ (own subjects) | ✓ | ✓ |
| `view_notifications` | ✓ | ✓ | ✓ | ✓ | ✓ |

> \* Admin views student data in aggregated/anonymized form unless
> explicit consent is given (NFR-010).

---

## G. Backend Workflows

### G.1 Authentication and Registration

```
1. Student/Parent self-registers via /api/v1/auth/register/
   - Must accept privacy policy (privacy_policy_accepted=True)
   - Account created as inactive
   - Email verification required before activation

2. Faculty/Guidance/Admin accounts created by Admin
   via /api/v1/accounts/users/

3. Login: POST /api/v1/auth/login/
   → Returns JWT access token + refresh token
   [ASSUMPTION — token lifetimes are implementation details, see §J]

4. Subsequent requests: Authorization: Bearer <access_token>
   → DRF middleware decodes JWT, attaches User
   → Custom permission classes enforce RBAC

5. Token refresh: POST /api/v1/auth/token/refresh/
6. Logout: blacklist refresh token
```

### G.2 Grade Encoding

```
Faculty encodes grades (manual entry or CSV/Excel import)
    ↓
Grade saved as status=draft
    ↓
Faculty reviews and submits (status=submitted)
    ↓
Admin reviews and finalizes (status=finalized)
    ↓
System computes GPA per student per quarter
    ↓
Domain event: GRADE_POSTED
    → Recipients: Student + Parent (of the student)
    → Creates in-app Notification
    → Sends email if user preference enabled
```

### G.3 Behavioral Note Recording

```
Faculty records a behavioral note
    ↓
  note_type = "positive" → saved. No notification.
  note_type = "warning"  → saved → DOMAIN EVENT: BEHAVIORAL_WARNING
  note_type = "incident" → saved → DOMAIN EVENT: BEHAVIORAL_INCIDENT

Domain event recipients:
  BEHAVIORAL_WARNING  → Guidance Counselor (all, or assigned if exists)
  BEHAVIORAL_INCIDENT → Guidance Counselor (all, or assigned)
                      → Faculty Adviser (of the student's section)
```

### G.4 Attendance Recording

```
Faculty selects date + section → loads student roster
    ↓
Faculty marks each student: present / late / absent
    ↓
Batch or individual POST to /api/v1/attendance/records/
    ↓
System saves records, updates attendance statistics
    ↓
Domain event: ATTENDANCE_THRESHOLD (if absence count exceeds threshold)
    → Recipients: Parent (of the absent student)
    [ASSUMPTION — threshold value is configurable via SystemSetting]
```

### G.5 Assessment Workflow

```
FACULTY creates academic assessment:
  POST /api/v1/assessments/
  {
      "title": "Mathematics Q1 Exam",
      "assessment_type": "academic",
      "creator_role": "faculty",
      "target_sections": ["<section_uuid>"],
      "quarter": "<grading_period_uuid>",
      "time_limit_minutes": 60,
      "deadline": "2026-08-25T23:59:00Z"
  }
  Permission check: create_academic_assessment (faculty only)

GUIDANCE creates wellness assessment:
  POST /api/v1/assessments/
  {
      "title": "Emotional Wellness Assessment",
      "assessment_type": "wellness",
      "creator_role": "guidance",
      ...
  }
  Permission check: create_wellness_assessment (guidance only)

Assessment is deployed:
  POST /api/v1/assessments/{id}/deploy/
    → Sets is_published=True, published_at=now
    → DOMAIN EVENT: ASSESSMENT_DEPLOYED
       Recipients: Target students + their parents

Student takes assessment:
  POST /api/v1/assessments/{id}/take/
  { "answers": { "<question_uuid>": "x=5", ... } }
    → System auto-grades MC/true_false
    → Stores results
```

### G.6 Risk Alert and Intervention Workflow

> **\[UNAPPROVED — See §I for details. This workflow describes the
> data flow, NOT the computation parameters.\]**

```
1. Risk computation triggered
   (manual by admin/counselor, or scheduled)

2. System collects features per student:
   - Grades (average, trend)
   - Attendance (rates, counts)
   - Behavioral notes (counts by type)
   - Consultation records (active count)
   [UNAPPROVED — exact features and weights TBD]

3. Decision Tree classifies student into risk level
   [UNAPPROVED — model parameters, thresholds TBD]

4. RiskAlert created for students not classified as "low"

5. DOMAIN EVENT: RISK_ALERT_GENERATED
   → Recipients: Guidance Counselor(s)
   → If HIGH risk: also Faculty Adviser + Parent

6. Guidance Counselor reviews alert:
   - Can acknowledge (status → under_monitoring)
   - Can create Intervention plan (status → escalated)
   - Can dismiss (status → resolved)

7. Intervention plan created:
   - Steps: [Specific steps are OPEN — §L-OQ4]
   - Progress notes tracked
   - Plan completion closes alert
```

### G.7 Notification Domain Events

> **Notifications are triggered ONLY by these explicit domain events,
> NOT by arbitrary database changes.**

| Event ID | Event Name | Trigger | Recipients | Priority |
|----------|-----------|---------|------------|----------|
| `EVT-01` | GRADE\_POSTED | Grade status changes to "finalized" | Student, Parent (of student) | normal |
| `EVT-02` | ATTENDANCE\_THRESHOLD | Student absence count exceeds configurable threshold | Parent (of student) | high |
| `EVT-03` | BEHAVIORAL\_WARNING | Faculty records note\_type="warning" | Guidance Counselor | normal |
| `EVT-04` | BEHAVIORAL\_INCIDENT | Faculty records note\_type="incident" | Guidance Counselor, Faculty Adviser | high |
| `EVT-05` | ASSESSMENT\_DEPLOYED | Assessment published to students | Target students, Parents of target students | normal |
| `EVT-06` | ASSESSMENT\_COMPLETED | Student submits assessment | Assessment creator (Faculty/Guidance) | normal |
| `EVT-07` | RISK\_ALERT\_GENERATED | Risk computation flags a student | Guidance Counselor; if high: Adviser + Parent | high |
| `EVT-08` | INTERVENTION\_UPDATE | Intervention step status changes | Assigned Guidance Counselor | normal |
| `EVT-09` | ANNOUNCEMENT\_PUBLISHED | Admin publishes announcement | Target roles (per announcement config) | normal |
| `EVT-10` | CONSULTATION\_SCHEDULED | Next session date set on consultation | Student, Parent (of student) | normal |

> **\[PROPOSED\]** — This event list must be confirmed. Adding or
> removing events is a design decision. See §L.

### G.8 Data Import Workflow

```
Faculty or Admin initiates import:
  POST /api/v1/data-import/jobs/
  Content-Type: multipart/form-data
  file: <csv/xlsx>
  import_type: "grades" | "attendance" | "students"
  sheet: <worksheet name or 1-based position>   # optional, xlsx only

  - XLSX: naming a worksheet selects it; without it the workbook must hold
    exactly one visible worksheet. Sheets are never merged or guessed at.
  - Faculty can import: grades (for own subjects), attendance (for advisory)
  - Admin can import: grades, attendance, students, guidance_records
  [CONFIRMED per FR-012, FR-013; Admin scope per FR-037]

  File keys are the school's own, not database UUIDs (FR-037):
  - attendance row: student_id, section (name or UUID), date, status
  - grade row: student_id, grading_period (name e.g. "Term 2", or UUID),
    score, and EITHER subject_assignment (UUID) OR section + subject_code
  - a value is resolved within the current academic year; a value that
    matches no record, or more than one, fails the row (never guessed)
  - re-uploading an existing record updates it in place: attendance by
    (student, date), grades by (student, subject_assignment, grading_period)
    returning to draft, guidance by (student, session_date, session_time).
    A `finalized` grade is locked and rejected (FINALIZED_GRADE_LOCKED)

System:
  1. Creates ImportJob (status=pending)
  2. Parses and validates each row against expected schema
  3. Captures validation errors per row (ImportRecord)
  4. Processes the rows: at or below IMPORT_SYNC_ROW_LIMIT (200) inside the
     request, so the response already carries the finished job; above it in a
     bounded worker pool in the same process, and the response returns the job
     as pending/processing for the client to poll
  5. Status → completed | failed | partial
  6. Returns the job with per-row error details (immediately for a small file,
     on the next poll for a large one)
  7. Valid records written to Grade/Attendance/Student models
  8. AuditLog entry created
[No Celery or Redis for v1: a large file is finished by a worker thread, not a
request — see §L-OQ9. Maximum 20,000 rows and 10 MB per file; re-uploading is
safe because importers update an existing record in place.]
```

---

## H. API Boundaries

> **\[PROPOSED\]** — Endpoint structure is a proposal. Confirmation
> needed before implementation.

### H.1 URL Structure

```
/api/v1/
├── auth/
│   ├── login/
│   ├── logout/
│   ├── register/                   # Students & parents
│   ├── token/refresh/
│   ├── password/change/
│   └── password/reset/
│
├── accounts/
│   ├── users/                      # Admin: CRUD all users
│   ├── users/{id}/
│   ├── students/                   # Admin: CRUD students
│   ├── parents/                    # Admin: CRUD parents
│   ├── faculty/                    # Admin: CRUD faculty
│   ├── guidance/                   # Admin: CRUD guidance
│   └── me/                         # Any user: own profile
│
├── academics/
│   ├── academic-years/
│   ├── grade-levels/
│   ├── sections/
│   ├── subjects/
│   ├── subject-assignments/
│   ├── schedules/
│   ├── grading-periods/
│   ├── enrollments/
│   └── grades/
│       ├── /                       # GET, POST
│       ├── {id}/                   # GET, PUT, PATCH
│       ├── encode/                 # POST: single grade
│       └── batch-import/           # POST: CSV/Excel
│
├── attendance/
│   ├── records/
│   │   ├── /                       # GET, POST
│   │   └── batch-import/           # POST: CSV/Excel
│   └── summary/                    # GET: per student
│
├── assessments/
│   ├── /                       # GET, POST
│   ├── {id}/                   # GET, PUT, PATCH
│   ├── {id}/questions/         # GET, POST
│   ├── {id}/deploy/            # POST: publish
│   ├── {id}/results/           # GET: view results
│   └── {id}/take/              # POST: student submits
│
├── guidance/
│   ├── behavioral-notes/
│   │   ├── /                       # GET, POST
│   │   └── {id}/                   # GET, PUT, PATCH, DELETE
│   ├── consultations/
│   │   ├── /                       # GET, POST
│   │   └── {id}/                   # GET, PUT, PATCH
│   ├── risk-alerts/
│   │   ├── /                       # GET: list
│   │   ├── {id}/                   # GET: detail
│   │   └── {id}/acknowledge/       # POST
│   ├── interventions/
│   │   ├── /                       # GET, POST
│   │   ├── {id}/                   # GET, PUT, PATCH
│   │   ├── {id}/steps/             # GET, POST
│   │   ├── {id}/notes/             # GET, POST
│   │   └── {id}/complete/          # POST
│   └── reports/
│       └── student/{id}/           # GET
│
├── analytics/
│   ├── risk-scores/
│   │   ├── /                       # GET
│   │   ├── compute/                # POST: trigger
│   │   └── student/{id}/           # GET
│   ├── recommendations/
│   │   └── student/{id}/           # GET
│   ├── dashboard/                  # GET: aggregated
│   └── reports/
│       ├── subject-performance/    # GET
│       ├── class-summary/          # GET
│       └── school-wide/            # GET
│
├── cms/
│   ├── announcements/
│   │   ├── /                       # GET, POST
│   │   └── {id}/                   # GET, PUT, PATCH, DELETE
│   ├── resources/
│   │   ├── /                       # GET, POST
│   │   └── {id}/                   # GET, PUT, PATCH, DELETE
│   └── settings/
│       ├── /                       # GET
│       └── {key}/                  # GET, PUT
│
├── data-import/
│   ├── jobs/                       # GET, POST (Faculty + Admin)
│   └── jobs/{id}/                  # GET
│
├── notifications/
│   ├── /                           # GET
│   ├── {id}/read/                  # POST
│   ├── read-all/                   # POST
│   └── preferences/                # GET, PUT
│
└── audit/
    └── logs/                       # GET (admin only)
```

### H.2 Key Endpoint Examples

**Encode a single grade:**
```
POST /api/v1/academics/grades/encode/
Authorization: Bearer <token>

{
    "student": "<uuid>",
    "subject_assignment": "<uuid>",
    "grading_period": "<uuid>",
    "score": 85.5,
    "remarks": ""
}

→ 201 Created
→ Domain event: GRADE_POSTED (if status becomes finalized)
```

**Batch import grades:**
```
POST /api/v1/academics/grades/batch-import/
Authorization: Bearer <token>
Content-Type: multipart/form-data

file: <csv or xlsx>
subject_assignment: <uuid>
grading_period: <uuid>

→ 200 OK
{
    "job_id": "<uuid>",
    "status": "completed",
    "total_rows": 35,
    "processed_rows": 33,
    "error_rows": 2,
    "message": "Import complete. 33 rows processed, 2 errors.",
    "errors": [
        {"row": 12, "error": "Student not found: STU-9999"},
        {"row": 28, "error": "Invalid score: 150 (max 100)"}
    ]
}
[201 Created with the job. Small files (up to 200 rows) are already
finished, so `status` is terminal. A larger file returns
"status": "pending"|"processing" and is finished by a worker afterwards;
poll GET /api/v1/data-import/jobs/{id}/ until the status is terminal.]
```

**Record a behavioral incident:**
```
POST /api/v1/guidance/behavioral-notes/
Authorization: Bearer <token>

{
    "student": "<uuid>",
    "note_type": "incident",
    "note_text": "Student involved in physical altercation.",
    "date_recorded": "2026-08-19"
}

→ 201 Created
→ Backend creates Notification for guidance counselor(s)
→ Backend creates AuditLog entry
```

**Trigger risk computation:**
```
POST /api/v1/analytics/risk-scores/compute/
Authorization: Bearer <token>

{
    "academic_year": "<uuid>",
    "grading_period": "<uuid>"
}

→ 200 OK
{
    "message": "Risk computation complete",
    "students_flagged": 12
}
[ASSUMPTION — synchronous for v1; see §L-OQ9]
```

**Error response format:**
```json
{
    "success": false,
    "error": {
        "code": "VALIDATION_ERROR",
        "message": "Invalid input data.",
        "details": {
            "score": ["Score must be between 0 and 100."],
            "student": ["This student is not enrolled in the specified section."]
        }
    }
}
```

### H.3 HTTP Status Codes

| Code | Usage |
|------|-------|
| 200 | Successful GET, PUT, PATCH |
| 201 | Successful POST (creation) |
| 204 | Successful DELETE |
| 400 | Validation error / bad request |
| 401 | Authentication required / invalid token |
| 403 | Authorized but not permitted (RBAC denied) |
| 404 | Resource not found |
| 409 | Conflict (e.g., duplicate enrollment) |
| 413 | File too large |
| 429 | Rate limit exceeded |
| 500 | Internal server error |

---

## I. AI/ML Boundary

> **Everything in this section is \[UNAPPROVED\] unless marked otherwise.
> The documents confirm that Decision Tree and Collaborative Filtering
> are required. The specific computation parameters, weights, thresholds,
> and feature definitions are NOT approved and MUST NOT be implemented
> until confirmed.**

### I.1 Confirmed Requirements

| ID | Requirement | Source |
|----|-------------|--------|
| FR-030 | The system shall generate AI-driven at-risk student alerts using a Decision Tree algorithm based on academic performance patterns. | Final\_REvision FR-030 |
| FR-039 | The system shall produce AI-driven recommendations using Collaborative Filtering. | Final\_REvision FR-039 |
| FR-040 | The system shall produce AI-driven recommendations using Decision Tree algorithms. | Final\_REvision FR-040 |
| NFR-007 | The Decision Tree shall produce consistent outputs given the same input data. | Final\_REvision NFR-007 |

### I.2 What the Panel Actually Asked For (Correction #2)

The panel said: **"Computation of Risk and prioritization — need
explicit process/formula."**

This means:
- The risk computation must be **documented and explainable**.
- The panel wants to **see** how risk is calculated.
- The panel did **NOT** approve specific weights, thresholds, or features.

### I.3 UNAPPROVED Illustrative Draft (DO NOT IMPLEMENT)

> The following is an **illustrative example only**. It is NOT an
> approved requirement. It shows the *kind* of thing that needs to be
> designed, not the actual implementation.

```
ILLUSTRATIVE ONLY — NOT APPROVED

A possible risk scoring approach:

risk_score = (w1 × grade_factor) +
             (w2 × attendance_factor) +
             (w3 × behavioral_factor) +
             (w4 × consultation_factor)

Possible features (TBD):
  grade_factor     = function of average grades and grade trend
  attendance_factor = function of absence rate and late count
  behavioral_factor = function of behavioral note counts by type
  consultation_factor = function of active consultation records

Possible thresholds (TBD):
  risk_score < X  → low
  risk_score X-Y  → moderate
  risk_score > Y  → high

The actual features, weights, thresholds, and formula MUST be
defined and approved before implementation.
```

### I.4 What Must Be Decided Before Implementation

| Decision | Status | Impact |
|----------|--------|--------|
| Which features to include in risk scoring | **UNAPPROVED** | Affects model training, data collection |
| Feature weights or tree structure | **UNAPPROVED** | Affects risk classification output |
| Risk level thresholds (low/moderate/high boundaries) | **UNAPPROVED** | Affects who gets flagged |
| Training data requirements | **UNAPPROVED** | Affects when ML model can be used |
| Fallback when insufficient data for ML | **UNAPPROVED** | Affects initial deployment |
| Risk computation trigger schedule | **UNAPPROVED** | Affects system load |

### I.5 Collaborative Filtering

| Decision | Status |
|----------|--------|
| Similarity metric | **UNAPPROVED** |
| Minimum data threshold | **UNAPPROVED** |
| Recommendation types and sources | **UNAPPROVED** |

### I.6 Chatbot Boundary

```
DEFERRED — No chatbot code in initial backend.

Future integration boundary:
  - POST /api/v1/guidance/risk-alerts/ (for chatbot escalation)
  - POST /api/v1/notifications/ (for chatbot-triggered alerts)
  - Chat conversation model (not implemented)

Technologies deferred: Botpress, Rasa, Gemini API
(Panel corrections #4, #12)
```

---

## J. Security and Privacy Requirements

### J.1 Confirmed Requirements (from Final\_REvision)

| ID | Requirement | Source |
|----|-------------|--------|
| NFR-008 | All user passwords shall be stored securely using one-way hashing (not reversible encryption). | Final\_REvision NFR-008 |
| NFR-009 | Students shall only view and modify their own data. | Final\_REvision NFR-009 |
| NFR-010 | Admins shall view student data in aggregated/anonymized form unless consent is given. | Final\_REvision NFR-010 |
| NFR-011 | Role-based access control shall enforce role-specific access. | Final\_REvision NFR-011 |
| SEC-PRIVACY | System shall comply with the Data Privacy Act of 2012 (RA 10173). | Final\_REvision §Scope, §Purpose |
| SEC-PRIVACY-ACCEPT | Users must accept a privacy policy upon registration. | Panel correction #11 |
| SEC-CHAT-PRIVACY | Chatbot conversations must be private (deferred with chatbot). | Panel correction #4 |

### J.2 Proposed Security Implementation

> **\[PROPOSED\]** — These are implementation proposals, not confirmed
> requirements. The documents specify *what* (passwords stored securely, RBAC
> enforced) but not *how* (specific algorithms, token lifetimes).

| Control | Proposal | Notes |
|---------|----------|-------|
| Password storage | Use Django's password hashing framework (`make_password` / `set_password`). Passwords are hashed using a **one-way, salted algorithm** (PBKDF2 by default, configurable to bcrypt/argon2). This is **not** reversible encryption — the source document's use of "encrypted passwords" (NFR-008) is satisfied by secure one-way hashing. | \[CONFIRMED\] NFR-008 requires password protection; Django's hashing framework satisfies this. |
| Authentication | JWT via `djangorestframework-simplejwt` | \[PROPOSED\] Document says "JWT" (§2, SAD text) |
| Token lifetimes | Access: TBD; Refresh: TBD | \[PROPOSED — NOT in documents, requires decision\] |
| RBAC | Custom DRF permission classes checking `User.role` | \[PROPOSED\] NFR-011 requires RBAC; exact implementation TBD |
| HTTPS/TLS | Nginx reverse proxy with TLS certificates | \[PROPOSED\] SAD mentions HTTPS; production deployment detail |
| Input validation | DRF serializers with field-level validation | \[PROPOSED\] |
| CORS | `django-cors-headers`, whitelist frontend origin only | \[PROPOSED\] |
| Audit trail | Middleware + model signals → AuditLog | \[CONFIRMED — FR-038\] |
| Rate limiting | On auth endpoints | \[PROPOSED — not in documents\] |
| File upload validation | Validate file type, size, and content before processing | \[PROPOSED\] |

### J.3 Data Access Rules

| Rule | Source |
|------|--------|
| Students only access their own data. | NFR-009 |
| Parents only access their linked child's data. | Derived from FR-024/025/026 |
| Faculty access their advisory class and assigned subject students. | Derived from FR-007–FR-016 |
| Guidance counselors access all student data for their caseload. | Derived from Objective 4 |
| Admins see aggregated/anonymized data unless explicit consent given. | NFR-010 |
| Behavioral notes are restricted: students/parents see only their own; faculty see their advisory class; guidance sees all. | Panel correction #5; privacy requirement |
| Consultation records are restricted to the assigned counselor and the student/parent. | Privacy requirement |

### J.4 Privacy Policy Requirement

**\[CONFIRMED — Panel correction #11\]**

- A privacy policy must be presented during registration.
- User must explicitly accept (`privacy_policy_accepted=True`) before
  account is activated.
- The privacy policy content is a school-provided document, not a
  backend implementation detail, but the backend enforces the acceptance
  flag.

---

## K. Explicit Assumptions

These are assumptions embedded in the specification that must be
confirmed before implementation.

| ID | Assumption | Section |
|----|-----------|---------|
| ASM-01 | A single PostgreSQL database with Django app-namespaced tables is acceptable (rather than 5 separate databases as shown in the SAD). | §C.2 |
| ASM-02 | The `User` model uses a single table with a `role` discriminator field, not separate tables per role. | §D.2 |
| ASM-03 | The `Assessment` model is shared between academic and wellness types, differentiated by `creator_role` and `assessment_type` fields. | §D.3 |
| ASM-04 | Data imports add no background task queue for v1 (no Celery/Redis). Files above 200 rows are finished by a bounded in-process worker pool and polled; small files still finish inside the request. | §C.2, §G.8 |
| ASM-05 | Attendance absence threshold for parent notification is configurable via `SystemSetting`. | §G.3 |
| ASM-06 | The `language_preference` field on User is a simple char field; full i18n is out of scope for v1. | §L-OQ6 |
| ASM-07 | JWT is the authentication mechanism. The documents mention JWT in the SAD description. | §J.2 |
| ASM-08 | Profile photos and uploaded files are stored on the server filesystem (or Supabase storage if available). No external CDN is required for v1. | §L-OQ10 |
| ASM-09 | Email notifications use a transactional email service. The specific provider is a deployment decision. | §G.7 |
| ASM-10 | The frontend React application is a separate project; this specification covers only the Django backend API. | §A.1 |

---

## L. Decisions Still Requiring Approval

| ID | Decision | Description | Blocks |
|----|---------|-------------|--------|
| **OQ-1** | Risk computation formula | Exact features, weights, thresholds, and Decision Tree parameters. The v1.0 draft proposed 40/30/20/10 weights with <30/30-69/≥70 thresholds. **These are NOT approved.** The panel wants the formula documented, not these specific values. | Risk scoring implementation, RiskAlert model fields |
| **OQ-2** | Assessment timing | Are assessments tied to quarters? Is there a fixed cadence? The documents and panel notes do not specify. The backend supports optional `quarter` linkage on Assessment. | Assessment scheduling UX |
| **OQ-3** | Assessment delivery context | Take home or at school? This is a school policy question. The backend provides the API; delivery context is a frontend/operational concern. | Nothing (backend) |
| **OQ-4** | Intervention escalation steps | Panel #9 asks "if high risk, what intervention is done first?" The documents describe InterventionStep generically but do not specify the ordered steps. Need school-specific steps. | Intervention workflow |
| **OQ-5** | Psychometrician role | Panel #13 mentions a psychometrician. Is this a 6th role, or a specialization of Guidance? | Role model, permission matrix |
| **OQ-6** | Language barrier checkbox | Panel #14 mentions this. What language(s)? Is this a v1 requirement or future? | User model fields |
| **OQ-7** | Push notifications | Panel #16 asks about feasibility. Web Push API is possible but adds complexity. Is in-app + email sufficient for v1? | Notification service |
| **OQ-8** | CMS: Strapi vs. native Django | The SAD references Strapi. The spec proposes native Django CMS. Which is approved? | CMS architecture |
| **OQ-9** | ~~Synchronous vs. async processing~~ | **DECIDED: Synchronous for v1.** No Celery or Redis. Can be revisited for v2 if performance requires it. | Resolved |
| **OQ-10** | File storage backend | Local filesystem, Supabase Storage, or cloud storage? | File handling implementation |
| **OQ-11** | Supabase hosting | PostgreSQL is confirmed. Supabase is the preferred hosting platform. Is this confirmed, or self-hosted PostgreSQL? | Deployment architecture |
| **OQ-12** | Notification email provider | What transactional email service? (e.g., SendGrid, Mailgun, SMTP via school server) | Email notification implementation |

---

## Appendix: Document Traceability

| Source Document | Sections Used | Key Content |
|----------------|--------------|-------------|
| Final\_REvision.pdf | Chapter 1 (Introduction, Objectives, Scope), Chapter 3 (DFDs, Functional Requirements, Non-Functional Requirements, UI Designs, Testing) | System purpose, all FR/NFR IDs, UI wireframes, test cases |
| commentary-notes.pdf | Both pages | All 16 panel corrections |
| SAD\_Diagram.png | Architecture diagram | System layers, component names, data flow structure |

---

*End of Backend Specification v2.0*

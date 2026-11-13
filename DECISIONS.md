# DECISIONS.md — AEGIS safety, Gemini and recommendation workstream

**Scope.** The work that added the role-aware Gemini assistant, the two-layer
sensitive-message detection, the flag workflow with escalation, the student
notice, the assessment review gate, the binary at-risk model and the Gemini
explanations for recommendations.

**Status.** Implemented, migrated, tested. Nothing in this workstream is
committed — the working tree holds every change.

---

## 1. Role vocabulary

The brief asked for `guidance_counselor`. The existing codebase uses
`"guidance"` everywhere: `User.Role.GUIDANCE`, `ALLOWED_INTENTS_BY_ROLE`,
the permission classes and every seed script.

**Decision:** keep `"guidance"` as the canonical role value. Adding a second
spelling would mean two role checks in the same request path, and the two
would drift. The mapping is:

| Brief | Code | Notes |
|---|---|---|
| `student` | `student` | unchanged |
| `faculty` | `faculty` | unchanged |
| `guidance_counselor` | `guidance` | renamed to match the existing code |
| `admin` | `admin` | unchanged |

Every place that compares a role literally (`routing.is_guidance_or_admin`,
`views._visible_flags`, `views.FlagActionView`) uses `"guidance"`.

## 2. Gemini augments; it never overrides

The deterministic layer in `apps/chatbot/policies.py` and
`apps/chatbot/service.py` was already the authority for intent, role policy,
data scope and the fallback reply. It stays that way.

| Decision | Where |
|---|---|
| Gemini may rewrite a reply for a **non-sensitive** message | `pipeline.process_message` |
| Gemini may **raise** a severity | `detection.detect` (union of severities) |
| Gemini may **not** lower a severity | `detection.detect` — the maximum wins |
| Gemini may **not** decide intent, urgency or routing | `pipeline.process_message` |
| A sensitive message is answered deterministically | `pipeline.process_message` |

**Why:** a model that can lower a severity can talk the application out of
routing a crisis message. The union rule is enforced in
`detection.detect` and covered by `LayerTwoTest.test_model_cannot_lower_a_layer_one_severity`.

## 3. Two detection layers

| Layer | What it is | When it runs |
|---|---|---|
| 1 | `KeywordTerm` rows (database) plus the built-in `policies` patterns | Always |
| 2 | Gemini classification | When `GEMINI_API_KEY` is set and the call succeeds |

The combination rule is **union of categories, maximum severity**:

```
severity   = max(layer1.severity, layer2.severity)
categories = layer1.categories | layer2.categories
sensitive  = layer1.sensitive or layer2.sensitive
```

**Failure behaviour.** If Layer 2 does not run — no key, rate limited, 5xx,
invalid JSON — Layer 1's answer stays in force and the message is flagged
`manual_review=True`. The screen is never skipped silently: a manual-review
flag is a visible work item, not a hole.

**Why not fail closed (treat every message as sensitive)?** A channel that
pages a counselor about every message is one they learn to ignore. Layer 1 is
strong enough to carry the load on its own; Layer 2 only adds recall.

**Model configuration is environment-only.** `GEMINI_API_KEY` is read from the
environment and never stored. `GEMINI_MODEL` defaults to `gemini-2.5-flash`.

## 4. What is sent to Gemini, and what is not
| Call | Sent | Never sent |
|---|---|---|
| Message classification | the message text | name, student number, email, role, any record |
| Assessment drafting | topic, question type, count | student names, rosters, grades |
| Intervention suggestions | severity, category vocabulary | the message text, the student |
| Recommendation reasons | item title/type/topic, need types | student name, id, grade average, attendance |

The classification call is the only one that carries free text a student
wrote, and it carries nothing else. `apps/chatbot/gemini_client.py` cannot
enforce that by itself — it cannot know what a string means — so each caller
documents its payload and a test asserts it. See
`apps/assessments/tests_review.py::GeminiDraftFailureTest::test_gemini_receives_only_the_topic`.

**Central client.** Every Gemini call goes through
`apps/chatbot/gemini_client.py`: one model name, one retry policy, one JSON
parser, one status endpoint. Retries are 3 attempts with exponential backoff
and jitter; 429 and 5xx are retryable; a rate-limited call raises
`GeminiRateLimited` so a caller can degrade deliberately instead of guessing.

**A call is bounded.** Two limits, both settings:
`GEMINI_TIMEOUT_SECONDS` (default 15) is the per-request HTTP timeout, and
`GEMINI_DEADLINE_SECONDS` (default 30) is the total budget for one call
including retries. Past the deadline the client stops starting new attempts
and the caller degrades.

**Why it matters, measured:** with the real API, a request that was going to
fail returned `503` after 85 seconds. Without the timeout, one stalled call
held a student's chat open for a minute and a half while Layer 1 — which
already had the answer — waited.

**An exhausted quota is not retried on the same key.** The API answers a burst
of requests and an exhausted plan with `RESOURCE_EXHAUSTED`. Only the first is
worth retrying; the second ("you exceeded your current quota, please check
your plan and billing details") would make every chat wait three times longer
before the deterministic layer answers.

**Fallback keys.** The quota is per key, so a second key is a second budget.
`GEMINI_API_KEY` is the primary and `GEMINI_API_KEYS` holds the fallbacks. The
client moves to the next key when one is rate limited, and gives up on a key
whose quota is spent — it will not come back within a deployment's lifetime,
and re-trying it on every message would add a wasted round trip to every
chat. A key that was merely rate limited is moved past for that call and can
be used again later.

A key is never logged: log lines carry `key_slot=2`, the position in the
list. `status()` reports how many keys are configured and how many are spent,
never the keys themselves.

**Fallback models.** A model can be *saturated* — `503 — This model is
currently experiencing high demand`, or `504 DEADLINE_EXCEEDED` — while the
account is perfectly healthy. That is a reason to try a different model, not
a different key, so `GEMINI_MODEL_FALLBACKS` rotates independently of the
keys. A model that works stays selected, so a saturated primary is paid for
once rather than on every message.

The school should approve the fallback model list as well: it decides which
models may see student text.

**The failure is visible.** `gemini_client.status()` reports the reason for
the last failed call, and the administrator console shows it, so "no key",
"quota gone" and "the API is down" are three different facts rather than one
grey badge.

**The test suite never calls Gemini.** `config/settings/test.py` blanks the
key. A key in `backend/.env` must not turn the tests into network calls: they
would be slow, flaky, and would spend the school's quota — which is exactly
what happened before this line existed.

## 5. Routing

| Severity | Recipients | Faculty notice carries |
|---|---|---|
| critical | guidance + admin + the student's faculty | no content, no identity |
| high | guidance + the student's faculty | no content, no identity |
| medium | guidance only | — |
| low | stored in the inbox, no notification | — |

**The faculty notice is content-blind.** The notification text and the
`FacultyFlagSerializer` payload contain severity, status and timestamps only —
no student name, no message, no reply, no summary, no categories. This is
enforced by two different serializers rather than one serializer with optional
fields, so a faculty screen cannot render content the server chose not to send.

Asserted in `apps/chatbot/tests_safety.py`:
`test_faculty_notice_carries_no_content` and
`test_faculty_feed_payload_has_no_content`.

**Faculty recipients are read-only.** Guidance and admin acknowledge, note,
resolve and mark false positives; a faculty recipient can read only their own
flags.

**Audit trail.** `FlagAction` is the append-only record of every action on a
flag — who acknowledged, what note was left, when it escalated — with the
actor and the timestamp. It is a case file, not the school-wide `AuditLog`
table: a case note is private to Guidance and must not land in a log that
every administrator can browse.

## 6. Acknowledgment timer

The timer is **data, not a daemon**.

* `Flag.escalation_due_at` is set at creation from the
  `chatbot.acknowledgment_timer_minutes` setting (default 15).
* `routing.escalate_stale_flags()` escalates open, unacknowledged flags past
  their due time and notifies administrators.
* It is called from the guidance inbox, the administrator dashboard, the
  explicit escalate endpoint and `manage.py escalate_stale_flags`.

**Why lazy escalation?** The repository has no Celery beat. A timer that only
fires when somebody opens a page is still a timer with teeth in every
deployment that has a human looking at the dashboard, and it needs no new
infrastructure. A deployment that needs a hard guarantee must schedule
`manage.py escalate_stale_flags` — that is stated in the setup notes, not
implied.

Escalation is idempotent: `escalated_at` prevents a second notice.

## 7. Student notice and agreement

* The notice text and its version live in `SystemSetting`
  (`chatbot.notice_text`, `chatbot.notice_version`), so an administrator can
  change them without a deploy.
* A student must accept the current version before `POST /chatbot/message/`
  will answer. The endpoint answers **HTTP 428** with the notice, and the
  panel shows it with the composer disabled.
* `AgreementAcceptance` records `(user, notice_version, accepted_at, ip)`.
  Changing `chatbot.notice_version` makes every student unaccepted again —
  which is the point.
* The same acceptance is collected at sign-up: the registration request carries
  `notice_accepted` and `notice_version`, and the server refuses a request
  that accepted a stale version.

**Why 428 and not 403?** 428 Precondition Required says "this request is
conditional on something that is not yet true", which is exactly the state.
403 would imply the student is forbidden from asking, which is not true.

## 8. Assessment review gate

An assistant-written assessment must be read by a human before it reaches a
student.

* Generated assessments are created with `ai_generated=True` and
  `review_status="pending"`.
* `Assessment.clean()` raises when an unapproved AI draft is published, so the
  rule lives on the model and not only in the view.
* `POST /assessments/assessments/{id}/deploy/` refuses an unapproved draft
  with 400.
* `POST /assessments/assessments/{id}/review/` records `approved` or
  `changes_requested` with the reviewer, the time and a note.
* Manually created assessments default to `review_status="not_required"`, so
  existing assessments and existing tests are unaffected.

**Why a model-level rule and not only an endpoint check?** A second code path
that sets `is_published=True` would otherwise walk straight around an
endpoint-only gate. The model check is the invariant; the endpoint returns a
readable message for it.

## 9. The binary at-risk model

The existing three-class scorer (`ai_engine/risk_scorer.py`, artifact version
`"v1"`) predicts low/moderate/high. The brief asked for a binary at-risk
model, so it was **added alongside** rather than replacing it:
`ai_engine/at_risk.py`, artifact version `at_risk_v1`.

* Features: `attendance_rate`, `current_term_grade_average`,
  `weak_subject_count`, `grade_trend`.
* The training label is a **documented rubric** (`at_risk.rule_label`), not
  ground truth. Accuracy against those labels is circular and the artifact
  metadata says so.
* Training refuses fewer than 20 usable rows and refuses single-class data
  rather than producing a confident model from nothing.
* The prediction carries the decision path as named factors, so a counselor
  can be told *why* a student was flagged.
* Alerts are `RiskAlert` rows with `source="decision_tree"`; a second run
  does not stack a second alert while one is still active.

The two model versions coexist. `RiskModelArtifact.version` distinguishes
them, and `RiskScore.model_version` records which one produced a score.

## 10. Recommendation explanations

`ai_engine/recommender.py` keeps the item-item cosine CF and the content-based
fallback unchanged. Gemini was added as a **wording** layer:
`recommender.explain_recommendations()` asks for one sentence per item and
falls back to the deterministic reason ("Similar to items this student
interacted with" / "Matched to an identified academic need") when the model
is unavailable or returns nothing usable.

Every recommendation therefore has a reason. A recommendation without a
stated reason is one the student cannot act on.

## 11. The false-positive feedback loop

A flag marked as a false positive is the only evidence the school has that a
screening term cries wolf. If that feedback stops at the flag, the term stays
active and the next counselor gets the same false alarm.

**Decision:** the administrator console lists the newest false positives with
the note the counselor left, next to the term table. The action stays manual
— an administrator reads the note and deactivates the term. Nothing is
retrained automatically, because an automatic change to what screens a child
is not something a keyword should decide on its own.

The listing does not repeat the message. The console is an oversight surface;
the conversation stays in the Guidance inbox.

## 12. New tables

`chatbot`: `KeywordTerm`, `ChatMessage`, `Flag`, `FlagRecipient`, `FlagAction`,
`AgreementAcceptance`.
`accounts`: `RegistrationRequest.notice_version`, `RegistrationRequest.notice_accepted_at`.
`assessments`: `Assessment.ai_generated`, `Assessment.review_status`,
`Assessment.reviewed_by`, `Assessment.reviewed_at`, `Assessment.review_note`.

`cms` gained no column. The chatbot settings live in the existing
`SystemSetting` table and are seeded by `cms/0005_seed_chatbot_settings`,
because `cms/0004` had already run before those settings were registered and
an administrator can only change a setting that has a row.

All other requested tables already existed in the repository (`users`,
`classes`, `class_enrollments`, `notifications`, `alerts`, `keyword_terms`,
`settings`, `audit_logs` under their existing names and apps) and were
extended rather than duplicated.

## 13. Placeholders

| Placeholder | Where | What is needed |
|---|---|---|
| `TODO: confirm the approved model name` | `config/settings/base.py`, `backend/.env.example` | **Partly resolved.** The technical answer is known: `gemini-2.5-flash` answers 404 for new API users ("no longer available to new users") and `gemini-3.8-flash` works, so the default is now `gemini-3.8-flash`. What is still needed is the *school's* approval of which model may receive student text — a policy decision, not a technical one. |
| `TODO: confirm production encryption at rest` | see §14 | **Done at the application layer.** The student free text is encrypted in the column with AES-SIV, the keys are in the environment, and a production deployment refuses to start without one. What is left is the *disk*: Postgres volume and backup encryption are the platform's decision and are still open. |
| `TODO: counsel review of the notice text` | `chatbot.notice_text` setting | The default notice text is written by the implementation, not by a counsellor or the school. |
| `TODO: agree the acknowledgement window` | `chatbot.acknowledgment_timer_minutes` (default 15) | The school may want a different window. **Now per severity**: `chatbot.acknowledgment_timer_minutes.critical` (and `.high`, `.medium`, `.low`) override the school-wide value when set; blank means use the school-wide one. |
| `TODO: retention period for chat messages and flags` | `chatbot.retention_days` (default 0) | **Implemented.** `manage.py purge_chatbot_data` applies the window; 0 means keep everything and the command refuses to run. Closed flags and their messages go; open flags never do. What is still needed is the school's decision on the number. |
| `TODO: severity-specific timers` | `routing.acknowledgment_minutes(severity)` | **Implemented** — see the row above. |
| `TODO: the API key's quota` | `backend/.env` | The key supplied for this work authenticates but its quota is exhausted ("You exceeded your current quota, please check your plan and billing details"). Four fallback keys were added and the client rotates between them, and a fallback model list covers a saturated model. The plan or billing still has to be fixed for the primary key. The administrator console says *why* the last call failed. |

## 14. Privacy and encryption — what is done, what is not

**Done: the student free text and the counseling narrative are encrypted in the
column.** These fields use `core.fields.EncryptedTextField` /
`EncryptedJSONField`, which store AES-SIV ciphertext and hand the application
plain text:

| Model | Field |
|---|---|
| `chatbot.ChatMessage` | `message`, `reply`, `detection_detail` |
| `chatbot.Flag` | `summary` |
| `chatbot.FlagAction` | `note` |
| `guidance.BehavioralNote` | `note_text` |
| `guidance.ConsultationRecord` | `session_notes`, `recommendations` |
| `guidance.InterventionStep` | `description` |
| `guidance.ProgressNote` | `note_text` |

The keys live in the environment (`FIELD_ENCRYPTION_KEYS`), never in the
database, and the first key encrypts while every key decrypts — so a rotation
is "add a key, deploy, drop the old one later".

Why AES-SIV and not AES-GCM: SIV is **deterministic**, so an equality lookup
on an encrypted column still works (`filter(chat_message__message=...)` is in
the codebase). A randomised mode would make those lookups impossible. The
cost is that two identical messages encrypt to identical ciphertexts, so a
reader with the database can count repeats — a smaller risk than a plaintext
dump, and stated here rather than discovered later.

**A production deployment cannot start without a key.** `production.py` sets
`FIELD_ENCRYPTION_REQUIRED = True`, and `apps/chatbot/checks` raises
`chatbot.E001` — an **error**, not a warning, because a deployment pipeline
that reads warnings still ships a plaintext deployment. The administrator
console shows whether encryption is on.

**One command reports the posture.** `manage.py security_posture` prints
whether field encryption is on, which columns are encrypted (read from the
live models), the acknowledgment window per severity, the retention window,
and the model status — without printing a key. `docs/SECURITY_POSTURE_RUNBOOK.md`
is the companion: the questions to ask the platform about the disk, the key,
access and backups, and what to do when something is wrong.

**Still open:**

1. **Disk-level encryption is a deployment decision.** The application
   encrypts the student text it knows about; the Postgres volume, its
   snapshots and its backups are the platform's business. The runbook lists
   the questions; it cannot answer them.
2. **Everything else in the database is unencrypted.** Grades, attendance, risk
   scores, structured concern categories and the announcement text are clear
   text. They are structured records, not narrative about a child, and
   encrypting them is a much larger change.
3. **The retention job exists but the window is unset** —
   `chatbot.retention_days` is 0, so nothing is deleted yet. The school has to
   decide the number. The posture command says so loudly, because "0" reads
   like a setting rather than a decision.
4. **Case notes are private, not encrypted to a different key.** They are
   encrypted at rest like everything else and hidden from non-guidance readers
   in the API, but a guidance reader sees them in plain text — which is the
   point of a case note.
5. **Log lines can carry message content.** The pipeline logs Gemini failures
   with an exception *type*, not the message, and the Django request log
   records the URL and status, not the body — so this is currently fine and
   would break if request bodies were ever logged.
6. **Third-party processing.** Gemini is a third party. The student notice
   says so in plain language, which is the mitigation available without a
   data-processing agreement. A school deploying this should add one.
7. **The API key is an environment variable.** It is not in the database and
   not in the frontend, and the frontend never sees it. It is still a
   long-lived shared secret; a deployment should rotate it and scope it. The
   key supplied for this work had **no quota left** — "you exceeded your
   current quota, please check your plan and billing details" — so four
   fallback keys were added and the client rotates between them. Until the
   plan is fixed, Layer 2 falls back to Layer 1 whenever every key is spent.
8. **Import validation does not send records to Gemini.** The import path
   validates CSV/XLSX rows and never calls the model, so no identifiable
   record reaches a third party from an import.
9. **The audit trail carries no free text.** `apps/audit/redact.py` is
   allowlist-driven and the chatbot and guidance models are not on it, so no
   message, flag, note or session note writes its content into `AuditLog`.
   That was checked before the encryption was built, because an audit log full
   of plaintext copies would have undone it.

## 15. What was deliberately not built

* No Celery/beat scheduler. The escalation timer is lazy and idempotent
  instead (§6).
* No second role vocabulary (§1).
* No student-facing "my flags" page. A student is told that Guidance was
  notified; the record stays with Guidance.
* No sentiment or emotion model. The layers are keyword screening and
  classification, and both are explainable.
* No model-based FAQ answers. Gemini rewrites an answer the deterministic
  layer already produced; it does not invent one.
* No vector store, embedding model or re-ranker. Retrieval is lexical and the
  corpus is the school's own documents (§17).
* No model status panel on the admin console. It named the model, the key and
  SDK, the fallback list, the two layers and the encryption posture on every
  visit — operator diagnostics, not a safety control.
  `GET /chatbot/admin/model-status/` and `manage.py security_posture` report the
  same thing, and a production deployment refuses to start without an
  encryption key (§14), so the console does not have to carry that warning to
  keep the failure safe.
* No automatic retuning from false positives (§11). A keyword does not get to
  decide what screens a child.

## 16. The default screening terms

The seeded Layer 1 terms are phrases wherever a word has an ordinary use in a
school sentence: "with a gun" rather than "gun", "abused at home" rather
than "abuse", "feeling depressed" rather than "depressed".

**Why:** PH12 established that a screening channel which fires on ordinary
language is one staff learn to ignore, and a real disclosure is then less
likely to be read. `chatbot/0003` retired the first, broader set of terms and
`DefaultTermPrecisionTest` pins the behaviour: a history project about gun
violence raises nothing, and "I am being abused at home" raises a high flag.

An administrator can still add a broad term — the table is theirs to edit.
This is a default, not a rule.

## 17. Answering from the school's own documents

The client reported that the chatbot is **not accurate**. There were two
separate causes, and both are fixed without a new dependency or a new service.

### 17.1 The deterministic layer had no sentence to say

`_deterministic_reply` (`apps/chatbot/service.py`) had no branch for a grade,
an attendance, a performance or a resource question. The facts were already
fetched — `handle_message` put `grade_summary` and `attendance_summary` into
`data` — and then no branch read them, so every one of those questions fell
through to one generic tail. With the key's quota spent, that tail was the
*only* answer a student could get.

The branches now read the facts they already had, and the tail names what the
assistant can do ("I can look up your grades, attendance and approved learning
resources") instead of pretending to answer. A parent's question about an
unresolved child still asks which child, and a late arrival still counts as a
day attended.

The attendance figures also reached the reply but not the panel: the detail
line read `present_count`/`late_count`/`absent_count` while the chatbot's own
summary sends `present_days`/`late_days`/`absent_days`, so it rendered three
dashes beside a correct sentence. Fixed to the names the endpoint sends, with a
test that would have caught it.

### 17.2 There was nothing to quote about the school itself

A question about a rule, a schedule or a procedure had no source at all: the
title lookup returned every approved item regardless of the question, and a
model asked the same question answers from what schools *in general* do, which
is not this school's policy. `apps/chatbot/retrieval.py` now answers those from
the school's own documents and names the document in the reply.

### 17.3 Why the retrieval is hand-written and lexical

* PostgreSQL full-text search is Postgres-only, and the suite runs on SQLite
  (`config/settings/test.py`). The path that decides what a student is told
  would be the one path the tests cannot exercise.
* pgvector needs a database extension and an embedding model, and the school's
  API key is out of quota. A feature that silently becomes "no retrieval" when
  a third-party quota runs out is not a safety improvement.

So the scorer is lexical: every query term is looked up with `icontains` (which
both databases support), then ranked in Python by term frequency, an
inverse-document-frequency weight over the candidate pool, and bonuses for a
term in the document's title and for the query appearing as a phrase. It
handles no synonyms and no paraphrase. That limit is written in the module as a
`shortcut:` note, not hidden.

**A weak match is refused, not shown.** A multi-word question must match two of
its words — or one word of the document's title — before a passage may be
quoted. One matched word out of several is the difference between an answer and
a plausible non-answer. When nothing matches, the reply says it does not have
an answer and names what it can do.

### 17.4 A record question never reaches retrieval

`KNOWLEDGE_INTENTS` (`apps/chatbot/service.py`) lists the intents retrieval may
answer, and a grade or an attendance intent is not in it. A passage is school
prose anyone with database access could have written; a grade is the student's
own record behind an authorization check. Letting the first stand in for the
second would trade a permission boundary for a search hit. The test
`RecordQuestionsBypassRetrievalTest` pins this with a document that is *about*
grades.

### 17.5 A grounded reply is not rewritten

The pipeline returns a grounded answer as it stands. It is a quotation of the
school's document with the document named; a paraphrase would put back the
drift retrieval exists to remove, and the citation — the part a student uses to
check the answer — is the first thing a rewrite drops. A sensitive reply is
deterministic for the same reason (already the case).

### 17.6 What the corpus may contain

`KnowledgeChunk.content` is stored in the clear, because retrieval has to
search it. So the corpus is school documents and only school documents:

* handbook and policy text an administrator enters in the admin console;
* published Strapi announcements and resources, pulled by
  `manage.py sync_knowledge` (idempotent by origin + source id; `--prune`
  deactivates a synced document whose source is gone, and never deletes one);
* approved, active `cms.LearningItem` records.

No student data. An administrator who pastes a student's name into a policy
document has published it, and the model docstring says so.

A document that has never been indexed holds no chunks and answers nothing,
which is why the admin console shows the chunk count on every row rather than
just the title.

### 17.7 What was not built

No embeddings, no vector store, no re-ranker, no query rewriting. The corpus is
tens of documents; a vector index earns its cost at a few thousand chunks. The
`shortcut:` note in `retrieval.py` records when to revisit it.

## 18. Test evidence

Backend, SQLite, `python manage.py test --settings=config.settings.test`. The
suite makes no network calls — `config/settings/test.py` blanks the key.

| Suite | Tests | What it covers |
|---|---|---|
| `core.tests_crypto` | 14 | the encryption round trip, determinism, key rotation, a malformed key refused, the status never leaking a key, and the deployment check refusing a production deployment without a key |
| `apps.guidance.tests_encryption` | 9 | the counseling narrative and the model rationale being ciphertext in the column and plain text in the application, and the posture command |
| `apps.chatbot.tests_safety` | 44 | Layer 1 and Layer 2, the union rule, the failure fallback, routing by severity, the content-blind faculty notice, the acknowledgment timer and its escalation, the per-severity window, the notice gate, the flag lifecycle, the administrator console, the false-positive feedback, the retention job, the key and model rotation, one notification per crisis, the precision of the shipped terms, and the free text being ciphertext in the column |
| `apps.assessments.tests_review` | 13 | the review gate at model, endpoint and review level; the deterministic fallback; the payload Gemini receives |
| `ai_engine.tests_at_risk` | 17 | the rubric, the refusal to train on thin or one-sided data, the decision path, the stored model round-trip, the duplicate-alert guard |
| `apps.chatbot` (whole app) | 194 | the above plus the pre-existing intent, urgency and policy tests, the deterministic answers for a grade, attendance, performance and resource question (`tests_accuracy`), and the retriever, grounded and refused answers, the record-bypass rule, the knowledge admin API and the sync command (`tests_retrieval`) |
| Whole backend | 2248 | everything above plus the pre-existing suite |

Frontend, `npm run typecheck && npm run lint && npm test`:

| Suite | Tests |
|---|---|
| `npm test` | 1018 in 75 files |

Two of those 1018 fail at `/app/admin/cms`, and they are not this work: a
concurrent, uncommitted rewrite of `AdminCmsPage.tsx` removed the text the two
route assertions look for (`/Content is authored in Strapi/i`). Every chatbot
and admin assertion in this work passes, and the count above includes the one
added test for the grounded-answer sources block.

The manual checklist for the parts no unit test can prove — a real Gemini
call, encryption at rest, retention and load — is in
[`docs/SAFETY_SETUP_AND_TEST_CHECKLIST.md`](docs/SAFETY_SETUP_AND_TEST_CHECKLIST.md).

**What the live API taught us.** The real model was exercised on this
machine, and four facts came out of it that no mocked test could have found:
`gemini-2.5-flash` is gone for new API users (404); `gemini-3.8-flash`,
`gemini-3.7-flash` and `gemini-3.6-flash` were saturated (503 / 504) while
`gemini-3.5-flash-lite` and `gemini-3.1-flash-lite` answered; a request that
was going to fail could hang for 85 seconds before the API answered; and the
first key's quota was spent. All four are now handled in the client (§4) and
recorded here so the next person does not rediscover them.

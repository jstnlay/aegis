# Safety, Gemini and recommendations — setup and test checklist

Everything in this document is for the workstream described in
[`DECISIONS.md`](../DECISIONS.md). It covers installing the new dependency,
configuring the model, migrating, seeding synthetic data, and the manual
checklist for the parts a unit test cannot prove.

---

## 1. Install the new dependency

```powershell
cd backend
.\.venv\Scripts\python.exe -m pip install -r requirements\base.txt
```

The only new package is `google-genai` (the current Google Gen AI SDK). It is
optional in the sense that the system runs without it — Layer 1 alone — but
`pip install` is required for Layer 2, assessment drafting and the
recommendation explanations.

## 2. Configure the model

Add to `backend/.env` (the file already exists; `.env.example` documents the
same keys):

```dotenv
GEMINI_API_KEY=your-key-here
GEMINI_API_KEYS=fallback-key-1,fallback-key-2
GEMINI_MODEL=gemini-3.8-flash
GEMINI_MODEL_FALLBACKS=gemini-3.5-flash-lite,gemini-3.1-flash-lite
GEMINI_TIMEOUT_SECONDS=15
GEMINI_DEADLINE_SECONDS=30
```

* `GEMINI_API_KEY` — the primary key. Environment-only: never stored in the
  database, never reaches the frontend.
* `GEMINI_API_KEYS` — fallback keys, comma- or whitespace-separated. The quota
  is per key, so a second key is a second budget. The client moves to the
  next key when one is rate limited or has spent its quota.
* `GEMINI_MODEL` — the model sent to the API. **`gemini-2.5-flash` no longer
  works**: the API answers `404 — This model ... is no longer available to new
  users` for it. `gemini-3.8-flash` is the current default. The school still
  has to approve which model may receive student text.
* `GEMINI_MODEL_FALLBACKS` — fallback models. A model can be *saturated*
  (`503 — This model is currently experiencing high demand`) while the account
  is perfectly healthy; that is a reason to try a different model, not a
  different key, so the two lists rotate independently. **The school should
  approve this list too** — it decides which models may see student text.
* `GEMINI_TIMEOUT_SECONDS` — per-request HTTP timeout (default 15). A student
  waiting on a chat must not wait on a stalled model call: Layer 1 already
  has the answer.
* `GEMINI_DEADLINE_SECONDS` — total budget for one call, retries included
  (default 30). Past it the client stops starting new attempts and the
  deterministic layer answers.

**How the keys rotate.** A key whose quota is spent ("you exceeded your
current quota, please check your plan and billing details") is given up on
for the rest of the process — it will not come back within a deployment's
lifetime, and re-trying it on every message would add a wasted round trip to
every chat. A key that was merely rate limited (a burst) is not given up on;
it is moved past for that call and can be used again later. Log lines carry
`key_slot=2`, the position in the list, never the key.

**How the models rotate.** A saturated model (`503 high demand`,
`504 DEADLINE_EXCEEDED`) moves to the next model and the key stays. A model
that works stays selected, so a saturated primary is paid for once rather than
on every message.

**What the live API looked like when this was built.** `gemini-2.5-flash` is
gone for new users. `gemini-3.8-flash`, `gemini-3.7-flash` and
`gemini-3.6-flash` were saturated (503 / 504). `gemini-3.5-flash-lite`,
`gemini-3.1-flash-lite`, `gemini-3-flash-preview` and `gemini-4-hydrogen`
answered. The fallback list is set to the two lite models, which is what
answered fastest.

**Nothing else is required.** If no key is configured,
`GET /api/v1/chatbot/admin/model-status/` reports `configured: false` and the
administrator console says "Layer 2 unavailable" — the failure is visible
rather than silent. If the keys are present but their quota is gone, the
console says so too: the client records the reason for the last failure
("quota exhausted: check the plan and billing") and shows it, along with how
many keys are configured and how many are spent.

**Quota exhaustion is not retried on the same key.** The API answers both a
burst of requests and an exhausted plan with `RESOURCE_EXHAUSTED`. Only the
first is worth retrying; the second moves to the next key.

**The test suite never calls Gemini.** `config/settings/test.py` blanks the
key, so a key in `backend/.env` cannot turn the tests into network calls that
are slow, flaky and spend the school's quota.

## 2a. Turn on field encryption

The student free text — chat messages, replies, flag summaries, private case
notes — is stored encrypted with AES-SIV. Generate a key and put it in the
environment:

```powershell
cd backend\aegis_backend
..\.venv\Scripts\python.exe manage.py generate_encryption_key
```

It prints one line to add to `backend/.env`:

```dotenv
FIELD_ENCRYPTION_KEYS=k1:<the value it printed>
```

* The key is 512 bits, base64-encoded. It is never stored in the database and
  never reaches the frontend.
* **Rotate** by adding the new key first, deploying, and dropping the old one
  once nothing is encrypted with it any more: the first key in the list
  encrypts, every key in the list decrypts.
* `production.py` sets `FIELD_ENCRYPTION_REQUIRED = True`, so a production
  deployment **refuses to start** without a key (`chatbot.E001`). Development
  and the test suite leave it off, so they work with no key at all.
* With no key the text is stored in the clear and the administrator console
  says "Field encryption is OFF".
* Migration `chatbot/0005_encrypt_existing_text` rewrites the rows that were
  already stored in plain text. With no key it does nothing.

The encryption is **deterministic** (AES-SIV), so an equality lookup on an
encrypted column still works. The cost is that two identical messages
encrypt to identical ciphertexts.

What it covers: the chatbot's messages, replies, model rationale, flag
summaries and case notes, plus the counseling narrative — a counselor's
session notes, a teacher's observation, an intervention step, a progress
note. `docs/SECURITY_POSTURE_RUNBOOK.md` has the full list, the rotation
procedure, the questions to ask the platform about the disk and the backups,
and what to do when something is wrong.

**Check a deployment with one command:**

```powershell
..\.venv\Scripts\python.exe manage.py security_posture
```

It prints whether field encryption is on, which columns are encrypted, the
acknowledgment window per severity, the retention window, and the model
status — and never prints a key.

## 3. Migrate
```powershell
cd backend\aegis_backend
..\.venv\Scripts\python.exe manage.py migrate
```

New migrations:

| App | Migration | What it does |
|---|---|---|
| `chatbot` | `0001_initial` | `KeywordTerm`, `ChatMessage`, `Flag`, `FlagRecipient`, `FlagAction`, `AgreementAcceptance` |
| `chatbot` | `0002_seed_default_keywords` | seeds the default Layer 1 terms |
| `chatbot` | `0003_retire_broad_default_terms` | replaces the first broad single-word terms with phrases |
| `chatbot` | `0004_alter_chatmessage_message_...` | marks the free-text fields as encrypted |
| `chatbot` | `0005_encrypt_existing_text` | encrypts the rows that were already stored in plain text |
| `chatbot` | `0006_alter_chatmessage_detection_detail` | marks the model rationale JSON as encrypted |
| `chatbot` | `0007_encrypt_existing_detection_detail` | encrypts the stored rationale |
| `guidance` | `0006_alter_behavioralnote_note_text_and_more` | marks the counseling narrative as encrypted |
| `guidance` | `0007_encrypt_existing_narrative` | encrypts the stored counseling narrative |
| `accounts` | `0009_registrationrequest_notice_accepted_at_and_more` | notice acceptance at sign-up |
| `assessments` | `0002_assessment_ai_generated_assessment_review_note_and_more` | the review gate fields |
| `cms` | `0005_seed_chatbot_settings` | the chatbot settings rows on an existing database |
| `cms` | `0006_seed_timer_and_retention_settings` | the per-severity windows and the retention window |

The keyword seed is idempotent: it creates missing terms and never overwrites
a term an administrator has edited. To run it by hand:

```powershell
..\.venv\Scripts\python.exe manage.py seed_chatbot_defaults
```

## 4. Seed synthetic data (optional, development only)

```powershell
cd backend
.\.venv\Scripts\python.exe scripts\seed_chatbot_synthetic.py
```

Creates synthetic students, benign chat turns and flags in every state, all
marked `[SYNTHETIC]`. It is safe to run twice — existing rows are skipped.

The rest of the school's synthetic data is unchanged:

```powershell
cd backend\aegis_backend
..\.venv\Scripts\python.exe manage.py shell < ..\scripts\seed_ph9_synthetic.py
```

## 5. Run the escalation timer

The acknowledgment timer is lazy: it fires when the guidance inbox or the
administrator dashboard is opened. A deployment that wants a hard guarantee
schedules the command instead:

```powershell
..\.venv\Scripts\python.exe manage.py escalate_stale_flags
```

Run it every minute or every five. It is idempotent — a flag escalated once
is not escalated again.

The window itself is data: `chatbot.acknowledgment_timer_minutes` is the
school-wide value (default 15), and
`chatbot.acknowledgment_timer_minutes.critical` (and `.high`, `.medium`,
`.low`) override it per severity when they hold a number. Blank means "use the
school-wide value". Edit them at `/app/admin/settings`.

## 5a. Apply the retention window

```powershell
..\.venv\Scripts\python.exe manage.py purge_chatbot_data --dry-run
..\.venv\Scripts\python.exe manage.py purge_chatbot_data
```

The window is `chatbot.retention_days` (default **0**, which keeps
everything). The command refuses to run without a window, because a job that
deletes on a default is a job that surprises somebody.

What it deletes: chat messages older than the window that are not attached to
a flag, and flags older than the window that are **closed** (resolved or
marked a false positive) — with their actions and recipients.

What it never deletes: an open, under-review or unacknowledged flag, whatever
its age, and anything outside the chatbot tables.

Schedule it the same way as the escalation timer.

## 6. The at-risk model

```powershell
..\.venv\Scripts\python.exe manage.py train_at_risk_model --dry-run
..\.venv\Scripts\python.exe manage.py train_at_risk_model
..\.venv\Scripts\python.exe manage.py run_at_risk_alerts --dry-run
..\.venv\Scripts\python.exe manage.py run_at_risk_alerts
```

Training refuses to run with fewer than 20 usable students or with one-class
data. The stored artifact is version `at_risk_v1` and coexists with the
existing three-class model (`v1`).

A second run does not stack a second alert on a student Guidance is already
working: `at_risk.has_active_at_risk_alert()` skips a student with an open
alert from this model.

## 7. Run the tests

```powershell
# Backend (SQLite, no services needed, no network)
cd backend\aegis_backend
..\.venv\Scripts\python.exe manage.py test --settings=config.settings.test

# Only the safety workstream
..\.venv\Scripts\python.exe manage.py test apps.chatbot apps.assessments.tests_review ai_engine.tests_at_risk --settings=config.settings.test

# Frontend
cd frontend
npm run typecheck
npm run lint
npm test
```

The suite makes **no network calls**: `config/settings/test.py` blanks
`GEMINI_API_KEY`, so Layer 2 does not run and every model interaction is
either mocked or falls back to the deterministic layer. A test that depends on
a third party's availability is not a test.

## 8. Manual checklist

The parts a unit test cannot prove. Each row is a thing to click, and what
must be true when it is done.

### Student

| # | Action | Expected |
|---|---|---|
| 1 | Open the assistant before accepting the notice | The notice is shown with an accept button; the composer is disabled; `POST /chatbot/message/` answers 428 |
| 2 | Accept the notice | The composer becomes usable; `AgreementAcceptance` is written for the current version |
| 3 | Send "What is my grade in Math?" | A grade answer; the turn is stored in `chat_messages`; it reappears when the panel is reopened |
| 4 | Send "I want to hurt myself" | A supportive reply that names Guidance; a banner says a counselor has been notified; a `critical` flag exists |
| 5 | Send a harmless message | No flag, no banner |
| 6 | Check another student's history | Impossible from the UI; `GET /chatbot/history/` is scoped to the caller |
| 6a | Send "I am being bullied every day" | The reply thanks them and says a counselor has been told — never "I didn't understand" — and a `medium` flag exists |

### Guidance

| # | Action | Expected |
|---|---|---|
| 7 | Open `/app/guidance/flags` | The inbox lists the critical flag with the student, the severity, the message and the reply |
| 8 | Open one flag | The message, the recipients and the action history are visible; the case-note box accepts a private note |
| 9 | Acknowledge the flag | The status becomes `acknowledged`; the acknowledgment is timestamped and recorded as an action |
| 10 | Add a case note, then resolve | Both are recorded; the flag becomes `resolved` |
| 11 | Mark a flag as a false positive | The status becomes `false_positive`; the note is kept for feedback |
| 12 | Let a flag age past the timer, then reopen the inbox | It is escalated to administrators; the administrators receive a notification; the flag moves to `under_review` |
| 13 | Ask for intervention suggestions | A severity-appropriate list appears; nothing is saved anywhere |
| 14 | Ask for check-in items | Draft questions appear; nothing is published |

### Faculty

| # | Action | Expected |
|---|---|---|
| 15 | Open `/app/faculty/flags` | Severity, status and timestamps only — no student, no message, no categories |
| 16 | Read the notification | The text says a student in your class needs support; it contains no name, no message, no categories |
| 17 | Try to open a flag in detail | 403 — the conversation belongs to Guidance |

### Administrator

| # | Action | Expected |
|---|---|---|
| 18 | Open `/app/admin/chatbot` | Flag counts, the average acknowledgment time, the model status and the Layer 1 term table |
| 19 | Deactivate a keyword term | It stops matching on the next message; the term stays in the table |
| 20 | Add a term with severity `critical` | A message containing it is flagged critical and reaches administrators |
| 21 | Press "Run escalation timer" | The number of escalated flags is reported; running it again reports zero |
| 22 | Read the model status with no API key | "Layer 2 unavailable", and the reason is stated |
| 23 | Read the model status with an exhausted quota | The console names the reason: "quota exhausted: check the plan and billing" |
| 24 | Read the model status with no encryption key | The console says "Field encryption is OFF. Student messages are stored in plain text." |
| 25 | With a key configured, look at the chatbot tables directly | The message column holds `enc1:k1:…`, not the text; the application still shows the text |
| 24 | Mark a flag as a false positive in Guidance, then reopen the console | The flag appears in the "False positives" list with the note; the message is not repeated there |
| 25 | Set `chatbot.acknowledgment_timer_minutes.critical` to 5 | A new critical flag is due in 5 minutes; a medium flag still uses the school-wide window |
| 26 | Set `chatbot.retention_days` and run `manage.py purge_chatbot_data --dry-run` | The counts are reported; an open flag is listed as kept; nothing is deleted |

### Faculty assessments

| # | Action | Expected |
|---|---|---|
| 27 | Generate an AI draft | The assessment appears with "AI draft · needs review"; the Deploy button is disabled with the reason |
| 28 | Deploy it anyway | 400 — "must be reviewed and approved before it can be published" |
| 29 | Approve it | The badge changes to "approved"; Deploy becomes available |
| 30 | Deploy and check completion | Target count, completed, in progress and not-started counts; the names of students who have not completed it |

### Registration

| # | Action | Expected |
|---|---|---|
| 31 | Open `/register` | The notice text is shown, fetched from the server, with its version |
| 32 | Submit without ticking the box | The form refuses: "You must accept the student notice" |
| 33 | Tick the box and submit | The request is accepted; the registration row records the notice version and the acceptance time |
| 34 | Change `chatbot.notice_version` and reload the notice | The version changes; every student must accept again |

## 9. What is *not* covered by the automated tests

* A real Gemini call. The tests mock the model, because a test that depends on
  a network call and an API key is a test that fails for reasons that have
  nothing to do with the code. Run the checklist with a real key before
  shipping. **The client was exercised against the live API while this was
  built**: `gemini-2.5-flash` is gone for new users and
  `gemini-3.8-flash` answers. What could not be exercised is a *successful*
  classification — the key supplied for this work had no quota left, so
  every call ended in 429 "you exceeded your current quota".
* Encryption at rest. The student free text is encrypted in the column
  (§2a); the *disk* — Postgres volume and backups — is still the platform's
  decision. See `DECISIONS.md` §14.
* Retention. The job exists (`manage.py purge_chatbot_data`) but the window is
  unset, so nothing is deleted yet. The school has to decide the number.
* Load. The flag inbox has no pagination; a school with thousands of flags
  will want it.

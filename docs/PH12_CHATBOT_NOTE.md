# PH12 - Chatbot Safety, Intent Accuracy, and the Classifier Decision

**Status:** implementation complete and regression-verified.
**The trained intent classifier was measured and deliberately NOT adopted.** See [§6](#6-the-classifier-experiment-and-why-it-was-declined).

**Scope:** the chatbot's intent, urgency and answer layers. No new dependency; no model is *required*.

---

## 1. What this phase delivered

| Item | Outcome |
|---|---|
| Escalation precision (P0) | False-positive escalations 1/4 -> **0/4** |
| Two unreachable intents (P1) | `ASSESSMENT_INSTRUCTIONS`, `ASK_ATTENDANCE_STATUS` wired |
| Taglish accuracy | 82% -> **100%** |
| Clean English accuracy | 70% -> **90%** |
| Typo accuracy | 20% (unchanged, documented as a known limit) |
| Trained classifier | Built, measured, **declined** |

Tests: `apps.chatbot` 23 -> **84**.

---

## 2. Why the order was safety first, accuracy second

The plan was to build a TF-IDF classifier. Measurement first showed that was the wrong first move, because the most serious defect was not an accuracy problem at all.

`classify_urgency` runs **before** intent classification and is regex-only. Replacing `classify_intent` with a model would not have touched it. Meanwhile `URGENT_PATTERNS` matched a bare `\bhurt\b` and `\bkill\b`, so:

```
"I hurt my ankle playing basketball"  ->  URGENT
"I'm killing it in math"                ->  URGENT
```

A URGENT match dispatches a real `BEHAVIORAL_WARNING` notification to a guidance counselor (`service.create_escalation`). A channel that pages staff about a sprained ankle is one they learn to ignore, which makes a genuine crisis notice less likely to be read.

---

## 3. P0 - escalation precision

Self-harm is now matched as a phrase with the object attached, plus recessive phrasing with no actor named:

```python
r"\b(hurt|harm|harming|hurts)\s+myself\b",
r"\b(been|always|constantly|keep|keeps|keeping)\s+(hurting|harming|hurt|harm)\s+myself\b",
r"\b(kill|killing)\s+myself\b",
r"\b(want|wants|wanted|wish|wishes)\s+to\s+(kill|hurt|harm)\b",
r"\b(don'?t|do not)\s+want\s+to\s+(live|be here|exist)\b",
r"\bwant\s+to\s+disappear\b",
```

A bare verb is deliberately **not** a trigger.

| | Before | After |
|---|---|---|
| Ordinary messages escalating | 1/4 | **0/4** |
| Real self-harm caught | 3/3 | **9/9** |

Covered by `UrgencyEscalationPrecisionTest`, including an end-to-end assertion that a real notification is still dispatched, so the precision fix cannot have silently disabled escalation.

---

## 4. P1 - two intents that could never fire

`ASSESSMENT_INSTRUCTIONS` and `ASK_ATTENDANCE_STATUS` were declared in `taxonomy.ChatIntent`, gated per role by `ALLOWED_INTENTS_BY_ROLE`, listed by `IntentsView`, and mirrored in the frontend - but `classify_intent` had **no branch that could return either**. They were unreachable states in the published contract.

Both are now wired, checked ahead of their siblings:

- Instructions are tested before schedule, because `"How many questions is the quiz?"` contains "how", which `SCHEDULE_PATTERNS` treats as a when-question.
- Attendance *status* is tested before the raw count, because `"Am I doing okay with my attendance?"` matches both.

`WiredIntentReachabilityTest` asserts that **every** declared intent is reachable, so the next intent added to the taxonomy without a classifier branch fails a test.

That test also caught a third defect: `NAVIGATION_PATTERNS` required `find|see|view` with no UI noun, so it could never win against `GRADE_PATTERNS` and `SYSTEM_NAVIGATION` was effectively unreachable too.

---

## 5. Taglish accuracy: 82% -> 100%

Taglish is a separate problem from typos: correct spelling, mixed language. Two stems were missing.

| Utterance | Before | Cause |
|---|---|---|
| `ilang absen ko` | `unknown` | no `absen` stem in `ATTENDANCE_PATTERNS` |
| `gusto ko makipag-usap sa counselor` | `guidance_help` | matched bare `counselor`; no `makipag-usap` |

The second is the more serious. A student asked to talk to someone and received *"Guidance is available to support you"* - which reads as being deflected rather than helped.

Nine permanent tests in `TaglishIntentTest`, including one asserting `GUIDANCE_HELP` and `REQUEST_COUNSELOR` stay distinguishable.

---

## 6. The classifier experiment, and why it was declined

### 6.1 What was built

Approved scope: a `char_wb` + `word` TF-IDF union with LogisticRegression, ~15 examples per intent, held-out probe.

| File | Role |
|---|---|
| `apps/chatbot/dataset.py` | Loads the committed labelled set |
| `apps/chatbot/data/intent_dataset.jsonl` | 174 labelled rows across 20 intents (the 165-row / 19-intent set measured below, plus `ask_risk_status`) |
| `apps/chatbot/data/holdout_probe.jsonl` | 68 probes, disjoint from training |
| `apps/chatbot/classifier.py` | Pipeline, prediction, **not wired in** |
| `manage.py evaluate_intent_classifier` | Reproduces every number below |

The model is fitted at import from the committed file, so there is no artifact to persist or go stale - the class of failure that left `run_risk_computation` unable to execute at all.

### 6.2 The result

| Path | Holdout (68 probes) |
|---|---|
| Regex layer alone | **64.7%** |
| Regex + classifier fallback | **64.7%** |
| Classifier alone | 5.9% |

The classifier contributed **nothing**. Two measured causes:

**It overfits.** Out-of-fold top-1 accuracy was **60.0%**, worse than regex's 64.7%. The character branch alone produces **1,110 features from the 165 documents measured** - it memorises rather than generalises.

**A confidence floor converts that into precision at the cost of coverage.** The floor was chosen by 5-fold stratified cross-validation on the *training* set, never on the holdout:

| floor | kept | accuracy on kept | overall |
|---|---|---|---|
| 0.00 | 165 | 60.0% | 60.0% |
| 0.25 | 47 | 89.4% | 25.5% |
| 0.35 | 13 | 92.3% | 7.3% |

At the best setting it rescues only a quarter of the `UNKNOWN` stratum.

### 6.3 The decision

**Not wired into `classify_intent`.** A 60%-accurate classifier behind the `UNKNOWN` branch would replace *"I didn't fully understand"* with a confidently wrong answer - worse for the student, and worse for the credibility of a system whose escalation path is its most safety-critical behaviour.

`NotWiredInTest` asserts `classify_intent("what is my absense record")` still returns `UNKNOWN`, so a future change that wires it in has to change a test deliberately.

### 6.4 What would change the answer

- **A narrower target.** A binary typo-corrector needs far less data than a 19-way classifier.
- **~1,000+ labelled rows.** Plausible, but a large data-generation effort against an uncertain payoff.

---

## 7. Limitations to state in the paper

1. The chatbot recognises a **fixed set of 20 intents** and does not hold open-ended conversation. Each message is classified and answered independently; there is no memory of earlier turns.
2. It is **deterministic when no model is reachable**. Intent is keyword/regex classification and answers are templates, but academic, attendance, status and recommendation answers are now built from the caller's imported records. A provider layer (`apps/chatbot/providers.py`) tries a **local** model first and an offsite one only as its fallback; if neither answers, the deterministic reply is used. See [§10](#10-response-providers).
3. **Misunderstands misspellings** (20%). Unhandled input degrades to the safe rephrase reply rather than a wrong answer.
4. **Parent queries across multiple children are refused, not guessed.** With one linked child the data is returned; with several the bot asks which child. Name disambiguation is absent because `parse_message` extracts only `subject` and `topic` - there is no `person` entity type to match against. That is a parser change, not a lookup change.
5. **Faculty, guidance and admin get a narrow assistant.** `ALLOWED_INTENTS_BY_ROLE` restricts them to greeting, help, navigation and unknown. The UI offers only prompts those roles can actually satisfy.
6. **The transcript is not persisted.** It is component state; closing the panel discards it. There is no `ChatSession` or `ChatMessage` model. A distress signal is the exception: it writes one open `RiskAlert` (`source=chatbot`) and a Guidance notification, without copying the message text into either.
7. **A local model is the default provider.** It is attempted first; the offsite provider is only its fallback and stays silent unless a vendor is configured. A deployment that installs no model degrades to the deterministic reply, and no provider can change the API, the frontend or the escalation path.

---

## 8. Security posture

- Student and parent messages never leave the server except to the chatbot endpoint itself.
- The classifier never sees urgency. `detect_urgent` is regex-only and runs first, so a model cannot decide whether a counselor gets paged. This is enforced by ordering, and by the fact that the classifier is not wired in at all.
- `URGENT_CONCERN` rows exist in the training data only to keep the label set balanced for evaluation; they are not an inference path.

---

## 9. Verification

| Check | Result |
|---|---|
| `manage.py test apps.chatbot` | 84/84 PASS |
| `manage.py test` - batch 1 (accounts, academics, attendance, guidance, notifications, assessments) | 540/540 PASS |
| `manage.py test` - batch 2 (data_import, chatbot, recommendations, analytics, audit, ai_engine) | 950/950 PASS |
| `manage.py check` | clean |
| `manage.py evaluate_intent_classifier` | reproduces every number above |

The suite is split into two batches because a single invocation exceeds the execution timeout. Batch totals: **1,490 tests**.

---

## 10. Response providers

The chatbot answers deterministically. A deployment that wants a model phrases
the answer through a **provider** without changing the API, the frontend or the
data flow.

| Provider | Offsite | Notes |
|---|---|---|
| `OllamaProvider` | no | **Default, first in the chain.** Local runtime (`AEGIS_OLLAMA_URL`, `AEGIS_OLLAMA_MODEL`). No key, no egress, works offline. |
| `OpenAICompatProvider` | **yes** | **Fallback.** Any OpenAI-compatible `/chat/completions` endpoint (Groq, Cerebras, OpenRouter, Mistral, GitHub Models, ...). Silent until a vendor is configured. |
| `ChainProvider` | — | Tries providers in order; first non-empty reply wins; a failure moves on; all-fail returns to the deterministic reply. |
| `NoopProvider` | no | Used only when the chain is empty by configuration. Returns no reply. |

The default is local-first, cloud-as-fallback:

```
AEGIS_CHATBOT_USE_LLM = True                       # default
AEGIS_CHATBOT_PROVIDER_CHAIN = (
    "apps.chatbot.providers.OllamaProvider,"
    "apps.chatbot.providers.OpenAICompatProvider"
)
AEGIS_OLLAMA_URL = "http://127.0.0.1:11434"
AEGIS_OLLAMA_MODEL = "llama3.2:3b"
```

With no model installed the request degrades to the deterministic reply
(`degraded=true` in the response, which the panel does not surface). With
Ollama running, the answer is local and no student record leaves the machine.
If Ollama is down and an offsite vendor is configured, the chain — and only
then — sends the **redacted** payload to that vendor. Set
`AEGIS_CHATBOT_USE_LLM=False` to stay fully deterministic, or
`AEGIS_CHATBOT_PROVIDER_CHAIN=""` to fall back to the single
`AEGIS_CHATBOT_PROVIDER`.

### 10.1 The policies that keep it safe

1. **Distress never reaches a provider.** The escalation path runs before the
   provider and returns, so a crisis reply is always the application's, not a
   model's.
2. **Only `LLM_ELIGIBLE_INTENTS` reach a provider**, and today that set is
   `ASK_STUDY_STRATEGY` alone — the one question whose answer is open-ended
   advice. Every answer that states a fact about a student's record (grades,
   status, risk, attendance, recommendations, resources) is written by the
   application. Greetings, help, navigation and `UNKNOWN` are deterministic; a
   message the classifier could not understand returns the honest rephrase
   prompt instead of a model's guess.
3. **A provider is handed only authorized, already-computed data** — never ORM
   access, never another student's records.
4. **An offsite provider receives a redacted payload.** `providers.redact`
   drops direct student identifiers (`student_id`, `student_name`) before the
   request leaves the machine; the local provider gets the full payload. Set
   `AEGIS_CHATBOT_REDACT_OFFSITE=False` only for a vendor cleared to hold
   student data.
5. **A provider cannot escalate.** Alert and notification writes stay in
   `service.create_escalation`.
6. **A provider reply must be grounded in the data it was given.** Every
   provider reply passes three checks before it is returned. `sanitize_provider_reply`
   rewrites internal field values (`at_risk`, `on_track`, ...) into plain words;
   `reply_is_grounded` requires every number in the prose to appear in the
   authorized payload; and `reply_echoes_payload` rejects a reply that prints one
   of the service's own section headings (`Grade Summary:`, `Academic Status:`,
   markdown `**`). A reply that names a figure it was not handed, or restates the
   record instead of giving advice, is discarded in favour of the deterministic
   answer. The checks exist because the local model was measured ignoring the
   prompt: it wrote `at_risk` verbatim, invented an 85% average for a student
   averaging 65.72, and — handed the full record for the advice intent — replied
   with a section dump plus a recommendation title no record held. Because no
   check can see a reversed comparison ("68.6, which is above the required 75"),
   the record-keeping answers are deterministic to begin with and a provider is
   kept only for `ASK_STUDY_STRATEGY`, whose payload is narrowed by
   `provider_payload` to the weak-subject names and the two numbers it may refer
   to (root fix; the label check is the backstop).

### 10.2 Privacy note

The provider payload contains real student records (grades, status, weak
subjects, recommendations). The PH9.0 discovery report already concluded that
a cloud LLM API is *not suitable for student data*; the local provider is the
default shape for that reason. Point an offsite provider only at a vendor the
school has cleared, and keep redaction on.

---

*Previous: `PH11.12_13_NOTE.md` - Back to `docs/`*
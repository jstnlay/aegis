# PH12 - Chatbot Safety, Intent Accuracy, and the Classifier Decision

**Status:** implementation complete and regression-verified.
**The trained intent classifier was measured and deliberately NOT adopted.** See [§6](#6-the-classifier-experiment-and-why-it-was-declined).

**Scope:** the chatbot's intent and urgency layers only. No backend schema change, no new dependency, no LLM.

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

Tests: `apps.chatbot` 23 -> **57**.

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
| `apps/chatbot/data/intent_dataset.jsonl` | 165 labelled rows across 19 intents |
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

**It overfits.** Out-of-fold top-1 accuracy was **60.0%**, worse than regex's 64.7%. The character branch alone produces **1,110 features from 165 documents** - it memorises rather than generalises.

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

1. The chatbot recognises a **fixed set of 19 intents** and does not hold open-ended conversation. Each message is classified and answered independently; there is no memory of earlier turns.
2. It is **deterministic, not an LLM**. Intent is keyword/regex classification and answers are templates. `views.py` passes `use_llm=False`.
3. **Misunderstands misspellings** (20%). Unhandled input degrades to the safe rephrase reply rather than a wrong answer.
4. **Parent queries across multiple children are refused, not guessed.** With one linked child the data is returned; with several the bot asks which child. Name disambiguation is absent because `parse_message` extracts only `subject` and `topic` - there is no `person` entity type to match against. That is a parser change, not a lookup change.
5. **Faculty, guidance and admin get a narrow assistant.** `ALLOWED_INTENTS_BY_ROLE` restricts them to greeting, help, navigation and unknown. The UI offers only prompts those roles can actually satisfy.
6. **Nothing is persisted.** The transcript is component state; closing the panel discards it. There is no `ChatSession` or `ChatMessage` model.
7. **No LLM is deployed.** D29 remains open; no provider is configured and no model is selected.

---

## 8. Security posture

- Student and parent messages never leave the server except to the chatbot endpoint itself.
- The classifier never sees urgency. `detect_urgent` is regex-only and runs first, so a model cannot decide whether a counselor gets paged. This is enforced by ordering, and by the fact that the classifier is not wired in at all.
- `URGENT_CONCERN` rows exist in the training data only to keep the label set balanced for evaluation; they are not an inference path.

---

## 9. Verification

| Check | Result |
|---|---|
| `manage.py test apps.chatbot` | 57/57 PASS |
| `manage.py test` - batch 1 (accounts, academics, attendance, guidance, notifications, assessments) | 540/540 PASS |
| `manage.py test` - batch 2 (data_import, chatbot, recommendations, analytics, audit, ai_engine) | 950/950 PASS |
| `manage.py check` | clean |
| `manage.py evaluate_intent_classifier` | reproduces every number above |

The suite is split into two batches because a single invocation exceeds the execution timeout. Batch totals: **1,490 tests**.

---

*Previous: `PH11.12_13_NOTE.md` - Back to `docs/`*
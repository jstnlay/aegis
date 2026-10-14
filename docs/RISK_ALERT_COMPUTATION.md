# Risk Alert — Computation Reference

Purpose: a self-contained, checkable description of how a student's risk level and
risk alert are produced. Written for external/domain review. Every number here is a
value currently in the code, not an aspiration.

Code paths (all under `backend/aegis_backend/`):

| Stage | File | Function |
|-------|------|----------|
| 1. Features | `ai_engine/feature_engine.py` | `compute_student_features` |
| 2. Training labels | `ai_engine/labeler.py` | `rule_based_label` / `reviewed_label` |
| 3. Model + training | `ai_engine/risk_scorer.py` | `train`, `build_model` |
| 4. Scoring | `ai_engine/risk_scorer.py` | `predict_single`, `_extract_decision_path` |
| 5. Alert state | `ai_engine/risk_service.py` | `integrate_risk_result`, `_compute_meaningful_change` |
| Batch driver | `ai_engine/management/commands/run_risk_computation.py` | `Command.handle` |
| Training driver | `ai_engine/management/commands/train_risk_model.py` | `Command.handle` |
| Thresholds | `ai_engine/config.py`, `ai_engine/labeler.py` | constants |

---

## 1. Input features (8)

Computed per student from finalized, completed data only.

Term gating: only grading periods with `end_date <= today` are used
(`run_risk_computation.py:68`, `feature_engine.py:81`). Grades are filtered to
`status="finalized"` with a non-null score.

If the student has no such grades → `computation_status = "insufficient_data"` and
the pipeline stops (no alert; a `RiskScore` row is still stored).

| Feature | Definition | Source |
|---------|------------|--------|
| `current_term_grade_average` | Unweighted decimal mean of all scores in the **latest completed** grading period | `feature_engine.py:104-108` |
| `lowest_subject_grade` | Minimum score in the latest completed period | `feature_engine.py:111-115` |
| `weak_subject_count` | Count of latest-period scores `< WEAK_SUBJECT_THRESHOLD` | `feature_engine.py:118-121` |
| `grade_trend` | `round(current_avg - previous_period_avg, 2)`; `None` if fewer than 2 completed periods | `feature_engine.py:124-129` |
| `attendance_rate` | `(present + late) / total` over the academic year, rounded to 4 dp; **late counts as attended** | `feature_engine.py:139-146` |
| `late_rate` | `late / total` over the academic year, 4 dp | `feature_engine.py:146` |
| `consultation_count` | Count of `ConsultationRecord` rows for the student — **no date filter** | `feature_engine.py:149-152` |
| `behavioral_count` | Count of `BehavioralNote` rows for the student — **no date filter** | `feature_engine.py:154-157` |

Free-text fields (notes, narratives, recommendations) are never features — enforced
by `ai_engine/validation.py` (`FORBIDDEN_FEATURES`, `EXCLUDED_FEATURES`).

### Feature → model vector
`features_to_matrix` / the row builder in `predict_single` map each feature by
position using `FEATURE_COLUMNS`, and **replace `None` with `0.0`**
(`risk_scorer.py:79-88`, `173-176`). Column order:
`current_term_grade_average, grade_trend, weak_subject_count, lowest_subject_grade,
attendance_rate, late_rate, consultation_count, behavioral_count`.

---

## 2. Training labels — rule rubric

The model is trained on labels produced by a hand-written rubric, not on
counselor-confirmed outcomes (`labeler.py:24-85`). Score starts at 0:

| Condition | Points |
|-----------|--------|
| `current_term_grade_average < 62` | +2 |
| else `current_term_grade_average < 75` | +1 |
| `weak_subject_count >= 4` | +3 |
| else `weak_subject_count >= 3` | +2 |
| else `weak_subject_count >= 1` | +1 |
| `grade_trend < -5` | +1 |
| `attendance_rate < 0.75` | +1 |
| `consultation_count >= 3` | +1 |
| `behavioral_count >= 2` | +1 |

Mapping to label:

- `insufficient_data` → `"insufficient_data"`
- total `0` → `"low"`
- total `1–4` → `"moderate"`
- total `>= 5` → `"high"`

Maximum possible total is 9.
`reviewed_label` (`labeler.py:88-98`): if a human label (`low`/`moderate`/`high`)
exists it overrides the rubric. **No human labels are currently supplied** —
`train_risk_model.py:138` always calls `reviewed_label(features, None)`.

## 2b. Training thresholds (current values)

| Constant | Value | Where |
|----------|-------|-------|
| `PASSING_GRADE` | 75 | `config.py:17` |
| `WEAK_SUBJECT_THRESHOLD` | 70 | `config.py:20` |
| `CRITICAL_GRADE_THRESHOLD` | 62 | `labeler.py:20` |
| `HIGH_WEAK_THRESHOLD` | 4 | `labeler.py:21` |

---

## 3. Model and training

`DecisionTreeClassifier` (`risk_scorer.py:56-65`):

```
criterion        = gini
splitter         = best
max_depth        = 4
min_samples_split= 10
min_samples_leaf = 5
random_state     = 42
```

Training (`risk_scorer.py:96-143`): drops rows labeled `insufficient_data`/`error`,
refuses if fewer than `min_samples_split` (10) remain, then fits on the rubric
labels. Class list comes from `model.classes_`.

Persistence: the fitted estimator + metadata are pickled into a
`RiskModelArtifact` DB row (`save_stored_model`, `risk_scorer.py:285-321`), loaded by
`load_stored_model`. A missing or unreadable artifact makes the batch command
refuse to score rather than invent a value.

---

## 4. Scoring (per student)

Class probabilities come from `model.predict_proba` (`risk_scorer.py:180-184`).

**Predicted risk level** = `model.predict` = the argmax class.

**Risk Index** (`risk_scorer.py:186-191`):

```
risk_score = P(low)*0 + P(moderate)*50 + P(high)*100
risk_score = round(clamp(risk_score, 0, 100), 2)
```

Anchors are in `config.py:40-44`. Note the index is the **expected value** of the
class, so it is continuous, while `risk_level` is the **most likely** class — the
two can disagree (e.g. `P(low)=0.40, P(moderate)=0.35, P(high)=0.25` gives level
`low` but score `42.5`).

**Explanation** (`_extract_decision_path`, `risk_scorer.py:206-247`): walks the
student's actual decision path and records every non-leaf node as
`{feature, threshold, value, direction}` where direction is `below` if
`value <= threshold` else `above`. Feature importances are deliberately *not* used
as the per-student explanation.

---

## 5. Alert / state logic

`integrate_risk_result` (`risk_service.py:99-263`):

1. **Always** insert a `RiskScore` row (full history), including
   `insufficient_data` and model version.
2. `insufficient_data` → no alert, no notification.
3. Find the student's existing alert with status `active` or `under_monitoring`
   (latest by `generated_at`).
4. Decide "meaningful change" (`_compute_meaningful_change`, `risk_service.py:60-96`):
   - no existing alert → change;
   - existing status not in `active`/`under_monitoring` → change;
   - risk level differs → change;
   - same level and `|current_score - existing_score| >= 10` → change;
   - otherwise → **no change** (no new alert, no notification).
5. On change:
   - existing `source="decision_tree"` alert → updated in place (level, score ref,
     risk factors); status is not auto-changed.
   - existing `source="manual"` alert → AI result is recorded as `RiskScore` only;
     the manual alert is **not** overwritten.
   - otherwise → new `RiskAlert` (`status="active"`, `source="decision_tree"`).
6. Notification on change:
   - recipients = all `role="guidance"` users;
   - if level is `high`, also the section adviser and all linked parents;
   - dedup key `risk_alert:{student_id}:{level}:{date}` (so one per student/level/day).

---

## 6. Points a reviewer should test / challenge

These are known properties of the current implementation, listed so a reviewer can
confirm or reject them rather than rediscover them.

1. **Labels are circular.** The tree learns the rubric in §2, computed from the same
   features it is scored on (`train_risk_model.py:20-25`, `label_caveat` metadata).
   Accuracy against these labels is not evidence of predicting real student risk.
   It becomes meaningful only once counselor-confirmed labels replace the rubric
   (`reviewed_label`'s `manual_label` path is the hook, currently unused).
2. **`None` becomes `0.0`.** Missing values are not imputed; they are treated as
   zero. For `attendance_rate`/`late_rate`/`grade_trend` this means "no data" reads
   as the worst possible value (0% attendance), pushing a student toward higher
   risk. Only the grade-average path has an `insufficient_data` guard, and it needs
   *zero* finalized grades to trigger. Confirm whether median imputation (as the
   `features_to_matrix` docstring claims) or explicit missing-handling is required.
3. **Time scope is inconsistent.** Grades/attendance are scoped to completed
   periods / the academic year, but `consultation_count` and `behavioral_count`
   count all-time rows. Confirm intended window.
4. **Late ≠ present.** `attendance_rate` counts `late` as attending. Confirm this
   matches school policy.
5. **Grade average is unweighted.** `GRADE_AVERAGING_METHOD` exists
   (`config.py:23`) but is not read anywhere. Confirm whether subjects/units should
   be weighted.
6. **Level vs index can disagree** (§4). Confirm which one drives downstream
   decisions and display.
7. **Guards are not on the training path.** `validate_training_data`
   (`validation.py:49`) enforces min 30 samples and min 5 per class but is only
   called from tests; `train()` checks only `>= min_samples_split` (10). Grouped
   (per-student) validation exists in `benchmark.py` (GroupKFold) but is not part of
   `train()`, so no grouped hold-out guards the shipped model.
8. **Every numeric threshold is an unvalidated default** (`62`, `75`, `70`, `0.75`,
   `4`, `3`, `2`, `-5`, `|Δ| >= 10`). They are marked configurable (D14) but have not
   been calibrated against outcomes. Review should state target sensitivity /
   specificity and a calibration plan.

---

## 7. Reproducing a score

```powershell
# 1. Train (rule labels) and store the artifact
python manage.py train_risk_model --dry-run     # inspect distribution first
python manage.py train_risk_model               # persist artifact v1

# 2. Inspect scores without persisting notifications
python manage.py run_risk_computation --dry-run
```

A single student's computation = §1 features → §4 model + Risk Index → §5 alert
decision. To audit one alert, read its `RiskScore.feature_snapshot`,
`RiskScore.explanation.contributing_factors`, and `RiskAlert.risk_factors`.

/**
 * Shared handling for `RiskAlert.risk_factors` entries.
 *
 * Lives outside the guidance feature because more than one role renders this
 * field, and a read-only surface (the parent portal) must not import the
 * guidance *client* module just to read a label — that module bundles the
 * counselor's mutation hooks.
 *
 * `RiskAlert.risk_factors` is a bare `models.JSONField(default=list)` with no
 * serializer validation, so both shapes genuinely occur and the client must
 * accept both:
 *
 * - **object** — what the AI engine writes. `ai_engine/risk_scorer.py`
 *   `_extract_decision_path` appends
 *   `{feature, threshold, value, direction}` per decision-tree node, and
 *   `ai_engine/risk_service.py` copies `explanation.contributing_factors`
 *   straight onto the alert. `ai_engine/resolver.py` already reads these with
 *   `factor.get("feature")`, so the object is the canonical form.
 * - **string** — what a counselor types on a manual alert, and what the QA seed
 *   writes.
 *
 * Typing this as `string[]` (as PH11.8 did) made `.join()` emit
 * "[object Object]" and `.map()` hand a raw object to React as a child, which
 * throws "Objects are not valid as a React child" and unmounts the page. The
 * object's `value`/`threshold` are also the only record of *why* the model
 * escalated a student, so they are rendered rather than discarded.
 */
export interface RiskFactorObject {
  feature?: string | null
  threshold?: number | null
  value?: number | null
  direction?: string | null
}

export type RiskFactor = string | RiskFactorObject

/**
 * A readable label for one factor, keeping the decision-tree detail.
 *
 * The raw `feature` key is preserved verbatim rather than prettified: it maps
 * directly onto `ai_engine.config.FEATURE_COLUMNS`, so a counselor auditing an
 * AI escalation can trace the row, and renaming it here would put the label out
 * of step with the model.
 */
export function riskFactorLabel(factor: RiskFactor): string {
  if (typeof factor === "string") return factor

  if (factor === null || typeof factor !== "object") return ""

  const feature =
    typeof factor.feature === "string" ? factor.feature.trim() : ""
  if (!feature) return ""

  const parts: string[] = [feature]

  const direction =
    typeof factor.direction === "string" ? factor.direction.trim() : ""
  if (direction) parts.push(direction)

  if (typeof factor.value === "number" && Number.isFinite(factor.value)) {
    parts.push(`value ${factor.value}`)
  }

  if (
    typeof factor.threshold === "number" &&
    Number.isFinite(factor.threshold)
  ) {
    parts.push(`threshold ${factor.threshold}`)
  }

  return parts.join(" ")
}

/**
 * Lower-cased text for search matching.
 *
 * Returns "" for an unusable entry so a malformed factor can never inject
 * "[object Object]" into the haystack and match every query.
 */
export function riskFactorSearchText(factor: RiskFactor): string {
  if (typeof factor === "string") return factor.toLowerCase()
  if (factor === null || typeof factor !== "object") return ""
  return [riskFactorLabel(factor), featureKeyOf(factor)]
    .filter(Boolean)
    .join(" ")
    .toLowerCase()
}

/** The bare `feature` key, for filtering that must match the model column. */
export function featureKeyOf(factor: RiskFactorObject): string {
  return typeof factor.feature === "string" ? factor.feature : ""
}

/** A score on the school's 0–100 scale; missing records never become zeroes. */
export function GradeMeter({
  score,
  label,
}: {
  score: number | null
  label: string
}) {
  if (score === null || !Number.isFinite(score) || score < 0 || score > 100)
    return null
  const tone =
    score >= 90 ? "excellent" : score >= 75 ? "passing" : "below-passing"
  return (
    <div
      className="school-grade-meter"
      data-tone={tone}
      role="meter"
      aria-label={`${label} grade`}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={score}
      aria-valuetext={`${score}%`}
    >
      <span style={{ width: `${score}%` }} />
    </div>
  )
}

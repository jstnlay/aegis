import { Badge } from "@/components/ui/badge"
import { formatPercent } from "@/lib/metric-format"
import { scoreStatus, scoreStatusLabel } from "@/lib/score-status"
import { getSubjectTheme } from "./subject-appearance"
import { SubjectArt } from "./SubjectArt"

export function SubjectGradeCard({
  name,
  code,
  score,
}: {
  name: string
  code: string
  score: number | null
}) {
  const theme = getSubjectTheme(name, code)
  const status = scoreStatus(score)

  return (
    <li className="student-subject-card" data-subject-theme={theme}>
      <div className="student-subject-banner">
        <SubjectArt theme={theme} />
        {code ? <span className="student-subject-code">{code}</span> : null}
        <h4 className="student-subject-name">{name}</h4>
      </div>
      <div className="student-subject-result">
        <div>
          <span className="student-subject-result-label">Finalized grade</span>
          <strong className="student-subject-score">
            {formatPercent(score, 2)}
          </strong>
        </div>
        <Badge
          status={status}
          variant={
            status === "below-passing"
              ? "destructive"
              : status === "passing"
                ? "secondary"
                : "outline"
          }
        >
          {scoreStatusLabel(status)}
        </Badge>
      </div>
    </li>
  )
}

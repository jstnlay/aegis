import { Badge } from "@/components/ui/badge"
import { GradeMeter } from "@/components/ui/grade-meter"
import { formatPercent } from "@/lib/metric-format"
import { scoreStatus, scoreStatusLabel } from "@/lib/score-status"
import { getSubjectTheme } from "./subject-appearance"
import { StudentSubjectSketch } from "./StudentJournalArtwork"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog"

export function SubjectGradeCard({
  name,
  code,
  score,
  selected = true,
  onSelect,
}: {
  name: string
  code: string
  score: number | null
  selected?: boolean
  onSelect?: () => void
}) {
  const theme = getSubjectTheme(name, code)
  const status = scoreStatus(score)

  return (
    <li
      className={`student-subject-card ${onSelect ? "student-subject-choice" : ""}`}
      data-subject-theme={theme}
    >
      {onSelect ? (
        <button
          type="button"
          className="student-subject-banner student-subject-select"
          onClick={onSelect}
          aria-haspopup="dialog"
          aria-label={`View ${name} grade`}
        >
          <StudentSubjectSketch theme={theme} />
          <h4 className="student-subject-name">{name}</h4>
          {code ? <span className="student-subject-code">{code}</span> : null}
        </button>
      ) : (
        <div className="student-subject-banner">
          <StudentSubjectSketch theme={theme} />
          {code ? <span className="student-subject-code">{code}</span> : null}
          <h4 className="student-subject-name">{name}</h4>
        </div>
      )}
      {!onSelect ? (
        <div className="student-subject-detail">
          <div className="student-subject-result">
            <div>
              <span className="student-subject-result-label">
                Finalized grade
              </span>
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
          <GradeMeter score={score} label={name} />
        </div>
      ) : (
        <Dialog
          open={selected}
          onOpenChange={(open) => {
            if (!open) onSelect()
          }}
        >
          <DialogContent className="student-grade-dialog">
            <DialogHeader>
              <DialogTitle>{name}</DialogTitle>
              <DialogDescription>{code} · Finalized grade</DialogDescription>
            </DialogHeader>
            <strong className="text-4xl font-bold text-primary">
              {formatPercent(score, 2)}
            </strong>
            <Badge status={status}>{scoreStatusLabel(status)}</Badge>
            <GradeMeter score={score} label={name} />
            <p className="text-xs text-muted-foreground">
              {score === null
                ? "No finalized grade available."
                : "Grade on a scale of 0–100."}
            </p>
          </DialogContent>
        </Dialog>
      )}
    </li>
  )
}

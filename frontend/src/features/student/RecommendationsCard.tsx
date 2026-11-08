import { BookMarked, Bookmark, Eye, Lightbulb } from "lucide-react"
import { useId, useState } from "react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { ErrorNote, PendingRegion } from "@/components/feedback/Feedback"
import { Skeleton } from "@/components/ui/skeleton"
import {
  INTERACTION_TYPE_LABELS,
  useRecordInteraction,
  useStudentRecommendations,
  type Recommendation,
} from "@/features/student/recommendations-api"
import { normalizeApiError } from "@/lib/error"
import { getSubjectTheme } from "@/features/student/subject-appearance"

/**
 * Recommended learning items for the signed-in student.
 *
 * The source is labelled rather than flattened, because the two methods are
 * different claims:
 *
 *   "Similar to what other students used"      — collaborative filtering, over
 *                                               real interaction history.
 *   "Based on your grades and attendance"      — content-based, over academic
 *                                               needs derived from this
 *                                               student's own records.
 *
 * A student shown an unexplained list would reasonably read both as "the system
 * knows what I need". They do not say that.
 *
 * An empty list is rendered as a real empty state. It is never padded with
 * placeholder items.
 */
export function RecommendationsCard({
  studentId,
}: {
  studentId: string | null
}) {
  const query = useStudentRecommendations(studentId)
  const record = useRecordInteraction()
  const [expanded, setExpanded] = useState(false)
  const listId = useId()

  const data = query.data
  const items = data?.recommendations ?? []

  return (
    <Card
      data-panel="resources"
      className="student-recommendations col-span-2 lg:col-span-3"
    >
      <CardHeader>
        <div className="flex flex-row items-center justify-between space-y-0">
          <CardTitle className="student-card-title">
            <Lightbulb
              className="size-4 text-muted-foreground"
              aria-hidden="true"
            />
            Recommended for you
          </CardTitle>
        </div>
        <CardDescription>
          {data
            ? METHOD_EXPLANATION[data.method]
            : "Learning resources matched to your records."}
        </CardDescription>
      </CardHeader>
      <CardContent>
        {query.isLoading ? (
          <PendingRegion label="Recommendations">
            <div className="space-y-2">
              <Skeleton className="h-12 w-full" />
              <Skeleton className="h-12 w-full" />
            </div>
          </PendingRegion>
        ) : query.isError ? (
          <ErrorNote message={normalizeApiError(query.error).message} />
        ) : items.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No recommendations are available for you right now. A teacher can
            approve learning resources for recommendation.
          </p>
        ) : (
          <div className="space-y-3">
            <ul id={listId} className="student-recommendation-list">
              {(expanded ? items : items.slice(0, 3)).map((item) => (
                <RecommendationRow
                  key={item.learning_item_id}
                  item={item}
                  onInteract={(interactionType) =>
                    record.mutate({
                      learningItemId: item.learning_item_id,
                      interactionType,
                    })
                  }
                  disabled={record.isPending}
                />
              ))}
            </ul>
            {items.length > 3 ? (
              <Button
                type="button"
                variant="outline"
                className="w-full"
                aria-expanded={expanded}
                aria-controls={listId}
                onClick={() => setExpanded((current) => !current)}
              >
                {expanded
                  ? "Show less"
                  : `Show all ${items.length} recommendations`}
              </Button>
            ) : null}
          </div>
        )}

        {record.isError ? (
          <p className="mt-2 text-xs text-destructive">
            {normalizeApiError(record.error).message}
          </p>
        ) : null}
      </CardContent>
    </Card>
  )
}

const METHOD_EXPLANATION: Record<"cf" | "content_based", string> = {
  cf: "Matched to what other students with a similar study history used.",
  content_based: "Matched to your grades and attendance.",
}

function RecommendationRow({
  item,
  onInteract,
  disabled,
}: {
  item: Recommendation
  onInteract: (type: "viewed" | "saved") => void
  disabled: boolean
}) {
  return (
    <li
      className="student-recommendation-item"
      data-subject-theme={getSubjectTheme(item.topic || item.title)}
    >
      <span className="student-resource-icon" aria-hidden="true">
        <BookMarked />
      </span>
      <div className="student-resource-copy">
        <div className="student-resource-meta">
          <Badge variant="secondary">
            {ITEM_TYPE_LABELS[item.item_type] ?? item.item_type}
          </Badge>
          {item.topic ? <span>{item.topic}</span> : null}
        </div>
        <h4>{item.title}</h4>
        <p className="text-xs text-muted-foreground">{item.reason}</p>
        <div className="student-resource-actions flex flex-wrap gap-2">
          <Button
            type="button"
            size="xs"
            variant="outline"
            disabled={disabled}
            onClick={() => onInteract("viewed")}
          >
            <Eye aria-hidden="true" />
            {INTERACTION_TYPE_LABELS.viewed}
          </Button>
          <Button
            type="button"
            size="xs"
            variant="outline"
            disabled={disabled}
            onClick={() => onInteract("saved")}
          >
            <Bookmark aria-hidden="true" />
            {INTERACTION_TYPE_LABELS.saved}
          </Button>
        </div>
      </div>
    </li>
  )
}

const ITEM_TYPE_LABELS: Record<string, string> = {
  study_activity: "Study activity",
  learning_resource: "Learning resource",
  learning_strategy: "Learning strategy",
}

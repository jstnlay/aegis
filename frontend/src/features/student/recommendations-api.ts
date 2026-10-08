import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { apiClient } from "@/lib/api"

/**
 * Recommendations (Final_Revision objective 6.2, FR-039/FR-040).
 *
 * `GET /api/v1/recommendations/students/{id}/` wraps
 * `ai_engine/recommender.recommend()`. The backend returns which method produced
 * the list, and this module keeps it, because the two are materially different
 * claims:
 *
 *   cf            — item-item cosine similarity over the cohort's real
 *                   interaction history.
 *   content_based — matched against academic needs derived from this student's
 *                   own grades and attendance.
 *
 * A student reading "5 recommendations" is not being told the same thing in
 * either case, so the UI labels the source rather than flattening both into one
 * list. Neither method is shown as a fallback: `fallback_used` says whether CF
 * was declined for want of data, which is a fact about the cohort, not a
 * degraded answer about the student.
 */

export type RecommendationMethod = "cf" | "content_based"

export interface Recommendation {
  learning_item_id: string
  title: string
  item_type: string
  subject_id: string | null
  topic: string | null
  relevance_score: number
  /** Present on CF rows; the content-based path does not set it per item. */
  method?: string
  reason: string
}

export interface StudentRecommendations {
  student_id: string
  method: RecommendationMethod
  recommendations: Recommendation[]
  fallback_used: boolean
  fallback_reason?: string
}

export interface RecommendationApiResponse {
  status: string
  data: StudentRecommendations
}

const keys = {
  recommendations: (studentId: string) =>
    ["recommendations", "student", studentId] as const,
}

/**
 * This student's recommendations.
 *
 * Disabled when there is no student, so a page without a resolved student does
 * not request the placeholder id.
 */
export function useStudentRecommendations(studentId: string | null) {
  return useQuery<StudentRecommendations | null, Error>({
    queryKey: keys.recommendations(studentId ?? ""),
    enabled: Boolean(studentId),
    queryFn: async () => {
      const { data } = await apiClient.get<RecommendationApiResponse>(
        `/recommendations/students/${studentId ?? ""}/`
      )
      return data.data
    },
  })
}

/**
 * Record that the student interacted with a learning item.
 *
 * This is the only write path into the collaborative-filtering signal.
 * `StudentInteraction` previously had no endpoint, which meant CF could never
 * populate and every response fell back to content-based.
 */
export function useRecordInteraction() {
  const queryClient = useQueryClient()
  return useMutation<
    unknown,
    Error,
    { learningItemId: string; interactionType: InteractionType }
  >({
    mutationFn: async ({ learningItemId, interactionType }) => {
      const { data } = await apiClient.post("/recommendations/interactions/", {
        learning_item: learningItemId,
        interaction_type: interactionType,
      })
      return data
    },
    onSuccess: () => {
      // The recorded interaction can change the recommendation list, so the
      // student's recommendations are refetched rather than left stale.
      void queryClient.invalidateQueries({ queryKey: ["recommendations"] })
    },
  })
}

/** `StudentInteraction.InteractionType.choices`. */
export const INTERACTION_TYPES = [
  "viewed",
  "started",
  "completed",
  "saved",
] as const

export type InteractionType = (typeof INTERACTION_TYPES)[number]

export const INTERACTION_TYPE_LABELS: Record<InteractionType, string> = {
  viewed: "Viewed",
  started: "Started",
  completed: "Completed",
  saved: "Saved",
}

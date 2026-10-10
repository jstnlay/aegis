import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import { apiClient } from "@/lib/api"
import { fetchAllPages } from "@/lib/pagination"

/**
 * Student portfolio entries.
 *
 * `GET /portfolio/entries/` (scope: own rows for students, linked children
 * for parents, everything for staff), `POST` for the owning student only.
 * Text plus an optional link URL — no file bytes, because this host has no
 * persistent disk to keep them on.
 */
export type PortfolioActivityType =
  | "paperwork"
  | "term_exam"
  | "recitation"
  | "quiz"
  | "project"
  | "performance_task"
  | "other"

export interface PortfolioEntry {
  id: string
  student: string
  student_name: string
  title: string
  activity_type: PortfolioActivityType
  description: string
  link_url: string | null
  created_at: string
  updated_at: string
}

export const PORTFOLIO_ACTIVITY_LABELS: Record<PortfolioActivityType, string> =
  {
    paperwork: "Paperwork",
    term_exam: "Term exam",
    recitation: "Recitation",
    quiz: "Quiz",
    project: "Project",
    performance_task: "Performance task",
    other: "Other",
  }

const KEY = "portfolio" as const

export function usePortfolioEntries(studentId?: string | null) {
  const params = studentId ? `?student=${studentId}` : ""
  return useQuery<PortfolioEntry[], Error>({
    queryKey: [KEY, "list", studentId ?? null],
    queryFn: async () => {
      const { results } = await fetchAllPages<PortfolioEntry>(
        `/portfolio/entries/${params}`
      )
      return results
    },
  })
}

export interface PortfolioPayload {
  title: string
  activity_type: PortfolioActivityType
  description?: string
  link_url?: string | null
}

export function useCreatePortfolioEntry() {
  const client = useQueryClient()
  return useMutation<PortfolioEntry, Error, PortfolioPayload>({
    mutationFn: async (payload) => {
      const { data } = await apiClient.post<PortfolioEntry>(
        "/portfolio/entries/",
        payload
      )
      return data
    },
    onSuccess: () => client.invalidateQueries({ queryKey: [KEY] }),
  })
}

export function useUpdatePortfolioEntry(entryId: string) {
  const client = useQueryClient()
  return useMutation<PortfolioEntry, Error, Partial<PortfolioPayload>>({
    mutationFn: async (payload) => {
      const { data } = await apiClient.patch<PortfolioEntry>(
        `/portfolio/entries/${entryId}/`,
        payload
      )
      return data
    },
    onSuccess: () => client.invalidateQueries({ queryKey: [KEY] }),
  })
}

export function useDeletePortfolioEntry() {
  const client = useQueryClient()
  return useMutation<void, Error, string>({
    mutationFn: async (entryId) => {
      await apiClient.delete(`/portfolio/entries/${entryId}/`)
    },
    onSuccess: () => client.invalidateQueries({ queryKey: [KEY] }),
  })
}

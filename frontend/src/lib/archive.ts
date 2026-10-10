import { useState } from "react"

/**
 * Per-user "hide completed" archive toggle.
 *
 * Completed logs (consultations, interventions) are history the backend keeps
 * — nothing is deleted. This only hides them from the list, persisted per
 * browser in `localStorage` so the choice survives a reload. "Show archived"
 * restores them.
 */
export function useHideCompleted(storageKey: string, defaultHidden = false) {
  const [hideCompleted, setHideCompleted] = useState<boolean>(() => {
    try {
      const stored = localStorage.getItem(storageKey)
      return stored === null ? defaultHidden : stored === "1"
    } catch {
      return defaultHidden
    }
  })

  function setHidden(next: boolean) {
    setHideCompleted(next)
    try {
      localStorage.setItem(storageKey, next ? "1" : "0")
    } catch {
      // Private mode etc: the toggle still works for this session.
    }
  }

  return { hideCompleted, setHidden }
}

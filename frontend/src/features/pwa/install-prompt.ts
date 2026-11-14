import { useSyncExternalStore } from "react"

/**
 * The browser's one-shot install prompt.
 *
 * `beforeinstallprompt` fires once, and only after the browser decides the
 * site is installable. The listener therefore has to exist before the account
 * menu mounts — importing this module from `main.tsx` registers it at start-up.
 * Holding the event (and calling `preventDefault`) is the documented way to
 * show the prompt later from a menu item.
 */
interface InstallChoice {
  outcome: "accepted" | "dismissed"
  platform: string
}

interface BeforeInstallPromptEvent extends Event {
  prompt: () => Promise<void>
  userChoice: Promise<InstallChoice>
}

let deferred: BeforeInstallPromptEvent | null = null
const listeners = new Set<() => void>()

function emit(): void {
  for (const listener of listeners) listener()
}

if (typeof window !== "undefined") {
  window.addEventListener("beforeinstallprompt", (event) => {
    event.preventDefault()
    deferred = event as BeforeInstallPromptEvent
    emit()
  })
  window.addEventListener("appinstalled", () => {
    deferred = null
    emit()
  })
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}

function getSnapshot(): BeforeInstallPromptEvent | null {
  return deferred
}

/** Single-use: the event cannot prompt twice, accepted or dismissed. */
export async function promptInstall(): Promise<void> {
  const event = deferred
  if (!event) return
  await event.prompt()
  await event.userChoice
  deferred = null
  emit()
}

export function useInstallPrompt() {
  const event = useSyncExternalStore(subscribe, getSnapshot, () => null)
  return { canInstall: event !== null, promptInstall }
}

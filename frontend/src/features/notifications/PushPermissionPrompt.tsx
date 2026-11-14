import { useState } from "react"
import { X } from "lucide-react"

import { normalizeApiError } from "@/lib/error"
import {
  enablePushOnThisDevice,
  isPushSupported,
  pushVapidKeyConfigured,
} from "./push"

const DISMISS_KEY = "aegis-push-prompt-dismissed"

/**
 * One-time offer, shown after a real notification arrives — never on first
 * load. Dismissal is remembered for the browser so the offer does not follow
 * every new alert.
 */
export function PushPermissionPrompt() {
  const [dismissed, setDismissed] = useState(() => {
    try {
      return localStorage.getItem(DISMISS_KEY) === "1"
    } catch {
      return false
    }
  })
  const [busy, setBusy] = useState(false)
  const [enabled, setEnabled] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const eligible =
    !dismissed &&
    !enabled &&
    typeof window !== "undefined" &&
    "Notification" in window &&
    Notification.permission === "default" &&
    isPushSupported() &&
    pushVapidKeyConfigured()

  if (!eligible) return null

  function dismiss() {
    setDismissed(true)
    try {
      localStorage.setItem(DISMISS_KEY, "1")
    } catch {
      // Storage disabled; the prompt stays hidden for this visit.
    }
  }

  async function enable() {
    setBusy(true)
    setError(null)
    try {
      const result = await enablePushOnThisDevice()
      if (result === "granted") {
        setEnabled(true)
      } else if (result === "denied") {
        dismiss()
      }
    } catch (cause) {
      setError(normalizeApiError(cause).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="notification-preview push-prompt" role="status">
      <div className="push-prompt-copy">
        <p className="push-prompt-title">Get alerts on this device?</p>
        <p className="push-prompt-body">
          AEGIS can notify you the moment an update arrives, even with the app
          closed.
        </p>
        {error ? <p className="push-prompt-error">{error}</p> : null}
      </div>
      <div className="push-prompt-actions">
        <button
          type="button"
          className="push-prompt-enable"
          onClick={enable}
          disabled={busy}
        >
          {busy ? "Enabling…" : "Enable"}
        </button>
        <button
          type="button"
          className="push-prompt-dismiss"
          onClick={dismiss}
          aria-label="Dismiss push notification offer"
        >
          <X aria-hidden="true" />
        </button>
      </div>
    </div>
  )
}

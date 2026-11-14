import { apiClient } from "@/lib/api"

/** Stored server id of this browser's subscription, set on subscribe. */
const SUBSCRIPTION_ID_KEY = "aegis-push-subscription-id"

interface PushKeys {
  p256dh?: string
  auth?: string
}

/**
 * The public VAPID key is compiled in at build time; an admin sets it as a
 * Vercel environment variable and redeploys. An empty key means this build
 * cannot subscribe, and the prompt stays hidden.
 */
export function pushVapidKeyConfigured(): boolean {
  return Boolean(import.meta.env.VITE_VAPID_PUBLIC_KEY)
}

export function isPushSupported(): boolean {
  return (
    typeof window !== "undefined" &&
    "serviceWorker" in navigator &&
    "PushManager" in window &&
    "Notification" in window
  )
}

/** `applicationServerKey` needs the raw bytes, not the base64url text. */
function urlBase64ToUint8Array(base64Url: string): Uint8Array<ArrayBuffer> {
  const padding = "=".repeat((4 - (base64Url.length % 4)) % 4)
  const base64 = (base64Url + padding).replace(/-/g, "+").replace(/_/g, "/")
  const raw = window.atob(base64)
  const bytes = new Uint8Array(raw.length)
  for (let index = 0; index < raw.length; index += 1) {
    bytes[index] = raw.charCodeAt(index)
  }
  return bytes
}

export type PushEnableResult = "granted" | "denied" | "unsupported"

/**
 * Ask for permission, register this browser's subscription and tell the
 * backend. `"denied"` means the browser blocked the prompt; the SPA cannot ask
 * again until the user changes the site permission in the browser settings.
 */
export async function enablePushOnThisDevice(): Promise<PushEnableResult> {
  if (!isPushSupported() || !pushVapidKeyConfigured()) {
    return "unsupported"
  }

  const permission = await Notification.requestPermission()
  if (permission !== "granted") return "denied"

  const registration = await navigator.serviceWorker.ready
  const subscription = await registration.pushManager.subscribe({
    userVisibleOnly: true,
    applicationServerKey: urlBase64ToUint8Array(
      import.meta.env.VITE_VAPID_PUBLIC_KEY as string
    ),
  })

  const json = subscription.toJSON() as {
    endpoint?: string
    keys?: PushKeys
  }
  if (!json.endpoint || !json.keys?.p256dh || !json.keys?.auth) {
    throw new Error("The browser did not return a complete subscription.")
  }

  const { data } = await apiClient.post<{ id: string }>(
    "/notifications/push-subscriptions/",
    {
      endpoint: json.endpoint,
      p256dh: json.keys.p256dh,
      auth: json.keys.auth,
    }
  )
  try {
    localStorage.setItem(SUBSCRIPTION_ID_KEY, data.id)
  } catch {
    // The subscription works without the id; only the settings-page opt-out
    // loses the handle to delete.
  }
  return "granted"
}

/** Unsubscribe the browser and forget the server row. */
export async function disablePushOnThisDevice(): Promise<void> {
  if (isPushSupported()) {
    const registration = await navigator.serviceWorker.ready
    const subscription = await registration.pushManager.getSubscription()
    if (subscription) await subscription.unsubscribe()
  }
  const id = localStorage.getItem(SUBSCRIPTION_ID_KEY)
  if (id) {
    try {
      await apiClient.delete(`/notifications/push-subscriptions/${id}/`)
    } catch {
      // The row may already be gone, or the token expired mid-flow; the
      // browser no longer receives push either way.
    }
    try {
      localStorage.removeItem(SUBSCRIPTION_ID_KEY)
    } catch {
      // Storage can be disabled.
    }
  }
}

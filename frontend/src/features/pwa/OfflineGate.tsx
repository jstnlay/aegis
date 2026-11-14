import { useEffect, useState, type ReactNode } from "react"

import { OfflinePage } from "./OfflinePage"

/**
 * Replaces the whole app with the offline page while the browser has no
 * connection.
 *
 * It sits above the router and the query client on purpose: an offline cold
 * start must not mount pages that immediately fail every API call. When the
 * `online` event fires the normal tree mounts again at the current URL.
 */
export function OfflineGate({ children }: { children: ReactNode }) {
  const [online, setOnline] = useState(() => navigator.onLine)

  useEffect(() => {
    const sync = () => setOnline(navigator.onLine)
    window.addEventListener("online", sync)
    window.addEventListener("offline", sync)
    return () => {
      window.removeEventListener("online", sync)
      window.removeEventListener("offline", sync)
    }
  }, [])

  return online ? <>{children}</> : <OfflinePage />
}

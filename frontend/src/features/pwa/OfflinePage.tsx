import { WifiOff } from "lucide-react"

import { Button } from "@/components/ui/button"

/**
 * Shown when the browser reports no connection.
 *
 * It is served from the precached app shell, so it appears even on a cold
 * start with the network off. It never shows school data: the worker caches no
 * API response (docs/WEB_APP_PLAN.md, D1), so there is nothing to display.
 */
export function OfflinePage() {
  return (
    <main className="flex min-h-svh flex-col items-center justify-center gap-6 bg-background px-6 py-12 text-center">
      <img
        src="/hcci-logo.png"
        alt="HIS CARE CHRISTIAN INSTITUTE seal"
        className="size-24"
      />
      <span className="flex size-12 items-center justify-center rounded-full bg-muted text-muted-foreground">
        <WifiOff className="size-6" aria-hidden="true" />
      </span>
      <div className="max-w-md space-y-2">
        <h1 className="text-2xl font-bold text-foreground">You are offline</h1>
        <p className="text-sm leading-relaxed text-muted-foreground">
          AEGIS needs an internet connection to show your school data. Nothing
          is stored on this device, so reconnect to continue.
        </p>
      </div>
      <Button onClick={() => window.location.reload()}>Try again</Button>
      <p className="text-xs text-muted-foreground">
        AEGIS continues automatically when the connection returns.
      </p>
    </main>
  )
}

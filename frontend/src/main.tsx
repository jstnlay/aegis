import { StrictMode } from "react"
import { createRoot } from "react-dom/client"
import { RouterProvider } from "react-router-dom"
import { QueryClientProvider } from "@tanstack/react-query"

import { ErrorBoundary } from "@/components/ErrorBoundary"
import { OfflineGate } from "@/features/pwa/OfflineGate"
// Registers the `beforeinstallprompt` listener at start-up, before the account
// menu exists. The event fires once; a listener mounted with the menu is late.
import "@/features/pwa/install-prompt"
import { AuthProvider } from "@/features/auth/AuthContext"
import { initErrorReporting } from "@/lib/error-reporting"
import { queryClient } from "@/lib/queryClient"
import { router } from "@/routes/router"

import "./index.css"

// Fire-and-forget, and a no-op unless VITE_SENTRY_DSN is set: the SDK loads in
// its own chunk, so the render below is never waiting on it.
initErrorReporting()

const container = document.getElementById("root")

if (!container) {
  throw new Error("Root element #root not found")
}

createRoot(container).render(
  <StrictMode>
    {/*
      Last-resort boundary. `AppShell` already traps route-level failures, so
      this only catches a throw above the router — a broken provider or a
      failed initial render — and keeps it from tearing down `#root` and
      leaving a blank page.
    */}
    <ErrorBoundary label="AEGIS">
      <OfflineGate>
        <QueryClientProvider client={queryClient}>
          <AuthProvider>
            <RouterProvider router={router} />
          </AuthProvider>
        </QueryClientProvider>
      </OfflineGate>
    </ErrorBoundary>
  </StrictMode>
)

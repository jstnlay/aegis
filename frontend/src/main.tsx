import { StrictMode } from "react"
import { createRoot } from "react-dom/client"
import { RouterProvider } from "react-router-dom"
import { QueryClientProvider } from "@tanstack/react-query"

import { ErrorBoundary } from "@/components/ErrorBoundary"
import { AuthProvider } from "@/features/auth/AuthContext"
import { queryClient } from "@/lib/queryClient"
import { router } from "@/routes/router"

import "./index.css"

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
      <QueryClientProvider client={queryClient}>
        <AuthProvider>
          <RouterProvider router={router} />
        </AuthProvider>
      </QueryClientProvider>
    </ErrorBoundary>
  </StrictMode>
)

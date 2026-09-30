import { StrictMode } from "react"
import { createRoot } from "react-dom/client"
import { RouterProvider } from "react-router-dom"
import { QueryClientProvider } from "@tanstack/react-query"

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
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <RouterProvider router={router} />
      </AuthProvider>
    </QueryClientProvider>
  </StrictMode>
)

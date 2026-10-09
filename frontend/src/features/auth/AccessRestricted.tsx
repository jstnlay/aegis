import { ShieldAlert } from "lucide-react"
import { Link } from "react-router-dom"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { ROLE_LABELS } from "@/lib/roles"
import type { Role } from "@/types/auth"

/**
 * Shown when an authenticated user opens a URL their role does not own.
 *
 * `RequireRole` used to answer every mismatch with a silent
 * `<Navigate to="/app" replace />`. The redirect never reached a `Forbidden`
 * response body (that is `apiClient`'s job), so from the user's seat a wrong
 * URL simply *moved them* to the dashboard: the QA log recorded this as
 * "no message — silently redirected", which is indistinguishable from a bug.
 *
 * Staying on the URL and saying why fixes both readings — the user learns
 * which audience the page is for and that no restricted data was loaded, and
 * the URL still shows where they tried to go. The backend stays the
 * authorization authority: every request the page would make is independently
 * rejected by `core/permissions.py`.
 */
export function AccessRestricted({
  allowedRoles,
}: {
  allowedRoles: readonly Role[]
}) {
  const audience = allowedRoles.map((role) => ROLE_LABELS[role]).join(" or ")

  return (
    <Card role="alert" aria-labelledby="access-restricted-title">
      <CardHeader>
        <CardTitle as="h2" id="access-restricted-title">
          <span className="inline-flex items-center gap-2">
            <ShieldAlert aria-hidden="true" className="size-4" />
            Access restricted
          </span>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <p>
          This page is for {audience} accounts only. Your account does not have
          access to it, so none of its data was loaded.
        </p>
        <p className="text-muted-foreground">
          The server enforces this too: every request to this area is rejected
          for your role regardless of what the page renders.
        </p>
        <Button asChild variant="outline">
          <Link to="/app">Go to my dashboard</Link>
        </Button>
      </CardContent>
    </Card>
  )
}

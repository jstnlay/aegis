import {
  BookOpen,
  ClipboardCheck,
  MessageSquare,
  Settings,
  Users,
  type LucideIcon,
} from "lucide-react"
import { Navigate, useOutlet } from "react-router-dom"

import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardHeader } from "@/components/ui/card"
import { useAuth } from "@/features/auth/AuthContext"
import { ROLE_LABELS, userDisplayName } from "@/lib/roles"
import type { Role } from "@/types/auth"

/**
 * Role-specific landing content rendered inside the shared Dashboard route.
 *
 * This is the fallback for a role whose nested dashboard route did not match.
 * Each role's real dashboard normally renders instead (see
 * `RoleDashboardRedirect`).
 *
 * It identifies the role and nothing more. An earlier revision kept a
 * per-role `upcomingFeatures` array rendered under a "Coming Soon" heading;
 * by PH11.9 that array described grades, attendance, assessments, risk alerts,
 * consultations and interventions as future work when all of them shipped, and
 * duplicated the sidebar besides.
 */

interface RoleLandingProps {
  role: Role
}

interface RoleContent {
  title: string
  icon: LucideIcon
}

const ROLE_CONTENT: Record<Role, RoleContent> = {
  student: { title: "Student Portal", icon: BookOpen },
  parent: { title: "Parent Portal", icon: Users },
  faculty: { title: "Faculty Dashboard", icon: ClipboardCheck },
  guidance: { title: "Guidance Center", icon: MessageSquare },
  admin: { title: "Administration Panel", icon: Settings },
}

function RoleLandingContent({ role }: RoleLandingProps) {
  const { user } = useAuth()
  const name = userDisplayName(user)
  const content = ROLE_CONTENT[role]
  const Icon = content.icon

  return (
    <div className="space-y-6">
      <div className="space-y-1">
        <div className="flex items-center gap-3">
          <h2 className="text-2xl font-bold text-foreground">
            {content.title}
          </h2>
          <Badge
            variant="outline"
            className="border-border bg-maroon-100 text-maroon-800"
          >
            {ROLE_LABELS[role]}
          </Badge>
        </div>
        <p className="text-sm text-muted-foreground">
          {name ? `Welcome back, ${name}.` : "Welcome."}
        </p>
      </div>

      <Card>
        <CardHeader className="gap-1">
          <div className="flex items-center gap-2">
            <Icon className="size-4 text-muted-foreground" aria-hidden="true" />
            <h3 className="text-lg font-semibold">Getting around</h3>
          </div>
        </CardHeader>
        <CardContent>
          {/*
           * PH11.5 listed this role's features here under a "Coming Soon"
           * heading, and PH11.8/11.9 made every one of those claims false —
           * grades, attendance, assessments, risk alerts, consultations and
           * interventions all ship. The list was also pure duplication: the
           * sidebar already renders the same items, as real links, grouped the
           * same way, so repeating them produced two elements with the same
           * accessible name per destination.
           *
           * Navigation is the sidebar's job. This page now only identifies the
           * signed-in role; a role that reaches it has no matching dashboard
           * route, and the sidebar is where everything else is reached.
           */}
          <p className="text-sm text-muted-foreground">
            Use the navigation menu to reach the screens available to your
            account.
          </p>
        </CardContent>
      </Card>
    </div>
  )
}

/**
 * Layout for the /app/dashboard route.
 *
 * Renders the matched nested role dashboard via <Outlet />. Falls back to
 * the role landing content when no nested route is matched (e.g. when
 * rendered directly without children).
 */
export function RoleLandingPage() {
  const outlet = useOutlet()
  const { user } = useAuth()

  if (outlet) return outlet

  return user ? <RoleLandingContent role={user.role} /> : null
}

/** Role-aware redirect for the bare /app/dashboard index route. */
const ROLE_DASHBOARD_PATHS: Record<Role, string> = {
  student: "student",
  parent: "parent",
  faculty: "faculty",
  guidance: "guidance",
  admin: "admin",
}

export function RoleDashboardRedirect() {
  const { user } = useAuth()
  const target = user ? ROLE_DASHBOARD_PATHS[user.role] : "student"
  return <Navigate to={target} replace />
}

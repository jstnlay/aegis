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
 * These are NOT complete dashboards. Each identifies the current role,
 * shows a greeting, and provides a clear place for later role-specific
 * features — without fabricated statistics, charts, or user data.
 */

interface RoleLandingProps {
  role: Role
}

interface RoleContent {
  title: string
  description: string
  icon: LucideIcon
  upcomingFeatures: readonly string[]
}

const ROLE_CONTENT: Record<Role, RoleContent> = {
  student: {
    title: "Student Portal",
    description:
      "Your academic overview, attendance, and assessments will appear here.",
    icon: BookOpen,
    upcomingFeatures: [
      "My Grades",
      "Attendance Records",
      "Take Assessments",
      "Resources",
    ],
  },
  parent: {
    title: "Parent Portal",
    description:
      "Your child's academic progress, attendance, and reports will appear here.",
    icon: Users,
    upcomingFeatures: [
      "Child's Grades",
      "Attendance Overview",
      "School Reports",
    ],
  },
  faculty: {
    title: "Faculty Dashboard",
    description:
      "Your classes, grade encoding, and attendance management will appear here.",
    icon: ClipboardCheck,
    upcomingFeatures: [
      "My Classes",
      "Grade Encoding",
      "Record Attendance",
      "Create Assessments",
      "Behavioral Notes",
    ],
  },
  guidance: {
    title: "Guidance Center",
    description:
      "Student risk alerts, consultations, and intervention tracking will appear here.",
    icon: MessageSquare,
    upcomingFeatures: [
      "Risk Alerts",
      "Student Monitoring",
      "Consultations",
      "Intervention Plans",
      "Wellness Assessments",
    ],
  },
  admin: {
    title: "Administration Panel",
    description:
      "School-wide management, user administration, and analytics will appear here.",
    icon: Settings,
    upcomingFeatures: [
      "User Management",
      "Academic Configuration",
      "Analytics",
      "Data Import",
      "CMS",
      "Audit Logs",
    ],
  },
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
          <h1 className="text-2xl font-bold text-foreground">
            {content.title}
          </h1>
          <Badge
            variant="outline"
            className="border-border bg-maroon-100 text-maroon-800"
          >
            {ROLE_LABELS[role]}
          </Badge>
        </div>
        <p className="text-sm text-muted-foreground">
          {name ? `Welcome back, ${name}.` : "Welcome."} {content.description}
        </p>
      </div>

      <Card>
        <CardHeader className="gap-1">
          <div className="flex items-center gap-2">
            <Icon className="size-4 text-muted-foreground" aria-hidden="true" />
            <h2 className="text-lg font-semibold">Coming Soon</h2>
          </div>
        </CardHeader>
        <CardContent>
          <p className="mb-3 text-sm text-muted-foreground">
            The following features are planned for your role:
          </p>
          <ul className="space-y-1.5">
            {content.upcomingFeatures.map((feature) => (
              <li
                key={feature}
                className="flex min-w-0 items-center gap-2 text-sm text-foreground"
              >
                <span
                  className="size-1.5 shrink-0 rounded-full bg-maroon-300"
                  aria-hidden="true"
                />
                {feature}
              </li>
            ))}
          </ul>
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

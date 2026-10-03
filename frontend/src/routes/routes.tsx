import { Navigate, type RouteObject } from "react-router-dom"

import { AppShell } from "@/components/layout/AppShell"
import { ProtectedRoute } from "@/features/auth/ProtectedRoute"
import { RequireRole } from "@/features/auth/RequireRole"
import { AcademicsPage } from "@/features/academics/AcademicsPage"
import { AttendancePage } from "@/features/attendance/AttendancePage"
import { AssessmentsPage } from "@/features/guidance/AssessmentsPage"
import { ConsultationsPage } from "@/features/guidance/ConsultationsPage"
import { InterventionsPage } from "@/features/guidance/InterventionsPage"
import { RiskAlertsPage } from "@/features/guidance/RiskAlertsPage"
import { StudentProfilePage } from "@/features/guidance/StudentProfilePage"
import { StudentsPage } from "@/features/guidance/StudentsPage"
import { NotificationsPage } from "@/features/notifications/NotificationsPage"
import { AccountSettingsPage } from "@/features/settings/AccountSettingsPage"
import { ChangePasswordPage } from "@/routes/pages/ChangePasswordPage"
import { LoginPage } from "@/routes/pages/LoginPage"
import { NotFoundPage } from "@/routes/pages/NotFoundPage"
import {
  RoleDashboardRedirect,
  RoleLandingPage,
} from "@/routes/pages/RoleLandingPage"
import { StudentDashboard } from "@/features/student/StudentDashboard"
import { ParentDashboard } from "@/features/parent/ParentDashboard"
import { FacultyDashboard } from "@/features/faculty/FacultyDashboard"
import { GuidanceDashboard } from "@/features/guidance/GuidanceDashboard"
import { AdminDashboard } from "@/features/admin/AdminDashboard"

export const appRoutes: RouteObject[] = [
  { path: "/login", element: <LoginPage /> },
  { path: "/change-password", element: <ChangePasswordPage /> },
  {
    path: "/",
    element: <ProtectedRoute />,
    children: [
      { index: true, element: <Navigate to="/app" replace /> },
      {
        path: "app",
        element: <AppShell />,
        children: [
          { index: true, element: <Navigate to="dashboard" replace /> },
          {
            path: "dashboard",
            element: <RoleLandingPage />,
            children: [
              {
                path: "student",
                element: (
                  <RequireRole allowedRoles={["student"]}>
                    <StudentDashboard />
                  </RequireRole>
                ),
              },
              {
                path: "parent",
                element: (
                  <RequireRole allowedRoles={["parent"]}>
                    <ParentDashboard />
                  </RequireRole>
                ),
              },
              {
                path: "faculty",
                element: (
                  <RequireRole allowedRoles={["faculty"]}>
                    <FacultyDashboard />
                  </RequireRole>
                ),
              },
              {
                path: "guidance",
                element: (
                  <RequireRole allowedRoles={["guidance"]}>
                    <GuidanceDashboard />
                  </RequireRole>
                ),
              },
              {
                path: "admin",
                element: (
                  <RequireRole allowedRoles={["admin"]}>
                    <AdminDashboard />
                  </RequireRole>
                ),
              },
              { index: true, element: <RoleDashboardRedirect /> },
            ],
          },
          {
            // PH11.7: one route, role-appropriate content. The backend scopes
            // every grade/attendance queryset to the caller, so the page never
            // filters by identity itself. Admin keeps the read-only placeholder
            // because PH11.7 covers student and faculty surfaces only.
            path: "academics",
            element: (
              <RequireRole allowedRoles={["student", "faculty", "admin"]}>
                <AcademicsPage />
              </RequireRole>
            ),
          },
          {
            path: "attendance",
            element: (
              <RequireRole allowedRoles={["student", "faculty"]}>
                <AttendancePage />
              </RequireRole>
            ),
          },
          /* PH11.8: the guidance surface. Every route below is guidance-only
             because the backend either scopes it to the counselor
             (consultations, interventions) or is guidance-specific
             (risk alerts, wellness/behavioral assessments). Risk alerts,
             grades, attendance and behavioral notes are school-wide to
             guidance, but no other role has a verified surface for them yet,
             so they are not opened up here. */
          {
            path: "risk-alerts",
            element: (
              <RequireRole allowedRoles={["guidance"]}>
                <RiskAlertsPage />
              </RequireRole>
            ),
          },
          {
            path: "consultations",
            element: (
              <RequireRole allowedRoles={["guidance"]}>
                <ConsultationsPage />
              </RequireRole>
            ),
          },
          {
            path: "interventions",
            element: (
              <RequireRole allowedRoles={["guidance"]}>
                <InterventionsPage />
              </RequireRole>
            ),
          },
          {
            path: "students",
            element: (
              <RequireRole allowedRoles={["guidance"]}>
                <StudentsPage />
              </RequireRole>
            ),
          },
          {
            path: "students/:studentId",
            element: (
              <RequireRole allowedRoles={["guidance"]}>
                <StudentProfilePage />
              </RequireRole>
            ),
          },
          {
            // PH11.8: this is the *guidance* assessments surface — only the
            // wellness/behavioral assessments the counselor created. It is a
            // distinct route from the faculty/admin assessment work, which
            // `RequireRole` keeps restricted to its own roles.
            path: "assessments",
            element: (
              <RequireRole allowedRoles={["guidance"]}>
                <AssessmentsPage />
              </RequireRole>
            ),
          },
          {
            // PH11.9: opened to all five roles. `/notifications/` is scoped to
            // `recipient=request.user` server-side, so the same screen serves
            // every role over their own rows.
            path: "notifications",
            element: <NotificationsPage />,
          },
          {
            // PH11.9: opened to all five roles. `/accounts/me/` is
            // self-scoped and `/notifications/preferences/` is
            // `get_or_create(request.user)`, so there is no cross-account
            // surface here to guard. PH11.8 kept this guidance-only because
            // only the counselor's sidebar had been changed at the time.
            path: "account-settings",
            element: <AccountSettingsPage />,
          },
        ],
      },
    ],
  },
  { path: "*", element: <NotFoundPage /> },
]

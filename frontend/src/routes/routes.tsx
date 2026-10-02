import { Navigate, type RouteObject } from "react-router-dom"

import { AppShell } from "@/components/layout/AppShell"
import { ProtectedRoute } from "@/features/auth/ProtectedRoute"
import { RequireRole } from "@/features/auth/RequireRole"
import { AcademicsPage } from "@/features/academics/AcademicsPage"
import { AttendancePage } from "@/features/attendance/AttendancePage"
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
        ],
      },
    ],
  },
  { path: "*", element: <NotFoundPage /> },
]

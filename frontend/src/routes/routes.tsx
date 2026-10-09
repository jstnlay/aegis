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
import { StudentAssessmentsPage } from "@/features/student/StudentAssessmentsPage"
import { StudentDashboard } from "@/features/student/StudentDashboard"
import { StudentSchedulePage } from "@/features/student/StudentSchedulePage"
import { ParentDashboard } from "@/features/parent/ParentDashboard"
import { ParentAcademicsPage } from "@/features/parent/ParentAcademicsPage"
import { ParentAssessmentsPage } from "@/features/parent/ParentAssessmentsPage"
import { ParentSupportRoute } from "@/features/parent/ParentSupportRoute"
import { FacultyAdvisoryPage } from "@/features/faculty/FacultyAdvisoryPage"
import { FacultyAssessmentsPage } from "@/features/faculty/FacultyAssessmentsPage"
import { FacultyDashboard } from "@/features/faculty/FacultyDashboard"
import { FacultyImportPage } from "@/features/faculty/FacultyImportPage"
import { GuidanceDashboard } from "@/features/guidance/GuidanceDashboard"
import { AdminDashboard } from "@/features/admin/AdminDashboard"
import { AdminAcademicsPage } from "@/features/admin/AdminAcademicsPage"
import { AdminAnalyticsPage } from "@/features/admin/AdminAnalyticsPage"
import { AdminAttendancePage } from "@/features/admin/AdminAttendancePage"
import { AdminAuditPage } from "@/features/admin/AdminAuditPage"
import { AdminCmsPage } from "@/features/admin/AdminCmsPage"
import { AdminDataPage } from "@/features/admin/AdminDataPage"
import { AdminGradesPage } from "@/features/admin/AdminGradesPage"
import { AdminUsersPage } from "@/features/admin/AdminUsersPage"

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
            // filters by identity itself.
            //
            // PH11.9 removed `admin` from this route. It served
            // `AcademicsLandingPage`, a placeholder that pointed admin at "the
            // Administration section of this workspace" — a section that had no
            // routes at all. Admin now has real pages under /app/admin/*, so
            // RequireRole sends it to its own surfaces instead.
            path: "academics",
            element: (
              <RequireRole allowedRoles={["student", "faculty"]}>
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
          {
            /*
             * Class schedule (TC-STU-04 / FR-018).
             *
             * `ScheduleViewSet` returns, for a student, only the schedules of
             * their own section and is read-only for every non-admin role, so
             * the page renders the rows the server chose and filters nothing.
             */
            path: "schedule",
            element: (
              <RequireRole allowedRoles={["student"]}>
                <StudentSchedulePage />
              </RequireRole>
            ),
          },
          {
            /*
             * Student assessments (objective 2.4).
             *
             * `AssessmentViewSet.get_queryset` returns, for a student, only
             * published assessments targeting them or their section, and
             * `AssessmentResultViewSet.get_queryset` returns only their own
             * submissions. The page therefore filters by nothing itself.
             */
            path: "student/assessments",
            element: (
              <RequireRole allowedRoles={["student"]}>
                <StudentAssessmentsPage />
              </RequireRole>
            ),
          },
          {
            /*
             * Faculty assessments, academic only.
             *
             * Its own route rather than the shared `assessments` path, which
             * `RequireRole` keeps guidance-only for their wellness/behavioral
             * assessments. The split mirrors `Assessment.clean()`: academic
             * requires `creator_role="faculty"`, wellness and behavioral require
             * `creator_role="guidance"`, so the two surfaces cannot overlap.
             */
            path: "faculty/assessments",
            element: (
              <RequireRole allowedRoles={["faculty"]}>
                <FacultyAssessmentsPage />
              </RequireRole>
            ),
          },
          {
            /*
             * Faculty bulk upload. Its own route because `/app/assessments`
             * belongs to guidance and the import surface must not collide with
             * it. The backend scopes the listing to the caller's own jobs and
             * accepts only grades/attendance from faculty.
             */
            path: "faculty/import",
            element: (
              <RequireRole allowedRoles={["faculty"]}>
                <FacultyImportPage />
              </RequireRole>
            ),
          },
          {
            /*
             * Advisory class roster + behavioral notes (TC-FAC-07 / 08).
             * Faculty-only: the roster comes from the role-scoped enrollment
             * queryset and `BehavioralNoteViewSet` accepts writes from
             * `IsFacultyUser` alone, so no other role may land here.
             */
            path: "faculty/advisory",
            element: (
              <RequireRole allowedRoles={["faculty"]}>
                <FacultyAdvisoryPage />
              </RequireRole>
            ),
          },
          /* PH11.9: the parent surface. Every route here is parent-only, and
             each page selects a child client-side from the linked set that
             `EnrollmentViewSet` returns — that queryset is already scoped to
             `ParentStudentLink` children, so no child UUID from another family
             can appear in the picker or be requested by these pages.

             None of these routes is shared with another role. A student reads
             their own records with no selector, and a counselor reads
             school-wide data under the guidance routes below. */
          {
            path: "parent/academics",
            element: (
              <RequireRole allowedRoles={["parent"]}>
                <ParentAcademicsPage />
              </RequireRole>
            ),
          },
          {
            path: "parent/assessments",
            element: (
              <RequireRole allowedRoles={["parent"]}>
                <ParentAssessmentsPage />
              </RequireRole>
            ),
          },
          {
            path: "parent/support",
            element: (
              <RequireRole allowedRoles={["parent"]}>
                <ParentSupportRoute />
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
          /* PH11.9: the admin surface. Each route is admin-only and each is
             built from an endpoint verified during this phase. Where the backend
             does not support an operation - an attendance write, a user update,
             a system setting - the page says so rather than offering a control
             that could only fail. See docs/PH11.9_NOTE.md for the
             endpoint-by-endpoint map and the operations deliberately left out. */
          {
            path: "admin/academics",
            element: (
              <RequireRole allowedRoles={["admin"]}>
                <AdminAcademicsPage />
              </RequireRole>
            ),
          },
          {
            path: "admin/grades",
            element: (
              <RequireRole allowedRoles={["admin"]}>
                <AdminGradesPage />
              </RequireRole>
            ),
          },
          {
            path: "admin/attendance",
            element: (
              <RequireRole allowedRoles={["admin"]}>
                <AdminAttendancePage />
              </RequireRole>
            ),
          },
          {
            path: "admin/analytics",
            element: (
              <RequireRole allowedRoles={["admin"]}>
                <AdminAnalyticsPage />
              </RequireRole>
            ),
          },
          {
            path: "admin/users",
            element: (
              <RequireRole allowedRoles={["admin"]}>
                <AdminUsersPage />
              </RequireRole>
            ),
          },
          {
            path: "admin/data",
            element: (
              <RequireRole allowedRoles={["admin"]}>
                <AdminDataPage />
              </RequireRole>
            ),
          },
          {
            path: "admin/cms",
            element: (
              <RequireRole allowedRoles={["admin"]}>
                <AdminCmsPage />
              </RequireRole>
            ),
          },
          {
            path: "admin/audit",
            element: (
              <RequireRole allowedRoles={["admin"]}>
                <AdminAuditPage />
              </RequireRole>
            ),
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

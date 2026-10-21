from django.urls import path

from ..views import (
    AdminParentInvitationApproveView,
    AdminParentInvitationListView,
    AdminParentInvitationRejectView,
    AdminRegistrationApproveView,
    AdminRegistrationListView,
    AdminRegistrationRejectView,
    ConsentListView,
    ConsentRevokeView,
    CurrentUserView,
    FacultyProfileListView,
    ParentInvitationAcceptView,
    ParentInvitationCreateView,
    PasswordChangeView,
    PasswordForgotView,
    PasswordResetView,
    RegistrationSubmitView,
    RegistrationVerifyView,
    UserCreateView,
    UserDetailView,
    UserListView,
)

app_name = "accounts"

urlpatterns = [
    path("users/", UserListView.as_view(), name="user-list"),
    path("users/<uuid:pk>/", UserDetailView.as_view(), name="user-detail"),
    path("users/create/", UserCreateView.as_view(), name="user-create"),
    path(
        "faculty-profiles/",
        FacultyProfileListView.as_view(),
        name="faculty-profile-list",
    ),
    path("me/", CurrentUserView.as_view(), name="current-user"),
    path("password/change/", PasswordChangeView.as_view(), name="password-change"),
    # Password recovery. Both are anonymous: the reset token is the
    # credential, so neither needs a session.
    path("password/forgot/", PasswordForgotView.as_view(), name="password-forgot"),
    path("password/reset/", PasswordResetView.as_view(), name="password-reset"),
    # Student registration. A request is not an account: it carries no role
    # and no permissions, and only an administrator turns it into one.
    path(
        "registrations/",
        RegistrationSubmitView.as_view(),
        name="registration-submit",
    ),
    path(
        "registrations/verify/",
        RegistrationVerifyView.as_view(),
        name="registration-verify",
    ),
    # Parent invitations. A nomination creates no account; an
    # administrator approves it and the parent accepts the link.
    path(
        "parent-invitations/",
        ParentInvitationCreateView.as_view(),
        name="parent-invitation-create",
    ),
    path(
        "parent-invitations/accept/",
        ParentInvitationAcceptView.as_view(),
        name="parent-invitation-accept",
    ),
    path(
        "admin/parent-invitations/",
        AdminParentInvitationListView.as_view(),
        name="admin-parent-invitation-list",
    ),
    path(
        "admin/parent-invitations/<uuid:pk>/approve/",
        AdminParentInvitationApproveView.as_view(),
        name="admin-parent-invitation-approve",
    ),
    path(
        "admin/parent-invitations/<uuid:pk>/reject/",
        AdminParentInvitationRejectView.as_view(),
        name="admin-parent-invitation-reject",
    ),
    # The review queue. Administrator only, like every other administrator
    # surface.
    path(
        "admin/registrations/",
        AdminRegistrationListView.as_view(),
        name="admin-registration-list",
    ),
    path(
        "admin/registrations/<uuid:pk>/approve/",
        AdminRegistrationApproveView.as_view(),
        name="admin-registration-approve",
    ),
    path(
        "admin/registrations/<uuid:pk>/reject/",
        AdminRegistrationRejectView.as_view(),
        name="admin-registration-reject",
    ),
    # NFR-010 / TC-ADM-17. `revoke` is a PATCH-only action, not a DELETE:
    # revocation closes the row so the history survives.
    path("consents/", ConsentListView.as_view(), name="consent-list"),
    path(
        "consents/<uuid:pk>/revoke/",
        ConsentRevokeView.as_view(),
        name="consent-revoke",
    ),
]

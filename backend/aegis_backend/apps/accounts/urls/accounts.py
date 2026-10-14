from django.urls import path

from ..views import (
    ConsentListView,
    ConsentRevokeView,
    CurrentUserView,
    FacultyProfileListView,
    PasswordChangeView,
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
    # NFR-010 / TC-ADM-17. `revoke` is a PATCH-only action, not a DELETE:
    # revocation closes the row so the history survives.
    path("consents/", ConsentListView.as_view(), name="consent-list"),
    path(
        "consents/<uuid:pk>/revoke/",
        ConsentRevokeView.as_view(),
        name="consent-revoke",
    ),
]

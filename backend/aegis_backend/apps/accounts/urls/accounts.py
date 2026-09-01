from django.urls import path

from ..views import (
    CurrentUserView,
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
    path("me/", CurrentUserView.as_view(), name="current-user"),
    path("password/change/", PasswordChangeView.as_view(), name="password-change"),
]

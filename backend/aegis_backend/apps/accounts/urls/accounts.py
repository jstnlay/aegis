from django.urls import path

from ..views import UserListView, UserDetailView, UserCreateView, CurrentUserView

app_name = "accounts"

urlpatterns = [
    path("users/", UserListView.as_view(), name="user-list"),
    path("users/<uuid:pk>/", UserDetailView.as_view(), name="user-detail"),
    path("users/create/", UserCreateView.as_view(), name="user-create"),
    path("me/", CurrentUserView.as_view(), name="current-user"),
]

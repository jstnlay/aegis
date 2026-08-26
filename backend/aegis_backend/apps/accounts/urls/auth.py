from django.urls import path

from ..views import LoginView, LogoutView, TokenRefreshView

app_name = "accounts-auth"

urlpatterns = [
    path("login/", LoginView.as_view(), name="token_obtain_pair"),
    path("token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("logout/", LogoutView.as_view(), name="logout"),
]

"""
API v1 URL configuration.

All versioned endpoints are routed through here.
"""

from django.urls import path, include

urlpatterns = [
    path("auth/", include("apps.accounts.urls.auth")),
    path("accounts/", include("apps.accounts.urls.accounts")),
]

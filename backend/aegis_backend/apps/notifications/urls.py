from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import NotificationViewSet, NotificationPreferenceView

app_name = "notifications"

router = DefaultRouter()
router.register(r"", NotificationViewSet, basename="notification")

urlpatterns = [
    path("preferences/", NotificationPreferenceView.as_view(), name="notification-preferences"),
    path("", include(router.urls)),
]

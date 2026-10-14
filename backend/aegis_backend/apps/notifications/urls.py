from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    MaintenanceWindowList,
    NotificationViewSet,
    NotificationPreferenceView,
)

app_name = "notifications"

router = DefaultRouter()
router.register(r"", NotificationViewSet, basename="notification")

urlpatterns = [
    path("preferences/", NotificationPreferenceView.as_view(), name="notification-preferences"),
    # NFR-012 / TC-SYS-08. Declared before the router's `r""` registration so
    # it is matched first - `""` is greedy and would otherwise capture
    # "maintenance/" as a notification primary key.
    path(
        "maintenance/",
        MaintenanceWindowList.as_view(),
        name="maintenance-window-list",
    ),
    path("", include(router.urls)),
]

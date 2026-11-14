from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    MaintenanceWindowList,
    NotificationViewSet,
    NotificationPreferenceView,
    PushSubscriptionDetail,
    PushSubscriptionListCreate,
)

app_name = "notifications"

router = DefaultRouter()
router.register(r"", NotificationViewSet, basename="notification")

urlpatterns = [
    path("preferences/", NotificationPreferenceView.as_view(), name="notification-preferences"),
    path(
        "push-subscriptions/",
        PushSubscriptionListCreate.as_view(),
        name="push-subscription-list",
    ),
    path(
        "push-subscriptions/<uuid:pk>/",
        PushSubscriptionDetail.as_view(),
        name="push-subscription-detail",
    ),
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

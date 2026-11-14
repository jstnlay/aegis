from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils import timezone
from rest_framework import viewsets, generics, status, mixins
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.permissions import IsAdminUser

from .events import schedule_maintenance_window
from .models import (
    MaintenanceWindow,
    Notification,
    NotificationPreference,
    PushSubscription,
)
from .serializers import (
    NotificationSerializer,
    NotificationPreferenceSerializer,
    MaintenanceWindowSerializer,
    PushSubscriptionSerializer,
)


class NotificationViewSet(mixins.DestroyModelMixin, viewsets.ReadOnlyModelViewSet):
    """
    Read and delete the requesting user's notifications.

    - GET  /notifications/            — list (paginated, filterable)
    - GET  /notifications/{id}/       — retrieve
    - DELETE /notifications/{id}/    — delete own notification
    - POST /notifications/{id}/read/  — mark one as read
    - POST /notifications/read-all/   — mark all as read
    """

    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = Notification.objects.filter(recipient=self.request.user)

        is_read = self.request.query_params.get("is_read")
        if is_read is not None:
            qs = qs.filter(is_read=is_read.lower() == "true")

        notification_type = self.request.query_params.get("notification_type")
        if notification_type:
            qs = qs.filter(notification_type=notification_type)

        return qs

    @action(detail=True, methods=["post"], url_path="read")
    def mark_read(self, request, pk=None):
        """Mark a single notification as read."""
        notification = self.get_object()
        if not notification.is_read:
            notification.is_read = True
            notification.read_at = timezone.now()
            notification.save(update_fields=["is_read", "read_at", "updated_at"])
        return Response(
            {"success": True, "message": "Notification marked as read."},
            status=status.HTTP_200_OK,
        )

    @action(detail=False, methods=["post"], url_path="read-all")
    def mark_all_read(self, request):
        """Mark all unread notifications as read."""
        updated = Notification.objects.filter(
            recipient=request.user,
            is_read=False,
        ).update(is_read=True, read_at=timezone.now())
        return Response(
            {
                "success": True,
                "message": "All notifications marked as read.",
                "count": updated,
            },
            status=status.HTTP_200_OK,
        )


class NotificationPreferenceView(generics.RetrieveUpdateAPIView):
    """
    GET /notifications/preferences/  — retrieve own preferences
    PUT /notifications/preferences/  — update own preferences
    """

    serializer_class = NotificationPreferenceSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        obj, _ = NotificationPreference.objects.get_or_create(user=self.request.user)
        return obj


class PushSubscriptionListCreate(generics.CreateAPIView):
    """
    POST /notifications/push-subscriptions/ — register this browser.

    Upserts on `endpoint`. A browser keeps the same endpoint across sign-ins, so
    a shared device that switches accounts moves the row to the new user instead
    of leaving the previous account subscribed to that browser.
    """

    serializer_class = PushSubscriptionSerializer
    permission_classes = [IsAuthenticated]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        subscription, created = PushSubscription.objects.update_or_create(
            endpoint=serializer.validated_data["endpoint"],
            defaults={
                "user": request.user,
                "p256dh": serializer.validated_data["p256dh"],
                "auth": serializer.validated_data["auth"],
            },
        )
        output = self.get_serializer(subscription)
        return Response(
            output.data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class PushSubscriptionDetail(generics.DestroyAPIView):
    """
    DELETE /notifications/push-subscriptions/{id}/ — forget this browser.

    The queryset is scoped to the caller, so another user's id is a 404 rather
    than a deletion.
    """

    serializer_class = PushSubscriptionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return PushSubscription.objects.filter(user=self.request.user)


class MaintenanceWindowList(generics.ListCreateAPIView):
    """
    Schedule and list maintenance windows (NFR-012, TC-SYS-08).

    Admin-only for both. Listing is unscoped because a maintenance window is
    system-wide by definition - there is no such thing as one role's downtime.

    `create` delegates to `events.schedule_maintenance_window` rather than
    saving the serializer directly, because the window and its notice have to
    land together. A plain `serializer.save()` would create the window and
    leave the notification to the caller, which is the one mistake this feature
    cannot survive.
    """

    serializer_class = MaintenanceWindowSerializer
    permission_classes = [IsAdminUser]
    pagination_class = None

    def get_queryset(self):
        return MaintenanceWindow.objects.all()

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated = serializer.validated_data

        try:
            window = schedule_maintenance_window(
                starts_at=validated["starts_at"],
                ends_at=validated["ends_at"],
                message=validated.get("message", ""),
                sender=request.user,
            )
        except DjangoValidationError as exc:
            # `clean()` speaks Django; the API speaks DRF. Translate once,
            # here, so no other caller has to care which exception it raised.
            raise DRFValidationError(exc.message_dict)

        return Response(
            self.get_serializer(window).data, status=status.HTTP_201_CREATED
        )

from django.utils import timezone
from rest_framework import viewsets, generics, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import Notification, NotificationPreference
from .serializers import NotificationSerializer, NotificationPreferenceSerializer


class NotificationViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Read-only access to the requesting user's notifications.

    - GET  /notifications/            — list (paginated, filterable)
    - GET  /notifications/{id}/       — retrieve
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

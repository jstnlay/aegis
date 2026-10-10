"""
Portfolio endpoints.

  GET    /api/v1/portfolio/entries/          — entries in the caller's scope
  POST   /api/v1/portfolio/entries/          — students only, on their own profile
  GET    /api/v1/portfolio/entries/{id}/     — one entry in scope
  PATCH  /api/v1/portfolio/entries/{id}/     — owning student only
  DELETE /api/v1/portfolio/entries/{id}/     — owning student only

Scope:
- student: own entries only
- parent: linked children's entries
- faculty/guidance/admin: all entries (read-only; writes are 403)
"""

from rest_framework import status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import PortfolioEntry
from .serializers import PortfolioEntrySerializer


def _get_student_profile(user):
    try:
        return user.student_profile
    except Exception:
        return None


def _get_linked_student_ids(user):
    from apps.accounts.models import ParentStudentLink

    try:
        parent_profile = user.parent_profile
    except Exception:
        return set()
    return set(
        ParentStudentLink.objects.filter(parent=parent_profile).values_list(
            "student_id", flat=True
        )
    )


class PortfolioEntryViewSet(viewsets.ModelViewSet):
    serializer_class = PortfolioEntrySerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_queryset(self):
        user = self.request.user
        qs = PortfolioEntry.objects.select_related("student__user").all()
        student_id = self.request.query_params.get("student")
        if user.role == "student":
            profile = _get_student_profile(user)
            if profile is None:
                return qs.none()
            qs = qs.filter(student=profile)
        elif user.role == "parent":
            qs = qs.filter(student_id__in=_get_linked_student_ids(user))
        if student_id:
            qs = qs.filter(student_id=student_id)
        return qs

    def _deny_unless_owning_student(self, entry):
        """Non-owners may read but never write."""
        if self.request.user.role != "student":
            return Response(
                {"detail": "Only the owning student can change portfolio entries."},
                status=status.HTTP_403_FORBIDDEN,
            )
        profile = _get_student_profile(self.request.user)
        if profile is None or entry.student_id != profile.id:
            return Response(
                {"detail": "Access denied."}, status=status.HTTP_403_FORBIDDEN
            )
        return None

    def create(self, request, *args, **kwargs):
        if request.user.role != "student":
            return Response(
                {"detail": "Only students can add portfolio entries."},
                status=status.HTTP_403_FORBIDDEN,
            )
        profile = _get_student_profile(request.user)
        if profile is None:
            return Response(
                {"detail": "No student profile for this account."},
                status=status.HTTP_403_FORBIDDEN,
            )
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(student=profile)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def partial_update(self, request, *args, **kwargs):
        entry = self.get_object()
        denied = self._deny_unless_owning_student(entry)
        if denied is not None:
            return denied
        return super().partial_update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        entry = self.get_object()
        denied = self._deny_unless_owning_student(entry)
        if denied is not None:
            return denied
        return super().destroy(request, *args, **kwargs)

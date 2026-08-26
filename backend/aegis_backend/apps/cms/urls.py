from django.urls import path

from .views import (
    CmsAnnouncementDetail,
    CmsAnnouncementList,
    CmsResourceDetail,
    CmsResourceFileDownload,
    CmsResourceList,
)

app_name = "cms"

urlpatterns = [
    path("announcements/", CmsAnnouncementList.as_view(), name="cms-announcement-list"),
    path(
        "announcements/<str:document_id>/",
        CmsAnnouncementDetail.as_view(),
        name="cms-announcement-detail",
    ),
    path("resources/", CmsResourceList.as_view(), name="cms-resource-list"),
    path(
        "resources/<str:document_id>/",
        CmsResourceDetail.as_view(),
        name="cms-resource-detail",
    ),
    # SEC-007: authorized download proxy for Strapi-hosted Resource files.
    path(
        "resources/<str:document_id>/file/",
        CmsResourceFileDownload.as_view(),
        name="cms-resource-file",
    ),
]

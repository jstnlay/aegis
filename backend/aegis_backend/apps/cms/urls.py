from django.urls import path

from .views import (
    CmsAnnouncementDetail,
    CmsAnnouncementList,
    CmsResourceDetail,
    CmsResourceFileDownload,
    CmsResourceList,
    PublicCmsAnnouncementList,
    PublicCmsResourceList,
)

app_name = "cms"

urlpatterns = [
    # Public landing-page feeds (anonymous). Declared before the
    # `<document_id>` patterns so "public" is never captured as an id.
    path(
        "announcements/public/",
        PublicCmsAnnouncementList.as_view(),
        name="cms-announcement-public-list",
    ),
    path(
        "resources/public/",
        PublicCmsResourceList.as_view(),
        name="cms-resource-public-list",
    ),
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

from django.urls import path

from .views import (
    CmsAnnouncementAdminDetail,
    CmsAnnouncementAdminList,
    CmsAnnouncementDetail,
    CmsAnnouncementImageDownload,
    CmsAnnouncementList,
    CmsResourceAdminDetail,
    CmsResourceAdminList,
    CmsResourceDetail,
    CmsResourceFileDownload,
    CmsResourceList,
    PublicCmsAnnouncementImageDownload,
    PublicCmsAnnouncementList,
    PublicCmsResourceList,
    SystemSettingDetail,
    SystemSettingList,
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
        "announcements/public/<str:document_id>/image/",
        PublicCmsAnnouncementImageDownload.as_view(),
        name="cms-announcement-public-image",
    ),
    path(
        "resources/public/",
        PublicCmsResourceList.as_view(),
        name="cms-resource-public-list",
    ),
    # Admin authoring routes. Declared before the `<document_id>` patterns so
    # "manage" is never captured as an announcement/resource id.
    path(
        "announcements/manage/",
        CmsAnnouncementAdminList.as_view(),
        name="cms-announcement-admin-list",
    ),
    path(
        "announcements/manage/<str:document_id>/",
        CmsAnnouncementAdminDetail.as_view(),
        name="cms-announcement-admin-detail",
    ),
    path(
        "resources/manage/",
        CmsResourceAdminList.as_view(),
        name="cms-resource-admin-list",
    ),
    path(
        "resources/manage/<str:document_id>/",
        CmsResourceAdminDetail.as_view(),
        name="cms-resource-admin-detail",
    ),
    path("announcements/", CmsAnnouncementList.as_view(), name="cms-announcement-list"),
    path(
        "announcements/<str:document_id>/image/",
        CmsAnnouncementImageDownload.as_view(),
        name="cms-announcement-image",
    ),
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
    # FR-034 / TC-ADM-11: runtime system-wide settings, addressed by key so a
    # caller can never be routed to a different setting by a reordered list.
    path("settings/", SystemSettingList.as_view(), name="system-setting-list"),
    path(
        "settings/<str:key>/",
        SystemSettingDetail.as_view(),
        name="system-setting-detail",
    ),
]

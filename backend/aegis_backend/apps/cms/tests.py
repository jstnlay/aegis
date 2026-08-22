"""
Phase 7 test suite for AEGIS CMS integration (Strapi).

Covers: webhook authentication/secret verification, event filtering,
canonical data validation/normalization, recipient resolution against
AEGIS Django users/roles, ANNOUNCEMENT_PUBLISHED dispatch through the
existing notification system, webhook idempotency, failure handling,
and the authenticated CMS read-through proxy endpoints.
"""

from datetime import date, timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import (
    FacultyProfile,
    ParentProfile,
    ParentStudentLink,
    StudentProfile,
)
from apps.academics.models import AcademicYear, GradeLevel, Section
from apps.cms.models import CmsWebhookEvent
from apps.cms.services.recipients import resolve_announcement_recipients
from apps.cms.services.strapi_client import normalize_announcement, normalize_resource
from apps.notifications.models import Notification

User = get_user_model()

WEBHOOK_URL = "/webhooks/strapi/announcements/"
SECRET = "phase7-test-webhook-secret"


def canonical_announcement(**overrides):
    """A valid normalized announcement as StrapiClient would return it."""
    data = {
        "document_id": "doc-abc123",
        "title": "Sports Fest",
        "content": "The annual sports fest is on Friday.",
        "announcement_type": "event",
        "priority": "normal",
        "target_roles": ["all"],
        "target_sections": [],
        "published_at": timezone.now(),
        "expires_at": None,
    }
    data.update(overrides)
    return data


def publish_payload(document_id="doc-abc123", published_at=None):
    """A Strapi entry.publish webhook payload."""
    return {
        "event": "entry.publish",
        "createdAt": (published_at or "2026-08-22T01:00:00.000Z"),
        "model": "announcement",
        "entry": {
            "id": 1,
            "documentId": document_id,
            "title": "Sports Fest",
            "publishedAt": (published_at or "2026-08-22T01:00:00.000Z"),
        },
    }


class CmsTestBase(TestCase):
    """Shared users/academic structure mirroring the other phase suites."""

    @classmethod
    def setUpTestData(cls):
        cls.admin_user = User.objects.create_user(
            email="admin_cms@test.com", password="pass12345",
            first_name="Admin", last_name="User", role="admin",
        )
        cls.faculty_user = User.objects.create_user(
            email="faculty_cms@test.com", password="pass12345",
            first_name="Fac", last_name="ulty", role="faculty",
        )
        cls.guidance_user = User.objects.create_user(
            email="guidance_cms@test.com", password="pass12345",
            first_name="Guid", last_name="ance", role="guidance",
        )
        cls.student_user = User.objects.create_user(
            email="student_cms@test.com", password="pass12345",
            first_name="Stu", last_name="dent", role="student",
        )
        cls.student2_user = User.objects.create_user(
            email="student2_cms@test.com", password="pass12345",
            first_name="Stu2", last_name="dent2", role="student",
        )
        cls.parent_user = User.objects.create_user(
            email="parent_cms@test.com", password="pass12345",
            first_name="Par", last_name="ent", role="parent",
        )
        # Inactive user must never receive anything.
        cls.inactive_student = User.objects.create_user(
            email="inactive_cms@test.com", password="pass12345",
            first_name="In", last_name="active", role="student",
        )
        cls.inactive_student.is_active = False
        cls.inactive_student.save(update_fields=["is_active"])

        cls.faculty_profile = FacultyProfile.objects.create(
            user=cls.faculty_user, employee_id="EMP-CMS-001", department="Math",
        )

        cls.academic_year = AcademicYear.objects.create(
            name="2026-2027", start_date=date(2026, 6, 1),
            end_date=date(2027, 3, 31), is_current=True,
        )
        cls.grade_level = GradeLevel.objects.create(name="Grade 7", level_number=7)
        cls.section_a = Section.objects.create(
            name="Einstein", grade_level=cls.grade_level,
            academic_year=cls.academic_year, adviser=cls.faculty_profile,
        )
        cls.section_b = Section.objects.create(
            name="Newton", grade_level=cls.grade_level,
            academic_year=cls.academic_year,
        )

        cls.student_profile = StudentProfile.objects.create(
            user=cls.student_user, student_id="STU-CMS-001",
            section=cls.section_a, grade_level=cls.grade_level,
            enrollment_date=date(2026, 6, 1),
        )
        cls.student2_profile = StudentProfile.objects.create(
            user=cls.student2_user, student_id="STU-CMS-002",
            section=cls.section_b, grade_level=cls.grade_level,
            enrollment_date=date(2026, 6, 1),
        )

        cls.parent_profile = ParentProfile.objects.create(
            user=cls.parent_user, relationship_to_student="mother",
        )
        ParentStudentLink.objects.create(
            parent=cls.parent_profile, student=cls.student_profile, is_primary=True,
        )


# ---------------------------------------------------------------------------
# Model tests
# ---------------------------------------------------------------------------


class CmsWebhookEventModelTest(CmsTestBase):
    def test_defaults_and_str(self):
        event = CmsWebhookEvent.objects.create(event_id="announcement:x:1")
        self.assertEqual(event.source, "strapi")
        self.assertEqual(event.status, CmsWebhookEvent.Status.PENDING)
        self.assertEqual(event.detail, {})
        self.assertIn("pending", str(event))

    def test_event_id_unique(self):
        CmsWebhookEvent.objects.create(event_id="announcement:dup:1")
        with self.assertRaises(Exception):
            CmsWebhookEvent.objects.create(event_id="announcement:dup:1")


# ---------------------------------------------------------------------------
# Webhook authentication / secret verification
# ---------------------------------------------------------------------------


@override_settings(STRAPI_WEBHOOK_SECRET=SECRET)
class WebhookAuthenticationTest(CmsTestBase):
    def setUp(self):
        self.client = APIClient()

    def test_missing_secret_header_rejected(self):
        response = self.client.post(WEBHOOK_URL, publish_payload(), format="json")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(Notification.objects.count(), 0)

    def test_wrong_secret_header_rejected(self):
        response = self.client.post(
            WEBHOOK_URL, publish_payload(), format="json", HTTP_X_AEGIS_WEBHOOK_SECRET="nope"
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(Notification.objects.count(), 0)

    def test_unconfigured_webhook_secret_returns_503(self):
        with override_settings(STRAPI_WEBHOOK_SECRET=""):
            response = self.client.post(
                WEBHOOK_URL, publish_payload(), format="json",
                HTTP_X_AEGIS_WEBHOOK_SECRET=SECRET,
            )
        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)

    def test_malformed_json_rejected(self):
        response = self.client.post(
            WEBHOOK_URL, data="{not json", content_type="application/json",
            HTTP_X_AEGIS_WEBHOOK_SECRET=SECRET,
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_non_dict_payload_rejected(self):
        response = self.client.post(
            WEBHOOK_URL, [1, 2, 3], format="json", HTTP_X_AEGIS_WEBHOOK_SECRET=SECRET
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_endpoint_requires_no_aegis_authentication(self):
        """Machine-to-machine: no JWT needed; secret header is the credential."""
        response = self.client.post(
            WEBHOOK_URL, publish_payload(), format="json",
            HTTP_X_AEGIS_WEBHOOK_SECRET=SECRET,
        )
        self.assertNotEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


# ---------------------------------------------------------------------------
# Event filtering (ignore non-announcement / non-publish events)
# ---------------------------------------------------------------------------


@override_settings(STRAPI_WEBHOOK_SECRET=SECRET)
class WebhookIgnoreTest(CmsTestBase):
    def setUp(self):
        self.client = APIClient()

    @mock.patch("apps.cms.services.webhook.StrapiClient")
    def _post(self, payload, mock_client_cls):
        return self.client.post(
            WEBHOOK_URL, payload, format="json", HTTP_X_AEGIS_WEBHOOK_SECRET=SECRET
        )

    def test_entry_create_ignored(self):
        payload = publish_payload()
        payload["event"] = "entry.create"
        response = self._post(payload)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], "ignored")

    def test_other_content_type_publish_ignored(self):
        payload = publish_payload()
        payload["model"] = "resource"
        response = self._post(payload)
        self.assertEqual(response.data["status"], "ignored")

    def test_ignored_events_do_not_notify_or_log_processing(self):
        payload = publish_payload()
        payload["event"] = "entry.unpublish"
        self._post(payload)
        self.assertEqual(Notification.objects.count(), 0)
        self.assertEqual(CmsWebhookEvent.objects.count(), 0)


# ---------------------------------------------------------------------------
# Full publication flow -> ANNOUNCEMENT_PUBLISHED notifications
# ---------------------------------------------------------------------------


@override_settings(STRAPI_WEBHOOK_SECRET=SECRET)
class AnnouncementPublishFlowTest(CmsTestBase):
    def setUp(self):
        self.client = APIClient()

    def _post_publish(self, payload=None, canonical=None):
        with mock.patch("apps.cms.services.webhook.StrapiClient") as mock_client:
            mock_client.return_value.get_announcement.return_value = (
                canonical or canonical_announcement()
            )
            return self.client.post(
                WEBHOOK_URL, payload or publish_payload(), format="json",
                HTTP_X_AEGIS_WEBHOOK_SECRET=SECRET,
            )

    def test_publish_notifies_all_active_users(self):
        response = self._post_publish()
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], "processed")

        notified_ids = set(
            Notification.objects.values_list("recipient_id", flat=True)
        )
        expected = {
            self.admin_user.id, self.faculty_user.id, self.guidance_user.id,
            self.student_user.id, self.student2_user.id, self.parent_user.id,
        }
        self.assertEqual(notified_ids, expected)
        for n in Notification.objects.all():
            self.assertEqual(n.notification_type, "ANNOUNCEMENT_PUBLISHED")
            self.assertEqual(n.title, "Announcement: Sports Fest")

    def test_publish_to_specific_roles(self):
        canonical = canonical_announcement(target_roles=["student", "parent"])
        self._post_publish(canonical=canonical)
        notified_roles = set(
            Notification.objects.values_list("recipient__role", flat=True)
        )
        self.assertEqual(notified_roles, {"student", "parent"})

    def test_publish_to_specific_section_scopes_students_and_parents(self):
        canonical = canonical_announcement(target_sections=["Einstein"])
        self._post_publish(canonical=canonical)
        recipients = set(Notification.objects.values_list("recipient_id", flat=True))
        # Staff see everything; students/parents limited to Einstein members.
        expected = {
            self.admin_user.id,
            self.faculty_user.id,
            self.guidance_user.id,
            self.student_user.id,   # Einstein student
            self.parent_user.id,    # parent of Einstein student
        }
        self.assertEqual(recipients, expected)
        self.assertNotIn(self.student2_user.id, recipients)  # Newton student

    def test_inactive_users_never_notified(self):
        self._post_publish()
        self.assertFalse(
            Notification.objects.filter(recipient=self.inactive_student).exists()
        )

    def test_link_and_dedup_key_set_on_notifications(self):
        self._post_publish()
        notification = Notification.objects.first()
        self.assertEqual(notification.link, "/announcements/doc-abc123")
        self.assertTrue(notification.deduplication_key.startswith("announcement:doc-abc123:"))

    def test_webhook_event_logged_as_processed_with_recipient_count(self):
        self._post_publish()
        event = CmsWebhookEvent.objects.get()
        self.assertEqual(event.status, CmsWebhookEvent.Status.PROCESSED)
        self.assertEqual(event.detail["recipient_count"], 6)
        self.assertEqual(event.source, "strapi")
        self.assertEqual(event.event_type, "entry.publish:announcement")

    def test_canonical_data_fetched_from_strapi_api(self):
        """Django must fetch the announcement from the REST API, not trust the payload."""
        payload = publish_payload(document_id="doc-canonical")
        payload["entry"]["title"] = "TAMPERED TITLE"
        canonical = canonical_announcement(document_id="doc-canonical", title="Real Title")
        with mock.patch("apps.cms.services.webhook.StrapiClient") as mock_client:
            mock_client.return_value.get_announcement.return_value = canonical
            self.client.post(
                WEBHOOK_URL, payload, format="json", HTTP_X_AEGIS_WEBHOOK_SECRET=SECRET
            )
        mock_client.return_value.get_announcement.assert_called_once_with("doc-canonical")
        self.assertEqual(
            Notification.objects.values_list("title", flat=True).distinct().first(),
            "Announcement: Real Title",
        )


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------


@override_settings(STRAPI_WEBHOOK_SECRET=SECRET)
class WebhookIdempotencyTest(CmsTestBase):
    def setUp(self):
        self.client = APIClient()

    def _deliver(self):
        with mock.patch("apps.cms.services.webhook.StrapiClient") as mock_client:
            mock_client.return_value.get_announcement.return_value = (
                canonical_announcement()
            )
            return self.client.post(
                WEBHOOK_URL, publish_payload(), format="json",
                HTTP_X_AEGIS_WEBHOOK_SECRET=SECRET,
            )

    def test_duplicate_delivery_does_not_duplicate_notifications(self):
        first = self._deliver()
        second = self._deliver()

        self.assertEqual(first.data["status"], "processed")
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.assertEqual(second.data["status"], "duplicate")
        self.assertEqual(Notification.objects.count(), 6)

    def test_duplicate_delivery_marks_no_second_event_row(self):
        self._deliver()
        self._deliver()
        self.assertEqual(CmsWebhookEvent.objects.count(), 1)
        self.assertEqual(
            CmsWebhookEvent.objects.get().status, CmsWebhookEvent.Status.PROCESSED
        )

    def test_notification_dedup_backstop_blocks_second_publication_cycle(self):
        """Republishing the same document (new publishedAt) is deduped only if key exists."""
        self._deliver()
        republish_payload = publish_payload(published_at="2026-08-23T09:00:00.000Z")
        with mock.patch("apps.cms.services.webhook.StrapiClient") as mock_client:
            mock_client.return_value.get_announcement.return_value = (
                canonical_announcement(
                    published_at=timezone.now() + timedelta(days=1)
                )
            )
            response = self.client.post(
                WEBHOOK_URL, republish_payload, format="json",
                HTTP_X_AEGIS_WEBHOOK_SECRET=SECRET,
            )
        # Different publication cycle -> processed again; dedup key differs so
        # this documents the intended per-cycle semantics.
        self.assertEqual(response.data["status"], "processed")
        cycle_keys = set(
            Notification.objects.values_list("deduplication_key", flat=True)
        )
        self.assertEqual(len(cycle_keys), 2)


# ---------------------------------------------------------------------------
# Failure handling
# ---------------------------------------------------------------------------


@override_settings(STRAPI_WEBHOOK_SECRET=SECRET)
class WebhookFailureHandlingTest(CmsTestBase):
    def setUp(self):
        self.client = APIClient()

    def test_strapi_unavailable_returns_502_and_marks_failed(self):
        from apps.cms.services.strapi_client import StrapiUnavailableError

        with mock.patch("apps.cms.services.webhook.StrapiClient") as mock_client:
            mock_client.return_value.get_announcement.side_effect = StrapiUnavailableError(
                "down"
            )
            response = self.client.post(
                WEBHOOK_URL, publish_payload(), format="json",
                HTTP_X_AEGIS_WEBHOOK_SECRET=SECRET,
            )
        self.assertEqual(response.status_code, status.HTTP_502_BAD_GATEWAY)
        self.assertEqual(CmsWebhookEvent.objects.get().status, CmsWebhookEvent.Status.FAILED)
        self.assertEqual(Notification.objects.count(), 0)

    def test_missing_announcement_is_rejected_without_notifications(self):
        from apps.cms.services.strapi_client import StrapiNotFoundError

        with mock.patch("apps.cms.services.webhook.StrapiClient") as mock_client:
            mock_client.return_value.get_announcement.side_effect = StrapiNotFoundError("404")
            response = self.client.post(
                WEBHOOK_URL, publish_payload(), format="json",
                HTTP_X_AEGIS_WEBHOOK_SECRET=SECRET,
            )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], "rejected")
        self.assertEqual(CmsWebhookEvent.objects.get().status, CmsWebhookEvent.Status.REJECTED)
        self.assertEqual(Notification.objects.count(), 0)

    def test_invalid_canonical_data_is_rejected(self):
        """Invalid raw Strapi data must be caught by Django-side validation."""
        from apps.cms.services.strapi_client import StrapiClient

        raw_invalid = {
            "data": {"id": 1, "documentId": "doc-abc123", "title": "", "content": "C"}
        }
        # Patch only the transport layer so the real get_announcement()
        # (including normalization/validation) executes.
        with mock.patch.object(StrapiClient, "_get", return_value=raw_invalid):
            response = self.client.post(
                WEBHOOK_URL, publish_payload(), format="json",
                HTTP_X_AEGIS_WEBHOOK_SECRET=SECRET,
            )
        self.assertEqual(response.status_code, status.HTTP_422_UNPROCESSABLE_ENTITY)
        self.assertEqual(CmsWebhookEvent.objects.get().status, CmsWebhookEvent.Status.REJECTED)
        self.assertEqual(Notification.objects.count(), 0)

    def test_failed_delivery_can_be_retried_after_fix(self):
        """A pending/failed event row allows reprocessing on retry."""
        from apps.cms.services.strapi_client import StrapiUnavailableError

        with mock.patch("apps.cms.services.webhook.StrapiClient") as mock_client:
            mock_client.return_value.get_announcement.side_effect = StrapiUnavailableError(
                "down"
            )
            self.client.post(
                WEBHOOK_URL, publish_payload(), format="json",
                HTTP_X_AEGIS_WEBHOOK_SECRET=SECRET,
            )
        # Strapi retries once Strapi is healthy again.
        with mock.patch("apps.cms.services.webhook.StrapiClient") as mock_client:
            mock_client.return_value.get_announcement.return_value = (
                canonical_announcement()
            )
            response = self.client.post(
                WEBHOOK_URL, publish_payload(), format="json",
                HTTP_X_AEGIS_WEBHOOK_SECRET=SECRET,
            )
        self.assertEqual(response.data["status"], "processed")
        self.assertEqual(Notification.objects.count(), 6)


# ---------------------------------------------------------------------------
# Recipient resolution unit tests
# ---------------------------------------------------------------------------


class RecipientResolutionTest(CmsTestBase):
    def test_all_targets_all_active_users(self):
        qs = resolve_announcement_recipients(["all"], [])
        self.assertEqual(qs.count(), 6)  # everyone except the inactive user

    def test_role_filtering(self):
        qs = resolve_announcement_recipients(["student"], [])
        self.assertTrue(all(u.role == "student" for u in qs))
        self.assertEqual(qs.count(), 2)

    def test_unknown_roles_dropped_means_everyone_via_normalizer(self):
        from apps.cms.services.strapi_client import _normalize_roles

        self.assertEqual(_normalize_roles(["wizard", "", None]), ["all"])

    def test_section_filter_includes_staff_excludes_other_sections(self):
        qs = resolve_announcement_recipients(["all"], ["Einstein"])
        ids = set(u.id for u in qs)
        self.assertIn(self.student_user.id, ids)
        self.assertIn(self.parent_user.id, ids)
        self.assertIn(self.admin_user.id, ids)
        self.assertIn(self.faculty_user.id, ids)
        self.assertIn(self.guidance_user.id, ids)
        self.assertNotIn(self.student2_user.id, ids)


# ---------------------------------------------------------------------------
# Normalization unit tests
# ---------------------------------------------------------------------------


class NormalizationTest(TestCase):
    def test_valid_announcement_normalized(self):
        result = normalize_announcement(
            {
                "documentId": "doc1",
                "title": "Hello",
                "content": "Body",
                "announcement_type": "NEWS",
                "priority": "HIGH",
                "target_roles": ["Student", "PARENT"],
                "target_sections": ["Einstein"],
                "publishedAt": "2026-08-22T01:00:00.000Z",
                "expiresAt": "2026-08-30T01:00:00.000Z",
            }
        )
        self.assertEqual(result["announcement_type"], "news")
        self.assertEqual(result["priority"], "high")
        self.assertEqual(result["target_roles"], ["student", "parent"])
        self.assertEqual(result["target_sections"], ["Einstein"])
        self.assertIsNotNone(result["published_at"])
        self.assertIsNotNone(result["expires_at"])

    def test_default_targeting_when_unset(self):
        result = normalize_announcement(
            {"documentId": "doc2", "title": "T", "content": "C", "announcement_type": "news"}
        )
        self.assertEqual(result["target_roles"], ["all"])
        self.assertEqual(result["target_sections"], [])
        self.assertEqual(result["priority"], "normal")
        self.assertIsNone(result["published_at"])

    def test_missing_required_enum_rejected(self):
        with self.assertRaises(ValueError):
            normalize_announcement({"documentId": "doc3", "title": "T", "content": "C"})

    def test_invalid_announcement_type_rejected(self):
        with self.assertRaises(ValueError):
            normalize_announcement(
                {"documentId": "d", "title": "T", "content": "C", "announcement_type": "spam"}
            )

    def test_missing_title_or_content_rejected(self):
        with self.assertRaises(ValueError):
            normalize_announcement({"documentId": "d", "title": " ", "content": "C"})
        with self.assertRaises(ValueError):
            normalize_announcement({"documentId": "d", "title": "T", "content": ""})

    def test_resource_normalized_with_url(self):
        result = normalize_resource(
            {
                "documentId": "r1",
                "title": "Handbook",
                "description": "PDF handbook",
                "resource_type": "document",
                "url": "/uploads/handbook.pdf",
                "target_audience": ["student"],
                "is_active": True,
            }
        )
        self.assertEqual(result["file_or_url"], "/uploads/handbook.pdf")
        self.assertEqual(result["target_audience"], ["student"])

    def test_resource_media_file_resolved_against_base_url(self):
        result = normalize_resource(
            {
                "documentId": "r2",
                "title": "Video",
                "resource_type": "video",
                "file": {"url": "/uploads/video.mp4"},
            },
            base_url="http://localhost:1337",
        )
        self.assertEqual(result["file_or_url"], "http://localhost:1337/uploads/video.mp4")
        self.assertEqual(result["target_audience"], ["all"])

    def test_resource_invalid_type_rejected(self):
        with self.assertRaises(ValueError):
            normalize_resource({"documentId": "r3", "title": "X", "resource_type": "meme"})


# ---------------------------------------------------------------------------
# CMS read-through proxy endpoints
# ---------------------------------------------------------------------------


@override_settings(STRAPI_WEBHOOK_SECRET=SECRET)
class CmsProxyEndpointsTest(CmsTestBase):
    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(user=self.student_user)

    def test_authentication_required(self):
        anon = APIClient()
        response = anon.get("/api/v1/cms/announcements/")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_student_sees_targeted_published_announcement(self):
        with mock.patch("apps.cms.views.StrapiClient") as mock_client:
            mock_client.return_value.list_announcements.return_value = [
                canonical_announcement(target_roles=["student"]),
                canonical_announcement(
                    document_id="doc-parent-only", title="Parents Only",
                    target_roles=["parent"],
                ),
            ]
            response = self.client.get("/api/v1/cms/announcements/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        titles = [item["title"] for item in response.data["results"]]
        self.assertIn("Sports Fest", titles)
        self.assertNotIn("Parents Only", titles)

    def test_expired_announcement_hidden_from_student_visible_to_admin(self):
        expired = canonical_announcement(expires_at=timezone.now() - timedelta(days=1))
        with mock.patch("apps.cms.views.StrapiClient") as mock_client:
            mock_client.return_value.list_announcements.return_value = [expired]
            student_response = self.client.get("/api/v1/cms/announcements/")
        self.assertEqual(student_response.data["results"], [])

        admin_client = APIClient()
        admin_client.force_authenticate(user=self.admin_user)
        with mock.patch("apps.cms.views.StrapiClient") as mock_client:
            mock_client.return_value.list_announcements.return_value = [expired]
            admin_response = admin_client.get("/api/v1/cms/announcements/")
        self.assertEqual(len(admin_response.data["results"]), 1)

    def test_announcement_detail_by_document_id(self):
        with mock.patch("apps.cms.views.StrapiClient") as mock_client:
            mock_client.return_value.get_announcement.return_value = canonical_announcement()
            response = self.client.get("/api/v1/cms/announcements/doc-abc123/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["document_id"], "doc-abc123")

    def test_announcement_detail_hidden_for_non_target_role(self):
        with mock.patch("apps.cms.views.StrapiClient") as mock_client:
            mock_client.return_value.get_announcement.return_value = canonical_announcement(
                target_roles=["parent"]
            )
            response = self.client.get("/api/v1/cms/announcements/doc-abc123/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_strapi_unavailable_returns_502_on_list(self):
        from apps.cms.services.strapi_client import StrapiUnavailableError

        with mock.patch("apps.cms.views.StrapiClient") as mock_client:
            mock_client.return_value.list_announcements.side_effect = StrapiUnavailableError(
                "down"
            )
            response = self.client.get("/api/v1/cms/announcements/")
        self.assertEqual(response.status_code, status.HTTP_502_BAD_GATEWAY)

    def test_resource_list_filters_by_audience_and_active(self):
        with mock.patch("apps.cms.views.StrapiClient") as mock_client:
            mock_client.return_value.list_resources.return_value = [
                {
                    "document_id": "res-1",
                    "title": "For Students",
                    "description": None,
                    "resource_type": "document",
                    "file_or_url": "http://localhost:1337/uploads/a.pdf",
                    "target_audience": ["student"],
                    "is_active": True,
                },
                {
                    "document_id": "res-2",
                    "title": "Faculty Only",
                    "description": None,
                    "resource_type": "link",
                    "file_or_url": "https://example.com",
                    "target_audience": ["faculty"],
                    "is_active": True,
                },
                {
                    "document_id": "res-3",
                    "title": "Retired",
                    "description": None,
                    "resource_type": "other",
                    "file_or_url": None,
                    "target_audience": ["all"],
                    "is_active": False,
                },
            ]
            response = self.client.get("/api/v1/cms/resources/")
        titles = [item["title"] for item in response.data["results"]]
        self.assertEqual(titles, ["For Students"])

    def test_resource_detail_retrieval(self):
        with mock.patch("apps.cms.views.StrapiClient") as mock_client:
            mock_client.return_value.get_resource.return_value = {
                "document_id": "res-9",
                "title": "Handbook",
                "description": "The student handbook.",
                "resource_type": "document",
                "file_or_url": "http://localhost:1337/uploads/hb.pdf",
                "target_audience": ["all"],
                "is_active": True,
            }
            response = self.client.get("/api/v1/cms/resources/res-9/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["resource_type"], "document")
        self.assertEqual(response.data["title"], "Handbook")

"""
Phase 10.1 test suite for AEGIS Audit domain model.

Covers: AuditLog creation, required fields, nullable fields,
action choices, UUID primary key, indexes, immutability fields,
and absence of prohibited fields.
"""

import uuid

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase
from django.utils import timezone

from apps.audit.models import AuditLog

User = get_user_model()


class AuditLogCreationTest(TestCase):
    """AuditLog can be created with valid data."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="audit-tester@example.com",
            password="testpass123",
            first_name="Audit",
            last_name="Tester",
            role="admin",
        )

    def test_create_with_authenticated_user(self):
        log = AuditLog.objects.create(
            user=self.user,
            action=AuditLog.Action.LOGIN,
            model_name="accounts.Authentication",
            object_repr="Login",
            timestamp=timezone.now(),
        )
        self.assertIsNotNone(log.pk)
        self.assertEqual(log.user, self.user)

    def test_create_with_user_none(self):
        log = AuditLog.objects.create(
            user=None,
            action=AuditLog.Action.UPDATE,
            model_name="guidance.RiskAlert",
            object_id=uuid.uuid4(),
            object_repr="RiskAlert:" + str(uuid.uuid4()),
            timestamp=timezone.now(),
        )
        self.assertIsNone(log.user)

    def test_id_is_uuid(self):
        log = AuditLog.objects.create(
            action=AuditLog.Action.LOGIN,
            model_name="accounts.Authentication",
            object_repr="Login",
            timestamp=timezone.now(),
        )
        self.assertIsInstance(log.pk, uuid.UUID)

    def test_timestamp_is_populated(self):
        now = timezone.now()
        log = AuditLog.objects.create(
            action=AuditLog.Action.LOGIN,
            model_name="accounts.Authentication",
            object_repr="Login",
            timestamp=now,
        )
        self.assertIsNotNone(log.timestamp)


class AuditLogActionChoicesTest(TestCase):
    """All eight specification-defined action choices are available."""

    def test_all_eight_choices_exist(self):
        expected = {"create", "update", "delete", "login", "logout", "import", "export", "access"}
        actual = {choice[0] for choice in AuditLog.Action.choices}
        self.assertEqual(actual, expected)

    def test_action_max_length_is_15(self):
        field = AuditLog._meta.get_field("action")
        self.assertEqual(field.max_length, 15)

    def test_create_action(self):
        log = AuditLog.objects.create(
            action=AuditLog.Action.CREATE,
            model_name="academics.Grade",
            object_id=uuid.uuid4(),
            object_repr="Grade:" + str(uuid.uuid4()),
            timestamp=timezone.now(),
        )
        self.assertEqual(log.action, "create")

    def test_update_action(self):
        log = AuditLog.objects.create(
            action=AuditLog.Action.UPDATE,
            model_name="academics.Grade",
            object_id=uuid.uuid4(),
            object_repr="Grade:" + str(uuid.uuid4()),
            timestamp=timezone.now(),
        )
        self.assertEqual(log.action, "update")

    def test_delete_action(self):
        log = AuditLog.objects.create(
            action=AuditLog.Action.DELETE,
            model_name="academics.Grade",
            object_id=uuid.uuid4(),
            object_repr="Grade:" + str(uuid.uuid4()),
            timestamp=timezone.now(),
        )
        self.assertEqual(log.action, "delete")

    def test_login_action(self):
        log = AuditLog.objects.create(
            action=AuditLog.Action.LOGIN,
            model_name="accounts.Authentication",
            object_repr="Login",
            timestamp=timezone.now(),
        )
        self.assertEqual(log.action, "login")

    def test_logout_action(self):
        log = AuditLog.objects.create(
            action=AuditLog.Action.LOGOUT,
            model_name="accounts.Authentication",
            object_repr="Logout",
            timestamp=timezone.now(),
        )
        self.assertEqual(log.action, "logout")

    def test_import_action(self):
        log = AuditLog.objects.create(
            action=AuditLog.Action.IMPORT,
            model_name="data_import.ImportJob",
            object_id=uuid.uuid4(),
            object_repr="ImportJob:" + str(uuid.uuid4()),
            timestamp=timezone.now(),
        )
        self.assertEqual(log.action, "import")

    def test_export_action(self):
        log = AuditLog.objects.create(
            action=AuditLog.Action.EXPORT,
            model_name="data_import.ImportJob",
            object_repr="ExportJob",
            timestamp=timezone.now(),
        )
        self.assertEqual(log.action, "export")

    def test_access_action(self):
        log = AuditLog.objects.create(
            action=AuditLog.Action.ACCESS,
            model_name="academics.Grade",
            object_id=uuid.uuid4(),
            object_repr="Grade:" + str(uuid.uuid4()),
            timestamp=timezone.now(),
        )
        self.assertEqual(log.action, "access")


class AuditLogNullableFieldsTest(TestCase):
    """Nullable fields accept NULL correctly."""

    def test_object_id_nullable(self):
        log = AuditLog.objects.create(
            action=AuditLog.Action.LOGIN,
            model_name="accounts.Authentication",
            object_repr="Login",
            timestamp=timezone.now(),
        )
        self.assertIsNone(log.object_id)

    def test_changes_nullable(self):
        log = AuditLog.objects.create(
            action=AuditLog.Action.LOGIN,
            model_name="accounts.Authentication",
            object_repr="Login",
            timestamp=timezone.now(),
        )
        self.assertIsNone(log.changes)

    def test_ip_address_nullable(self):
        log = AuditLog.objects.create(
            action=AuditLog.Action.LOGIN,
            model_name="accounts.Authentication",
            object_repr="Login",
            timestamp=timezone.now(),
        )
        self.assertIsNone(log.ip_address)

    def test_user_agent_nullable(self):
        log = AuditLog.objects.create(
            action=AuditLog.Action.LOGIN,
            model_name="accounts.Authentication",
            object_repr="Login",
            timestamp=timezone.now(),
        )
        self.assertIsNone(log.user_agent)

    def test_changes_with_json(self):
        changes_data = {
            "old": {"score": 80, "status": "draft"},
            "new": {"score": 85, "status": "posted"},
        }
        log = AuditLog.objects.create(
            action=AuditLog.Action.UPDATE,
            model_name="academics.Grade",
            object_id=uuid.uuid4(),
            object_repr="Grade:" + str(uuid.uuid4()),
            changes=changes_data,
            timestamp=timezone.now(),
        )
        self.assertEqual(log.changes, changes_data)

    def test_ip_address_with_valid_ipv4(self):
        log = AuditLog.objects.create(
            action=AuditLog.Action.LOGIN,
            model_name="accounts.Authentication",
            object_repr="Login",
            ip_address="192.168.1.100",
            timestamp=timezone.now(),
        )
        self.assertEqual(log.ip_address, "192.168.1.100")

    def test_ip_address_with_valid_ipv6(self):
        log = AuditLog.objects.create(
            action=AuditLog.Action.LOGIN,
            model_name="accounts.Authentication",
            object_repr="Login",
            ip_address="2001:0db8:85a3:0000:0000:8a2e:0370:7334",
            timestamp=timezone.now(),
        )
        self.assertIsNotNone(log.ip_address)


class AuditLogRequiredFieldsTest(TestCase):
    """Required fields enforce NOT NULL at the database level."""

    def test_model_name_required(self):
        with self.assertRaises(IntegrityError):
            AuditLog.objects.create(
                action=AuditLog.Action.LOGIN,
                model_name=None,
                object_repr="Login",
                timestamp=timezone.now(),
            )

    def test_object_repr_required(self):
        with self.assertRaises(IntegrityError):
            AuditLog.objects.create(
                action=AuditLog.Action.LOGIN,
                model_name="accounts.Authentication",
                object_repr=None,
                timestamp=timezone.now(),
            )

    def test_action_required(self):
        with self.assertRaises(IntegrityError):
            AuditLog.objects.create(
                action=None,
                model_name="accounts.Authentication",
                object_repr="Login",
                timestamp=timezone.now(),
            )

    def test_timestamp_required(self):
        with self.assertRaises(IntegrityError):
            AuditLog.objects.create(
                action=AuditLog.Action.LOGIN,
                model_name="accounts.Authentication",
                object_repr="Login",
            )

    def test_object_repr_max_length_255(self):
        field = AuditLog._meta.get_field("object_repr")
        self.assertEqual(field.max_length, 255)

    def test_model_name_max_length_100(self):
        field = AuditLog._meta.get_field("model_name")
        self.assertEqual(field.max_length, 100)


class AuditLogSchemaConformanceTest(TestCase):
    """Verify schema matches §E.9 specification."""

    def test_no_created_at_field(self):
        field_names = [f.name for f in AuditLog._meta.fields]
        self.assertNotIn("created_at", field_names)

    def test_no_updated_at_field(self):
        field_names = [f.name for f in AuditLog._meta.fields]
        self.assertNotIn("updated_at", field_names)

    def test_no_actor_type_field(self):
        field_names = [f.name for f in AuditLog._meta.fields]
        self.assertNotIn("actor_type", field_names)

    def test_no_success_field(self):
        field_names = [f.name for f in AuditLog._meta.fields]
        self.assertNotIn("success", field_names)

    def test_exact_field_count(self):
        """§E.9 defines exactly 10 fields."""
        self.assertEqual(len(AuditLog._meta.fields), 10)

    def test_expected_field_names(self):
        expected = [
            "id",
            "user",
            "action",
            "model_name",
            "object_id",
            "object_repr",
            "changes",
            "ip_address",
            "user_agent",
            "timestamp",
        ]
        actual = [f.name for f in AuditLog._meta.fields]
        self.assertEqual(actual, expected)

    def test_id_is_primary_key(self):
        self.assertTrue(AuditLog._meta.pk.name == "id")

    def test_id_is_not_auto_bigautofield(self):
        pk_field = AuditLog._meta.pk
        self.assertEqual(pk_field.__class__.__name__, "UUIDField")


class AuditLogIndexTest(TestCase):
    """Verify expected database indexes exist."""

    def test_user_index_exists(self):
        index_names = [idx.name for idx in AuditLog._meta.indexes]
        self.assertIn("audit_user_idx", index_names)

    def test_model_name_index_exists(self):
        index_names = [idx.name for idx in AuditLog._meta.indexes]
        self.assertIn("audit_model_name_idx", index_names)

    def test_timestamp_index_exists(self):
        index_names = [idx.name for idx in AuditLog._meta.indexes]
        self.assertIn("audit_timestamp_idx", index_names)

    def test_action_index_exists(self):
        index_names = [idx.name for idx in AuditLog._meta.indexes]
        self.assertIn("audit_action_idx", index_names)

    def test_expected_index_count(self):
        self.assertEqual(len(AuditLog._meta.indexes), 4)


class AuditLogStrTest(TestCase):
    """Verify __str__ representation."""

    def test_str_with_user(self):
        user = User.objects.create_user(
            email="str-test@example.com",
            password="testpass123",
            role="admin",
        )
        log = AuditLog.objects.create(
            user=user,
            action=AuditLog.Action.LOGIN,
            model_name="accounts.Authentication",
            object_repr="Login",
            timestamp=timezone.now(),
        )
        result = str(log)
        self.assertIn("login", result)
        self.assertIn("accounts.Authentication", result)

    def test_str_without_user(self):
        log = AuditLog.objects.create(
            user=None,
            action=AuditLog.Action.UPDATE,
            model_name="guidance.RiskAlert",
            object_repr="RiskAlert:" + str(uuid.uuid4()),
            timestamp=timezone.now(),
        )
        result = str(log)
        self.assertIn("system", result)


class AuditLogDefaultOrderingTest(TestCase):
    """Verify default ordering is by timestamp descending."""

    def test_default_ordering(self):
        ordering = AuditLog._meta.ordering
        self.assertEqual(ordering, ["-timestamp"])

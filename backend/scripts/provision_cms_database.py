"""
One-time provisioning for the Strapi CMS database (Phase 7).

Creates a dedicated PostgreSQL role and database for the self-hosted
Strapi Community instance, using the Django development database
connection for privileged SQL so credentials never leave the process.

Generated secrets are written ONLY to the JSON file given as argv[1]
(a temporary handoff file used to compose cms/.env). Nothing is printed.

Idempotent: re-running resets the role password and reuses the database.

Usage:
    python scripts/provision_cms_database.py <output-json-path>
"""

import json
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "aegis_backend"))

import django
from django.conf import settings
from django.db import connections

CMS_ROLE = "aegis_cms"
CMS_DB_NAME = "aegis_cms_db"


def _quote_literal(value):
    return "'" + value.replace("'", "''") + "'"


def main():
    if len(sys.argv) != 2:
        print("usage: provision_cms_database.py <output-json-path>", file=sys.stderr)
        sys.exit(2)

    output_path = sys.argv[1]

    import os

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")
    django.setup()

    connection = connections["default"]
    # CREATE DATABASE cannot run inside a transaction block.
    connection.settings_dict.setdefault("OPTIONS", {})
    connection.ensure_connection()
    connection.connection.autocommit = True

    db_password = secrets.token_urlsafe(24)
    webhook_secret = secrets.token_urlsafe(32)
    admin_password = secrets.token_urlsafe(18)

    with connection.cursor() as cursor:
        cursor.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", [CMS_ROLE])
        role_exists = cursor.fetchone() is not None

        if role_exists:
            cursor.execute(
                f"ALTER ROLE {CMS_ROLE} WITH LOGIN PASSWORD {_quote_literal(db_password)}"
            )
        else:
            cursor.execute(
                f"CREATE ROLE {CMS_ROLE} WITH LOGIN PASSWORD {_quote_literal(db_password)}"
            )

        cursor.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s", [CMS_DB_NAME]
        )
        db_exists = cursor.fetchone() is not None

        if not db_exists:
            cursor.execute(f'CREATE DATABASE "{CMS_DB_NAME}" OWNER {CMS_ROLE}')

    payload = {
        "DATABASE_NAME": CMS_DB_NAME,
        "DATABASE_USERNAME": CMS_ROLE,
        "DATABASE_PASSWORD": db_password,
        "DATABASE_HOST": settings.DATABASES["default"].get("HOST") or "localhost",
        "DATABASE_PORT": str(settings.DATABASES["default"].get("PORT") or "5432"),
        "STRAPI_WEBHOOK_SECRET": webhook_secret,
        "ADMIN_EMAIL": "admin@aegis.local",
        "ADMIN_PASSWORD": admin_password,
        "role_existed": role_exists,
        "database_existed": db_exists,
    }

    with open(output_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh)

    print("PROVISIONED")


if __name__ == "__main__":
    main()

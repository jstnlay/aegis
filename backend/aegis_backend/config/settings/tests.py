"""
Where uploaded files end up.

The free Render plan has no persistent disk, so an upload written to the
service's own disk is lost on the next redeploy. The settings switch the
media storage to a Supabase bucket when the `SUPABASE_S3_*` variables are
set, and keep the local disk when they are not.

The switch is evaluated while the settings module is imported, so the two
states are checked by importing it in a subprocess with the variables set
and unset - `override_settings` cannot re-run that block.
"""

import os
import subprocess
import sys
from pathlib import Path

from django.test import SimpleTestCase

BACKEND_DIR = Path(__file__).resolve().parents[2]

REPORT = """
from django.conf import settings

print(settings.STORAGES.get("default", {}).get("BACKEND", ""))
print(settings.MEDIA_URL)
"""


class MediaStorageSettingsTest(SimpleTestCase):
    def _settings_report(self, **environment_overrides):
        environment = dict(os.environ)
        environment["DJANGO_SETTINGS_MODULE"] = "config.settings.test"
        environment.update(environment_overrides)
        result = subprocess.run(
            [sys.executable, "-c", REPORT],
            cwd=BACKEND_DIR,
            env=environment,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        lines = result.stdout.strip().splitlines()
        return lines[0], lines[1]

    def test_without_the_variables_the_disk_is_used(self):
        backend, media_url = self._settings_report(
            SUPABASE_S3_BUCKET="",
            SUPABASE_S3_ACCESS_KEY="",
            SUPABASE_S3_SECRET_KEY="",
        )

        self.assertNotIn("s3", backend)
        self.assertEqual(media_url, "/media/")

    def test_with_the_variables_the_bucket_is_used(self):
        backend, media_url = self._settings_report(
            SUPABASE_S3_ENDPOINT="https://project.supabase.co/storage/v1/s3",
            SUPABASE_S3_BUCKET="cms-upload",
            SUPABASE_S3_ACCESS_KEY="an-access-key",
            SUPABASE_S3_SECRET_KEY="a-secret-key",
        )

        self.assertEqual(backend, "storages.backends.s3.S3Storage")
        self.assertEqual(
            media_url,
            "https://project.supabase.co/storage/v1/object/public/cms-upload/",
        )

    def test_an_explicit_public_url_wins(self):
        _backend, media_url = self._settings_report(
            SUPABASE_S3_ENDPOINT="https://project.supabase.co/storage/v1/s3",
            SUPABASE_S3_BUCKET="cms-upload",
            SUPABASE_S3_ACCESS_KEY="an-access-key",
            SUPABASE_S3_SECRET_KEY="a-secret-key",
            SUPABASE_S3_PUBLIC_URL="https://cdn.example.org/media/",
        )

        self.assertEqual(media_url, "https://cdn.example.org/media/")

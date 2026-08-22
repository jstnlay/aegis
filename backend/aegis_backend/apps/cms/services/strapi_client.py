"""
Strapi REST client (server-side only).

Used by the webhook handler to fetch the *canonical* announcement from
Strapi instead of trusting unverified webhook payload content, and by
the read-through proxy endpoints that expose CMS content to
authenticated AEGIS users.

The API token is a Strapi custom content-API token scoped to read-only
Announcement/Resource access, stored server-side only
(cms/.env / environment). It is never exposed to AEGIS end users.
"""

import logging
from datetime import datetime

import requests
from django.conf import settings

logger = logging.getLogger("apps.cms")

ANNOUNCEMENT_TYPES = ("news", "event", "alert", "academic")
PRIORITIES = ("normal", "high", "urgent")
RESOURCE_TYPES = ("document", "link", "video", "other")


class StrapiError(Exception):
    """Base class for Strapi client errors."""


class StrapiUnavailableError(StrapiError):
    """Strapi is unreachable or returned a server error (retryable)."""


class StrapiNotFoundError(StrapiError):
    """The requested entry does not exist or is not published."""


def _parse_datetime(value):
    """Parse an ISO-8601 datetime string; return None for falsy input."""
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def normalize_announcement(raw):
    """
    Validate/normalize a raw Strapi announcement object into the
    specification-defined shape. Raises ValueError on invalid data.
    """
    title = str(raw.get("title") or "").strip()
    if not title:
        raise ValueError("announcement.title is required")
    if len(title) > 255:
        raise ValueError("announcement.title exceeds 255 characters")

    content = str(raw.get("content") or "").strip()
    if not content:
        raise ValueError("announcement.content is required")

    announcement_type = str(raw.get("announcement_type") or "").strip().lower()
    if announcement_type not in ANNOUNCEMENT_TYPES:
        raise ValueError(f"invalid announcement_type: {announcement_type!r}")

    priority = str(raw.get("priority") or "normal").strip().lower()
    if priority not in PRIORITIES:
        raise ValueError(f"invalid priority: {priority!r}")

    target_roles = _normalize_roles(raw.get("target_roles"))
    target_sections = _normalize_sections(raw.get("target_sections"))

    published_at = _parse_datetime(raw.get("publishedAt") or raw.get("published_at"))
    expires_at = _parse_datetime(raw.get("expiresAt") or raw.get("expires_at"))

    document_id = str(
        raw.get("documentId") or raw.get("id") or ""
    ).strip()
    if not document_id:
        raise ValueError("announcement.documentId is required")

    return {
        "document_id": document_id,
        "title": title,
        "content": content,
        "announcement_type": announcement_type,
        "priority": priority,
        "target_roles": target_roles,
        "target_sections": target_sections,
        "published_at": published_at,
        "expires_at": expires_at,
    }


def normalize_resource(raw, base_url=""):
    """
    Validate/normalize a raw Strapi resource object into the
    specification-defined shape. Raises ValueError on invalid data.
    """
    title = str(raw.get("title") or "").strip()
    if not title:
        raise ValueError("resource.title is required")
    if len(title) > 255:
        raise ValueError("resource.title exceeds 255 characters")

    resource_type = str(raw.get("resource_type") or "").strip().lower()
    if resource_type not in RESOURCE_TYPES:
        raise ValueError(f"invalid resource_type: {resource_type!r}")

    description = str(raw.get("description") or "").strip() or None

    # file_or_url equivalent representation: explicit URL wins, else the
    # uploaded media file's URL resolved against the Strapi base URL.
    file_or_url = str(raw.get("url") or "").strip()
    if not file_or_url:
        file_obj = raw.get("file")
        if isinstance(file_obj, dict) and file_obj.get("url"):
            file_or_url = file_obj["url"]
            if file_or_url.startswith("/"):
                file_or_url = base_url.rstrip("/") + file_or_url

    document_id = str(raw.get("documentId") or raw.get("id") or "").strip()
    if not document_id:
        raise ValueError("resource.documentId is required")

    return {
        "document_id": document_id,
        "title": title,
        "description": description,
        "resource_type": resource_type,
        "file_or_url": file_or_url or None,
        "target_audience": _normalize_roles(raw.get("target_audience")),
        "is_active": bool(raw.get("is_active", True)),
    }


def _normalize_roles(value):
    """
    Normalize a target_roles/target_audience JSON value to a list of
    lowercase AEGIS role strings, or ["all"] when unset/empty/"all".
    Unknown role tokens are dropped.
    """
    valid_roles = {"student", "parent", "faculty", "guidance", "admin"}
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return ["all"]
    tokens = [str(v).strip().lower() for v in value if str(v).strip()]
    if not tokens or "all" in tokens:
        return ["all"]
    filtered = [t for t in tokens if t in valid_roles]
    return filtered or ["all"]


def _normalize_sections(value):
    """Normalize target_sections JSON to a list of section names ([] = all)."""
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    return [str(v).strip() for v in value if str(v).strip()]


class StrapiClient:
    """Minimal REST client for the AEGIS Strapi instance."""

    def __init__(self, base_url=None, api_token=None, timeout=5):
        self.base_url = (base_url or settings.STRAPI_BASE_URL).rstrip("/")
        self.api_token = api_token if api_token is not None else settings.STRAPI_API_TOKEN
        self.timeout = timeout

    def _headers(self):
        headers = {"Accept": "application/json"}
        if self.api_token:
            headers["Authorization"] = f"Bearer {self.api_token}"
        return headers

    def _get(self, path, params=None):
        url = f"{self.base_url}{path}"
        try:
            response = requests.get(
                url, headers=self._headers(), params=params, timeout=self.timeout
            )
        except requests.RequestException as exc:
            logger.warning("Strapi request failed (%s): %s", url, exc)
            raise StrapiUnavailableError(f"Strapi unreachable at {url}") from exc

        if response.status_code == 404:
            raise StrapiNotFoundError(f"Not found: {url}")
        if response.status_code >= 500:
            raise StrapiUnavailableError(
                f"Strapi server error {response.status_code} for {url}"
            )
        if response.status_code != 200:
            raise StrapiError(
                f"Unexpected Strapi response {response.status_code} for {url}"
            )

        try:
            return response.json()
        except ValueError as exc:
            raise StrapiError(f"Invalid JSON from Strapi at {url}") from exc

    @staticmethod
    def _unwrap_single(payload):
        data = payload.get("data") if isinstance(payload, dict) else None
        if isinstance(data, list):
            return data[0] if data else None
        return data

    @staticmethod
    def _unwrap_list(payload):
        data = payload.get("data") if isinstance(payload, dict) else None
        return data if isinstance(data, list) else []

    def get_announcement(self, document_id):
        """Fetch one announcement by documentId and normalize it."""
        payload = self._get(f"/api/announcements/{document_id}")
        raw = self._unwrap_single(payload)
        if not raw:
            raise StrapiNotFoundError(f"Announcement {document_id} not found")
        try:
            return normalize_announcement(raw)
        except ValueError as exc:
            raise StrapiError(f"Invalid announcement data: {exc}") from exc

    def get_resource(self, document_id):
        """Fetch one resource by documentId and normalize it."""
        payload = self._get(f"/api/resources/{document_id}")
        raw = self._unwrap_single(payload)
        if not raw:
            raise StrapiNotFoundError(f"Resource {document_id} not found")
        try:
            return normalize_resource(raw, base_url=self.base_url)
        except ValueError as exc:
            raise StrapiError(f"Invalid resource data: {exc}") from exc

    def list_announcements(self):
        """List all published announcements, normalized."""
        payload = self._get("/api/announcements", params={"pagination[pageSize]": 100})
        results = []
        for raw in self._unwrap_list(payload):
            try:
                results.append(normalize_announcement(raw))
            except ValueError as exc:
                logger.warning("Skipping invalid announcement from Strapi: %s", exc)
        return results

    def list_resources(self):
        """List all resources, normalized."""
        payload = self._get("/api/resources", params={"pagination[pageSize]": 100})
        results = []
        for raw in self._unwrap_list(payload):
            try:
                results.append(normalize_resource(raw, base_url=self.base_url))
            except ValueError as exc:
                logger.warning("Skipping invalid resource from Strapi: %s", exc)
        return results

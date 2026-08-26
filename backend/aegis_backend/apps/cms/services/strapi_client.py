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
from urllib.parse import unquote, urlsplit

import requests
from django.conf import settings
from django.urls import reverse

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


def _safe_strapi_media_path(file_url, base_url=""):
    """
    SEC-007: classify a Strapi media `file.url` value.

    Returns a safe, rooted path (e.g. "/uploads/handbook.pdf") when the
    file is hosted by the trusted Strapi origin, or None when the value
    points elsewhere (e.g. a CDN configured in Strapi) — such values are
    treated as authored external links.

    Raises ValueError on unsafe/invalid values (traversal segments,
    backslashes, embedded scheme/host tricks) so malformed data is
    rejected exactly like other invalid Strapi payloads.

    The returned path is re-validated by every fetch site, so no caller
    can turn it into an arbitrary server-side request target.
    """
    if not isinstance(file_url, str):
        raise ValueError("resource.file.url must be a string")
    candidate = file_url.strip()
    if not candidate:
        raise ValueError("resource.file.url must not be empty")
    if "\\" in candidate or "\x00" in candidate:
        raise ValueError("unsafe resource file path")

    base = urlsplit(base_url or "")
    parsed = urlsplit(candidate)

    if parsed.scheme or parsed.netloc:
        # Absolute URL forms. Protocol-relative ("//host/path") and any
        # non-http(s) scheme are rejected outright.
        if candidate.startswith("//") or (parsed.netloc and not parsed.scheme):
            raise ValueError("unsafe resource file path")
        if parsed.scheme not in ("http", "https"):
            raise ValueError("unsafe resource file path")
        if not parsed.path or parsed.path == "/":
            raise ValueError("unsafe resource file path")
        if (
            base.netloc
            and (parsed.hostname or "").lower() == (base.hostname or "").lower()
        ):
            # Same-host-as-Strapi upload: safe to proxy by path.
            return parsed.path
        # Foreign-host http(s) media (e.g. CDN configured in Strapi):
        # cannot be proxied safely; caller treats it as an authored
        # external link instead.
        return None
    if not candidate.startswith("/"):
        raise ValueError("unsafe resource file path")
    path = candidate

    if not path or path == "/" or ".." in path.split("/"):
        raise ValueError("unsafe resource file path")
    if ".." in unquote(path).split("/"):
        raise ValueError("unsafe resource file path")
    return path


def normalize_resource(raw, base_url=""):
    """
    Validate/normalize a raw Strapi resource object into the
    specification-defined shape. Raises ValueError on invalid data.

    SEC-007: uploaded Strapi media is never exposed as a direct Strapi
    URL. `file_or_url` becomes an authorized Django proxy path that only
    resolves after audience/role authorization; the raw Strapi media
    path stays in the internal-only `strapi_file_path` field.
    Authored external URLs are passed through unchanged.
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

    document_id = str(raw.get("documentId") or raw.get("id") or "").strip()
    if not document_id:
        raise ValueError("resource.documentId is required")

    # file_or_url representation: explicit authored URL wins; else the
    # uploaded media file becomes an authorized Django proxy path.
    file_or_url = str(raw.get("url") or "").strip()
    file_source = "external" if file_or_url else None
    strapi_file_path = None

    if not file_or_url:
        file_obj = raw.get("file")
        if isinstance(file_obj, dict) and file_obj.get("url"):
            media_path = _safe_strapi_media_path(
                file_obj["url"], base_url=base_url
            )
            if media_path is not None:
                file_source = "proxy"
                strapi_file_path = media_path
                try:
                    file_or_url = reverse(
                        "cms:cms-resource-file",
                        kwargs={"document_id": document_id},
                    )
                except Exception as exc:  # pragma: no cover - config error
                    raise ValueError(
                        "cms resource file route is unavailable"
                    ) from exc
            else:
                # Media hosted off the trusted Strapi origin (e.g. a CDN
                # configured in Strapi): exposed as an authored external
                # link, never proxied through Django.
                file_or_url = str(file_obj["url"]).strip()
                file_source = "external"

    return {
        "document_id": document_id,
        "title": title,
        "description": description,
        "resource_type": resource_type,
        "file_or_url": file_or_url or None,
        "target_audience": _normalize_roles(raw.get("target_audience")),
        "is_active": bool(raw.get("is_active", True)),
        # Internal-only fields: never serialized to clients. Used by the
        # authorized download view to locate the bytes on the trusted
        # Strapi origin after Django-side authorization succeeds.
        "file_source": file_source,
        "strapi_file_path": strapi_file_path,
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

    def get_media_stream(self, media_path):
        """
        SEC-007: open a streaming response for a Strapi-hosted upload.

        `media_path` must be a rooted path previously validated by
        _safe_strapi_media_path; it is re-validated here so the fetch
        target is always pinned to the configured Strapi origin — never
        to anything derived from client input (SSRF containment).
        Redirects are disabled so a compromised upstream cannot bounce
        the fetch elsewhere.
        """
        try:
            safe = _safe_strapi_media_path(media_path, base_url=self.base_url)
        except ValueError as exc:
            raise StrapiError("Refusing to fetch unsafe media path") from exc
        if safe is None or not safe.startswith("/"):
            raise StrapiError("Refusing to fetch non-Strapi media path")

        url = f"{self.base_url}{safe}"
        try:
            response = requests.get(
                url,
                headers=self._headers(),
                timeout=self.timeout,
                stream=True,
                allow_redirects=False,
            )
        except requests.RequestException as exc:
            logger.warning("Strapi media request failed (%s): %s", url, exc)
            raise StrapiUnavailableError(f"Strapi media unreachable at {url}") from exc

        if response.status_code == 404:
            response.close()
            raise StrapiNotFoundError(f"Media not found: {url}")
        if response.status_code >= 500:
            response.close()
            raise StrapiUnavailableError(
                f"Strapi media server error {response.status_code} for {url}"
            )
        if response.status_code != 200:
            response.close()
            raise StrapiError(
                f"Unexpected Strapi media response {response.status_code} for {url}"
            )
        return response

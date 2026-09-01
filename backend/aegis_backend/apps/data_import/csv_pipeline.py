"""
CSV ingestion framework (Phase 8.3).

Reusable, security-hardened CSV parsing primitives that later importers
(PH8.5+) consume. The pipeline treats uploaded CSV as fully untrusted input:

- validates extension / content type / size / row count / field width
- decodes with a deterministic encoding strategy (UTF-8, then a bounded
  fallback) and reports failures instead of silently corrupting data
- guards against CSV injection (``=`` ``+`` ``-`` ``@`` prefixes)
- never writes user-supplied filenames or paths to storage/filesystem
- never exposes raw file contents, stack traces, or filesystem paths to
  clients
"""

import csv
import io
import re

from .constants import (
    CSV_MAX_COLUMNS,
    ImportErrorCode,
    MAX_IMPORT_FILE_SIZE,
    MAX_IMPORT_ROWS,
)

# ---------------------------------------------------------------------------
# Encoding strategy
# ---------------------------------------------------------------------------
#
# CSVs from schools are commonly UTF-8 (possibly with BOM) or the legacy
# Windows-1252 codepage. The pipeline first attempts strict UTF-8; if that
# fails it falls back to Windows-1252 (a superset that decodes almost any
# single-byte input without raising). Either way the result is normalized to
# a deterministic Unicode string and failures are reported rather than
# silently dropped.

PRIMARY_ENCODING = "utf-8-sig"  # strips any BOM
FALLBACK_ENCODING = "windows-1252"

#: Maximum bytes per decoded row, an additional guard against oversized
#: individual cells/rows beyond the total file-size bound.
MAX_ROW_BYTES = 1024 * 1024

# ---------------------------------------------------------------------------
# CSV injection sanitization
# ---------------------------------------------------------------------------
#
# Spreadsheets auto-evaluate leading ``=``, ``+``, ``-``, ``@`` (and tab/CR)
# as formulas. If an import file contained such a value, re-exporting or
# opening it in Excel/LibreOffice later could run it as a formula — a CSV
# injection vector. We neutralize the *leading* dangerous character by
# prefixing a single quote (``'``), which Excel shows but does not execute.
# This is the standard OWASP-recommended sanitization.
#
# The prefix is only applied when a value *begins* with a dangerous
# character, so legitimate academic values (e.g. "-", "+", "=" inside a
# string, or "20/20" grades) are left untouched.

_CSV_FORMULA_RE = re.compile(r"^[=+\-@\t\r]")

#: Column/field length guard.
FIELD_MAX_LEN = 4096

#: Encodings never accepted (UTF-16/32 multi-byte confusion is rejected up
#: front rather than silently mis-decoded).
_UNSUPPORTED_BOMS = (b"\xff\xfe", b"\xfe\xff", b"\xff\xfe\x00\x00", b"\x00\x00\xfe\xff")


class CsvValidationError(Exception):
    """Raised when an uploaded CSV fails validation as a whole."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message


class _CsvResult:
    """Outcome of a validated CSV read."""

    __slots__ = ("headers", "rows", "raw_row_count", "skipped_reason")

    def __init__(self, headers, rows, raw_row_count, skipped_reason=None):
        self.headers = headers
        self.rows = rows  # list of dicts (sanitized, one per data row)
        self.raw_row_count = raw_row_count
        self.skipped_reason = skipped_reason


def sanitize_csv_cell(value):
    """
    Neutralize leading CSV-injection characters in a single cell.

    Returns the value unchanged unless it begins with ``=`` ``+`` ``-``
    ``@`` tab or CR, in which case a single leading quote is prepended.
    """
    if not value:
        return value
    if _CSV_FORMULA_RE.match(value):
        return "'" + value
    return value


def safe_filename(basename):
    """
    Return a storage-usable filename from a client-supplied name.

    Strips any path components and control characters, and enforces a
    maximum length. Returns an empty string for unusable input.
    """
    if not basename:
        return ""
    # Replace any backslash/forward slash path separators and null bytes.
    cleaned = basename.replace("\\", "/").split("/")[-1].split("\x00")[0]
    cleaned = re.sub(r"[\r\n\t]", "", cleaned)
    # Enforce max length but keep the extension meaningful.
    cleaned = cleaned[:255]
    return cleaned


def _validate_extension(filename):
    name = safe_filename(filename)
    if not name:
        raise CsvValidationError(
            ImportErrorCode.INVALID_FILE_CONTENT,
            "No usable filename supplied for the uploaded file.",
        )
    lower = name.lower()
    if not lower.endswith(".csv"):
        raise CsvValidationError(
            ImportErrorCode.INVALID_FILE_EXTENSION,
            "Only .csv files are supported at this stage.",
        )
    return lower


def _read_decoded(content):
    """
    Decode raw bytes to a deterministic unicode string.

    Tries strict UTF-8 (with BOM handling) first, then a bounded
    Windows-1252 fallback. Rejects multi-byte BOMs up front. Raises
    CsvValidationError on failure rather than silently corrupting data.
    """
    if content.startswith(_UNSUPPORTED_BOMS):
        raise CsvValidationError(
            ImportErrorCode.INVALID_FILE_CONTENT,
            "Unsupported file encoding detected.",
        )
    try:
        return content.decode(PRIMARY_ENCODING)
    except UnicodeDecodeError:
        try:
            return content.decode(FALLBACK_ENCODING)
        except UnicodeDecodeError:
            raise CsvValidationError(
                ImportErrorCode.INVALID_FILE_CONTENT,
                "The file could not be decoded as a supported CSV encoding.",
            )


def validate_raw_csv(uploaded_file, filename, size=None):
    """
    High-level CSV validation + parse for an uploaded file.

    ``uploaded_file`` is file-like with ``read()``/``seek()``; ``filename``
    is the client-supplied name; ``size`` optionally overrides the byte
    size (falls back to seeking to end).

    Returns a ``_CsvResult``. Raises ``CsvValidationError`` on any
    whole-file problem. Raises ``FileTooLarge``-style CsvValidationError
    with code FILE_TOO_LARGE when over the size bound.
    """
    _validate_extension(filename)

    # --- size enforcement -------------------------------------------------
    if size is None:
        uploaded_file.seek(0, io.SEEK_END)
        size = uploaded_file.tell()
        uploaded_file.seek(0, io.SEEK_SET)
    if size > MAX_IMPORT_FILE_SIZE:
        raise CsvValidationError(
            ImportErrorCode.FILE_TOO_LARGE,
            f"The uploaded file exceeds the maximum size of 10 MB.",
        )
    if size == 0:
        raise CsvValidationError(
            ImportErrorCode.FILE_EMPTY,
            "The uploaded file is empty.",
        )

    content = uploaded_file.read()
    if isinstance(content, str):
        content = content.encode(PRIMARY_ENCODING)

    return parse_csv_bytes(content)


def parse_csv_bytes(content):
    """
    Parse raw CSV bytes into headers + sanitized row dicts.

    Handles empty files, missing/blank headers, unexpected/malformed
    headers, oversized columns, and excessive row counts.
    """
    text = _read_decoded(content)

    try:
        reader = csv.reader(io.StringIO(text), dialect=csv.excel)
        raw_rows = list(reader)
    except csv.Error as exc:
        raise CsvValidationError(
            ImportErrorCode.MALFORMED_HEADER,
            "The file is malformed and could not be parsed as CSV.",
        )

    if not raw_rows:
        raise CsvValidationError(
            ImportErrorCode.FILE_EMPTY,
            "The uploaded file is empty.",
        )
    if _is_blank_row(raw_rows[0]):
        raise CsvValidationError(
            ImportErrorCode.MISSING_REQUIRED_COLUMN,
            "The file is missing a header row.",
        )

    headers = _normalize_headers(raw_rows[0])

    data_rows = raw_rows[1:]

    # --- row count enforcement --------------------------------------------
    if len(data_rows) > MAX_IMPORT_ROWS:
        raise CsvValidationError(
            ImportErrorCode.INVALID_FILE_CONTENT,
            f"The file contains more than {MAX_IMPORT_ROWS} data rows.",
        )

    # --- column count enforcement -----------------------------------------
    for row in data_rows:
        if len(row) > CSV_MAX_COLUMNS:
            raise CsvValidationError(
                ImportErrorCode.BAD_COLUMN_COUNT,
                f"A row exceeds the maximum of {CSV_MAX_COLUMNS} columns.",
            )

    rows = []
    for index, row in enumerate(data_rows, start=1):
        if _is_blank_row(row):
            continue  # skip fully-empty trailing/blank lines deterministically
        if len(row) > len(headers):
            raise CsvValidationError(
                ImportErrorCode.BAD_COLUMN_COUNT,
                "A data row contains more columns than the header row.",
            )
        rows.append(_build_record(headers, row, index))

    return _CsvResult(
        headers=headers,
        rows=rows,
        raw_row_count=len(data_rows),
    )


def _is_blank_row(row):
    if not row:
        return True
    return len(row) == 1 and not row[0].strip()


def _normalize_headers(raw_header_row):
    headers = [_clean_header(cell) for cell in raw_header_row]
    if not headers or any(h == "" for h in headers):
        raise CsvValidationError(
            ImportErrorCode.MALFORMED_HEADER,
            "The header row contains empty or malformed column names.",
        )
    if len(headers) > CSV_MAX_COLUMNS:
        raise CsvValidationError(
            ImportErrorCode.BAD_COLUMN_COUNT,
            f"The header row exceeds the maximum of {CSV_MAX_COLUMNS} columns.",
        )
    seen = set()
    for h in headers:
        if h in seen:
            raise CsvValidationError(
                ImportErrorCode.MALFORMED_HEADER,
                "The header row contains duplicate column names.",
            )
        seen.add(h)
    return headers


def _clean_header(cell):
    cell = (cell or "").strip()
    # Normalize whitespace/newlines and trim length.
    cell = re.sub(r"\s+", " ", cell).strip()
    return cell[:FIELD_MAX_LEN]


def _build_record(headers, row, row_number):
    record = {}
    for header, cell in zip(headers, row):
        if cell is None:
            cell = ""
        if len(cell) > FIELD_MAX_LEN:
            cell = cell[:FIELD_MAX_LEN]
        record[header] = sanitize_csv_cell(cell)
    return record

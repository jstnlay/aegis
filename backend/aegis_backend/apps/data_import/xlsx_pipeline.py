"""
XLSX ingestion framework (Phase 8.4).

Reusable, security-hardened XLSX parsing primitives that later importers
(PH8.5+) consume.  The pipeline treats uploaded XLSX as fully untrusted input:

- validates extension / ZIP magic bytes / Office Open XML content / size
- uses openpyxl in read-only, data_only mode (no macro execution)
- enforces single-sheet, row-count, and column-count limits
- normalizes cell values deterministically (strings, numbers, dates,
  booleans, blanks) and guards against formula-injection vectors
- never exposes raw file contents, stack traces, or filesystem paths to
  clients

Design decisions (locked with project owner):
- ``.xlsx`` and ``.xlsm`` only; legacy ``.xls`` is rejected.
- ``openpyxl`` is the ONLY Excel library.
- Multi-sheet workbooks are rejected (ambiguous — one import file
  represents one dataset) UNLESS the workbook is a recognised DepEd form, in
  which case ``deped_forms`` translates its fixed layout into the same flat
  rows the generic path produces.
- Hidden/system worksheets are skipped entirely and never processed.
"""

import io
import re
from datetime import datetime, date
from decimal import Decimal

import openpyxl

from . import deped_forms
from .constants import (
    ImportErrorCode,
    MAX_IMPORT_FILE_SIZE,
    MAX_IMPORT_ROWS,
    XLSX_MAX_COLUMNS,
    XLSX_MAX_WORKSHEETS,
)
from .csv_pipeline import FIELD_MAX_LEN, safe_filename, sanitize_csv_cell

# ---------------------------------------------------------------------------
# XLSX magic bytes & content validation
# ---------------------------------------------------------------------------

#: ZIP local file header signature (little-endian \x50\x4b\x03\x04).
_ZIP_MAGIC = b"PK\x03\x04"


class XlsxValidationError(Exception):
    """Raised when an uploaded XLSX fails validation as a whole."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message


class _XlsxResult:
    """Outcome of a validated XLSX read."""

    __slots__ = ("headers", "rows", "raw_row_count", "skipped_reason")

    def __init__(self, headers, rows, raw_row_count, skipped_reason=None):
        self.headers = headers
        self.rows = rows  # list of dicts (sanitized, one per data row)
        self.raw_row_count = raw_row_count
        self.skipped_reason = skipped_reason


# ---------------------------------------------------------------------------
# Content-level validation (before openpyxl opens the workbook)
# ---------------------------------------------------------------------------


def _validate_extension(filename):
    """Reject files that are neither ``.xlsx`` nor ``.xlsm``."""
    name = safe_filename(filename)
    if not name:
        raise XlsxValidationError(
            ImportErrorCode.INVALID_FILE_CONTENT,
            "No usable filename supplied for the uploaded file.",
        )
    lower = name.lower()
    if not lower.endswith((".xlsx", ".xlsm")):
        raise XlsxValidationError(
            ImportErrorCode.INVALID_FILE_EXTENSION,
            "Only .xlsx and .xlsm files are supported.",
        )
    return lower


def _validate_zip_magic(content):
    """
    Verify the raw bytes begin with a ZIP local-file-header signature.

    A legitimate ``.xlsx`` is a ZIP-based Office Open XML workbook.  This
    catches renamed text files, plain-text CSVs with ``.xlsx`` extensions,
    and other non-workbook imposters.
    """
    if not content or len(content) < 4:
        raise XlsxValidationError(
            ImportErrorCode.INVALID_FILE_CONTENT,
            "The uploaded file is empty or too small to be a valid XLSX workbook.",
        )
    if content[:4] != _ZIP_MAGIC:
        raise XlsxValidationError(
            ImportErrorCode.INVALID_FILE_CONTENT,
            "The uploaded file is not a valid XLSX workbook.",
        )


# ---------------------------------------------------------------------------
# Cell value normalization
# ---------------------------------------------------------------------------
#
# All cell values are converted to safe, deterministic Python primitives
# suitable for later domain-specific validation.  Dates/datetimes become
# ISO-8601 strings (date-typed cells, read back as midnight datetimes,
# become plain ``YYYY-MM-DD``).  Decimals become strings to avoid
# floating-point precision loss.  Booleans become "TRUE"/"FALSE".
# Numeric values (including negative numbers) are preserved verbatim as
# strings WITHOUT formula-injection sanitization — a cell typed as a
# number is not a formula vector.  Formula cells use their cached value
# if present; otherwise they are reported as empty strings (we never
# evaluate formulas).

_ISO_DATE_FMT = "%Y-%m-%d"
_ISO_DATETIME_FMT = "%Y-%m-%dT%H:%M:%S"


def normalize_xlsx_cell(value):
    """
    Convert an openpyxl cell value to a safe, deterministic representation.

    - None → ""
    - bool → "TRUE" / "FALSE"
    - datetime.datetime → ISO-8601 string
    - datetime.date → ISO-8601 string
    - Decimal → string (avoids float precision loss)
    - int / float → string (integers preserved without decimal point)
    - str → stripped, whitespace-collapsed, length-capped, injection-sanitized
    - everything else → str(value) and sanitized
    """
    if value is None:
        return ""

    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"

    if isinstance(value, datetime):
        if (value.hour, value.minute, value.second, value.microsecond) == (0, 0, 0, 0):
            # Date-typed cells are read back as midnight datetimes; emit a
            # date string deterministically instead of a time-suffixed value.
            return value.strftime(_ISO_DATE_FMT)
        return value.strftime(_ISO_DATETIME_FMT)

    if isinstance(value, date):
        return value.strftime(_ISO_DATE_FMT)

    if isinstance(value, Decimal):
        return str(value)

    if isinstance(value, (int, float)):
        # Avoid "90.0" for whole-number floats; preserve as "90".
        if isinstance(value, float) and value.is_integer():
            return str(int(value))
        return str(value)

    # Strings and everything else.
    text = str(value).strip()
    # Collapse internal whitespace.
    text = re.sub(r"\s+", " ", text)
    # Cap length.
    if len(text) > FIELD_MAX_LEN:
        text = text[:FIELD_MAX_LEN]
    # Apply CSV-injection sanitization (same vector applies if re-exported).
    return sanitize_csv_cell(text)


# ---------------------------------------------------------------------------
# Header normalization
# ---------------------------------------------------------------------------
#
# Reuses the same clean/normalize logic as CSV headers to ensure
# consistent behavior across file types.


def _clean_xlsx_header(cell):
    """Normalize a single header cell from openpyxl."""
    if cell is None:
        return ""
    text = str(cell).strip()
    text = re.sub(r"\s+", " ", text)
    if len(text) > FIELD_MAX_LEN:
        text = text[:FIELD_MAX_LEN]
    return text


def _normalize_headers(raw_header_row):
    """
    Normalize and validate a list of raw header strings.

    Raises ``XlsxValidationError`` on empty, blank, duplicate, or
    excessive headers.
    """
    headers = [_clean_xlsx_header(cell) for cell in raw_header_row]

    if not headers or any(h == "" for h in headers):
        raise XlsxValidationError(
            ImportErrorCode.MALFORMED_HEADER,
            "The header row contains empty or malformed column names.",
        )

    if len(headers) > XLSX_MAX_COLUMNS:
        raise XlsxValidationError(
            ImportErrorCode.BAD_COLUMN_COUNT,
            f"The header row exceeds the maximum of {XLSX_MAX_COLUMNS} columns.",
        )

    seen = set()
    for h in headers:
        if h in seen:
            raise XlsxValidationError(
                ImportErrorCode.MALFORMED_HEADER,
                "The header row contains duplicate column names.",
            )
        seen.add(h)

    return headers


# ---------------------------------------------------------------------------
# Worksheet selection
# ---------------------------------------------------------------------------


def _visible_sheet_names(visible_sheets):
    """Comma-separated preview of visible worksheet titles (first five)."""
    names = [ws.title for ws in visible_sheets]
    preview = ", ".join(names[:5])
    if len(names) > 5:
        preview += f", and {len(names) - 5} more"
    return preview


def _select_worksheet(wb, sheet=None):
    """
    Select the worksheet to import from an openpyxl workbook.

    ``sheet`` names the worksheet to import: either its title (trimmed,
    case-sensitive as Excel is) or its 1-based position among the visible
    worksheets.  Naming one is how a workbook that also carries a
    README/instructions sheet is imported.  Sheets are never merged or
    guessed at — one import file is still one dataset.

    Without ``sheet``, exactly one visible worksheet is required.  Workbooks
    with several visible worksheets are rejected as ambiguous.

    Hidden worksheets (``sheet_state`` ``hidden``/``veryHidden``) are skipped
    entirely: they are never selected, never counted toward the limit, and
    never processed.
    """
    visible_sheets = [ws for ws in wb.worksheets if ws.sheet_state == "visible"]

    if not visible_sheets:
        raise XlsxValidationError(
            ImportErrorCode.EMPTY_WORKSHEET,
            "The workbook contains no visible worksheets.",
        )

    if sheet is not None:
        return _resolve_named_worksheet(visible_sheets, sheet)

    if len(visible_sheets) > XLSX_MAX_WORKSHEETS:
        raise XlsxValidationError(
            ImportErrorCode.MULTIPLE_WORKSHEETS,
            f"The workbook contains {len(visible_sheets)} visible worksheets "
            f"({_visible_sheet_names(visible_sheets)}). Only a single worksheet "
            "is allowed unless one is named with the 'sheet' field.",
        )

    return visible_sheets[0]


def _resolve_named_worksheet(visible_sheets, sheet):
    """Resolve a caller-supplied worksheet title or 1-based visible position."""
    wanted = str(sheet).strip()
    for ws in visible_sheets:
        if ws.title.strip() == wanted:
            return ws

    if wanted.isdigit():
        position = int(wanted)
        if 1 <= position <= len(visible_sheets):
            return visible_sheets[position - 1]

    # The requested value is not echoed back: it is client input, and the
    # visible titles already tell the caller what may be named.  A blank
    # value is treated as "not named" by the caller, not as a lookup.
    raise XlsxValidationError(
        ImportErrorCode.WORKSHEET_NOT_FOUND,
        "No visible worksheet matches the requested 'sheet' value "
        f"({_visible_sheet_names(visible_sheets)} are available).",
    )


# ---------------------------------------------------------------------------
# Row extraction
# ---------------------------------------------------------------------------


def _extract_rows(ws, headers):
    """
    Extract data rows from an openpyxl worksheet, converting each row
    to a dict keyed by the normalized headers.

    ``iter_rows`` is bounded to the header column count (``max_col``), so
    every yielded row has exactly ``len(headers)`` cells and rows are never
    wider than the header.  Returns (rows, raw_row_count) where rows is a
    list of dicts and raw_row_count is the number of non-empty data rows
    encountered.
    """
    rows = []
    for row in ws.iter_rows(min_row=2, max_col=len(headers)):
        values = [cell.value for cell in row]
        if all(v is None for v in values):
            continue  # defensive: fully-empty row

        record = {}
        for header, value in zip(headers, values):
            record[header] = normalize_xlsx_cell(value)
        rows.append(record)

        if len(rows) > MAX_IMPORT_ROWS:
            raise XlsxValidationError(
                ImportErrorCode.INVALID_FILE_CONTENT,
                f"The file contains more than {MAX_IMPORT_ROWS} data rows.",
            )

    return rows, len(rows)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def validate_raw_xlsx(uploaded_file, filename, size=None, sheet=None):
    """
    High-level XLSX validation + parse for an uploaded file.

    ``uploaded_file`` is file-like with ``read()``/``seek()``; ``filename``
    is the client-supplied name; ``size`` optionally overrides the byte
    size (falls back to seeking to end); ``sheet`` optionally names the
    worksheet to import (title or 1-based visible position).

    Returns a ``_XlsxResult``.  Raises ``XlsxValidationError`` on any
    whole-file problem.
    """
    _validate_extension(filename)

    # --- size enforcement ---------------------------------------------------
    if size is None:
        uploaded_file.seek(0, io.SEEK_END)
        size = uploaded_file.tell()
        uploaded_file.seek(0, io.SEEK_SET)

    if size > MAX_IMPORT_FILE_SIZE:
        raise XlsxValidationError(
            ImportErrorCode.FILE_TOO_LARGE,
            "The uploaded file exceeds the maximum size of 10 MB.",
        )
    if size == 0:
        raise XlsxValidationError(
            ImportErrorCode.FILE_EMPTY,
            "The uploaded file is empty.",
        )

    content = uploaded_file.read()
    if isinstance(content, str):
        raise XlsxValidationError(
            ImportErrorCode.INVALID_FILE_CONTENT,
            "The uploaded file is not a valid XLSX workbook.",
        )

    # --- content validation -------------------------------------------------
    _validate_zip_magic(content)

    # parse_xlsx_bytes opens the workbook with openpyxl; any structural
    # problem (renamed ZIP, corrupt archive, malformed OOXML) surfaces as
    # an INVALID_WORKBOOK whole-file error.
    return parse_xlsx_bytes(content, sheet=sheet)


def parse_xlsx_bytes(content, sheet=None):
    """
    Parse raw XLSX bytes into headers + sanitized row dicts.

    Opens the workbook in read-only, data_only mode (no formula evaluation,
    no macro execution).  Selects the worksheet named by ``sheet`` (title or
    1-based visible position), or the only visible one when ``sheet`` is
    ``None``, validates and normalizes headers, then extracts and sanitizes
    data rows.

    No code is executed: openpyxl only reads stored XML cell data, and
    ``data_only=True`` reads cached formula results without evaluating them.
    """
    try:
        zip_file = io.BytesIO(content)
        wb = openpyxl.load_workbook(zip_file, read_only=True, data_only=True)
    except Exception:
        raise XlsxValidationError(
            ImportErrorCode.INVALID_WORKBOOK,
            "The uploaded file could not be opened as an XLSX workbook.",
        )

    try:
        # A DepEd SF2/SF9 workbook is recognised by its sheets and translated
        # into the same flat rows a plain table would produce, so the importer
        # validates a fill-in form exactly like a CSV export.
        if deped_forms.detect(wb.sheetnames):
            try:
                headers, rows = deped_forms.read(wb)
            except deped_forms.DepedFormError as exc:
                raise XlsxValidationError(exc.code, exc.message)
            return _XlsxResult(
                headers=headers, rows=rows, raw_row_count=len(rows)
            )

        ws = _select_worksheet(wb, sheet=sheet)

        # Read the header row (row 1).  In read-only mode, rows that have
        # no cell values at all are not yielded, so an empty worksheet
        # produces no rows here.
        header_rows = list(ws.iter_rows(min_row=1, max_row=1))
        if not header_rows:
            if ws.max_row and ws.max_row > 1:
                # Content exists below row 1 but there is no header.
                raise XlsxValidationError(
                    ImportErrorCode.MISSING_REQUIRED_COLUMN,
                    "The worksheet is missing a header row.",
                )
            raise XlsxValidationError(
                ImportErrorCode.EMPTY_WORKSHEET,
                "The worksheet is empty.",
            )

        raw_header = [cell.value for cell in header_rows[0]]
        if all(value is None for value in raw_header):
            raise XlsxValidationError(
                ImportErrorCode.MISSING_REQUIRED_COLUMN,
                "The worksheet is missing a header row.",
            )

        headers = _normalize_headers(raw_header)
        rows, raw_row_count = _extract_rows(ws, headers)

    finally:
        wb.close()

    return _XlsxResult(
        headers=headers,
        rows=rows,
        raw_row_count=raw_row_count,
    )

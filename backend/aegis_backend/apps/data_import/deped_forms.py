"""
Template-aware readers for the DepEd SF2 and SF9 workbooks.

A DepEd form is not a flat table: SF2 packs a month of daily marks into fixed
columns of one sheet and keeps its school header on a separate ``COVER`` sheet,
and SF9 puts the learning areas in a header *band* (row 12, from column K) with
one numbered row per learner.  The generic row-1-header path in
``xlsx_pipeline`` cannot read either, which is why the shipped forms were
rejected.

These readers recognise a form by its sheet names, verify the shape they depend
on, and translate it into the flat row dictionaries the importers already
validate.  One uploaded workbook is still one dataset, and there is still a
single validation path: the translator only decides *which* rows exist, never
whether a score or a status is legal.

Recognised today
----------------
    G4-10  School Form 9 (SY ..).xlsx   -> grades
        ``TERM n SUMMARY`` sheets, one row per learner and learning area.
    SF2 JUNIOR HS.xlsm                  -> attendance
        ``SF2-JHS`` grid plus the ``COVER`` header (section, level, month).

Both readers are structural: a revised form that moves the header band, drops a
sheet, or renames a learning area fails loudly here instead of silently
attaching values to the wrong learner or subject.

Learner identity
----------------
Neither form carries the app's student code.  The learner's *name* cell (SF9
column C, SF2 column B) is taken as ``student_id`` and resolved by the existing
importer, so a filled form must carry the school code the Students export
shows -- see ``docs/test-data/README.md``.
"""

from __future__ import annotations

from datetime import date, datetime

# ---------------------------------------------------------------------------
# SF9 (grades)
# ---------------------------------------------------------------------------

#: Learning-area band: one label per column, starting at column K, on row 12 of
#: every ``TERM n SUMMARY`` sheet.
SF9_AREA_BAND_ROW = 12
SF9_AREA_FIRST_COL = 11
#: SF9 label -> base subject code.  ``GMRC/VE`` is the current DepEd name for
#: the seeded ``ESP`` subject; ``EPP/TLE`` is ``TLE``.
SF9_LABEL_TO_BASE = (
    ("Filipino", "FIL"),
    ("English", "ENG"),
    ("Mathematics", "MATH"),
    ("Science", "SCI"),
    ("AP", "AP"),
    ("GMRC/VE", "ESP"),
    ("EPP/TLE", "TLE"),
    ("MAPEH", "MAPEH"),
)
#: Columns each learning area occupies.  MAPEH is the only area the form splits
#: (``M A`` | ``P E H``); its two sub-scores are averaged into one grade.
SF9_AREA_COLUMNS = ((11,), (12,), (13,), (14,), (15,), (16,), (17,), (18, 19))
SF9_FIRST_LEARNER_ROW = 15
SF9_NAME_COL = 3
SF9_GRADE_LEVEL_CELL = (9, 7)
SF9_SECTION_CELL = (10, 7)
#: SF9 covers Grades 4-10.  The unfilled template caches a ``0`` in the GRADE
#: LEVEL cell (its formula has not been evaluated yet), so a summary whose level
#: is not in this range carries no importable rows.
SF9_LEVEL_RANGE = (4, 10)
#: Summary sheet -> the grading-period name the seeded school uses.
SF9_TERM_SHEETS = (
    ("TERM 1 SUMMARY", "Term 1"),
    ("TERM 2 SUMMARY", "Term 2"),
    ("TERM 3 SUMMARY", "Term 3"),
)

GRADE_HEADERS = (
    "student_id",
    "section",
    "subject_code",
    "grading_period",
    "score",
)

# ---------------------------------------------------------------------------
# SF2 (attendance)
# ---------------------------------------------------------------------------

SF2_SHEET = "SF2-JHS"
SF2_FIRST_LEARNER_ROW = 8
SF2_NAME_COL = 2
SF2_NUMBER_COL = 1
SF2_FIRST_DAY_COL = 5
SF2_LAST_DAY_COL = 29
#: Row 7 is the day-of-week band (``M T W TH F`` five times); row 6 holds the
#: day-of-month number the adviser typed for each column.
SF2_DAY_CODE_ROW = 7
SF2_DAY_NUMBER_ROW = 6
SF2_WEEK_CYCLE = ("M", "T", "W", "TH", "F")
#: SF2 marks the exceptions only: ``X`` absent, ``L`` tardy, blank present.
SF2_STATUS_BY_CODE = {"X": "absent", "L": "late", "T": "late"}
SF2_DEFAULT_STATUS = "present"

ATTENDANCE_HEADERS = ("student_id", "section", "date", "status")

#: ``COVER`` sheet cells (rows 1..6, value column B).
SF2_COVER_CELLS = {
    "section": "B2",
    "school_year": "B4",
    "grade_level": "B5",
    "month": "B6",
}

_MONTH_NAMES = (
    "january",
    "february",
    "march",
    "april",
    "may",
    "june",
    "july",
    "august",
    "september",
    "october",
    "november",
    "december",
)
_MONTH_BY_PREFIX = {name[:3]: index for index, name in enumerate(_MONTH_NAMES, 1)}


class DepedFormError(Exception):
    """A recognised DepEd form did not have the shape its reader requires."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message


# ---------------------------------------------------------------------------
# Small cell helpers
# ---------------------------------------------------------------------------


def _text(value):
    if value is None:
        return ""
    return " ".join(str(value).split())


def _number(value):
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).strip())
    except ValueError:
        return None


def _format_number(value):
    """Whole scores read as whole numbers; the importer parses the rest."""
    return str(int(value)) if float(value).is_integer() else f"{value:g}"


def _normalize_level(raw):
    """``8``, ``"8"`` and ``"Grade 8"`` all mean level 8."""
    text = _text(raw)
    if text.lower().startswith("grade"):
        text = text[5:].strip()
    return text


def _valid_level(text):
    """True when ``text`` names a grade level an SF9 may carry."""
    return text.isdigit() and SF9_LEVEL_RANGE[0] <= int(text) <= SF9_LEVEL_RANGE[1]


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------


def detect(sheet_names):
    """Return ``"sf9"`` / ``"sf2"`` when the workbook is a known DepEd form."""
    names = set(sheet_names)
    if "FINAL GRADES" in names and all(
        sheet in names for sheet, _ in SF9_TERM_SHEETS
    ):
        return "sf9"
    if SF2_SHEET in names:
        return "sf2"
    return None


def read(workbook):
    """
    Translate a recognised DepEd workbook into ``(headers, rows)``.

    ``rows`` are flat dicts keyed by the importers' own column names, ready for
    the same header/row validation a CSV upload goes through.
    """
    kind = detect(workbook.sheetnames)
    if kind == "sf9":
        return read_sf9(workbook)
    if kind == "sf2":
        return read_sf2(workbook)
    raise DepedFormError(
        "INVALID_WORKBOOK", "The workbook is not a recognised DepEd form."
    )


# ---------------------------------------------------------------------------
# SF9 -> grade rows
# ---------------------------------------------------------------------------


def _check_sf9_band(worksheet, sheet_name):
    """Assert the learning-area band is where and what the reader expects."""
    labels = tuple(
        _text(worksheet.cell(row=SF9_AREA_BAND_ROW, column=SF9_AREA_FIRST_COL + i).value)
        for i in range(len(SF9_LABEL_TO_BASE))
    )
    expected = tuple(label for label, _ in SF9_LABEL_TO_BASE)
    if labels != expected:
        raise DepedFormError(
            "MALFORMED_HEADER",
            f"{sheet_name}'s learning-area band is not the expected form: {labels!r}",
        )


def read_sf9(workbook):
    """Per-term ``TERM n SUMMARY`` sheets -> one grade row per (learner, area)."""
    rows = []
    for sheet_name, period in SF9_TERM_SHEETS:
        worksheet = workbook[sheet_name]
        _check_sf9_band(worksheet, sheet_name)

        level = _normalize_level(
            worksheet.cell(row=SF9_GRADE_LEVEL_CELL[0], column=SF9_GRADE_LEVEL_CELL[1]).value
        )
        section_name = _text(
            worksheet.cell(row=SF9_SECTION_CELL[0], column=SF9_SECTION_CELL[1]).value
        )
        if not _valid_level(level) or not section_name:
            # A summary with no school level/section carries no importable rows.
            # The unfilled template lands here: its level cell caches ``0``.
            continue
        section = f"Grade {level} - {section_name}"

        learners = 0
        for row in range(SF9_FIRST_LEARNER_ROW, worksheet.max_row + 1):
            student_id = _text(
                worksheet.cell(row=row, column=SF9_NAME_COL).value
            )
            if not student_id:
                break

            learners += 1
            for (label, base), columns in zip(SF9_LABEL_TO_BASE, SF9_AREA_COLUMNS):
                scores = [
                    value
                    for value in (
                        _number(worksheet.cell(row=row, column=column).value)
                        for column in columns
                    )
                    if value is not None
                ]
                if not scores:
                    continue
                rows.append(
                    {
                        "student_id": student_id,
                        "section": section,
                        "subject_code": f"{base}-{level}",
                        "grading_period": period,
                        "score": _format_number(sum(scores) / len(scores)),
                    }
                )

        if not learners:
            continue

    return GRADE_HEADERS, rows


# ---------------------------------------------------------------------------
# SF2 -> attendance rows
# ---------------------------------------------------------------------------


def _resolve_month(raw, school_year):
    """
    The month the form is for: a date cell, ``YYYY-MM``, or a month name.

    The year comes from the ``School Year`` cell (``2026-2027``): a month from
    June onward belongs to its first year, earlier months to its second.
    """
    if isinstance(raw, (datetime, date)):
        return raw.year, raw.month

    text = _text(raw).lower()
    if not text:
        return None

    if "-" in text:
        parts = text.split("-")
        if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
            return int(parts[0]), int(parts[1])

    month = None
    for name in _MONTH_NAMES:
        if name in text:
            month = _MONTH_NAMES.index(name) + 1
            break
    if month is None:
        for prefix, index in _MONTH_BY_PREFIX.items():
            if prefix in text:
                month = index
                break
    if month is None:
        return None

    years = [int(part) for part in school_year.split("-") if part.strip().isdigit()]
    if not years:
        return None
    year = years[0] if month >= 6 else (years[1] if len(years) > 1 else years[0] + 1)
    return year, month


def read_sf2(workbook):
    """The ``SF2-JHS`` month grid -> one attendance row per (learner, day)."""
    if "COVER" not in workbook.sheetnames:
        raise DepedFormError(
            "MISSING_REQUIRED_COLUMN",
            "The SF2 workbook has no COVER sheet carrying the school header.",
        )

    cover = workbook["COVER"]
    sheet = workbook[SF2_SHEET]
    if _text(sheet.cell(row=5, column=1).value) != "No.":
        raise DepedFormError(
            "MISSING_REQUIRED_COLUMN",
            "The SF2-JHS sheet is not the expected attendance form.",
        )

    cover_value = lambda key: cover[SF2_COVER_CELLS[key]].value  # noqa: E731
    section_name = _text(cover_value("section"))
    level = _normalize_level(cover_value("grade_level"))
    resolved = _resolve_month(cover_value("month"), _text(cover_value("school_year")))
    if not (section_name and level and resolved):
        raise DepedFormError(
            "MISSING_REQUIRED_COLUMN",
            "The SF2 is missing its section, grade level, or report month; "
            "fill the COVER sheet first.",
        )
    year, month = resolved
    section = f"Grade {level} - {section_name}"

    columns = range(SF2_FIRST_DAY_COL, SF2_LAST_DAY_COL + 1)
    codes = tuple(_text(sheet.cell(row=SF2_DAY_CODE_ROW, column=c).value) for c in columns)
    if codes[:5] != SF2_WEEK_CYCLE:
        raise DepedFormError(
            "MALFORMED_HEADER",
            f"SF2-JHS row {SF2_DAY_CODE_ROW} is not the M/T/W/TH/F day band: {codes[:5]!r}",
        )

    days = {}
    for column in columns:
        day = _number(sheet.cell(row=SF2_DAY_NUMBER_ROW, column=column).value)
        if day is None:
            continue  # a week slot the month has no school day for
        day = int(day)
        try:
            days[column] = date(year, month, day).isoformat()
        except ValueError:
            raise DepedFormError(
                "INVALID_FILE_CONTENT",
                f"SF2-JHS row {SF2_DAY_NUMBER_ROW} column {column} is not a real "
                f"day of {year}-{month:02d}: {day}.",
            )

    rows = []
    for row in range(SF2_FIRST_LEARNER_ROW, sheet.max_row + 1):
        student_id = _text(sheet.cell(row=row, column=SF2_NAME_COL).value)
        if not student_id:
            break
        for column, day in days.items():
            mark = _text(sheet.cell(row=row, column=column).value).upper()
            rows.append(
                {
                    "student_id": student_id,
                    "section": section,
                    "date": day,
                    "status": SF2_STATUS_BY_CODE.get(mark, SF2_DEFAULT_STATUS),
                }
            )

    return ATTENDANCE_HEADERS, rows

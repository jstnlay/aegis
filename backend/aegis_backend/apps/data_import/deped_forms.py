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
    the school's Electronic Class Record -> grades or students
        the same ``TERM n SUMMARY`` layout, plus an ``INPUT DATA`` roster
        and a ``COMMENT`` sheet.  See ``ECR`` below.

All readers are structural: a revised form that moves the header band, drops a
sheet, or renames a learning area fails loudly here instead of silently
attaching values to the wrong learner or subject.

Learner identity
----------------
Neither form carries the app's student code.  The learner's *name* cell (SF9
column C, SF2 column B) is taken as ``student_id`` and resolved by the existing
importer, so a filled form must carry the school code the Students export
shows -- see ``docs/test-data/README.md``.

The ECR is the exception: it carries the learner's LRN next to the name, and
the LRN is the key.  The two forms are told apart by their sheets -- the ECR
has no ``FINAL GRADES`` sheet -- so the two identity rules never mix.
"""

from __future__ import annotations

from datetime import date, datetime

from .constants import ImportType

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

# ---------------------------------------------------------------------------
# ECR (the school's Electronic Class Record)
# ---------------------------------------------------------------------------

#: The ECR workbook is the same DepEd form family as the SF9 template -- the
#: same ``TERM n SUMMARY`` layout -- minus the ``FINAL GRADES`` sheet and plus
#: a ``COMMENT`` sheet that carries the teacher's remarks for each term.
ECR_INPUT_DATA_SHEET = "INPUT DATA"
ECR_SF9_SHEET = "SF9 - GRADE 4-10"
ECR_COMMENT_SHEET = "COMMENT"

#: The ECR identifies a learner by LRN: column F of a summary sheet, and
#: columns M / R of the ``INPUT DATA`` roster.  The legacy SF9 form carries
#: the school's own code in the *name* column instead.
ECR_LRN_COLUMN = 6
#: ``INPUT DATA`` roster blocks: (name column, LRN column, birthdate column)
#: for the male block and the female block.  Both start at the same row.
ECR_ROSTER_COLUMNS = ((12, 13, 14), (17, 18, 19))
ECR_ROSTER_FIRST_ROW = 11
#: The roster's last column (the female block's birthdate).
ECR_ROSTER_MAX_COLUMN = 19
#: ``INPUT DATA`` header cells: school year, grade level, section.
ECR_SCHOOL_YEAR_CELL = (18, 6)
ECR_GRADE_LEVEL_CELL = (27, 6)
ECR_SECTION_CELL = (28, 6)
#: ``COMMENT`` sheet: the learner's name, then one column per term.
ECR_COMMENT_NAME_COLUMN = 2
ECR_COMMENT_FIRST_ROW = 3
ECR_COMMENT_TERM_COLUMNS = {"Term 1": 3, "Term 2": 4, "Term 3": 5}
#: The COMMENT sheet's last column (Term 3).
ECR_COMMENT_MAX_COLUMN = 5
#: The ECR has no email column and a learner account needs one.  The LRN is
#: unique across the roster, so the address is derived from it and never
#: collides.  The domain is deliberately not routable.
ECR_STUDENT_EMAIL_DOMAIN = "students.aegis.local"

#: The roster columns the students importer accepts.
STUDENT_HEADERS = (
    "student_id",
    "first_name",
    "last_name",
    "email",
    "grade_level",
    "section",
    "academic_year",
    "date_of_birth",
)


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
    """``8``, ``"8"``, ``8.0`` and ``"Grade 8"`` all mean level 8."""
    text = _text(raw)
    if text.endswith(".0") and text[:-2].isdigit():
        text = text[:-2]
    if text.lower().startswith("grade"):
        text = text[5:].strip()
    return text


def _key(value):
    """Casefolded, whitespace-collapsed comparison form."""
    return " ".join(str(value).split()).casefold()


def _lrn(value):
    """The LRN cell as text; a whole number keeps every digit it carries."""
    if value is None or isinstance(value, bool):
        return ""
    if isinstance(value, (int, float)):
        return str(int(value)) if float(value).is_integer() else str(value)
    return _text(value)


def _iso_date(value):
    """A date cell as ``YYYY-MM-DD``; anything else reads as empty."""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return ""


def _split_name(name):
    """
    ``"Andaya, Gabriel"`` -> ``("Andaya", "Gabriel")``.

    The ECR writes names as ``Surname, Given names``.  A name that arrives
    without its comma is still a learner, so the separators are tried in the
    order the school writes them -- the comma, then the full stop the one
    name in the current roster carries, then plain whitespace -- rather than
    dropping the learner from the school.
    """
    for separator in (",", ". "):
        last, found, first = name.partition(separator)
        if found:
            return last.strip(), first.strip().rstrip(",").strip()
    last, _, first = name.partition(" ")
    return last.strip(), first.strip().rstrip(",").strip()


def _last_row(worksheet):
    """
    The sheet's last row that carries content.

    A read-only workbook reports ``max_row`` from the sheet's dimension
    record, and a sheet written without one reports ``None``.  The last row
    with content is then found by looking at the cells.
    """
    if worksheet.max_row:
        return worksheet.max_row
    last = 0
    for cells in worksheet.iter_rows():
        for cell in cells:
            if cell.value is not None and getattr(cell, "row", 0) > last:
                last = cell.row
    return last


def _sheet_snapshot(worksheet, max_column):
    """
    The sheet's cells, read once: ``{row number: {column number: value}}``.

    ``worksheet.cell()`` on a read-only workbook re-reads the sheet's XML on
    every call, so one lookup on a form with a thousand rows costs a thousand
    parses.  One pass over the rows is a fraction of that.

    A read-only row is padded with ``EmptyCell`` objects, which carry neither
    a row nor a column, so the cells that hold something decide the row.
    """
    snapshot = {}
    for cells in worksheet.iter_rows(max_col=max_column):
        values = {}
        row_number = None
        for cell in cells:
            if not hasattr(cell, "row"):
                continue
            if cell.value is not None:
                values[cell.column] = cell.value
                if row_number is None:
                    row_number = cell.row
        if values:
            snapshot[row_number] = values
    return snapshot


def _valid_level(text):
    """True when ``text`` names a grade level an SF9 may carry."""
    return text.isdigit() and SF9_LEVEL_RANGE[0] <= int(text) <= SF9_LEVEL_RANGE[1]


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------


def _is_ecr(names):
    """The school's ECR: the SF9 form family without the ``FINAL GRADES`` sheet."""
    return (
        ECR_INPUT_DATA_SHEET in names
        and ECR_SF9_SHEET in names
        and "FINAL GRADES" not in names
        and all(sheet in names for sheet, _ in SF9_TERM_SHEETS)
    )


def detect(sheet_names):
    """Return ``"sf9"`` / ``"sf2"`` / ``"ecr"`` when the workbook is a known DepEd form."""
    names = set(sheet_names)
    if _is_ecr(names):
        return "ecr"
    if "FINAL GRADES" in names and all(
        sheet in names for sheet, _ in SF9_TERM_SHEETS
    ):
        return "sf9"
    if SF2_SHEET in names:
        return "sf2"
    return None


def read(workbook, import_type=None):
    """
    Translate a recognised DepEd workbook into ``(headers, rows)``.

    ``rows`` are flat dicts keyed by the importers' own column names, ready for
    the same header/row validation a CSV upload goes through.

    ``import_type`` decides which dataset an ECR workbook yields: one workbook
    carries the roster, the grades and the teacher's remarks, and one upload is
    still one dataset.
    """
    kind = detect(workbook.sheetnames)
    if kind == "sf9":
        return read_sf9(workbook)
    if kind == "sf2":
        return read_sf2(workbook)
    if kind == "ecr":
        return read_ecr(workbook, import_type)
    raise DepedFormError(
        "INVALID_WORKBOOK", "The workbook is not a recognised DepEd form."
    )


# ---------------------------------------------------------------------------
# SF9 -> grade rows
# ---------------------------------------------------------------------------


def _check_sf9_band(snapshot, sheet_name):
    """Assert the learning-area band is where and what the reader expects."""
    band = snapshot.get(SF9_AREA_BAND_ROW, {})
    labels = tuple(
        _text(band.get(SF9_AREA_FIRST_COL + i))
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
    return _read_summary_sheets(workbook, SF9_NAME_COL)


def _read_summary_sheets(workbook, id_column, remarks=None):
    """
    The shared ``TERM n SUMMARY`` reader.

    ``id_column`` is the column carrying the learner's key, and ``remarks``
    maps a learner's name to ``{grading period: remark}``.  Everything else --
    the learning-area band, the term a sheet stands for, the MAPEH sub-scores
    -- is the same form in both workbooks.
    """
    rows = []
    for sheet_name, period in SF9_TERM_SHEETS:
        worksheet = workbook[sheet_name]
        snapshot = _sheet_snapshot(worksheet, SF9_AREA_COLUMNS[-1][-1])
        _check_sf9_band(snapshot, sheet_name)

        header = snapshot.get(SF9_GRADE_LEVEL_CELL[0], {})
        level = _normalize_level(header.get(SF9_GRADE_LEVEL_CELL[1]))
        section_name = _text(
            snapshot.get(SF9_SECTION_CELL[0], {}).get(SF9_SECTION_CELL[1])
        )
        if not _valid_level(level) or not section_name:
            # A summary with no school level/section carries no importable rows.
            # The unfilled template lands here: its level cell caches ``0``.
            continue
        section = f"Grade {level} - {section_name}"

        learners = 0
        for row in range(SF9_FIRST_LEARNER_ROW, max(snapshot, default=0) + 1):
            values = snapshot.get(row)
            if not values:
                break
            name = _text(values.get(SF9_NAME_COL))
            if not name:
                break

            learners += 1
            # The ECR identifies the learner by LRN; the legacy SF9 form
            # carries the school's own code in the name cell.  A learner row
            # whose LRN is missing keeps no key, and the importer rejects that
            # row with its own reason -- failing the whole file would throw
            # away the other learners' grades for one empty cell.
            student_id = (
                name
                if id_column == SF9_NAME_COL
                else _lrn(values.get(ECR_LRN_COLUMN))
            )
            remark = (remarks or {}).get(_key(name), {}).get(period, "")
            for (label, base), columns in zip(SF9_LABEL_TO_BASE, SF9_AREA_COLUMNS):
                scores = [
                    score
                    for score in (
                        _number(values.get(column)) for column in columns
                    )
                    if score is not None
                ]
                if not scores:
                    continue
                grade_row = {
                    "student_id": student_id,
                    "section": section,
                    "subject_code": f"{base}-{level}",
                    "grading_period": period,
                    "score": _format_number(sum(scores) / len(scores)),
                }
                if remark:
                    grade_row["remarks"] = remark
                rows.append(grade_row)

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
    for row in range(SF2_FIRST_LEARNER_ROW, _last_row(sheet) + 1):
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


# ---------------------------------------------------------------------------
# ECR -> grade rows, roster rows
# ---------------------------------------------------------------------------


def read_ecr(workbook, import_type):
    """
    The school's Electronic Class Record -> one dataset, chosen by import type.

    The workbook carries the roster, the grades and the teacher's remarks, so
    the import type decides which one is read.  A type the workbook does not
    carry fails loudly: a silent 0-row job would read as a successful import
    of nothing.
    """
    if import_type is None:
        raise DepedFormError(
            "INVALID_FILE_CONTENT",
            "This workbook carries several datasets; the import type decides "
            "which one is read.",
        )
    if import_type == ImportType.GRADES:
        return _read_summary_sheets(
            workbook, ECR_LRN_COLUMN, _ecr_remarks(workbook)
        )
    if import_type == ImportType.STUDENTS:
        return _read_ecr_students(workbook)
    if import_type == ImportType.ATTENDANCE:
        raise DepedFormError(
            "INVALID_FILE_CONTENT",
            "This ECR workbook carries no daily attendance marks: its "
            "ATTENDANCE RECORD SUMMARY sheet lists the roster and the school "
            "days per month. Upload the DepEd SF2 form for attendance.",
        )
    if import_type == ImportType.GUIDANCE_RECORDS:
        raise DepedFormError(
            "INVALID_FILE_CONTENT",
            "This ECR workbook carries no guidance records: its COMMENT sheet "
            "holds the teacher's remarks, which are imported with the grades.",
        )
    raise DepedFormError(
        "INVALID_FILE_CONTENT",
        f"This ECR workbook carries no {import_type} dataset.",
    )


def _ecr_remarks(workbook):
    """``{learner name: {grading period: remark}}`` from the COMMENT sheet."""
    if ECR_COMMENT_SHEET not in workbook.sheetnames:
        return {}
    sheet = workbook[ECR_COMMENT_SHEET]
    snapshot = _sheet_snapshot(sheet, ECR_COMMENT_MAX_COLUMN)
    remarks = {}
    for row in range(ECR_COMMENT_FIRST_ROW, max(snapshot, default=0) + 1):
        values = snapshot.get(row, {})
        name = _text(values.get(ECR_COMMENT_NAME_COLUMN))
        if not name:
            continue
        for period, column in ECR_COMMENT_TERM_COLUMNS.items():
            remark = _text(values.get(column))
            if remark:
                remarks.setdefault(_key(name), {})[period] = remark
    return remarks


def _read_ecr_students(workbook):
    """The ``INPUT DATA`` roster -> one student row per learner."""
    if ECR_INPUT_DATA_SHEET not in workbook.sheetnames:
        raise DepedFormError(
            "MISSING_REQUIRED_COLUMN",
            "The ECR workbook has no INPUT DATA sheet carrying the roster.",
        )
    sheet = workbook[ECR_INPUT_DATA_SHEET]
    snapshot = _sheet_snapshot(sheet, ECR_ROSTER_MAX_COLUMN)

    level = _normalize_level(
        snapshot.get(ECR_GRADE_LEVEL_CELL[0], {}).get(ECR_GRADE_LEVEL_CELL[1])
    )
    section_name = _text(
        snapshot.get(ECR_SECTION_CELL[0], {}).get(ECR_SECTION_CELL[1])
    )
    school_year = _text(
        snapshot.get(ECR_SCHOOL_YEAR_CELL[0], {}).get(ECR_SCHOOL_YEAR_CELL[1])
    )
    if not (level and section_name):
        raise DepedFormError(
            "MISSING_REQUIRED_COLUMN",
            "The ECR INPUT DATA sheet is missing its grade level or section; "
            "fill them in before importing the roster.",
        )

    rows = []
    for row in range(ECR_ROSTER_FIRST_ROW, max(snapshot, default=0) + 1):
        values = snapshot.get(row, {})
        for name_column, lrn_column, dob_column in ECR_ROSTER_COLUMNS:
            name = _text(values.get(name_column))
            lrn = _lrn(values.get(lrn_column))
            if not name:
                continue
            # A learner without an LRN keeps its row: the importer gives that
            # row its own reason instead of the whole roster failing.
            last_name, first_name = _split_name(name)
            rows.append(
                {
                    "student_id": lrn,
                    "first_name": first_name,
                    "last_name": last_name,
                    "email": f"{lrn}@{ECR_STUDENT_EMAIL_DOMAIN}" if lrn else "",
                    "grade_level": level,
                    "section": section_name,
                    "academic_year": school_year,
                    "date_of_birth": _iso_date(values.get(dob_column)),
                }
            )

    return STUDENT_HEADERS, rows

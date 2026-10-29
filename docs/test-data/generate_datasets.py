"""
Generate the import-ready datasets derived from the DepEd SF2 and SF9 forms.

Which templates
---------------
Both DepEd forms ship in this folder and both are read here:

    SF2 JUNIOR HS.xlsm                     -> attendance-sf2.csv
    G4-10  School Form 9 (SY 26-27).xlsx   -> grades-sf9.csv,
                                              grades-sf9-terms-1-2.csv

SF2 is the School Form 2 daily attendance record; SF9 is the School Form 9
Learner's Progress Report Card (formerly Form 138).  SF9 carries the per-term
grades in its ``TERM 1/2/3 SUMMARY`` sheets and the report card itself on
``SF9 - GRADE 4-10``, which is why the grade outputs are named
``grades-sf9*.csv`` and follow SF9's eight learning areas.

Why this file exists
--------------------
The shipped forms are not importable as they stand: SF2 is a per-month
absence/tardy grid with a multi-row header (metadata rows 3-4, header rows 5-7,
one row per learner from row 8), and SF9 is a per-term class summary whose
learning areas sit in one header band with numbered, not named, learner rows.
A school's export arrives in that shape; the importer consumes a flat,
one-record-per-row table (``apps/data_import/importers``).

This script is the bridge.  It reads each template, confirms the shape it
depends on is the shape actually on disk, and writes flat CSV files whose
headers are exactly the columns the importers accept:

Nothing here invents a rule the importers do not already enforce.  The school
keys written (``Grade 8 - Bonifacio``, ``ENG-8``, ``Term 3``) are the human
forms ``resolution.py`` resolves, and the loader resolves the student codes and
the reference data it needs at run time -- see ``seed_datasets.py``.

Determinism: every draw is keyed on a stable string, so regenerating produces
byte-identical files.  Re-running this script must never move a value a test
asserts on.

Usage (from ``backend/aegis_backend``):

    python ../../../docs/test-data/generate_datasets.py

Run it only when a template changes; the generated CSVs are committed.
"""

from __future__ import annotations

import csv
import io
import random
import re
import zipfile
from datetime import date, datetime, timedelta
from pathlib import Path

import openpyxl

HERE = Path(__file__).resolve().parent

SF2_TEMPLATE = "SF2 JUNIOR HS.xlsm"
SF9_TEMPLATE = "G4-10  School Form 9 (SY 26-27).xlsx"

ATTENDANCE_OUT = HERE / "attendance-sf2.csv"
GRADES_OUT = HERE / "grades-sf9.csv"
#: A second grade batch covering the earlier terms.  Uploaded *after*
#: ``GRADES_OUT`` in the trend test, it adds history so the academic trend has
#: more than one period to plot.  Same roster, same subjects, different terms.
GRADES_EARLIER_OUT = HERE / "grades-sf9-terms-1-2.csv"

# ---------------------------------------------------------------------------
# References that must match the seeded QA world (seed_qa_dataset.py).
#
# These are constants, not lookups: the generator does not touch the database.
# A mismatch is caught by the ``_check`` calls below and by the pipeline test,
# which imports the files through the real API against a freshly seeded school.
# ---------------------------------------------------------------------------

SCHOOL_YEAR = "2026-2027"

#: The sections the dataset covers: 50 learners, two sections of 25.  Each
#: tuple is (first roster index, grade level number, section name).
#:
#: ``seed_qa_dataset`` numbers students ``S{roster_index + 1:04d}`` over a
#: 100-student roster laid out section by section, so index 25 opens Grade 8
#: Bonifacio (S0026-S0050) and index 50 opens Grade 9 Mabini (S0051-S0075).
SECTIONS = (
    (25, 8, "Bonifacio"),
    (50, 9, "Mabini"),
)
STUDENTS_PER_SECTION = 25
LEARNER_COUNT = STUDENTS_PER_SECTION * len(SECTIONS)  # 50

#: Eight DepEd JHS learning areas, base code -> name.  ``Subject.code`` is
#: globally unique, so the seeded school suffixes the level: ``FIL-8`` for
#: Grade 8, ``FIL-9`` for Grade 9.  ``_subject_code`` composes the two.
LEARNING_AREAS = (
    ("FIL", "Filipino"),
    ("ENG", "English"),
    ("MATH", "Mathematics"),
    ("AP", "Araling Panlipunan"),
    ("SCI", "Science"),
    ("TLE", "Technology and Livelihood Education"),
    ("MAPEH", "MAPEH"),
    ("ESP", "Edukasyon sa Pagpapakatao"),
)

#: SF9's own learning-area labels, mapped to the base subject code.  The labels
#: are read from the workbook and compared to this mapping, so a revised form
#: that renames or reorders an area fails the check instead of silently writing
#: grades against the wrong column.
#:
#: ``GMRC/VE`` is the current DepEd name for what the seed command still calls
#: "Edukasyon sa Pagpapakatao" (``ESP``); ``EPP/TLE`` is ``TLE``.  The dataset
#: keeps the seed's codes -- the template supplies the structure.
SF9_LEARNING_AREAS = {
    "Filipino": "FIL",
    "English": "ENG",
    "Mathematics": "MATH",
    "Science": "SCI",
    "AP": "AP",
    "GMRC/VE": "ESP",
    "EPP/TLE": "TLE",
    "MAPEH": "MAPEH",
}

#: Where SF9's per-term summary puts the learning-area band: one label per
#: column, starting at column K, on row 12 of each ``TERM n SUMMARY`` sheet.
SF9_LEARNING_AREA_ROW = 12
SF9_LEARNING_AREA_FIRST_COL = 11

#: Base subject code -> the column its grade belongs in on that band.  Derived
#: from ``SF9_LEARNING_AREAS`` so the writer and the check cannot disagree.
SF9_AREA_COLUMNS = {
    base: SF9_LEARNING_AREA_FIRST_COL + offset
    for offset, base in enumerate(SF9_LEARNING_AREAS.values())
}
#: First learner row and the name column on a summary sheet.
SF9_FIRST_LEARNER_ROW = 15
SF9_NAME_COL = 3
#: The summary sheets carry GRADE LEVEL and SECTION here; both are formulas
#: pointing at the input sheet, so the generator writes plain values.
SF9_GRADE_LEVEL_CELL = (9, 7)
SF9_SECTION_CELL = (10, 7)

#: Filled DepEd workbooks -- the files a person uploads.  One workbook is one
#: section: SF9's summary sheet and SF2's month grid each hold a single class.
SF9_WORKBOOK_NAME = "grades-sf9-{slug}.xlsx"
SF9_EARLIER_WORKBOOK_NAME = "grades-sf9-terms-1-2-{slug}.xlsx"
SF2_WORKBOOK_NAME = "attendance-sf2-{slug}.xlsm"

#: SF2's school header lives on its own COVER sheet.
SF2_COVER_ROWS = (
    ("school_name", "B1", "AEGIS QA National High School"),
    ("section", "B2", None),
    ("school_id", "B3", "123456"),
    ("school_year", "B4", SCHOOL_YEAR),
    ("grade_level", "B5", None),
    ("month", "B6", None),
    ("adviser", "B7", "EUNICE FERNANDEZ"),
)
SF2_FIRST_LEARNER_ROW = 8
SF2_NAME_COL = 2
SF2_FIRST_DAY_COL = 5
SF2_LAST_DAY_COL = 29
SF2_DAY_NUMBER_ROW = 6

#: One completed term's worth of attendance.  SF2 is a monthly form; the files
#: carry one school week per learner across a term-closing week, which is a
#: legal, in-the-past window (nothing here is in the future).
ATTENDANCE_MONTH = date(2026, 9, 7)  # Monday, inside Term 1.
ATTENDANCE_WEEKDAYS = 5

#: DepEd SF2 day codes.  ``X`` = absent, ``L`` = tardy, blank = present.
SF2_ABSENT_CODE = "X"
SF2_TARDY_CODE = "L"

#: Term the grade file belongs to.  Term 1 is finalized in the seeded school,
#: so the importer locks it -- the file targets Term 3, which is open, exactly
#: like the existing ``grades-import.xlsx`` does.
GRADING_PERIOD = "Term 3"

#: Earlier terms, written to their own file and uploaded in a *second* batch.
#: Two batches is what makes the historical trend real: the trend endpoint then
#: has one point per term instead of one term repeated.
EARLIER_TERMS = ("Term 1", "Term 2")

# ---------------------------------------------------------------------------
# Score / attendance mix
#
# Deliberately shaped so the rule engine produces a real at-risk population:
# a third of the roster is a weak cohort whose scores sit below the passing
# mark and whose attendance is poor, a third is borderline, and a third is
# secure.  Without this spread the algorithm has nothing to flag.
# ---------------------------------------------------------------------------

#: (label, mean score, spread, present-probability) per band.
BANDS = (
    ("secure", 90.0, 3.0, 0.98),
    ("borderline", 78.0, 3.5, 0.88),
    ("at_risk", 63.0, 4.0, 0.68),
)

#: Which roster positions (0-based) land in which band.  Round-robin keeps the
#: bands interleaved across the roster, which is what a real section looks like
#: and what makes the dashboard's filters show a full spread.
def band_for(index: int) -> tuple:
    return BANDS[index % len(BANDS)]


def _student_code(first_index: int, index: int) -> str:
    """Roster position within a section -> the school code seed wrote for it."""
    return f"AEGIS-QA-S{first_index + index + 1:04d}"


def _section_key(level_number: int, section_name: str) -> str:
    """The human section form the importer resolves (``Grade 8 - Bonifacio``)."""
    return f"Grade {level_number} - {section_name}"


def _subject_code(area_code: str, level_number: int) -> str:
    """``Subject.code`` as the seed builds it: ``FIL`` + ``8`` -> ``FIL-8``."""
    return f"{area_code}-{level_number}"


def _rand(seed_key: str) -> random.Random:
    return random.Random(f"aegis-datasets::{seed_key}")


def _learner_scores(level_number: int, index: int, term: str, seed_prefix: str) -> dict:
    """
    One learner's score per learning area for one term.

    Insertion order follows ``LEARNING_AREAS`` and the RNG draws happen in that
    same order, so the flat CSV and the filled workbook carry identical values.
    """
    _, mean, spread, _ = band_for(index)
    rng = _rand(f"{seed_prefix}::{level_number}::{index}")
    return {
        area_code: max(0.0, min(100.0, round(rng.gauss(mean, spread), 2)))
        for area_code, _name in LEARNING_AREAS
    }


def _learner_attendance(level_number: int, index: int) -> list:
    """One learner's status for each school day of the recorded week."""
    _, _, _, present_prob = band_for(index)
    rng = _rand(f"attendance::{level_number}::{index}")
    statuses = []
    for _ in range(ATTENDANCE_WEEKDAYS):
        draw = rng.random()
        if draw < present_prob:
            statuses.append("present")
        elif draw < present_prob + 0.10:
            statuses.append("late")
        else:
            statuses.append("absent")
    return statuses


# ---------------------------------------------------------------------------
# Template shape checks
# ---------------------------------------------------------------------------


def _check_sf2_template() -> None:
    """
    Confirm the SF2 sheet is the shape this generator fills.

    SF2 is a blank form on disk (no learner data), so the check is structural:
    the metadata cells and the day-header band must be where the sheet places
    them.  If DepEd or the school revises the form, this fails loudly instead
    of silently writing a file against a layout the form no longer has.
    """
    wb = openpyxl.load_workbook(HERE / SF2_TEMPLATE, read_only=True, data_only=True)
    try:
        ws = wb["SF2-JHS"]
        a3 = ws.cell(row=3, column=1).value or ""
        a4 = ws.cell(row=4, column=1).value or ""
        assert "School ID" in a3, f"SF2 row 3 no longer the metadata row: {a3!r}"
        grade_level_cell = ws.cell(row=4, column=15).value or ""
        assert (
            "Grade Level" in grade_level_cell
        ), f"SF2 row 4 no longer the metadata row: {grade_level_cell!r}"
        day_codes = [
            (ws.cell(row=7, column=c).value or "") for c in range(5, 30)
        ]
        assert day_codes[:5] == ["M", "T", "W", "TH", "F"], day_codes[:5]
    finally:
        wb.close()


def _check_sf9_template() -> None:
    """
    Confirm SF9 is the shape the grade writer reads.

    Two things must hold, or the generated grades would be silently attached to
    the wrong subjects: the per-term summary sheets must exist, and each one's
    learning-area band must be exactly the areas ``SF9_LEARNING_AREAS`` maps.
    SF9 ships blank, so this is a structural check rather than a data one --
    the same contract ``_check_sf2_template`` makes for attendance.
    """
    wb = openpyxl.load_workbook(HERE / SF9_TEMPLATE, read_only=True, data_only=True)
    try:
        for sheet in (
            "TERM 1 SUMMARY",
            "TERM 2 SUMMARY",
            "TERM 3 SUMMARY",
            "FINAL GRADES",
            "SF9 - GRADE 4-10",
        ):
            assert sheet in wb.sheetnames, f"SF9 lost the {sheet!r} sheet: {wb.sheetnames}"

        expected = tuple(SF9_LEARNING_AREAS)
        for sheet in ("TERM 1 SUMMARY", "TERM 2 SUMMARY", "TERM 3 SUMMARY"):
            ws = wb[sheet]
            labels = tuple(
                ws.cell(
                    row=SF9_LEARNING_AREA_ROW,
                    column=SF9_LEARNING_AREA_FIRST_COL + offset,
                ).value
                for offset in range(len(SF9_LEARNING_AREAS))
            )
            assert labels == expected, (
                f"{sheet} learning areas moved or were renamed: {labels!r}"
            )
    finally:
        wb.close()


def _check_subject_mapping() -> None:
    """SF9's areas must resolve to the codes the grade writer emits."""
    codes = {code for code, _name in LEARNING_AREAS}
    mapped = set(SF9_LEARNING_AREAS.values())
    assert mapped == codes, (
        "SF9 learning areas and LEARNING_AREAS disagree: "
        f"only in SF9 {sorted(mapped - codes)}, "
        f"only in LEARNING_AREAS {sorted(codes - mapped)}"
    )


def _check_learner_count() -> None:
    """The objective asks for at least 50 student samples."""
    assert LEARNER_COUNT >= 50, f"only {LEARNER_COUNT} learners are covered"


# ---------------------------------------------------------------------------
# Dataset writers
# ---------------------------------------------------------------------------


def write_attendance() -> int:
    """
    SF2 grid -> flat attendance rows.

    One row per (learner, school day) for every section.  The status vocabulary
    is the SF2 day code mapped to the importer's own: present / late / absent.
    """
    rows = []
    for first_index, level_number, section_name in SECTIONS:
        section = _section_key(level_number, section_name)
        for index in range(STUDENTS_PER_SECTION):
            student = _student_code(first_index, index)
            for day_offset, status in enumerate(_learner_attendance(level_number, index)):
                day = ATTENDANCE_MONTH + timedelta(days=day_offset)
                rows.append(
                    {
                        "student_id": student,
                        "section": section,
                        "date": day.isoformat(),
                        "status": status,
                    }
                )

    _write_csv(
        ATTENDANCE_OUT,
        ("student_id", "section", "date", "status"),
        rows,
    )
    return len(rows)


def write_grades() -> int:
    """
    SF9 term grades -> flat grade rows.

    One row per (learner, SF9 learning area) for the open term.  The area set and
    its order come from ``LEARNING_AREAS``, which ``_check_sf9_template`` has
    already proved is the template's own band.  ``letter_grade`` and the DepEd
    ``remarks`` come from the same scale the seed command uses, so a row's
    descriptor agrees with its score.
    """
    rows = _grade_rows(GRADING_PERIOD, f"grades::{GRADING_PERIOD}")

    _write_csv(
        GRADES_OUT,
        (
            "student_id",
            "section",
            "subject_code",
            "grading_period",
            "score",
            "letter_grade",
            "remarks",
        ),
        rows,
    )
    return len(rows)


def write_earlier_grades() -> int:
    """
    The earlier terms' grades -> a second grade batch.

    Uploaded after ``write_grades`` in the trend test.  Each term draws from
    the same band mean as Term 3 but with its own seed, so every period has a
    distinct average and the trend is a real curve rather than one flat line.
    """
    rows = []
    for term in EARLIER_TERMS:
        rows.extend(_grade_rows(term, f"grades::{term}"))

    _write_csv(
        GRADES_EARLIER_OUT,
        (
            "student_id",
            "section",
            "subject_code",
            "grading_period",
            "score",
            "letter_grade",
            "remarks",
        ),
        rows,
    )
    return len(rows)


def _grade_rows(term: str, seed_prefix: str) -> list[dict]:
    """One row per (learner, learning area) for one term, across all sections."""
    rows = []
    for first_index, level_number, section_name in SECTIONS:
        section = _section_key(level_number, section_name)
        for index in range(STUDENTS_PER_SECTION):
            student = _student_code(first_index, index)
            scores = _learner_scores(level_number, index, term, seed_prefix)
            for area_code, score in scores.items():
                letter, remark = _descriptor(score)
                rows.append(
                    {
                        "student_id": student,
                        "section": section,
                        "subject_code": _subject_code(area_code, level_number),
                        "grading_period": term,
                        "score": _format_score(score),
                        "letter_grade": letter,
                        "remarks": remark,
                    }
                )
    return rows


#: (minimum, letter, remark), highest first.  Mirrors seed_qa_dataset.GRADE_SCALE
#: so an imported row reads the same way a seeded one does.
_GRADE_SCALE = (
    (90, "A", "Outstanding"),
    (85, "B+", "Very Satisfactory"),
    (80, "B", "Satisfactory"),
    (75, "C+", "Fairly Satisfactory"),
    (70, "C", "Fairly Satisfactory"),
    (65, "D", "Fairly Satisfactory"),
    (0, "F", "Failed"),
)


def _descriptor(score: float) -> tuple[str, str]:
    for minimum, letter, remark in _GRADE_SCALE:
        if score >= minimum:
            return letter, remark
    return "F", "Failed"


def _format_score(score: float) -> str:
    """Drop a trailing ``.0`` so whole scores read as whole numbers."""
    return str(int(score)) if float(score).is_integer() else f"{score:g}"


def _write_csv(path: Path, headers: tuple, rows: list[dict]) -> None:
    """Write deterministic UTF-8 CSV with ``\\n`` endings and no BOM."""
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(headers), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


# ---------------------------------------------------------------------------
# Filled DepEd workbooks
#
# The CSVs above are the flat intermediate the automated tests read.  These
# writers fill a copy of each shipped template instead, so a person can import
# a file that looks like the form the school actually fills in.
# ``apps/data_import/deped_forms.py`` reads them back.
# ---------------------------------------------------------------------------

#: Pinned so regenerating a workbook is byte-identical run to run.
_FIXED_TIMESTAMP = datetime(2026, 9, 1, 0, 0, 0)

#: SF2 mark per importer status.  The form marks the exceptions only.
_SF2_MARK_BY_STATUS = {"present": "", "late": "L", "absent": "X"}


def _stamp(workbook) -> None:
    workbook.properties.created = _FIXED_TIMESTAMP
    workbook.properties.modified = _FIXED_TIMESTAMP


def _finalize_workbook(path: Path) -> None:
    """
    Pin the clock openpyxl stamps into a saved workbook.

    ``openpyxl`` writes the current time into every ZIP entry and into
    ``docProps/core.xml``'s ``dcterms:modified``, so two runs of this script
    would otherwise produce different bytes for identical content.  Rewriting
    the archive with a fixed timestamp keeps the committed workbooks
    reproducible.  Nothing inside a sheet is touched.
    """
    buffer = io.BytesIO()
    modified = _FIXED_TIMESTAMP.strftime("%Y-%m-%dT%H:%M:%SZ").encode()
    with zipfile.ZipFile(path) as source:
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as target:
            for item in source.infolist():
                data = source.read(item.filename)
                if item.filename == "docProps/core.xml":
                    data = re.sub(
                        rb"<dcterms:modified[^>]*>[^<]*</dcterms:modified>",
                        b'<dcterms:modified xsi:type="dcterms:W3CDTF">'
                        + modified
                        + b"</dcterms:modified>",
                        data,
                    )
                item.date_time = (1980, 1, 1, 0, 0, 0)
                target.writestr(item, data)
    path.write_bytes(buffer.getvalue())


def _section_for_level(level_number: int) -> tuple[int, str]:
    """(first roster index, section name) for a grade level in ``SECTIONS``."""
    for first_index, level, section_name in SECTIONS:
        if level == level_number:
            return first_index, section_name
    raise KeyError(f"no section for grade level {level_number}")


def _workbook_path(name_template: str, section_name: str) -> Path:
    return HERE / name_template.format(slug=section_name.lower())


def _clear_sf9_learner_rows(worksheet) -> None:
    """
    Blank the learner area before writing.

    The shipped SF9 carries three sample learners (rows 15-17) with grades in
    them.  Left in place they would survive into the first rows of a filled
    form -- the reader would then average a sample score with a real one.
    """
    columns = (SF9_NAME_COL, *range(SF9_LEARNING_AREA_FIRST_COL, SF9_LEARNING_AREA_FIRST_COL + 9))
    for index in range(STUDENTS_PER_SECTION):
        row = SF9_FIRST_LEARNER_ROW + index
        for column in columns:
            worksheet.cell(row=row, column=column).value = None


def write_sf9_workbook(path: Path, level_number: int, term_seeds: dict) -> int:
    """
    Fill a copy of the SF9 template for one section.

    ``term_seeds`` maps a grading-period name (``Term 3``) to the seed prefix
    its scores were drawn with.  Each term names its own ``TERM n SUMMARY``
    sheet; the learner rows and the learning-area columns are the ones
    ``deped_forms.read_sf9`` reads.
    """
    first_index, section_name = _section_for_level(level_number)
    workbook = openpyxl.load_workbook(HERE / SF9_TEMPLATE)
    written = 0
    try:
        for term, seed_prefix in term_seeds.items():
            worksheet = workbook[f"{term.upper()} SUMMARY"]
            worksheet.cell(
                row=SF9_GRADE_LEVEL_CELL[0], column=SF9_GRADE_LEVEL_CELL[1]
            ).value = level_number
            worksheet.cell(
                row=SF9_SECTION_CELL[0], column=SF9_SECTION_CELL[1]
            ).value = section_name
            _clear_sf9_learner_rows(worksheet)
            for index in range(STUDENTS_PER_SECTION):
                row = SF9_FIRST_LEARNER_ROW + index
                worksheet.cell(
                    row=row, column=SF9_NAME_COL
                ).value = _student_code(first_index, index)
                for base, score in _learner_scores(
                    level_number, index, term, seed_prefix
                ).items():
                    worksheet.cell(
                        row=row, column=SF9_AREA_COLUMNS[base]
                    ).value = score
                    written += 1
        _stamp(workbook)
        workbook.save(path)
        _finalize_workbook(path)
    finally:
        workbook.close()
    return written


def write_sf2_workbook(path: Path, level_number: int) -> int:
    """
    Fill a copy of the SF2 template for one section's recorded week.

    The school header goes on ``COVER`` (the sheet the form reads it from), the
    day numbers on the date row, and each learner's marks in the day columns.
    """
    first_index, section_name = _section_for_level(level_number)
    workbook = openpyxl.load_workbook(HERE / SF2_TEMPLATE, keep_vba=True)
    written = 0
    try:
        cover = workbook["COVER"]
        for key, cell, value in SF2_COVER_ROWS:
            if value is None:
                value = {
                    "section": section_name,
                    "grade_level": level_number,
                    "month": ATTENDANCE_MONTH.strftime("%B"),
                }[key]
            cover[cell] = value

        sheet = workbook["SF2-JHS"]
        # The shipped form carries a placeholder day number in every column.
        # Clear the slots this month does not use, or the reader would import
        # the same day once per column.
        for column in range(SF2_FIRST_DAY_COL, SF2_LAST_DAY_COL + 1):
            offset = column - SF2_FIRST_DAY_COL
            sheet.cell(row=SF2_DAY_NUMBER_ROW, column=column).value = (
                ATTENDANCE_MONTH.day + offset if offset < ATTENDANCE_WEEKDAYS else None
            )

        for index in range(STUDENTS_PER_SECTION):
            row = SF2_FIRST_LEARNER_ROW + index
            sheet.cell(
                row=row, column=SF2_NAME_COL
            ).value = _student_code(first_index, index)
            for offset, status in enumerate(_learner_attendance(level_number, index)):
                sheet.cell(
                    row=row, column=SF2_FIRST_DAY_COL + offset
                ).value = _SF2_MARK_BY_STATUS[status]
                written += 1
        _stamp(workbook)
        workbook.save(path)
        _finalize_workbook(path)
    finally:
        workbook.close()
    return written


def main() -> None:
    _check_sf2_template()
    _check_sf9_template()
    _check_subject_mapping()
    _check_learner_count()

    attendance_rows = write_attendance()
    grade_rows = write_grades()
    earlier_rows = write_earlier_grades()
    print(f"{ATTENDANCE_OUT.name}: {attendance_rows} rows")
    print(f"{GRADES_OUT.name}: {grade_rows} rows")
    print(f"{GRADES_EARLIER_OUT.name}: {earlier_rows} rows")

    for _first_index, level_number, section_name in SECTIONS:
        grades_path = _workbook_path(SF9_WORKBOOK_NAME, section_name)
        earlier_path = _workbook_path(SF9_EARLIER_WORKBOOK_NAME, section_name)
        attendance_path = _workbook_path(SF2_WORKBOOK_NAME, section_name)
        grades = write_sf9_workbook(
            grades_path, level_number, {GRADING_PERIOD: f"grades::{GRADING_PERIOD}"}
        )
        earlier = write_sf9_workbook(
            earlier_path,
            level_number,
            {term: f"grades::{term}" for term in EARLIER_TERMS},
        )
        attendance = write_sf2_workbook(attendance_path, level_number)
        print(
            f"{grades_path.name}: {grades} grades | "
            f"{earlier_path.name}: {earlier} earlier-term grades | "
            f"{attendance_path.name}: {attendance} attendance marks"
        )

    print(f"learners: {LEARNER_COUNT} across {len(SECTIONS)} sections")


if __name__ == "__main__":
    main()

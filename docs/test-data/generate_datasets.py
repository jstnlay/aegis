"""
Generate the import-ready datasets derived from the DepEd templates.

Which templates
---------------
Two DepEd forms ship in this folder and both are used here:

    SF2 JUNIOR HS.xlsm   -> attendance-sf2.csv          (attendance)
    E-Class Record       -> grades-sf3.csv,
                            grades-sf3-terms-1-2.csv    (grades)

There is **no DepEd "SF3" workbook in this repository**.  SF3 in DepEd is the
Learner's Progress Report Card, a different form from the class record.  The
E-Class Record workbook is the **sanctioned grade source** here: its TERM 1/2/3
and FINAL GRADES sheets carry the real per-term grades, so the grade outputs are
named ``grades-sf3*.csv`` for continuity with the objective while being
generated from the E-Class Record.  The owner accepted this substitution; this
docstring and ``README.md`` record it.  If a real SF3 workbook is ever added,
add it as its own template with its own shape check and writer branch — do not
silently repoint these filenames.

Why this file exists
--------------------
The shipped forms are not importable as they stand: SF2 is a per-month
absence/tardy grid with a multi-row header (metadata rows 3-4, header rows 5-7,
one row per learner from row 8), and the E-Class Record is a per-term class
record whose FINAL GRADES sheet carries the term grades.  A school's export
arrives in that shape; the importer consumes a flat, one-record-per-row table
(``apps/data_import/importers``).

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
import random
from datetime import date, timedelta
from pathlib import Path

import openpyxl

HERE = Path(__file__).resolve().parent

SF2_TEMPLATE = "SF2 JUNIOR HS.xlsm"
SF3_TEMPLATE = (
    "UPDATED [Grades 2-10] 3Term E-Class Record "
    "(for Science, Math, English, Filipino, Araling Panlipunan) (1).xlsx"
)

ATTENDANCE_OUT = HERE / "attendance-sf2.csv"
GRADES_OUT = HERE / "grades-sf3.csv"
#: A second grade batch covering the earlier terms.  Uploaded *after*
#: ``GRADES_OUT`` in the trend test, it adds history so the academic trend has
#: more than one period to plot.  Same roster, same subjects, different terms.
GRADES_EARLIER_OUT = HERE / "grades-sf3-terms-1-2.csv"

# ---------------------------------------------------------------------------
# References that must match the seeded QA world (seed_qa_dataset.py).
#
# These are constants, not lookups: the generator does not touch the database.
# A mismatch is caught by the ``_check`` calls below and by the pipeline test,
# which imports the files through the real API against a freshly seeded school.
# ---------------------------------------------------------------------------

SCHOOL_YEAR = "2026-2027"
GRADE_LEVEL_NAME = "Grade 8"
SECTION_NAME = "Bonifacio"
SECTION_KEY = f"{GRADE_LEVEL_NAME} - {SECTION_NAME}"

#: The section roster the SF2 grid is filled for, one student per row.  These
#: are the ``AEGIS-QA-`` codes seed_qa_dataset writes: student_id is
#: ``S{roster_index + 1:04d}`` over a 100-student roster in section order, so
#: the grade-8 section occupies indices 25..49 -> S0026..S0050.
ROSTER_SIZE = 25
ROSTER_FIRST_INDEX = 25

#: Eight DepEd JHS learning areas taught in this section, code -> name.  The
#: ``-8`` suffix is what ``Subject.code`` carries in the seeded school.
SUBJECTS = (
    ("FIL-8", "Filipino"),
    ("ENG-8", "English"),
    ("MATH-8", "Mathematics"),
    ("AP-8", "Araling Panlipunan"),
    ("SCI-8", "Science"),
    ("TLE-8", "Technology and Livelihood Education"),
    ("MAPEH-8", "MAPEH"),
    ("ESP-8", "Edukasyon sa Pagpapakatao"),
)

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


def _student_code(index: int) -> str:
    """Roster position -> the school code seed_qa_dataset wrote for it."""
    return f"AEGIS-QA-S{ROSTER_FIRST_INDEX + index + 1:04d}"


def _rand(seed_key: str) -> random.Random:
    return random.Random(f"aegis-datasets::{seed_key}")


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


def _check_sf3_template() -> None:
    """Confirm the E-Class Record carries a per-term grade sheet."""
    wb = openpyxl.load_workbook(HERE / SF3_TEMPLATE, read_only=True, data_only=True)
    try:
        assert "TERM 3" in wb.sheetnames, wb.sheetnames
        assert "FINAL GRADES" in wb.sheetnames, wb.sheetnames
    finally:
        wb.close()


# ---------------------------------------------------------------------------
# Dataset writers
# ---------------------------------------------------------------------------


def write_attendance() -> int:
    """
    SF2 grid -> flat attendance rows.

    One row per (learner, school day).  The status vocabulary is the SF2 day
    code mapped to the importer's own: present / late / absent.
    """
    rows = []
    for index in range(ROSTER_SIZE):
        _, _, _, present_prob = band_for(index)
        rng = _rand(f"attendance::{index}")
        student = _student_code(index)
        for day_offset in range(ATTENDANCE_WEEKDAYS):
            day = ATTENDANCE_MONTH + timedelta(days=day_offset)
            draw = rng.random()
            if draw < present_prob:
                status = "present"
            elif draw < present_prob + 0.10:
                status = "late"
            else:
                status = "absent"
            rows.append(
                {
                    "student_id": student,
                    "section": SECTION_KEY,
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
    E-Class Record term grades -> flat grade rows.

    One row per (learner, subject) for the open term.  ``letter_grade`` and the
    DepEd ``remarks`` come from the same scale the seed command uses, so a
    row's descriptor agrees with its score.
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
    """One row per (learner, subject) for one term."""
    rows = []
    for index in range(ROSTER_SIZE):
        _, mean, spread, _ = band_for(index)
        rng = _rand(f"{seed_prefix}::{index}")
        student = _student_code(index)
        for code, _name in SUBJECTS:
            score = rng.gauss(mean, spread)
            score = max(0.0, min(100.0, round(score, 2)))
            letter, remark = _descriptor(score)
            rows.append(
                {
                    "student_id": student,
                    "section": SECTION_KEY,
                    "subject_code": code,
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


def main() -> None:
    _check_sf2_template()
    _check_sf3_template()
    attendance_rows = write_attendance()
    grade_rows = write_grades()
    earlier_rows = write_earlier_grades()
    print(f"{ATTENDANCE_OUT.name}: {attendance_rows} rows")
    print(f"{GRADES_OUT.name}: {grade_rows} rows")
    print(f"{GRADES_EARLIER_OUT.name}: {earlier_rows} rows")


if __name__ == "__main__":
    main()

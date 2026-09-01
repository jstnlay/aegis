"""Domain importers for data_import (Phase 8.5 / 8.6 / 8.7).

Each importer consumes the normalized row dicts produced by the CSV and
XLSX pipelines, validates each row against the real academic/attendance
business rules, and writes Grade / Attendance / Student records.  This
layer is a thin orchestration seam: parsing lives in csv_pipeline /
xlsx_pipeline, domain validation lives in the existing models/serializers,
and these importers only decide row outcomes and write through the domain
path.
"""

from .grades import GradeImporter
from .attendance import AttendanceImporter
from .students import StudentImporter

__all__ = ["GradeImporter", "AttendanceImporter", "StudentImporter"]

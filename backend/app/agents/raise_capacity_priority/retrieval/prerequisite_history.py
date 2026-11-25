"""
Retrieval of the student's Takes records for a SET of courses: the courses
the knowledge-file factors need (the requested course, its prerequisite
courses, its direct dependents and the courses in their requirements — see
deterministic/evidence.related_course_ids). Course IDs are compared as text,
so leading zeros are preserved.

Not to be confused with retrieval/academic_history.py, which retrieves the
student's records for the REQUESTED course itself (previous attempts).
"""

from typing import Any

from ..retrieval._query import select_rows_in
from ..schemas.academic_history import TakesRecord

_COLUMNS = "Course_ID, Grade, Section_ID, Term"


def get_takes_for_courses(
    client: Any, student_id: str, course_ids: set[str]
) -> list[TakesRecord]:
    if not course_ids:
        return []

    rows = select_rows_in(
        client,
        "Takes",
        _COLUMNS,
        {"Student_ID": student_id},
        "Course_ID",
        sorted(course_ids),
    )

    return [
        TakesRecord(
            course_id=row["Course_ID"],
            grade=row["Grade"],
            section_id=row["Section_ID"],
            term=row["Term"],
        )
        for row in rows
    ]

"""
Retrieval for the Takes table — the student's records for the REQUESTED
course (previous attempts).

Only records from terms BEFORE the requested academic term count as
previous attempts, whatever their grade (a pass, a fail, a withdrawal, an
incomplete or a NULL grade all count). Records in the requested term (any
section) and in later terms never count. A record whose order relative to
the requested term cannot be determined (unsupported semester suffix) makes
the status UNKNOWN unless an earlier attempt is already confirmed.
"""

from typing import Any

from ..deterministic.term import compare_terms
from ..retrieval._query import select_rows
from ..schemas.academic_history import PreviousAttemptRecord, PreviousAttemptsSummary

_COLUMNS = "Course_ID, Grade, Section_ID, Term"
_RELATION = {-1: "BEFORE_REQUEST_TERM", 0: "REQUEST_TERM", 1: "AFTER_REQUEST_TERM", None: "UNKNOWN_TERM"}


def term_relation(term: int, request_term: int) -> str:
    return _RELATION[compare_terms(term, request_term)]


def get_previous_attempts(
    client: Any,
    student_id: str,
    course_id: str,
    current_term: int,
) -> PreviousAttemptsSummary:
    rows = select_rows(
        client,
        "Takes",
        _COLUMNS,
        {"Student_ID": student_id, "Course_ID": course_id},
    )
    records = [
        PreviousAttemptRecord(
            course_id=row["Course_ID"],
            grade=row["Grade"],
            section_id=row["Section_ID"],
            term=row["Term"],
            term_relation=term_relation(row["Term"], current_term),
        )
        for row in rows
    ]
    return summarize_previous_attempts(records)


def summarize_previous_attempts(records: list[PreviousAttemptRecord]) -> PreviousAttemptsSummary:
    earlier = [r for r in records if r.term_relation == "BEFORE_REQUEST_TERM"]
    unknown = [r for r in records if r.term_relation == "UNKNOWN_TERM"]
    if earlier:
        status, attempted = "PREVIOUSLY_ATTEMPTED", True
    elif unknown:
        status, attempted = "UNKNOWN", None
    else:
        status, attempted = "NEVER_ATTEMPTED", False
    return PreviousAttemptsSummary(
        status=status,
        attempted_before=attempted,
        number_of_attempts=len(earlier),
        records=records,
    )

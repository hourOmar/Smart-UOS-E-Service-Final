"""
Pydantic schemas for a student's Takes (transcript) records.

Every record carries its term_relation to the requested academic term:
- BEFORE_REQUEST_TERM: a genuine earlier record (counts as a previous
  attempt and can complete a prerequisite);
- REQUEST_TERM: the requested term itself (current enrolment; never a
  previous attempt, regardless of section);
- AFTER_REQUEST_TERM: a future record (ignored everywhere);
- UNKNOWN_TERM: the term (or the request term) has an unsupported
  semester suffix, so the order cannot be determined.
Records are kept with their relation rather than silently discarded.
"""

from typing import Literal, Optional

from pydantic import BaseModel

TermRelation = Literal["BEFORE_REQUEST_TERM", "REQUEST_TERM", "AFTER_REQUEST_TERM", "UNKNOWN_TERM"]


class PreviousAttemptRecord(BaseModel):
    course_id: str  # text, leading zeros preserved
    grade: Optional[str]
    section_id: str
    term: int
    term_relation: TermRelation


class PreviousAttemptsSummary(BaseModel):
    status: Literal["NEVER_ATTEMPTED", "PREVIOUSLY_ATTEMPTED", "UNKNOWN"]
    attempted_before: Optional[bool]
    number_of_attempts: int
    records: list[PreviousAttemptRecord]


class TakesRecord(BaseModel):
    """A raw Takes row for any course (used for prerequisite and dependent
    course evaluation)."""

    course_id: str  # text, leading zeros preserved
    grade: Optional[str]
    section_id: str
    term: int

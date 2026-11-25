"""
Deterministic course-availability facts, sourced ONLY from
knowledge/course_offerings.json (usual Fall/Spring/Summer offerings for
the supported program, each YES, NO or UNKNOWN).

Rules:
- UNKNOWN is never read as NO, and no course is ever said to be "never
  offered": a usual offering is not a guaranteed future offering.
- The next known usual offering is the first YES semester within the three
  terms after the requested term (one full Fall/Spring/Summer cycle).
  UNKNOWN semesters before it are reported as earlier possible but
  unconfirmed offerings.
- A Course_ID missing from the file is reported as not available
  (found_in_kb=False, every offering field None) — never defaulted.

The file is validated when it is loaded; a malformed file fails loudly.
"""

import json
import re
from pathlib import Path
from typing import Optional

from .. import KNOWLEDGE_DIR
from ..deterministic.term import (
    Semester,
    calculate_terms_until_graduation,
    compare_terms,
    following_terms,
    parse_term,
)
from ..schemas.deterministic import RequestedCourseOfferingEvidence

_KB_PATH = KNOWLEDGE_DIR / "course_offerings.json"
SOURCE = "knowledge/course_offerings.json"
_STATUSES = frozenset({"YES", "NO", "UNKNOWN"})
_SEMESTER_KEYS = ("fall", "spring", "summer")
_KEY_FOR = {Semester.FALL: "fall", Semester.SPRING: "spring", Semester.SUMMER: "summer"}
_COURSE_ID = re.compile(r"^[0-9]{7}$")


def load_offerings(path: Path = _KB_PATH) -> tuple[str, dict[str, dict[str, str]]]:
    """Returns (program_id, {course_id: {"fall"|"spring"|"summer": status}})."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    program_id = data.get("program_id")
    if not isinstance(program_id, str) or not program_id:
        raise ValueError("course_offerings.json: program_id must be non-empty text.")
    courses = data.get("courses")
    if not isinstance(courses, list):
        raise ValueError("course_offerings.json: courses must be a list.")

    index: dict[str, dict[str, str]] = {}
    for course in courses:
        course_id = course.get("course_id")
        if not isinstance(course_id, str) or not _COURSE_ID.match(course_id):
            raise ValueError(f"course_offerings.json: invalid course_id {course_id!r}.")
        if course_id in index:
            raise ValueError(f"course_offerings.json: duplicate course_id {course_id}.")
        offerings = course.get("offerings")
        if not isinstance(offerings, dict) or set(offerings) != set(_SEMESTER_KEYS):
            raise ValueError(f"course_offerings.json: {course_id} must give fall, spring and summer.")
        for key in _SEMESTER_KEYS:
            if offerings[key] not in _STATUSES:
                raise ValueError(f"course_offerings.json: {course_id} {key} must be YES, NO or UNKNOWN.")
        index[course_id] = {key: offerings[key] for key in _SEMESTER_KEYS}
    return program_id, index


OFFERINGS_PROGRAM_ID, _OFFERINGS_INDEX = load_offerings()


def get_course_offering(course_id: str) -> Optional[dict[str, str]]:
    """{"fall": status, "spring": status, "summer": status}, or None when the
    course is not in the file."""
    entry = _OFFERINGS_INDEX.get(course_id)
    return dict(entry) if entry is not None else None


def _not_available(course_id, found, offering, request_semester, supported, note) -> RequestedCourseOfferingEvidence:
    return RequestedCourseOfferingEvidence(
        course_id=course_id,
        found_in_kb=found,
        fall=offering["fall"] if offering else None,
        spring=offering["spring"] if offering else None,
        summer=offering["summer"] if offering else None,
        usually_offered_semesters=[s for s in Semester if offering and offering[_KEY_FOR[s]] == "YES"],
        not_offered_semesters=[s for s in Semester if offering and offering[_KEY_FOR[s]] == "NO"],
        unknown_offering_semesters=[s for s in Semester if offering and offering[_KEY_FOR[s]] == "UNKNOWN"],
        request_semester=request_semester,
        term_suffix_supported=supported,
        next_term=None,
        next_term_offering=None,
        next_offering_status="NOT_AVAILABLE",
        next_known_offering_term=None,
        next_known_offering_semester=None,
        earlier_unconfirmed_offering_terms=[],
        waiting_terms_including_summer=None,
        waiting_terms_excluding_summer=None,
        next_known_offering_vs_expected_graduation="UNKNOWN",
        availability_uncertain=True,
        notes=[note],
        source=SOURCE,
    )


def not_evaluated_offering_evidence(course_id: str, reason: str) -> RequestedCourseOfferingEvidence:
    """Availability that was deliberately not evaluated (e.g. a program
    outside the supported scope): every value unavailable."""
    return _not_available(course_id, False, None, None, False, reason)


def build_requested_course_offering_evidence(
    course_id: str, request_term: Optional[int], expected_graduation_term: Optional[int]
) -> RequestedCourseOfferingEvidence:
    offering = get_course_offering(course_id)
    request_semester = parse_term(request_term) if request_term is not None else None
    supported = request_semester is not None

    if offering is None:
        return _not_available(
            course_id, False, None, request_semester, supported,
            "The requested course is not in the course offerings knowledge file; its usual offering is unknown.",
        )
    if not supported:
        return _not_available(
            course_id, True, offering, None, False,
            "The request term has an unsupported semester suffix; the next offering cannot be calculated.",
        )

    def status_of(term: int) -> str:
        return offering[_KEY_FOR[parse_term(term)]]

    cycle = following_terms(request_term, 3)
    next_known: Optional[int] = None
    earlier_unconfirmed: list[int] = []
    for term in cycle:
        status = status_of(term)
        if status == "YES":
            next_known = term
            break
        if status == "UNKNOWN":
            earlier_unconfirmed.append(term)

    notes: list[str] = []
    waiting_including: Optional[int] = None
    waiting_excluding: Optional[int] = None
    if next_known is not None:
        next_status = "KNOWN"
        waiting_including, waiting_excluding = calculate_terms_until_graduation(request_term, next_known)
        if earlier_unconfirmed:
            notes.append(
                "Offering information is UNKNOWN for term(s) before the next known usual offering; "
                "the course may be offered earlier, but this is not confirmed."
            )
    elif any(offering[key] == "UNKNOWN" for key in _SEMESTER_KEYS):
        next_status = "UNDETERMINED"
        notes.append(
            "No semester is listed as a usual offering and at least one is UNKNOWN; "
            "the next offering cannot be determined."
        )
    else:
        next_status = "NO_USUAL_OFFERING_LISTED"
        notes.append(
            "No semester is listed as a usual offering; this does not establish that the course will not be offered."
        )

    if next_known is None or expected_graduation_term is None:
        versus = "UNKNOWN"
    else:
        comparison = compare_terms(next_known, expected_graduation_term)
        versus = {
            -1: "BEFORE_EXPECTED_GRADUATION", 0: "SAME_AS_EXPECTED_GRADUATION", 1: "AFTER_EXPECTED_GRADUATION",
            None: "UNKNOWN",
        }[comparison]

    notes.append("Usual offerings are not guaranteed future offerings.")
    return RequestedCourseOfferingEvidence(
        course_id=course_id,
        found_in_kb=True,
        fall=offering["fall"],
        spring=offering["spring"],
        summer=offering["summer"],
        usually_offered_semesters=[s for s in Semester if offering[_KEY_FOR[s]] == "YES"],
        not_offered_semesters=[s for s in Semester if offering[_KEY_FOR[s]] == "NO"],
        unknown_offering_semesters=[s for s in Semester if offering[_KEY_FOR[s]] == "UNKNOWN"],
        request_semester=request_semester,
        term_suffix_supported=True,
        next_term=cycle[0],
        next_term_offering=status_of(cycle[0]),
        next_offering_status=next_status,
        next_known_offering_term=next_known,
        next_known_offering_semester=parse_term(next_known) if next_known is not None else None,
        earlier_unconfirmed_offering_terms=earlier_unconfirmed,
        waiting_terms_including_summer=waiting_including,
        waiting_terms_excluding_summer=waiting_excluding,
        next_known_offering_vs_expected_graduation=versus,
        availability_uncertain=next_status != "KNOWN" or bool(earlier_unconfirmed),
        notes=notes,
        source=SOURCE,
    )

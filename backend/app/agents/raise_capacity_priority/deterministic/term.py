"""
Deterministic term parsing, per the confirmed convention: Term is an
integer whose FINAL TWO DIGITS are the semester suffix.

    01 = Fall
    02 = Spring
    03 = Summer

Progression is Fall -> Spring -> Summer -> Fall. Nothing about the
first four digits (the year) is interpreted — only the confirmed
suffix. An unsupported suffix returns None rather than guessing.
"""

from enum import Enum
from typing import Optional


class Semester(str, Enum):
    FALL = "FALL"
    SPRING = "SPRING"
    SUMMER = "SUMMER"


_SUFFIX_TO_SEMESTER = {1: Semester.FALL, 2: Semester.SPRING, 3: Semester.SUMMER}
_NEXT_SEMESTER = {
    Semester.FALL: Semester.SPRING,
    Semester.SPRING: Semester.SUMMER,
    Semester.SUMMER: Semester.FALL,
}


def parse_term(term: int) -> Optional[Semester]:
    suffix = term % 100
    return _SUFFIX_TO_SEMESTER.get(suffix)


def next_semester(semester: Semester) -> Semester:
    return _NEXT_SEMESTER[semester]


_SEMESTER_OFFSET = {Semester.FALL: 0, Semester.SPRING: 1, Semester.SUMMER: 2}


def _term_sequence_index(term: int) -> Optional[int]:
    """A strictly increasing integer for each real term (Fall/Spring/
    Summer), so subtracting two of these counts term transitions
    directly. Year is read from the digits preceding the confirmed
    two-digit suffix; nothing else about it is interpreted."""
    semester = parse_term(term)
    if semester is None:
        return None
    year = term // 100
    return year * 3 + _SEMESTER_OFFSET[semester]


def term_index(term: int) -> Optional[int]:
    """Public form of _term_sequence_index: None for an unsupported suffix."""
    return _term_sequence_index(term)


def term_from_index(index: int) -> int:
    """The term code for a sequence index (the inverse of term_index)."""
    year, offset = divmod(index, 3)
    return year * 100 + offset + 1


def compare_terms(term: int, reference: int) -> Optional[int]:
    """-1, 0 or 1 as term is before, equal to or after reference; None when
    either term has an unsupported semester suffix (never guessed)."""
    a, b = _term_sequence_index(term), _term_sequence_index(reference)
    if a is None or b is None:
        return None
    return (a > b) - (a < b)


def following_terms(term: int, count: int) -> list[int]:
    """The next `count` term codes after term (Fall -> Spring -> Summer ->
    Fall); empty when term's suffix is unsupported."""
    index = _term_sequence_index(term)
    if index is None:
        return []
    return [term_from_index(index + step) for step in range(1, count + 1)]


def calculate_terms_until_graduation(
    request_term: int, expected_graduation_term: int
) -> Optional[tuple[int, int]]:
    """Counts term transitions strictly after request_term, up to and
    including expected_graduation_term. Returns
    (terms_including_summer, terms_excluding_summer), where the second
    value only counts Fall/Spring steps — a Summer step is still passed
    through but does not increment it, even when Summer is the
    graduation term itself.

    Returns None (never a negative or guessed value) when either term
    has an unsupported semester suffix, or when expected_graduation_term
    is chronologically before request_term.
    """
    request_index = _term_sequence_index(request_term)
    expected_index = _term_sequence_index(expected_graduation_term)
    if request_index is None or expected_index is None:
        return None
    if expected_index < request_index:
        return None

    including_summer = expected_index - request_index
    excluding_summer = 0
    for index in range(request_index + 1, expected_index + 1):
        if index % 3 != _SEMESTER_OFFSET[Semester.SUMMER]:
            excluding_summer += 1

    return including_summer, excluding_summer

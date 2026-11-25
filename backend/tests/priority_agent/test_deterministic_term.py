import pytest

from app.agents.raise_capacity_priority.deterministic.term import (
    Semester,
    calculate_terms_until_graduation,
    next_semester,
    parse_term,
)


def test_parse_term_fall():
    assert parse_term(202601) == Semester.FALL


def test_parse_term_spring():
    assert parse_term(202602) == Semester.SPRING


def test_parse_term_summer():
    assert parse_term(202603) == Semester.SUMMER


def test_next_semester_fall_to_spring():
    assert next_semester(Semester.FALL) == Semester.SPRING


def test_next_semester_spring_to_summer():
    assert next_semester(Semester.SPRING) == Semester.SUMMER


def test_next_semester_summer_to_fall():
    assert next_semester(Semester.SUMMER) == Semester.FALL


def test_parse_term_unsupported_suffix_returns_none():
    assert parse_term(202699) is None


# calculate_terms_until_graduation — table from the task, plus edge cases.
@pytest.mark.parametrize(
    "request_term, expected_graduation_term, including_summer, excluding_summer",
    [
        (202601, 202601, 0, 0),  # same term (also: same-term graduation)
        (202601, 202602, 1, 1),
        (202601, 202603, 2, 1),  # Summer graduation: excluding != including
        (202601, 202701, 3, 2),  # year transition
        (202601, 202802, 7, 5),  # multi-year transition
    ],
)
def test_calculate_terms_until_graduation_examples(
    request_term, expected_graduation_term, including_summer, excluding_summer
):
    result = calculate_terms_until_graduation(request_term, expected_graduation_term)
    assert result == (including_summer, excluding_summer)


def test_summer_graduation_term_is_preserved_as_is():
    # The task requires 202603 (Summer) to remain the actual expected
    # graduation term while still yielding excluding_summer=1, not 2.
    result = calculate_terms_until_graduation(202601, 202603)
    assert result is not None
    including_summer, excluding_summer = result
    assert including_summer == 2
    assert excluding_summer == 1


def test_expected_graduation_term_before_request_term_returns_none():
    result = calculate_terms_until_graduation(202602, 202601)
    assert result is None


def test_invalid_request_term_suffix_returns_none():
    result = calculate_terms_until_graduation(202699, 202701)
    assert result is None


def test_invalid_expected_graduation_term_suffix_returns_none():
    result = calculate_terms_until_graduation(202601, 202699)
    assert result is None


# Term helpers used by the availability calculation (same Fall -> Spring -> Summer convention).
from app.agents.raise_capacity_priority.deterministic.term import (  # noqa: E402
    compare_terms,
    following_terms,
    term_from_index,
    term_index,
)


def test_following_terms_cross_the_year_boundary():
    assert following_terms(202602, 3) == [202603, 202701, 202702]
    assert following_terms(202603, 1) == [202701]


def test_following_terms_unsupported_suffix_is_empty():
    assert following_terms(202604, 3) == []


def test_compare_terms():
    assert compare_terms(202601, 202602) == -1
    assert compare_terms(202603, 202603) == 0
    assert compare_terms(202701, 202603) == 1
    assert compare_terms(202600, 202601) is None


def test_term_index_round_trip():
    for term in (202601, 202602, 202603, 199903):
        assert term_from_index(term_index(term)) == term

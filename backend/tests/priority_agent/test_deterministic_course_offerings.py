"""Factor 4 — course availability from knowledge/course_offerings.json (YES/NO/UNKNOWN)."""

import json

import pytest

from app.agents.raise_capacity_priority import KNOWLEDGE_DIR
from app.agents.raise_capacity_priority.deterministic import course_offerings as offerings
from app.agents.raise_capacity_priority.deterministic.course_offerings import (
    OFFERINGS_PROGRAM_ID,
    build_requested_course_offering_evidence,
    get_course_offering,
    load_offerings,
    not_evaluated_offering_evidence,
)

FALL = 202601
SPRING = 202602
SUMMER = 202603

ALL_SEMESTERS = "1501215"  # Data Structures: YES/YES/YES
FALL_ONLY = "1501322"  # YES/NO/NO (offered once per year)
SPRING_ONLY = "1501246"  # NO/YES/NO
FALL_SPRING = "1501279"  # YES/YES/NO
ALL_UNKNOWN = "1501355"  # UNKNOWN/UNKNOWN/UNKNOWN


def _ev(course_id, term=FALL, graduation=None):
    return build_requested_course_offering_evidence(course_id, term, graduation)


def test_loader_reads_all_58_courses_with_text_ids():
    program_id, index = load_offerings()
    assert program_id == OFFERINGS_PROGRAM_ID == "1501"
    assert len(index) == 58
    assert all(isinstance(cid, str) and len(cid) == 7 for cid in index)
    for cid in ("1501100", "0104100", "1502201", "1502202"):
        assert cid in index


def test_leading_zero_course_ids_are_preserved():
    assert get_course_offering("0201102") == {"fall": "YES", "spring": "YES", "summer": "YES"}
    assert get_course_offering("201102") is None


def test_six_electives_are_unknown_not_no():
    for cid in ("1501355", "1501433", "1501440", "1501441", "1501451", "1501474"):
        assert get_course_offering(cid) == {"fall": "UNKNOWN", "spring": "UNKNOWN", "summer": "UNKNOWN"}


def test_usual_semesters_are_reported():
    ev = _ev(FALL_SPRING)
    assert (ev.fall, ev.spring, ev.summer) == ("YES", "YES", "NO")
    assert ev.usually_offered_semesters == ["FALL", "SPRING"]
    assert ev.not_offered_semesters == ["SUMMER"]
    assert ev.unknown_offering_semesters == []


def test_next_known_offering_next_semester():
    ev = _ev(ALL_SEMESTERS, FALL)
    assert ev.next_term == SPRING and ev.next_term_offering == "YES"
    assert ev.next_offering_status == "KNOWN"
    assert ev.next_known_offering_term == SPRING
    assert (ev.waiting_terms_including_summer, ev.waiting_terms_excluding_summer) == (1, 1)
    assert ev.availability_uncertain is False


def test_once_per_year_course_waits_a_full_cycle():
    ev = _ev(FALL_ONLY, FALL)
    assert ev.next_term_offering == "NO"
    assert ev.next_known_offering_term == 202701
    assert ev.next_known_offering_semester == "FALL"
    assert (ev.waiting_terms_including_summer, ev.waiting_terms_excluding_summer) == (3, 2)


def test_spring_request_next_term_is_summer():
    ev = _ev(FALL_SPRING, SPRING)
    assert ev.next_term == SUMMER and ev.next_term_offering == "NO"
    assert ev.next_known_offering_term == 202701
    assert (ev.waiting_terms_including_summer, ev.waiting_terms_excluding_summer) == (2, 1)


def test_summer_availability_reported():
    ev = _ev(ALL_SEMESTERS, SPRING)
    assert ev.summer == "YES"
    assert ev.next_known_offering_term == SUMMER
    assert (ev.waiting_terms_including_summer, ev.waiting_terms_excluding_summer) == (1, 0)


def test_summer_request_next_term_is_fall():
    ev = _ev(SPRING_ONLY, SUMMER)
    assert ev.next_term == 202701 and ev.next_term_offering == "NO"
    assert ev.next_known_offering_term == 202702


@pytest.mark.parametrize("graduation, expected", [
    (202602, "AFTER_EXPECTED_GRADUATION"),
    (202701, "SAME_AS_EXPECTED_GRADUATION"),
    (202702, "BEFORE_EXPECTED_GRADUATION"),
    (None, "UNKNOWN"),
])
def test_next_known_offering_compared_with_graduation(graduation, expected):
    assert _ev(FALL_ONLY, FALL, graduation).next_known_offering_vs_expected_graduation == expected


def test_all_unknown_cannot_be_determined_and_is_never_no():
    ev = _ev(ALL_UNKNOWN)
    assert ev.found_in_kb is True
    assert (ev.fall, ev.spring, ev.summer) == ("UNKNOWN", "UNKNOWN", "UNKNOWN")
    assert ev.not_offered_semesters == []
    assert ev.next_offering_status == "UNDETERMINED"
    assert ev.next_known_offering_term is None
    assert ev.waiting_terms_including_summer is None
    assert ev.earlier_unconfirmed_offering_terms == [202602, 202603, 202701]
    assert ev.availability_uncertain is True
    assert any("cannot be determined" in n for n in ev.notes)


def test_partially_unknown_reports_earlier_unconfirmed_offerings(monkeypatch):
    monkeypatch.setitem(offerings._OFFERINGS_INDEX, "1234567", {"fall": "YES", "spring": "UNKNOWN", "summer": "NO"})
    ev = _ev("1234567", FALL)
    assert ev.next_offering_status == "KNOWN"
    assert ev.next_known_offering_term == 202701
    assert ev.earlier_unconfirmed_offering_terms == [202602]
    assert ev.availability_uncertain is True
    assert any("not confirmed" in n for n in ev.notes)


def test_no_usual_offering_listed_never_claims_never_offered(monkeypatch):
    monkeypatch.setitem(offerings._OFFERINGS_INDEX, "1234567", {"fall": "NO", "spring": "NO", "summer": "NO"})
    ev = _ev("1234567")
    assert ev.next_offering_status == "NO_USUAL_OFFERING_LISTED"
    assert any("does not establish" in n for n in ev.notes)


def test_missing_course_is_not_available_not_defaulted():
    ev = _ev("9999999")
    assert ev.found_in_kb is False
    assert ev.fall is ev.spring is ev.summer is None
    assert ev.next_offering_status == "NOT_AVAILABLE"
    assert ev.availability_uncertain is True


def test_unsupported_request_term_suffix():
    ev = _ev(ALL_SEMESTERS, 202604)
    assert ev.term_suffix_supported is False
    assert ev.next_offering_status == "NOT_AVAILABLE"
    assert ev.fall == "YES"


def test_not_evaluated_evidence():
    ev = not_evaluated_offering_evidence("1502232", "Program outside scope.")
    assert ev.found_in_kb is False and ev.notes == ["Program outside scope."]


def test_usual_offerings_disclaimer_present():
    assert "Usual offerings are not guaranteed future offerings." in _ev(ALL_SEMESTERS).notes


@pytest.mark.parametrize("mutate, message", [
    (lambda d: d["courses"][0]["offerings"].update(fall="MAYBE"), "YES, NO or UNKNOWN"),
    (lambda d: d["courses"].append(dict(d["courses"][0])), "duplicate"),
    (lambda d: d["courses"][0].update(course_id=201102), "invalid course_id"),
])
def test_malformed_file_fails_loudly(tmp_path, mutate, message):
    data = json.loads((KNOWLEDGE_DIR / "course_offerings.json").read_text(encoding="utf-8"))
    mutate(data)
    path = tmp_path / "offerings.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match=message):
        load_offerings(path)

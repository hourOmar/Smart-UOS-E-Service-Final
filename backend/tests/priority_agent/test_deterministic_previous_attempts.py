"""Factor 5 — previous attempts: three-way status and request-term filtering."""

from app.agents.raise_capacity_priority.deterministic.previous_attempts import build_previous_attempt_summary
from app.agents.raise_capacity_priority.retrieval.academic_history import summarize_previous_attempts, term_relation
from app.agents.raise_capacity_priority.schemas.academic_history import PreviousAttemptRecord

REQUEST_TERM = 202601


def _record(grade, term):
    return PreviousAttemptRecord(
        course_id="1501215", grade=grade, section_id="SEC-1", term=term,
        term_relation=term_relation(term, REQUEST_TERM),
    )


def _evidence(*records):
    return build_previous_attempt_summary(summarize_previous_attempts(list(records)))


def test_never_attempted():
    ev = _evidence()
    assert ev.status == "NEVER_ATTEMPTED"
    assert ev.attempted_before is False
    assert ev.number_of_attempts == 0
    assert ev.previous_grades == [] and ev.previous_terms == []


def test_earlier_attempts_with_passing_failing_withdrawn_incomplete_and_null_grades():
    ev = _evidence(_record("B", 202402), _record("F", 202501), _record("W", 202502), _record("I", 202503),
                   _record(None, 202403))
    assert ev.status == "PREVIOUSLY_ATTEMPTED"
    assert ev.attempted_before is True
    assert ev.number_of_attempts == 5
    assert ev.previous_grades == ["B", "F", "W", "I", None]


def test_same_and_future_term_records_are_excluded_and_counted_separately():
    ev = _evidence(_record(None, REQUEST_TERM), _record("A", 202602), _record("D", 202503))
    assert ev.status == "PREVIOUSLY_ATTEMPTED"
    assert ev.number_of_attempts == 1
    assert ev.previous_terms == [202503]
    assert ev.excluded_same_term_records == 1
    assert ev.excluded_future_term_records == 1


def test_only_same_term_record_is_never_attempted():
    ev = _evidence(_record(None, REQUEST_TERM))
    assert ev.status == "NEVER_ATTEMPTED"
    assert ev.attempted_before is False


def test_unorderable_record_is_unknown():
    ev = _evidence(_record("A", 202504))
    assert ev.status == "UNKNOWN"
    assert ev.attempted_before is None
    assert ev.unknown_term_records == 1


def test_term_relation_boundaries():
    assert term_relation(202503, 202601) == "BEFORE_REQUEST_TERM"
    assert term_relation(202601, 202601) == "REQUEST_TERM"
    assert term_relation(202602, 202601) == "AFTER_REQUEST_TERM"
    assert term_relation(202600, 202601) == "UNKNOWN_TERM"
    assert term_relation(202601, 202604) == "UNKNOWN_TERM"

"""Factor 6 — prerequisite evaluation against knowledge/course_prerequisites.json."""

import json

import pytest

from app.agents.raise_capacity_priority import KNOWLEDGE_DIR
from app.agents.raise_capacity_priority.deterministic.prerequisite_evaluator import (
    evaluate_course_leaf,
    evaluate_prerequisite_completion,
    not_evaluated_prerequisite_evidence,
)
from app.agents.raise_capacity_priority.deterministic.prerequisite_knowledge import (
    PREREQUISITE_KNOWLEDGE,
    load_prerequisite_knowledge,
)
from app.agents.raise_capacity_priority.schemas.academic_history import TakesRecord

REQUEST_TERM = 202601
KB = PREREQUISITE_KNOWLEDGE


def take(course_id, grade, term=202502):
    return TakesRecord(course_id=course_id, grade=grade, section_id="1", term=term)


def evaluate(course_id, *records, hours=70, knowledge=KB, term=REQUEST_TERM):
    return evaluate_prerequisite_completion(course_id, knowledge, list(records), term, hours)


# PRE — 1501215 Data Structures requires 1501211 (PRE)
@pytest.mark.parametrize("grade, status", [
    ("A", "SATISFIED"), ("D", "SATISFIED"),
    ("F", "NOT_SATISFIED"), ("WF", "NOT_SATISFIED"), ("FA", "NOT_SATISFIED"),
    ("W", "UNRESOLVED"), ("I", "UNRESOLVED"), (None, "UNRESOLVED"), ("XYZ", "UNRESOLVED"),
])
def test_earlier_term_grades_follow_the_approved_policy(grade, status):
    assert evaluate("1501215", take("1501211", grade)).status == status


def test_no_record_is_not_satisfied():
    ev = evaluate("1501215")
    assert ev.status == "NOT_SATISFIED"
    assert ev.knowledge_status == "REQUIREMENT_DEFINED"
    assert ev.leaf_evaluations[0].reason == "No transcript record for 1501211."


def test_a_pass_after_an_earlier_fail_satisfies():
    assert evaluate("1501215", take("1501211", "F", 202501), take("1501211", "B", 202502)).status == "SATISFIED"


def test_current_enrolment_never_satisfies_pre():
    assert evaluate("1501215", take("1501211", None, REQUEST_TERM)).status == "NOT_SATISFIED"


def test_future_term_records_are_ignored():
    ev = evaluate("1501215", take("1501211", "A", 202602))
    assert ev.status == "NOT_SATISFIED"
    assert ev.leaf_evaluations[0].matched_takes_records[0].term_relation == "AFTER_REQUEST_TERM"


def test_unorderable_term_is_unresolved():
    assert evaluate("1501215", take("1501211", "A", 202509)).status == "UNRESOLVED"


# PRE_OR_CO
def test_pre_or_co_satisfied_by_current_enrolment():
    # 1420102 General Chemistry I Lab: Pre/Co 1420101
    assert evaluate("1420102", take("1420101", None, REQUEST_TERM)).status == "SATISFIED"


def test_pre_or_co_satisfied_by_earlier_pass():
    assert evaluate("1420102", take("1420101", "C")).status == "SATISFIED"


def test_pre_or_co_failing_grade_in_request_term_is_not_enrolment():
    assert evaluate("1420102", take("1420101", "WF", REQUEST_TERM)).status == "NOT_SATISFIED"


def test_pre_or_co_withdrawn_grade_in_request_term_is_unresolved():
    assert evaluate("1420102", take("1420101", "W", REQUEST_TERM)).status == "UNRESOLVED"


def test_pre_or_co_alternative_id_1430115_satisfies_physics_lab():
    # 1430116 Physics I Lab: (1430110 OR 1430115), both Pre/Co
    assert evaluate("1430116", take("1430115", "B")).status == "SATISFIED"
    assert evaluate("1430116", take("1430110", None, REQUEST_TERM)).status == "SATISFIED"
    assert evaluate("1430116").status == "NOT_SATISFIED"


# CO-only (supported for future knowledge; not used by the current file)
def test_co_only_requires_request_term_enrolment():
    assert evaluate_course_leaf("1420101", "CO", [take("1420101", None, REQUEST_TERM)], REQUEST_TERM).status == "SATISFIED"
    assert evaluate_course_leaf("1420101", "CO", [take("1420101", "A")], REQUEST_TERM).status == "NOT_SATISFIED"
    assert evaluate_course_leaf("1420101", "CO", [], REQUEST_TERM).status == "NOT_SATISFIED"


# AND / OR / nested
def test_and_requires_every_branch():
    # 1501371: 1501215 AND 1501279
    assert evaluate("1501371", take("1501215", "A"), take("1501279", "B")).status == "SATISFIED"
    assert evaluate("1501371", take("1501215", "A")).status == "NOT_SATISFIED"
    assert evaluate("1501371", take("1501215", "A"), take("1501279", None)).status == "UNRESOLVED"
    assert evaluate("1501371", take("1501215", "F"), take("1501279", None)).status == "NOT_SATISFIED"


def test_or_needs_one_branch():
    # 1501445: 1501211 OR 1501341
    assert evaluate("1501445", take("1501341", "C")).status == "SATISFIED"
    assert evaluate("1501445").status == "NOT_SATISFIED"
    assert evaluate("1501445", take("1501211", "I")).status == "UNRESOLVED"


def test_nested_and_or():
    # 1501443: 1501341 AND (1501246 OR 1501247)
    assert evaluate("1501443", take("1501341", "A"), take("1501247", "B")).status == "SATISFIED"
    assert evaluate("1501443", take("1501341", "A")).status == "NOT_SATISFIED"
    assert evaluate("1501443", take("1501246", "A")).status == "NOT_SATISFIED"


def test_leading_zero_alternative_course_id():
    # 1501252: 1502201 OR 0403201
    ev = evaluate("1501252", take("0403201", "B"))
    assert ev.status == "SATISFIED"
    assert {leaf.course_id for leaf in ev.leaf_evaluations} == {"1502201", "0403201"}


# Standing (thresholds from the knowledge file)
@pytest.mark.parametrize("hours, status", [(64, "NOT_SATISFIED"), (65, "SATISFIED"), (98, "SATISFIED"), (99, "SATISFIED")])
def test_junior_standing_boundaries(hours, status):
    # 1501344 2D Character Design: Junior Standing
    assert evaluate("1501344", hours=hours).status == status


@pytest.mark.parametrize("hours, status", [(64, "NOT_SATISFIED"), (65, "NOT_SATISFIED"), (98, "NOT_SATISFIED"), (99, "SATISFIED")])
def test_senior_standing_boundaries(hours, status):
    # 1501441 Multimedia Technology: 1501215 AND Senior Standing
    assert evaluate("1501441", take("1501215", "A"), hours=hours).status == status


@pytest.mark.parametrize("hours, status", [(64, "NOT_SATISFIED"), (65, "SATISFIED"), (99, "SATISFIED")])
def test_junior_or_senior_standing(hours, status):
    # 1501397 CO-OP: Junior OR Senior Standing
    assert evaluate("1501397", hours=hours).status == status


def test_course_and_standing():
    # 1501394 Junior Project: 1501215 AND Junior Standing
    ev = evaluate("1501394", take("1501215", "B"), hours=65)
    assert ev.status == "SATISFIED"
    standing = next(leaf for leaf in ev.leaf_evaluations if leaf.kind == "STANDING")
    assert standing.required_earned_credits == 65 and standing.completed_hours == 65


@pytest.mark.parametrize("hours", [None, -1])
def test_missing_or_invalid_completed_hours_is_unresolved(hours):
    assert evaluate("1501344", hours=hours).status == "UNRESOLVED"


def test_standing_thresholds_come_from_the_knowledge_file(tmp_path):
    data = json.loads((KNOWLEDGE_DIR / "course_prerequisites.json").read_text(encoding="utf-8"))
    data["standing_definitions"]["Junior Standing"]["prerequisite_min_earned_credits"] = 70
    path = tmp_path / "kb.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    custom = load_prerequisite_knowledge(path)
    assert evaluate("1501344", hours=65, knowledge=custom).status == "NOT_SATISFIED"
    assert evaluate("1501344", hours=70, knowledge=custom).status == "SATISFIED"


# Knowledge status
def test_explicitly_no_prerequisites():
    ev = evaluate("1501116")
    assert ev.status == "SATISFIED"
    assert ev.knowledge_status == "NO_PREREQUISITES"
    assert ev.requirement_expression is None


def test_leading_zero_course_without_prerequisites():
    assert evaluate("0202213").knowledge_status == "NO_PREREQUISITES"


def test_missing_prerequisite_knowledge_is_unresolved_not_none():
    ev = evaluate("9999999")
    assert ev.status == "UNRESOLVED"
    assert ev.knowledge_status == "MISSING_FROM_KNOWLEDGE_BASE"


@pytest.mark.parametrize("knowledge_status, status, expected", [
    ("CONFLICTING", "CONFLICT", "CONFLICTING"),
    ("UNVERIFIED", "UNRESOLVED", "NOT_VERIFIED"),
    ("NOT_COLLECTED", "UNRESOLVED", "NOT_VERIFIED"),
])
def test_non_verified_entries(tmp_path, knowledge_status, status, expected):
    data = json.loads((KNOWLEDGE_DIR / "course_prerequisites.json").read_text(encoding="utf-8"))
    data["courses"]["1501215"]["prerequisite_status"] = knowledge_status
    path = tmp_path / "kb.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    ev = evaluate("1501215", take("1501211", "A"), knowledge=load_prerequisite_knowledge(path))
    assert (ev.status, ev.knowledge_status) == (status, expected)


def test_not_evaluated_evidence():
    ev = not_evaluated_prerequisite_evidence("1502232", "Outside scope.")
    assert (ev.status, ev.knowledge_status) == ("UNRESOLVED", "NOT_EVALUATED")


def test_evidence_records_the_knowledge_expression_and_source():
    ev = evaluate("1501443", take("1501341", "A"))
    assert ev.requirement_expression.type == "ALL_OF"
    assert ev.source == "knowledge/course_prerequisites.json"

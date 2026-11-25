"""Factor 2 (degree progress) and factor 3 (course requirement) from the study plan."""

import pytest

from app.agents.raise_capacity_priority.deterministic.course_requirement import build_course_requirement_evidence
from app.agents.raise_capacity_priority.deterministic.remaining_credits import calculate_remaining_credits
from app.agents.raise_capacity_priority.schemas.study_plan import StudyPlanInfo


def plan(total=123, status="OK", total_status="OK", types=None, notes=None):
    return StudyPlanInfo(
        program_id="1501", status=status, plan_version="CS-WEB-2026-10-31" if status == "OK" else None,
        requirement_types=types if types is not None else {"1501215": "REQUIRED", "1501341": "ELECTIVE"},
        total_required_credits=total, total_status=total_status, notes=notes or [],
    )


def test_remaining_credits_and_completion_percentage():
    ev = calculate_remaining_credits(90, plan())
    assert (ev.remaining_credits, ev.completion_percentage, ev.status) == (33, 73.2, "OK")
    assert ev.total_required_credits == 123
    assert ev.plan_version == "CS-WEB-2026-10-31"


def test_total_comes_from_the_study_plan_not_a_constant():
    ev = calculate_remaining_credits(66, plan(total=132))
    assert (ev.remaining_credits, ev.completion_percentage) == (66, 50.0)


@pytest.mark.parametrize("completed, total, expected", [(0, 123, (123, 0.0)), (123, 123, (0, 100.0))])
def test_boundaries(completed, total, expected):
    ev = calculate_remaining_credits(completed, plan(total=total))
    assert (ev.remaining_credits, ev.completion_percentage) == expected
    assert ev.status == "OK"


def test_missing_completed_hours_is_unresolved():
    ev = calculate_remaining_credits(None, plan())
    assert ev.status == "UNRESOLVED"
    assert ev.remaining_credits is None and ev.completion_percentage is None
    assert "Student.Completed_Hours" in ev.note


def test_missing_total_is_unresolved_with_the_reason():
    ev = calculate_remaining_credits(60, plan(total=None, total_status="NOT_FOUND", notes=["No total recorded."]))
    assert ev.status == "UNRESOLVED"
    assert "No total recorded." in ev.note


def test_negative_completed_hours_is_an_anomaly():
    ev = calculate_remaining_credits(-3, plan())
    assert ev.status == "ANOMALY" and ev.remaining_credits is None


def test_completed_above_total_is_preserved_and_flagged():
    ev = calculate_remaining_credits(130, plan())
    assert ev.status == "ANOMALY"
    assert ev.remaining_credits == -7


@pytest.mark.parametrize("course_id, expected", [
    ("1501215", "REQUIRED"), ("1501341", "ELECTIVE"), ("1502232", "NOT_IN_STUDY_PLAN"),
])
def test_course_requirement_types(course_id, expected):
    ev = build_course_requirement_evidence(course_id, "Course", plan())
    assert ev.requirement_type == expected
    assert ev.plan_version == "CS-WEB-2026-10-31"


def test_course_requirement_unknown_when_no_current_plan():
    ev = build_course_requirement_evidence("1501215", "Data Structures",
                                           plan(status="NO_CURRENT_PLAN", types={}, notes=["No current plan."]))
    assert ev.requirement_type == "UNKNOWN"
    assert ev.note == "No current plan."


def test_course_requirement_leading_zero_id():
    ev = build_course_requirement_evidence("0202213", "Critical Reading and Writing", plan(types={"0202213": "REQUIRED"}))
    assert ev.course_id == "0202213" and ev.requirement_type == "REQUIRED"

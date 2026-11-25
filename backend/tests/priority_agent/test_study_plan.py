"""Factors 2 and 3 sources — the current study plan and its total from the database (fake client)."""

from app.agents.raise_capacity_priority.retrieval.study_plan import get_study_plan
from priority_agent.fakes import FakeSupabaseClient


def _plan_row(course_id, kind="Required", version="CS-1", current=True, program="1501"):
    return {"Program_ID": program, "Plan_Version": version, "Course_ID": course_id,
            "Requirement_Type": kind, "Is_Current": current}


def _client(plan_rows, total_rows):
    return FakeSupabaseClient({"Program_Study_Plan_Course": plan_rows, "Program_Study_Plan_Total": total_rows})


TOTAL = {"Program_ID": "1501", "Plan_Version": "CS-1", "Total_Credit_Hours": 123}


def test_current_plan_and_total():
    plan = get_study_plan(_client(
        [_plan_row("1501215"), _plan_row("1501341", "Elective"), _plan_row("1501999", version="OLD", current=False)],
        [TOTAL, {**TOTAL, "Plan_Version": "OLD", "Total_Credit_Hours": 130}],
    ), "1501")
    assert plan.status == "OK" and plan.plan_version == "CS-1"
    assert plan.total_required_credits == 123 and plan.total_status == "OK"
    assert plan.requirement_type("1501215") == "REQUIRED"
    assert plan.requirement_type("1501341") == "ELECTIVE"
    assert plan.requirement_type("1501999") == "NOT_IN_STUDY_PLAN"  # only in a non-current version


def test_leading_zero_ids_are_kept():
    plan = get_study_plan(_client(
        [_plan_row("0202213", program="0302", version="X")],
        [{"Program_ID": "0302", "Plan_Version": "X", "Total_Credit_Hours": 120}],
    ), "0302")
    assert plan.requirement_type("0202213") == "REQUIRED"
    assert plan.total_required_credits == 120


def test_missing_program():
    plan = get_study_plan(_client([], []), None)
    assert plan.status == "NO_PROGRAM"
    assert plan.requirement_type("1501215") == "UNKNOWN"


def test_no_current_plan():
    plan = get_study_plan(_client([_plan_row("1501215", current=False)], [TOTAL]), "1501")
    assert plan.status == "NO_CURRENT_PLAN"
    assert plan.requirement_type("1501215") == "UNKNOWN"
    assert plan.total_required_credits is None


def test_multiple_current_plans_are_inconsistent():
    plan = get_study_plan(_client([_plan_row("1501215"), _plan_row("1501215", version="CS-2")], [TOTAL]), "1501")
    assert plan.status == "MULTIPLE_CURRENT_PLANS"
    assert plan.requirement_type("1501215") == "UNKNOWN"


def test_missing_total():
    plan = get_study_plan(_client([_plan_row("1501215")], []), "1501")
    assert plan.status == "OK" and plan.total_status == "NOT_FOUND"
    assert plan.total_required_credits is None


def test_conflicting_totals():
    plan = get_study_plan(_client([_plan_row("1501215")], [TOTAL, {**TOTAL, "Total_Credit_Hours": 120}]), "1501")
    assert plan.total_status == "MULTIPLE" and plan.total_required_credits is None


def test_invalid_total():
    plan = get_study_plan(_client([_plan_row("1501215")], [{**TOTAL, "Total_Credit_Hours": 0}]), "1501")
    assert plan.total_status == "INVALID" and plan.total_required_credits is None


def test_shared_program_id_selects_the_plan_by_program_name():
    cs, ai = "Computer Science", "Artificial Intelligence"
    plans = [{**_plan_row("1501215"), "Program_Name": cs},
             {**_plan_row("1501215", "Elective", version="AI-1"), "Program_Name": ai}]
    totals = [{**TOTAL, "Program_Name": cs}, {**TOTAL, "Plan_Version": "AI-1", "Total_Credit_Hours": 130, "Program_Name": ai}]

    plan = get_study_plan(_client(plans, totals), "1501", cs)

    assert plan.status == "OK" and plan.plan_version == "CS-1"
    assert plan.requirement_type("1501215") == "REQUIRED"
    assert plan.total_required_credits == 123
    # Without the name, two programs' current plans under one ID are reported, never mixed.
    assert get_study_plan(_client(plans, totals), "1501").status == "MULTIPLE_CURRENT_PLANS"


def test_program_name_with_no_plan_is_no_current_plan():
    plans = [{**_plan_row("1501215"), "Program_Name": "Computer Science"}]
    plan = get_study_plan(_client(plans, [TOTAL]), "1501", "Artificial Intelligence")
    assert plan.status == "NO_CURRENT_PLAN"


def test_unexpected_requirement_type_is_unknown():
    plan = get_study_plan(_client([_plan_row("1501215", "Core")], [TOTAL]), "1501")
    assert plan.requirement_type("1501215") == "UNKNOWN"
    assert plan.notes

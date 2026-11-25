"""The complete requirement (prerequisites + academic standing) and the two
administrator-facing checks derived from it, built from real evidence."""

import pytest

from raise_capacity_eligibility.fixtures import REQUEST_TERM, evidence, take


def req(ev):
    return ev["academic_requirement"]


def keywords(ev):
    return [f["keyword"] for f in req(ev)["confirmed_failures"]]


def cards(ev):
    return ev["checks"]["prerequisite"]["status"], ev["checks"]["completed_hours"]["status"]


# PRE and grades
def test_passed_prerequisite():
    ev = evidence(transcript=[take("1501211", "B")])
    assert req(ev)["status"] == "SATISFIED"
    assert cards(ev) == ("SATISFIED", "NOT_APPLICABLE")
    assert keywords(ev) == []


@pytest.mark.parametrize("grade", ["F", "WF", "FA"])
def test_failing_grade_is_not_passed(grade):
    ev = evidence(transcript=[take("1501211", grade)])
    assert req(ev)["status"] == "NOT_SATISFIED"
    assert keywords(ev) == ["prerequisite_not_passed"]
    assert req(ev)["confirmed_failures"][0]["recorded_grades"] == [grade]
    assert cards(ev) == ("NOT_SATISFIED", "NOT_APPLICABLE")


def test_no_record_is_not_completed():
    ev = evidence()
    assert keywords(ev) == ["prerequisite_not_completed"]


@pytest.mark.parametrize("grade", ["W", "I", None, "XYZ"])
def test_unresolved_grades_never_fail(grade):
    ev = evidence(transcript=[take("1501211", grade)])
    assert req(ev)["status"] == "UNRESOLVED"
    assert keywords(ev) == []
    assert cards(ev)[0] == "UNRESOLVED"


def test_requested_term_enrolment_does_not_satisfy_pre():
    ev = evidence(transcript=[take("1501211", None, REQUEST_TERM)])
    assert keywords(ev) == ["prerequisite_not_completed"]


def test_future_term_pass_is_ignored():
    ev = evidence(transcript=[take("1501211", "A", 202602)])
    assert req(ev)["status"] == "NOT_SATISFIED"


def test_pass_after_an_earlier_fail():
    assert req(evidence(transcript=[take("1501211", "F", 202501), take("1501211", "C", 202502)]))["status"] == "SATISFIED"


# PRE_OR_CO
def test_pre_or_co_satisfied_by_current_enrolment():
    ev = evidence(course_id="1420102", transcript=[take("1420101", None, REQUEST_TERM)])
    assert req(ev)["status"] == "SATISFIED"


def test_pre_or_co_failure_is_a_corequisite_failure():
    ev = evidence(course_id="1420102")
    assert keywords(ev) == ["corequisite_not_satisfied"]


# Nested AND/OR: the complete requirement decides
def test_nested_requirement_satisfied_through_the_alternative():
    ev = evidence(course_id="1501443", transcript=[take("1501341", "A"), take("1501247", "B")])
    assert req(ev)["status"] == "SATISFIED"
    assert keywords(ev) == []


def test_nested_requirement_failure_is_reported_for_the_whole_or_group():
    ev = evidence(course_id="1501443", transcript=[take("1501341", "A")])
    assert req(ev)["status"] == "NOT_SATISFIED"
    assert keywords(ev) == ["prerequisite_options_not_satisfied"]
    failure = req(ev)["confirmed_failures"][0]
    assert failure["course_ids"] == ["1501246", "1501247"]
    assert "1501341" not in failure["course_ids"]


def test_one_failed_or_alternative_is_not_a_failure_when_another_satisfies():
    ev = evidence(course_id="1501445", transcript=[take("1501211", "F"), take("1501341", "C")])
    assert req(ev)["status"] == "SATISFIED"
    assert keywords(ev) == []
    assert cards(ev)[0] == "SATISFIED"


def test_one_failed_or_alternative_is_not_a_failure_when_another_is_unresolved():
    ev = evidence(course_id="1501445", transcript=[take("1501211", "I")])
    assert req(ev)["status"] == "UNRESOLVED"
    assert keywords(ev) == []


def test_confirmed_and_failure_is_kept_even_when_a_sibling_is_unresolved():
    ev = evidence(course_id="1501371", transcript=[take("1501215", "F"), take("1501279", "W")])
    assert req(ev)["status"] == "NOT_SATISFIED"
    assert [f["course_ids"] for f in req(ev)["confirmed_failures"]] == [["1501215"]]


# Academic standing (thresholds from the knowledge file only)
@pytest.mark.parametrize("hours, status", [(64, "NOT_SATISFIED"), (65, "SATISFIED"), (98, "SATISFIED"), (99, "SATISFIED")])
def test_junior_standing(hours, status):
    ev = evidence(course_id="1501344", hours=hours)
    assert req(ev)["status"] == status
    assert cards(ev) == ("NOT_APPLICABLE", status)


@pytest.mark.parametrize("hours, status", [(98, "NOT_SATISFIED"), (99, "SATISFIED")])
def test_senior_standing(hours, status):
    ev = evidence(course_id="1501441", transcript=[take("1501215", "A")], hours=hours)
    assert req(ev)["status"] == status


def test_standing_failure_with_satisfied_course_conditions():
    ev = evidence(course_id="1501394", transcript=[take("1501215", "B")], hours=60)
    assert req(ev)["status"] == "NOT_SATISFIED"
    assert cards(ev) == ("SATISFIED", "NOT_SATISFIED")
    failure = req(ev)["confirmed_failures"][0]
    assert (failure["keyword"], failure["required_earned_credits"], failure["completed_hours"]) == (
        "academic_standing_not_satisfied", 65, 60)


def test_standing_options_give_one_standing_failure():
    ev = evidence(course_id="1501397", hours=64)
    failure = req(ev)["confirmed_failures"]
    assert len(failure) == 1
    assert failure[0]["keyword"] == "academic_standing_not_satisfied"
    assert failure[0]["standings"] == ["Junior Standing", "Senior Standing"]
    assert failure[0]["required_earned_credits"] == 65


def test_missing_completed_hours_leaves_standing_unresolved():
    ev = evidence(course_id="1501344", hours=None)
    assert req(ev)["status"] == "UNRESOLVED"
    assert cards(ev)[1] == "UNRESOLVED"
    assert ev["checks"]["completed_hours"]["student_completed_hours"] is None


def test_course_without_standing_reports_it():
    ev = evidence(transcript=[take("1501211", "A")])
    assert ev["checks"]["completed_hours"]["applicable"] is False
    assert "no academic standing condition" in ev["checks"]["completed_hours"]["details"]


# Identifiers and knowledge
def test_leading_zero_alternative_course():
    ev = evidence(course_id="1501252", transcript=[take("0403201", "B")])
    assert req(ev)["status"] == "SATISFIED"
    assert {leaf["course_id"] for leaf in ev["checks"]["prerequisite"]["course_conditions"]} == {"1502201", "0403201"}


def test_leading_zero_course_without_prerequisites():
    ev = evidence(course_id="0202213", course_name="Critical Reading and Writing")
    assert req(ev)["knowledge_status"] == "NO_PREREQUISITES"
    assert cards(ev) == ("NOT_APPLICABLE", "NOT_APPLICABLE")
    assert ev["course"]["Course_ID"] == "0202213"


def test_course_missing_from_the_knowledge_is_unresolved():
    ev = evidence(course_id="1502232", course_name="Other")
    assert (req(ev)["status"], req(ev)["knowledge_status"]) == ("UNRESOLVED", "MISSING_FROM_KNOWLEDGE_BASE")
    assert cards(ev) == ("UNRESOLVED", "UNRESOLVED")
    assert keywords(ev) == []

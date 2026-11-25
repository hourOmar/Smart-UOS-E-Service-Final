"""Factor 7 — direct dependent courses from the prerequisite knowledge file."""

from app.agents.raise_capacity_priority.deterministic.prerequisite_knowledge import PREREQUISITE_KNOWLEDGE
from app.agents.raise_capacity_priority.deterministic.progression import (
    build_progression_evidence,
    not_evaluated_progression_evidence,
    requested_course_role,
)
from app.agents.raise_capacity_priority.schemas.academic_history import TakesRecord
from app.agents.raise_capacity_priority.schemas.study_plan import StudyPlanInfo

REQUEST_TERM = 202601
REQUIRED = ["1501250", "1501263", "1501319", "1501330", "1501352", "1501366", "1501371", "1501372", "1501394",
            "1501454", "1501459", "1501211", "1501246"]
ELECTIVE = ["1501433", "1501440", "1501441", "1501458", "1501490", "1501491", "1501492", "1501341", "1501443",
            "1501445", "1501465", "1501342", "1501343"]
PLAN = StudyPlanInfo(
    program_id="1501", status="OK", plan_version="CS-WEB-2026-10-31",
    requirement_types={**{c: "REQUIRED" for c in REQUIRED}, **{c: "ELECTIVE" for c in ELECTIVE}},
    total_required_credits=123, total_status="OK", notes=[],
)


def take(course_id, grade, term=202502):
    return TakesRecord(course_id=course_id, grade=grade, section_id="1", term=term)


def progression(course_id, *records, hours=70, plan=PLAN):
    return build_progression_evidence(course_id, PREREQUISITE_KNOWLEDGE, list(records), REQUEST_TERM, hours, plan)


def dependent(ev, course_id):
    return next(d for d in ev.dependent_courses if d.course_id == course_id)


def test_data_structures_direct_dependents():
    ev = progression("1501215")
    assert ev.evaluated is True
    assert ev.total_direct_dependents == 18
    assert ev.required_dependents == 11
    assert ev.elective_dependents == 7
    assert ev.potentially_affected_dependents == 18
    assert ev.potentially_affected_required_dependents == 11
    assert ev.completed_dependents == 0


def test_mandatory_and_alternative_roles():
    ev = progression("1501215")
    assert dependent(ev, "1501371").requested_course_role == "MANDATORY"  # 1501215 AND 1501279
    assert dependent(ev, "1501250").requested_course_role == "ALTERNATIVE"  # 1501215 OR 1501214
    assert dependent(ev, "1501394").requested_course_role == "MANDATORY"  # 1501215 AND Junior Standing


def test_completed_dependent_is_not_blocked():
    ev = progression("1501215", take("1501263", "B"))
    dep = dependent(ev, "1501263")
    assert dep.completion_status == "COMPLETED"
    assert dep.potentially_affected_by_delay is False
    assert ev.completed_dependents == 1
    assert ev.potentially_affected_dependents == 17


def test_satisfied_alternative_route_is_not_blocked():
    ev = progression("1501215", take("1501214", "A"))
    for course_id in ("1501250", "1501458", "1501490"):
        dep = dependent(ev, course_id)
        assert dep.alternative_route_already_satisfied is True
        assert dep.potentially_affected_by_delay is False
    assert ev.alternative_route_satisfied_dependents == 3
    assert ev.potentially_affected_dependents == 15


def test_unsatisfied_alternative_route_is_potentially_affected():
    dep = dependent(progression("1501215"), "1501250")
    assert dep.alternative_route_already_satisfied is False
    assert dep.potentially_affected_by_delay is True


def test_alternative_route_via_other_course_for_web_programming():
    # 1501341 dependents: 1501443 (1501341 AND ...), 1501445 (1501211 OR 1501341), 1501465 (1501263 AND 1501341)
    ev = progression("1501341", take("1501211", "C"))
    assert dependent(ev, "1501445").potentially_affected_by_delay is False
    assert dependent(ev, "1501443").potentially_affected_by_delay is True
    assert dependent(ev, "1501465").potentially_affected_by_delay is True
    assert dependent(ev, "1501443").requested_course_role == "MANDATORY"


def test_nested_alternative_role():
    # 1501443: 1501341 AND (1501246 OR 1501247) -> 1501246 is an alternative
    assert requested_course_role(PREREQUISITE_KNOWLEDGE.entry("1501443").requirement, "1501246") == "ALTERNATIVE"
    ev = progression("1501246", take("1501247", "B"))
    assert dependent(ev, "1501443").potentially_affected_by_delay is False


def test_unresolved_other_route_is_unknown_not_blocked():
    ev = progression("1501341", take("1501211", "I"))
    dep = dependent(ev, "1501445")
    assert dep.alternative_route_already_satisfied is None
    assert dep.potentially_affected_by_delay is None
    assert ev.unresolved_dependents == 1


def test_dependent_with_unresolved_completion():
    dep = dependent(progression("1501215", take("1501263", None)), "1501263")
    assert dep.completion_status == "UNRESOLVED"
    assert dep.potentially_affected_by_delay is None


def test_requested_course_already_passed_blocks_nothing():
    ev = progression("1501215", take("1501215", "D"))
    assert ev.requested_course_already_passed is True
    assert ev.potentially_affected_dependents == 0


def test_unrelated_unmet_condition_does_not_change_the_answer():
    # 1501371 needs 1501215 AND 1501279: whether 1501279 is done does not
    # make the requested course any less needed.
    assert dependent(progression("1501215"), "1501371").potentially_affected_by_delay is True
    assert dependent(progression("1501215", take("1501279", "A")), "1501371").potentially_affected_by_delay is True


def test_nested_alternative_unsatisfied_is_affected():
    ev = progression("1501246")
    assert dependent(ev, "1501443").potentially_affected_by_delay is True
    assert dependent(ev, "1501443").alternative_route_already_satisfied is False


def test_future_record_does_not_complete_a_dependent():
    dep = dependent(progression("1501215", take("1501263", "A", 202602)), "1501263")
    assert dep.completion_status == "NOT_COMPLETED"


def test_course_without_dependents():
    ev = progression("1501494")
    assert ev.total_direct_dependents == 0 and ev.dependent_courses == []


def test_dependent_requirement_types_from_the_study_plan():
    plan = PLAN.model_copy(update={"requirement_types": {"1501371": "REQUIRED"}})
    ev = progression("1501215", plan=plan)
    assert dependent(ev, "1501371").requirement_type == "REQUIRED"
    assert dependent(ev, "1501433").requirement_type == "NOT_IN_STUDY_PLAN"


def test_dependent_offerings_are_included_and_unknown_kept():
    ev = progression("1501215")
    assert (dependent(ev, "1501433").fall, dependent(ev, "1501433").spring) == ("UNKNOWN", "UNKNOWN")
    assert dependent(ev, "1501459").fall == "YES"


def test_not_evaluated_progression():
    ev = not_evaluated_progression_evidence("1502232", "Outside scope.")
    assert ev.evaluated is False and ev.not_evaluated_reason == "Outside scope."

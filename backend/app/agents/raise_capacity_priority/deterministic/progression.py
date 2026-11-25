"""
Factor 7 — academic progression: the DIRECT dependent courses of the
requested course, derived from knowledge/course_prerequisites.json (no
separate dependency file), and whether delaying the requested course could
genuinely affect each one for this student.

For each direct dependent:
- requirement_type: REQUIRED / ELECTIVE / NOT_IN_STUDY_PLAN / UNKNOWN in the
  student's current study plan;
- requested_course_role: MANDATORY when every route through the dependent's
  requirement needs the requested course, ALTERNATIVE when another route
  exists (a structural property of the requirement);
- completion_status: COMPLETED when the dependent was passed before the
  requested term (not blocked);
- alternative_route_already_satisfied / potentially_affected_by_delay:
  whether the requested course is still NEEDED on the dependent's route,
  given what the student has already satisfied (requested_course_needed):
  in an AND group it is needed if any part needs it; in an OR group it is
  not needed when another branch is ALREADY satisfied, unknown when such a
  branch is unresolved, and needed otherwise. Conditions unrelated to the
  requested course (e.g. another course still to be taken alongside it)
  never make a dependent "affected" or "unaffected" by themselves. A
  requested course already passed before the requested term blocks nothing.

Direct dependencies only — no future study schedule is generated, and a
dependency never means a guaranteed delay. Counts never decide priority.
"""

from typing import Optional

from ..deterministic.course_offerings import get_course_offering
from ..deterministic.prerequisite_evaluator import combine, evaluate_course_leaf, evaluate_requirement
from ..deterministic.prerequisite_knowledge import SOURCE, PrerequisiteKnowledge
from ..schemas.academic_history import TakesRecord
from ..schemas.deterministic import DependentCourseEvidence, ProgressionEvidence
from ..schemas.prerequisites import CourseRequirement, RequirementGroup, RequirementNode, StandingRequirement
from ..schemas.study_plan import StudyPlanInfo


def requested_course_role(node: RequirementNode, requested_course_id: str) -> str:
    """MANDATORY if the requirement cannot be met without the requested course
    even when every other condition is met; otherwise ALTERNATIVE."""

    def structural(n: RequirementNode) -> str:
        if isinstance(n, CourseRequirement):
            return "NOT_SATISFIED" if n.course_id == requested_course_id else "SATISFIED"
        if isinstance(n, StandingRequirement):
            return "SATISFIED"
        assert isinstance(n, RequirementGroup)
        return combine(n.type, [structural(item) for item in n.items])

    return "MANDATORY" if structural(node) == "NOT_SATISFIED" else "ALTERNATIVE"


def requested_course_needed(
    node: RequirementNode,
    requested_course_id: str,
    transcript: list[TakesRecord],
    request_term: int,
    completed_hours: Optional[int],
    knowledge: PrerequisiteKnowledge,
) -> Optional[bool]:
    """True when meeting `node` still requires the requested course, False
    when it does not (not involved, or an alternative branch is already
    satisfied), None when an alternative branch is unresolved."""
    if isinstance(node, CourseRequirement):
        return node.course_id == requested_course_id
    if isinstance(node, StandingRequirement):
        return False
    assert isinstance(node, RequirementGroup)
    needs = [requested_course_needed(item, requested_course_id, transcript, request_term, completed_hours, knowledge)
             for item in node.items]
    if node.type == "ALL_OF":
        if any(n is True for n in needs):
            return True
        return None if any(n is None for n in needs) else False
    # ANY_OF: branches that do not need the requested course are alternatives.
    if all(n is False for n in needs):
        return False
    alternatives = [
        evaluate_requirement(item, transcript, request_term, completed_hours, knowledge)
        for item, n in zip(node.items, needs) if n is False
    ]
    if any(status == "SATISFIED" for status in alternatives):
        return False
    if any(status == "UNRESOLVED" for status in alternatives) or any(n is None for n in needs):
        return None
    return True


def not_evaluated_progression_evidence(course_id: str, reason: str) -> ProgressionEvidence:
    return ProgressionEvidence(
        requested_course_id=course_id, evaluated=False, not_evaluated_reason=reason,
        requested_course_already_passed=False, total_direct_dependents=0, required_dependents=0,
        elective_dependents=0, not_in_study_plan_dependents=0, unknown_requirement_dependents=0,
        completed_dependents=0, alternative_route_satisfied_dependents=0, potentially_affected_dependents=0,
        potentially_affected_required_dependents=0, unresolved_dependents=0, dependent_courses=[], source=SOURCE,
    )


def build_progression_evidence(
    requested_course_id: str,
    knowledge: PrerequisiteKnowledge,
    transcript: list[TakesRecord],
    request_term: int,
    completed_hours: Optional[int],
    study_plan: StudyPlanInfo,
) -> ProgressionEvidence:
    already_passed = evaluate_course_leaf(requested_course_id, "PRE", transcript, request_term).status == "SATISFIED"

    dependents: list[DependentCourseEvidence] = []
    for dependent_id in knowledge.direct_dependents(requested_course_id):
        entry = knowledge.entry(dependent_id)
        role = requested_course_role(entry.requirement, requested_course_id)
        completion = {
            "SATISFIED": "COMPLETED", "NOT_SATISFIED": "NOT_COMPLETED", "UNRESOLVED": "UNRESOLVED",
        }[evaluate_course_leaf(dependent_id, "PRE", transcript, request_term).status]

        alternative: Optional[bool]
        affected: Optional[bool]
        if completion == "COMPLETED":
            alternative, affected = None, False
            note = "Already passed before the requested term; not blocked."
        elif completion == "UNRESOLVED":
            alternative, affected = None, None
            note = "A transcript record exists but its completion cannot be confirmed."
        elif already_passed:
            alternative, affected = None, False
            note = "The requested course was already passed before the requested term; not blocked."
        else:
            needed = requested_course_needed(
                entry.requirement, requested_course_id, transcript, request_term, completed_hours, knowledge
            )
            if needed is False:
                alternative, affected = True, False
                note = "An alternative route in its requirement is already satisfied; not blocked."
            elif needed is True:
                alternative, affected = False, True
                note = ("Its requirement still needs the requested course; delaying the requested course "
                        "could delay access to it.")
            else:
                alternative, affected = None, None
                note = "An alternative route in its requirement is unresolved; whether it is blocked is unknown."

        offering = get_course_offering(dependent_id)
        dependents.append(DependentCourseEvidence(
            course_id=dependent_id, course_name=entry.course_name,
            requirement_type=study_plan.requirement_type(dependent_id), requested_course_role=role,
            completion_status=completion, alternative_route_already_satisfied=alternative,
            potentially_affected_by_delay=affected, note=note,
            fall=offering["fall"] if offering else None,
            spring=offering["spring"] if offering else None,
            summer=offering["summer"] if offering else None,
        ))

    def count(predicate) -> int:
        return sum(1 for d in dependents if predicate(d))

    return ProgressionEvidence(
        requested_course_id=requested_course_id,
        evaluated=True,
        not_evaluated_reason=None,
        requested_course_already_passed=already_passed,
        total_direct_dependents=len(dependents),
        required_dependents=count(lambda d: d.requirement_type == "REQUIRED"),
        elective_dependents=count(lambda d: d.requirement_type == "ELECTIVE"),
        not_in_study_plan_dependents=count(lambda d: d.requirement_type == "NOT_IN_STUDY_PLAN"),
        unknown_requirement_dependents=count(lambda d: d.requirement_type == "UNKNOWN"),
        completed_dependents=count(lambda d: d.completion_status == "COMPLETED"),
        alternative_route_satisfied_dependents=count(lambda d: d.alternative_route_already_satisfied is True),
        potentially_affected_dependents=count(lambda d: d.potentially_affected_by_delay is True),
        potentially_affected_required_dependents=count(
            lambda d: d.potentially_affected_by_delay is True and d.requirement_type == "REQUIRED"),
        unresolved_dependents=count(lambda d: d.potentially_affected_by_delay is None),
        dependent_courses=dependents,
        source=SOURCE,
    )

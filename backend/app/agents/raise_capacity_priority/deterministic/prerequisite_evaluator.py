"""
Factor 6 — deterministic prerequisite evaluation against the validated
local knowledge/course_prerequisites.json and the student's Takes records.
Never returns a priority: only SATISFIED / NOT_SATISFIED / UNRESOLVED /
CONFLICT plus the evidence behind that status.

Record use (approved decisions 1 and 2):
- Only records from terms BEFORE the requested term can complete a
  prerequisite: a passing grade (grade_policy.json) -> satisfied; F, WF, FA
  -> not satisfied; W, I, NULL and any unrecognized grade -> unresolved.
- A record in the requested term is current enrolment (NULL grade, or a
  passing grade). It satisfies CO and PRE_OR_CO, never PRE. A failing or
  withdrawn grade in the requested term is not enrolment; an unrecognized
  one (e.g. W, I) leaves concurrent enrolment unresolved.
- Records AFTER the requested term are ignored.
- A record whose order cannot be determined (unsupported semester suffix)
  is unresolved.

Modes: PRE (completed before), CO (enrolled in the requested term only),
PRE_OR_CO (either). The knowledge file expresses PRE and PRE_OR_CO through
concurrent_allowed; CO is supported for future use.

STANDING: satisfied when Student.Completed_Hours (earned credit hours) is at
least the standing's prerequisite_min_earned_credits from the knowledge
file; missing or invalid completed hours are unresolved.

AND / OR use three-valued logic: AND is NOT_SATISFIED if any branch is
NOT_SATISFIED, SATISFIED only if every branch is; OR is the mirror;
otherwise UNRESOLVED.
"""

from typing import Optional

from ..deterministic.grade_policy import classify_grade
from ..deterministic.prerequisite_knowledge import SOURCE, PrerequisiteKnowledge, referenced_course_ids
from ..retrieval.academic_history import term_relation
from ..schemas.academic_history import TakesRecord
from ..schemas.deterministic import (
    PrerequisiteCompletionEvidence,
    PrerequisiteLeafEvaluation,
    TakesRecordEvaluation,
)
from ..schemas.prerequisites import CourseRequirement, RequirementGroup, RequirementNode, StandingRequirement

__all__ = [
    "evaluate_course_leaf",
    "evaluate_prerequisite_completion",
    "evaluate_requirement",
    "evaluate_standing_leaf",
    "mode_for",
    "not_evaluated_prerequisite_evidence",
    "referenced_course_ids",
]


def mode_for(node: CourseRequirement) -> str:
    return "PRE_OR_CO" if node.concurrent_allowed else "PRE"


def combine(operator: str, statuses: list[str]) -> str:
    if operator == "ALL_OF":
        if any(s == "NOT_SATISFIED" for s in statuses):
            return "NOT_SATISFIED"
        if all(s == "SATISFIED" for s in statuses):
            return "SATISFIED"
        return "UNRESOLVED"
    if any(s == "SATISFIED" for s in statuses):
        return "SATISFIED"
    if all(s == "NOT_SATISFIED" for s in statuses):
        return "NOT_SATISFIED"
    return "UNRESOLVED"


def evaluate_course_leaf(
    course_id: str, mode: str, transcript: list[TakesRecord], request_term: int
) -> PrerequisiteLeafEvaluation:
    evaluations: list[TakesRecordEvaluation] = []
    passed_before = unresolved_before = enrolled_now = enrolment_unresolved = unknown_order = False
    for record in transcript:
        if record.course_id != course_id:
            continue
        relation = term_relation(record.term, request_term)
        grade_status = classify_grade(record.grade)
        evaluations.append(TakesRecordEvaluation(
            course_id=record.course_id, grade=record.grade, term=record.term,
            term_relation=relation, grade_status=grade_status,
        ))
        if relation == "BEFORE_REQUEST_TERM":
            if grade_status == "PASSING":
                passed_before = True
            elif grade_status in ("MISSING", "UNRECOGNIZED"):
                unresolved_before = True
        elif relation == "REQUEST_TERM":
            if grade_status in ("MISSING", "PASSING"):
                enrolled_now = True
            elif grade_status == "UNRECOGNIZED":
                enrolment_unresolved = True
        elif relation == "UNKNOWN_TERM":
            unknown_order = True

    can_complete = mode in ("PRE", "PRE_OR_CO")
    can_enrol = mode in ("CO", "PRE_OR_CO")
    if can_complete and passed_before:
        status, reason = "SATISFIED", f"{course_id} was passed in a term before the requested term."
    elif can_enrol and enrolled_now:
        status, reason = "SATISFIED", f"The student is enrolled in {course_id} in the requested term ({mode})."
    elif (can_complete and unresolved_before) or (can_enrol and enrolment_unresolved) or unknown_order:
        status = "UNRESOLVED"
        reason = (
            f"Record(s) for {course_id} have a grade that is NULL, withdrawn, incomplete or not in the grade "
            "policy, or a term whose order cannot be determined; completion cannot be confirmed."
        )
    else:
        status = "NOT_SATISFIED"
        if not evaluations:
            reason = f"No transcript record for {course_id}."
        elif mode == "PRE":
            reason = f"{course_id} was not passed in any term before the requested term."
        elif mode == "CO":
            reason = f"The student is not enrolled in {course_id} in the requested term."
        else:
            reason = f"{course_id} was neither passed before nor taken in the requested term."
    return PrerequisiteLeafEvaluation(
        kind="COURSE", course_id=course_id, mode=mode, standing_text=None, required_earned_credits=None,
        completed_hours=None, status=status, reason=reason, matched_takes_records=evaluations,
    )


def evaluate_standing_leaf(
    standing_text: str, completed_hours: Optional[int], knowledge: PrerequisiteKnowledge
) -> PrerequisiteLeafEvaluation:
    threshold = knowledge.standing_threshold(standing_text)
    if threshold is None:
        status, reason = "UNRESOLVED", f"{standing_text} is not defined in the prerequisite knowledge file."
    elif completed_hours is None:
        status, reason = "UNRESOLVED", "Student.Completed_Hours is missing; standing cannot be evaluated."
    elif completed_hours < 0:
        status, reason = "UNRESOLVED", "Student.Completed_Hours is negative (invalid); standing cannot be evaluated."
    elif completed_hours >= threshold:
        status = "SATISFIED"
        reason = f"{completed_hours} earned credit hours meet the {threshold} required for {standing_text}."
    else:
        status = "NOT_SATISFIED"
        reason = f"{completed_hours} earned credit hours are below the {threshold} required for {standing_text}."
    return PrerequisiteLeafEvaluation(
        kind="STANDING", course_id=None, mode=None, standing_text=standing_text, required_earned_credits=threshold,
        completed_hours=completed_hours, status=status, reason=reason, matched_takes_records=[],
    )


def evaluate_requirement(
    node: RequirementNode,
    transcript: list[TakesRecord],
    request_term: int,
    completed_hours: Optional[int],
    knowledge: PrerequisiteKnowledge,
    leaves: Optional[list[PrerequisiteLeafEvaluation]] = None,
) -> str:
    """Status of one requirement tree (leaf evaluations appended to `leaves`)."""
    if isinstance(node, CourseRequirement):
        leaf = evaluate_course_leaf(node.course_id, mode_for(node), transcript, request_term)
    elif isinstance(node, StandingRequirement):
        leaf = evaluate_standing_leaf(node.text, completed_hours, knowledge)
    else:
        assert isinstance(node, RequirementGroup)
        statuses = [
            evaluate_requirement(item, transcript, request_term, completed_hours, knowledge, leaves)
            for item in node.items
        ]
        return combine(node.type, statuses)
    if leaves is not None:
        leaves.append(leaf)
    return leaf.status


def _evidence(course_id, status, knowledge_status, reason, expression=None, leaves=None):
    return PrerequisiteCompletionEvidence(
        course_id=course_id, status=status, knowledge_status=knowledge_status, reason=reason,
        requirement_expression=expression, leaf_evaluations=leaves or [], source=SOURCE,
    )


def not_evaluated_prerequisite_evidence(course_id: str, reason: str) -> PrerequisiteCompletionEvidence:
    return _evidence(course_id, "UNRESOLVED", "NOT_EVALUATED", reason)


def evaluate_prerequisite_completion(
    course_id: str,
    knowledge: PrerequisiteKnowledge,
    transcript: list[TakesRecord],
    request_term: int,
    completed_hours: Optional[int],
) -> PrerequisiteCompletionEvidence:
    entry = knowledge.entry(course_id)
    if entry is None:
        return _evidence(course_id, "UNRESOLVED", "MISSING_FROM_KNOWLEDGE_BASE",
                         "The requested course is not in the prerequisite knowledge file; its requirement is unknown.")
    if entry.prerequisite_status == "CONFLICTING":
        return _evidence(course_id, "CONFLICT", "CONFLICTING",
                         "The prerequisite knowledge file records conflicting requirements for this course.")
    if entry.prerequisite_status != "VERIFIED":
        return _evidence(course_id, "UNRESOLVED", "NOT_VERIFIED",
                         f"The prerequisite requirement is not verified ({entry.prerequisite_status}).")
    if entry.requirement is None:
        return _evidence(course_id, "SATISFIED", "NO_PREREQUISITES",
                         "The course explicitly has no prerequisites.")

    leaves: list[PrerequisiteLeafEvaluation] = []
    status = evaluate_requirement(entry.requirement, transcript, request_term, completed_hours, knowledge, leaves)
    return _evidence(
        course_id, status, "REQUIREMENT_DEFINED",
        f"Evaluated the verified requirement from the prerequisite knowledge file: {status}.",
        entry.requirement, leaves,
    )

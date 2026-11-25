"""
The academic part of the evaluation: the course's COMPLETE requirement
(prerequisite courses and academic standing together, as one nested AND/OR
tree from knowledge_base/course_prerequisites.json) evaluated ONCE by the
copied, validated evaluator — and the two administrator-facing checks derived
from that single result:

- checks.prerequisite     the requirement's COURSE conditions;
- checks.completed_hours  the requirement's ACADEMIC STANDING conditions
                          (Student.Completed_Hours against the knowledge file's
                          standing thresholds; no other threshold exists).

Both checks carry the complete requirement's status (requirement_status). A
check is NOT_SATISFIED only when a CONFIRMED failure of the complete
requirement belongs to it (academic/requirement_failures.py), so one failed
alternative never fails a check when another alternative satisfies — or may
still satisfy — the requirement. The recommendation policy uses the complete
requirement's status, never a check on its own.
"""

from typing import Optional

from .academic.prerequisite_evaluator import evaluate_prerequisite_completion, not_evaluated_prerequisite_evidence
from .academic.prerequisite_knowledge import PREREQUISITE_KNOWLEDGE, PrerequisiteKnowledge
from .academic.records import TakesRecord
from .academic.requirement_failures import confirmed_failures


def _component_status(kind: str, completion: dict, leaves: list[dict], failures: list[dict]) -> str:
    knowledge_status = completion["knowledge_status"]
    if knowledge_status == "NOT_EVALUATED":
        return "NOT_EVALUATED"
    if knowledge_status == "CONFLICTING":
        return "CONFLICT"
    if knowledge_status in ("MISSING_FROM_KNOWLEDGE_BASE", "NOT_VERIFIED"):
        return "UNRESOLVED"  # the requirement itself is unknown
    if knowledge_status == "NO_PREREQUISITES" or not leaves:
        return "NOT_APPLICABLE"
    if completion["status"] == "SATISFIED":
        return "SATISFIED"
    if any(kind in f["kinds"] for f in failures):
        return "NOT_SATISFIED"
    if any(leaf["status"] == "UNRESOLVED" for leaf in leaves):
        return "UNRESOLVED"
    return "SATISFIED"  # these conditions are met; the requirement fails or is unresolved elsewhere


def build_academic_checks(
    course_id: str,
    transcript: list[TakesRecord],
    request_term: int,
    completed_hours: Optional[int],
    scope: dict,
    knowledge: PrerequisiteKnowledge = PREREQUISITE_KNOWLEDGE,
) -> tuple[dict, dict, dict]:
    """Returns (academic_requirement, prerequisite_check, standing_check)."""
    if scope["status"] != "SUPPORTED":
        completion = not_evaluated_prerequisite_evidence(course_id, scope["note"]).model_dump(mode="json")
        failures: list[dict] = []
    else:
        evidence = evaluate_prerequisite_completion(course_id, knowledge, transcript, request_term, completed_hours)
        completion = evidence.model_dump(mode="json")
        entry = knowledge.entry(course_id)
        failures = (
            confirmed_failures(entry.requirement, transcript, request_term, completed_hours, knowledge)
            if evidence.status == "NOT_SATISFIED" and entry is not None else []
        )

    leaves = completion["leaf_evaluations"]
    course_leaves = [leaf for leaf in leaves if leaf["kind"] == "COURSE"]
    standing_leaves = [leaf for leaf in leaves if leaf["kind"] == "STANDING"]
    requirement = {**completion, "confirmed_failures": failures}
    evaluated = completion["knowledge_status"] != "NOT_EVALUATED"

    prerequisite = {
        "evaluated": evaluated,
        "applicable": bool(course_leaves) if evaluated else None,
        "status": _component_status("prerequisite", completion, course_leaves, failures),
        "requirement_status": completion["status"],
        "knowledge_status": completion["knowledge_status"],
        "course_conditions": course_leaves,
        "confirmed_failures": [f for f in failures if "prerequisite" in f["kinds"]],
        "details": completion["reason"],
        "source": completion["source"],
    }
    standing = {
        "evaluated": evaluated,
        "applicable": bool(standing_leaves) if evaluated else None,
        "status": _component_status("standing", completion, standing_leaves, failures),
        "requirement_status": completion["status"],
        "student_completed_hours": completed_hours,
        "standing_conditions": standing_leaves,
        "confirmed_failures": [f for f in failures if "standing" in f["kinds"]],
        "details": (
            "The course's requirement includes no academic standing condition."
            if evaluated and not standing_leaves and completion["knowledge_status"] in ("REQUIREMENT_DEFINED", "NO_PREREQUISITES")
            else completion["reason"] if not evaluated else None
        ),
    }
    return requirement, prerequisite, standing

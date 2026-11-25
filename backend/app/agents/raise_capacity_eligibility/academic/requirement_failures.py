"""
The CONFIRMED failures of a course's complete requirement (prerequisites and
academic standing together), found by walking only the parts of the
requirement tree that are themselves NOT_SATISFIED:

- ALL_OF: each child that is NOT_SATISFIED is a confirmed failure (its own
  failures are collected); unresolved siblings are left out — a confirmed
  failure establishes the failure of the whole AND.
- ANY_OF: reached only when EVERY option is NOT_SATISFIED. One failure is
  recorded for the whole group (prerequisite_options_not_satisfied, or
  academic_standing_not_satisfied when every option is a standing).
- COURSE: PRE -> prerequisite_not_passed when an earlier attempt exists
  (failing grades only — any unresolved grade makes the leaf UNRESOLVED, not
  NOT_SATISFIED), otherwise prerequisite_not_completed; CO / PRE_OR_CO ->
  corequisite_not_satisfied.
- STANDING -> academic_standing_not_satisfied.

A requirement that is SATISFIED, UNRESOLVED or CONFLICT has NO confirmed
failure, so an individual failed condition inside a satisfied or unresolved
requirement (e.g. one failed OR alternative) never appears here.

Statuses come from the copied, validated evaluator; nothing is re-decided.
"""

from typing import Iterator, Optional

from .prerequisite_evaluator import evaluate_course_leaf, evaluate_requirement, evaluate_standing_leaf, mode_for
from .prerequisite_knowledge import PrerequisiteKnowledge, referenced_course_ids
from .prerequisite_schemas import CourseRequirement, RequirementGroup, RequirementNode, StandingRequirement
from .records import TakesRecord


def describe(node: RequirementNode) -> str:
    """A plain description of a requirement node (course IDs as text)."""
    if isinstance(node, CourseRequirement):
        return node.course_id + (" (completed before, or taken in the same term)" if node.concurrent_allowed else "")
    if isinstance(node, StandingRequirement):
        return node.text
    joiner = " and " if node.type == "ALL_OF" else " or "
    return joiner.join(f"({describe(item)})" if isinstance(item, RequirementGroup) else describe(item)
                       for item in node.items)


def _walk(node: RequirementNode) -> Iterator[RequirementNode]:
    yield node
    if isinstance(node, RequirementGroup):
        for item in node.items:
            yield from _walk(item)


def confirmed_failures(
    node: Optional[RequirementNode],
    transcript: list[TakesRecord],
    request_term: int,
    completed_hours: Optional[int],
    knowledge: PrerequisiteKnowledge,
) -> list[dict]:
    if node is None:
        return []
    if evaluate_requirement(node, transcript, request_term, completed_hours, knowledge) != "NOT_SATISFIED":
        return []

    if isinstance(node, CourseRequirement):
        leaf = evaluate_course_leaf(node.course_id, mode_for(node), transcript, request_term)
        earlier = [r for r in leaf.matched_takes_records if r.term_relation == "BEFORE_REQUEST_TERM"]
        if leaf.mode in ("CO", "PRE_OR_CO"):
            keyword = "corequisite_not_satisfied"
        else:
            keyword = "prerequisite_not_passed" if earlier else "prerequisite_not_completed"
        return [{
            "keyword": keyword,
            "kinds": ["prerequisite"],
            "course_ids": [node.course_id],
            "mode": leaf.mode,
            "recorded_grades": [r.grade for r in earlier],
            "detail": leaf.reason,
        }]

    if isinstance(node, StandingRequirement):
        leaf = evaluate_standing_leaf(node.text, completed_hours, knowledge)
        return [{
            "keyword": "academic_standing_not_satisfied",
            "kinds": ["standing"],
            "standings": [node.text],
            "required_earned_credits": leaf.required_earned_credits,
            "completed_hours": completed_hours,
            "detail": leaf.reason,
        }]

    assert isinstance(node, RequirementGroup)
    if node.type == "ALL_OF":
        found: list[dict] = []
        for item in node.items:
            found.extend(confirmed_failures(item, transcript, request_term, completed_hours, knowledge))
        return found

    # ANY_OF: every option is NOT_SATISFIED.
    leaves = list(_walk(node))
    if all(isinstance(n, (StandingRequirement, RequirementGroup)) for n in leaves):
        standings = [n.text for n in leaves if isinstance(n, StandingRequirement)]
        thresholds = [t for t in (knowledge.standing_threshold(s) for s in standings) if t is not None]
        return [{
            "keyword": "academic_standing_not_satisfied",
            "kinds": ["standing"],
            "standings": standings,
            # The lowest threshold among the options is the one that would satisfy the group.
            "required_earned_credits": min(thresholds) if thresholds else None,
            "completed_hours": completed_hours,
            "detail": f"None of the standing options is met ({describe(node)}).",
        }]
    has_standing = any(isinstance(n, StandingRequirement) for n in leaves)
    return [{
        "keyword": "prerequisite_options_not_satisfied",
        "kinds": ["prerequisite", "standing"] if has_standing else ["prerequisite"],
        "course_ids": sorted(referenced_course_ids(node)),
        "options": [describe(item) for item in node.items],
        "option_failures": [
            confirmed_failures(item, transcript, request_term, completed_hours, knowledge) for item in node.items
        ],
        "completed_hours": completed_hours if has_standing else None,
        "detail": f"None of the options is satisfied ({describe(node)}).",
    }]

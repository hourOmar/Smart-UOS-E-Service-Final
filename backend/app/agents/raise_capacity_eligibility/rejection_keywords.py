"""
Rejection keyword detection (deterministic, no AI). Keywords come ONLY from
confirmed failures of complete applicable requirements in the eligibility
evidence:

- academic_requirement.confirmed_failures (academic/requirement_failures.py:
  a failure exists only when the complete AND/OR requirement is NOT_SATISFIED,
  and only for its parts that are themselves NOT_SATISFIED);
- checks.capacity.status NOT_SATISFIED -> no_remaining_capacity.

Nothing is detected for a program outside the supported scope, or from
unresolved, conflicting or unevaluated evidence. Each detected keyword carries
the verified facts its sentences are filled from.
"""

import json

from . import KNOWLEDGE_DIR
from .academic.prerequisite_knowledge import PREREQUISITE_KNOWLEDGE

_KB_PATH = KNOWLEDGE_DIR / "rejection_keywords.json"
APPROVED_KEYWORDS = (
    "prerequisite_not_completed",
    "prerequisite_not_passed",
    "prerequisite_options_not_satisfied",
    "corequisite_not_satisfied",
    "academic_standing_not_satisfied",
    "no_remaining_capacity",
)


def load_rejection_knowledge() -> dict:
    data = json.loads(_KB_PATH.read_text(encoding="utf-8"))
    if tuple(data["keywords"]) != APPROVED_KEYWORDS:
        raise ValueError("rejection_keywords.json must define exactly the six approved keywords, in order.")
    for keyword, entry in data["keywords"].items():
        for field in ("requirement", "label", "policy_basis", "plain_reason", "concise_reason", "supportive_guidance"):
            if not isinstance(entry.get(field), str):
                raise ValueError(f"rejection_keywords.json: {keyword} is missing {field}.")
    if set(data["templates"]) != {"formal", "concise", "supportive"}:
        raise ValueError("rejection_keywords.json must define the formal, concise and supportive templates.")
    return data


REJECTION_KNOWLEDGE = load_rejection_knowledge()


def course_label(course_id: str) -> str:
    entry = PREREQUISITE_KNOWLEDGE.entry(course_id)
    return f"{course_id} ({entry.course_name})" if entry is not None else course_id


def _join(items: list[str]) -> str:
    items = [i for i in items if i]
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


def _facts(failure: dict) -> dict:
    keyword = failure["keyword"]
    if keyword == "academic_standing_not_satisfied":
        return {
            "standing": " or ".join(failure["standings"]),
            "required_credits": failure.get("required_earned_credits"),
            "completed_hours": failure.get("completed_hours"),
        }
    if keyword == "prerequisite_options_not_satisfied":
        return {"options": "; ".join(failure["options"]), "course_ids": failure["course_ids"]}
    facts = {"course_list": _join([course_label(c) for c in failure["course_ids"]]), "course_ids": failure["course_ids"]}
    if keyword == "prerequisite_not_passed":
        facts["grades"] = ", ".join(g for g in failure.get("recorded_grades", []) if g)
    return facts


def _entry(keyword: str, facts: dict) -> dict:
    vocabulary = REJECTION_KNOWLEDGE["keywords"][keyword]
    fill = {k: ("(not recorded)" if v is None else v) for k, v in facts.items()}
    return {
        "keyword": keyword,
        "requirement": vocabulary["requirement"],
        "label": vocabulary["label"],
        "policy_basis": vocabulary["policy_basis"],
        "plain_reason": vocabulary["plain_reason"].format_map(fill),
        "concise_reason": vocabulary["concise_reason"].format_map(fill),
        "supportive_guidance": vocabulary["supportive_guidance"].format_map(fill),
        "facts": facts,
    }


def detect_rejection_keywords(evidence: dict) -> list[dict]:
    if evidence.get("program_scope", {}).get("status") != "SUPPORTED":
        return []
    detected = [
        _entry(failure["keyword"], _facts(failure))
        for failure in evidence["academic_requirement"].get("confirmed_failures", [])
    ]
    capacity = evidence["checks"]["capacity"]
    if capacity.get("status") == "NOT_SATISFIED":
        detected.append(_entry("no_remaining_capacity", {
            "section_id": evidence.get("section_id"),
            "current_capacity": capacity.get("current_capacity"),
            "maximum_allowed_capacity": capacity.get("maximum_allowed_capacity"),
        }))
    return detected

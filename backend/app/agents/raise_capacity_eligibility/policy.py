"""
The eligibility policy (knowledge_base/eligibility_policy.json), loaded and
checked when the agent is imported, and the recommendation the policy permits
for a piece of verified evidence.

permitted_recommendation() is used ONLY to validate Gemini's reply: a reply
whose recommendation differs is invalid and is retried (decision.py). It is
never stored, shown or used as a recommendation — when every attempt fails,
the run fails.
"""

import json

from . import KNOWLEDGE_DIR

POLICY_PATH = KNOWLEDGE_DIR / "eligibility_policy.json"
RECOMMENDATIONS = ("APPROVE", "REJECT", "MANUAL_REVIEW")


def load_eligibility_policy() -> dict:
    policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    if set(policy.get("recommendations", {})) != set(RECOMMENDATIONS):
        raise ValueError("eligibility_policy.json must define exactly APPROVE, REJECT and MANUAL_REVIEW.")
    if not policy.get("rules") or not all(isinstance(rule, str) and rule.strip() for rule in policy["rules"]):
        raise ValueError("eligibility_policy.json must list its rules as non-empty text.")
    return policy


ELIGIBILITY_POLICY = load_eligibility_policy()


def permitted_recommendation(evidence: dict) -> str:
    """The recommendation the policy rules give for this verified evidence."""
    if evidence["program_scope"]["status"] != "SUPPORTED":
        return "MANUAL_REVIEW"
    requirement = evidence["academic_requirement"]["status"]
    capacity = evidence["checks"]["capacity"]["status"]
    if requirement == "NOT_SATISFIED" or capacity == "NOT_SATISFIED":
        return "REJECT"
    if requirement == "SATISFIED" and capacity == "SATISFIED":
        return "APPROVE"
    return "MANUAL_REVIEW"

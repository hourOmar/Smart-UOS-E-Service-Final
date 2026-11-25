"""
Raise Capacity Rejection Explanation Agent (modelled on
app/agents/incomplete_exam/rejection_agent.py).

Input : the finished, VALIDATED eligibility result (never the database).
Steps : only for REJECT in the supported program -> detect keywords from the
        confirmed failures -> three suggested reasons (formal, concise,
        supportive), each validated; validated templates otherwise.
The administrator chooses, edits and sends the reason; this agent only
suggests. It never raises: a failure here never invalidates the eligibility
evaluation (the result then records it, with no suggestions).
"""

import logging

from app.core.gemini import describe_failure

from .rejection_explanation import generate_rejection_explanations
from .rejection_keywords import detect_rejection_keywords

log = logging.getLogger(__name__)


def explain_rejection(result: dict) -> dict | None:
    """The stored rejection explanation, or None when none applies (not a
    REJECT, or a program outside the supported scope)."""
    evidence = result["evidence"]
    if result.get("recommendation") != "REJECT" or evidence.get("program_scope", {}).get("status") != "SUPPORTED":
        return None
    try:
        keywords = detect_rejection_keywords(evidence)
        return {"request_id": result.get("request_id"),
                **generate_rejection_explanations(result, keywords, evidence.get("student") or {})}
    except Exception as exc:  # noqa: BLE001 - never invalidates the eligibility evaluation
        log.error("Rejection explanation for %s failed: %s", result.get("request_id"), describe_failure(exc))
        return {
            "request_id": result.get("request_id"), "status": "unavailable", "gemini_status": None,
            "gemini_error": "The rejection explanation could not be generated.", "model": None,
            "keywords": [], "suggested_reasons": [], "conflict_note": "", "dropped": [],
        }

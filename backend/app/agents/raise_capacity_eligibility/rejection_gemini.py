"""
Gemini wording step of the Rejection Explanation Agent (modelled on
app/agents/incomplete_exam/rejection_gemini.py: same reply shape, temperature
0.3, three attempts on the same model after a temporary error with waits of
1 s and 2 s, then the configured fallback models). Gemini receives only the
verified failures and facts — never the student's identity — and writes the
three suggestions; Python validates every one (rejection_explanation.py).

Statuses: "ok", "unavailable" (no API key) or "error" (any failure). Never raises.
"""

import json
from typing import Literal

from pydantic import BaseModel

from app.config import get_settings
from app.core.gemini import GeminiUnavailableError, describe_failure, generate_structured_with_model


class _SuggestedReason(BaseModel):
    tone: Literal["formal", "concise", "supportive"]
    text: str
    addresses_keywords: list[str]


class _RejectionSuggestions(BaseModel):
    suggested_reasons: list[_SuggestedReason]
    conflict_note: str  # empty string means none


RULES = """You write SUGGESTED rejection explanations for a University of Sharjah Raise Capacity request that the
eligibility agent has already recommended rejecting. You do NOT decide anything: an administrator reviews,
edits and sends the explanation, and makes the final decision.

Rules:
1. Use ONLY the information in the provided context. Never invent requirements, courses, grades, credit hours,
   capacity figures, dates, policies or procedures.
2. Write exactly 3 suggested_reasons, one each with tone formal, concise and supportive.
3. Every suggestion must explain every keyword in keywords, and list all of their ids (and nothing else) in
   addresses_keywords. Do not mention any requirement that is not one of these keywords.
4. Use only the course IDs, grades and numbers that appear in the context, exactly as given.
5. Address the student in the second person. The student's name and ID are not given: do not invent or use them.
6. Do not say or imply that the request has already been rejected; the administrator has not decided yet.
   Say that the request does not meet, or cannot be approved under, the requirement(s).
7. Do not mention AI, Gemini, an automated system or an agent. Do not promise appeals, exceptions or any
   procedure that is not in the context.
8. If the eligibility explanations contradict the verified keywords or facts, state it briefly in conflict_note;
   otherwise return an empty string.
"""

TEMPERATURE = 0.3
RETRY_DELAYS = (1, 2)


def get_rejection_suggestions(context: dict) -> dict:
    out = {"status": "ok", "error": None, "model": None, "suggested_reasons": [], "conflict_note": ""}
    settings = get_settings()
    if not settings.gemini_api_key:
        out.update(status="unavailable", error="GEMINI_API_KEY is not set.")
        return out
    try:
        parsed, model = generate_structured_with_model(
            json.dumps(context, indent=2, default=str),
            _RejectionSuggestions,
            model=settings.gemini_model,
            fallback_models=settings.gemini_fallback_models,
            system_instruction=RULES,
            temperature=TEMPERATURE,
            retry_delays=RETRY_DELAYS,
            context=f"raise capacity rejection {context.get('request_id')}",
        )
        out["model"] = model
        out["suggested_reasons"] = [r.model_dump() for r in parsed.suggested_reasons]
        out["conflict_note"] = parsed.conflict_note or ""
    except GeminiUnavailableError as exc:
        out.update(status="error", error=str(exc))  # already sanitized
    except Exception as exc:  # noqa: BLE001 - any failure -> validated templates
        out.update(status="error", error=describe_failure(exc))
    return out

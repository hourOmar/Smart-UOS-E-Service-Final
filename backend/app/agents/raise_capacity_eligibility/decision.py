"""
Gemini is the decision-making layer. Python collects and verifies the
evidence; Gemini applies the eligibility policy (knowledge_base/
eligibility_policy.json) to it and returns APPROVE / REJECT / MANUAL_REVIEW
with an explanation per check.

Reply handling:
- The reply must match EligibilityDecision (non-empty reasoning and check
  explanations; one of the three recommendations).
- Its recommendation must be the one the policy permits for the verified
  evidence (policy.permitted_recommendation). A reply that cannot be parsed,
  or that contradicts the policy, is invalid and is asked for again, up to
  MAX_ATTEMPTS times. Every attempt goes through app.core.gemini, with the
  configured fallback models after a temporary 429/503 error.
- When every attempt fails, or Gemini cannot be reached, an error is raised and
  the run is recorded as FAILED. Python never produces, replaces or invents a
  recommendation.

The student's identity (ID and name) is removed from what Gemini receives.
"""

import json

from app.core.gemini import GeminiUnavailableError, fallback_model_names, generate_structured_with_model

from .exceptions import EligibilityReplyInvalidError
from .policy import ELIGIBILITY_POLICY, permitted_recommendation
from .schemas import EligibilityDecision

MAX_ATTEMPTS = 3
_UNPARSABLE = "Gemini's structured response could not be parsed"

SYSTEM_INSTRUCTION = """You are the Academic Eligibility Evaluation Agent for University of Sharjah Raise Capacity requests.

YOUR ROLE
Recommend APPROVE, REJECT or MANUAL_REVIEW for one request by applying the POLICY below to the EVIDENCE below, and explain the recommendation. The recommendation is advisory: the administrator makes the final decision. You do not retrieve data, call any tool, database or website, or access anything beyond what is given below.

THE EVIDENCE IS VERIFIED
Python has already collected and evaluated every fact: the student's transcript against the validated prerequisite knowledge and the approved grade policy, the student's completed credit hours against the knowledge file's academic standing thresholds, and the section's capacity. Every status in the EVIDENCE is authoritative. Do not recompute, re-derive or second-guess any status, number or grade.

HOW TO DECIDE
- Apply POLICY.rules exactly, using academic_requirement.status, checks.capacity.status and program_scope.status. Use no other rule.
- Program scope comes first: if program_scope.status is UNSUPPORTED_PROGRAM or MISSING_PROGRAM, recommend MANUAL_REVIEW and explain that the student's program is outside the supported scope (or is not recorded) and that no program-specific requirement was applied — even when the section is full.
- REJECT requires a CONFIRMED failure: academic_requirement.status NOT_SATISFIED, or checks.capacity.status NOT_SATISFIED. A confirmed failure establishes REJECT even when another check is unresolved.
- APPROVE requires academic_requirement.status SATISFIED and checks.capacity.status SATISFIED.
- Otherwise MANUAL_REVIEW. Missing, unresolved, conflicting or unverifiable evidence is never a failure and never justifies REJECT.

THE REQUIREMENT IS EVALUATED AS A WHOLE
academic_requirement is the course's complete requirement: prerequisite courses and academic standing combined in one nested AND/OR requirement. checks.prerequisite shows its course conditions and checks.completed_hours its academic standing conditions; both share academic_requirement.status. One failed alternative of an OR requirement is NOT a failure when another alternative satisfies the requirement or is unresolved: only academic_requirement.confirmed_failures are confirmed failures. Do not reinterpret requirement_expression, and do not apply any requirement that is not in the EVIDENCE.

ANTI-HALLUCINATION RULES (follow strictly)
- Use ONLY the POLICY and EVIDENCE below. Do not use outside knowledge about the University of Sharjah, its courses or its students.
- Do not invent academic policies, prerequisites, standing thresholds, student records, grades, credit hours or capacity figures.
- Do not assume a value for anything the EVIDENCE marks as missing, null or unresolved: say that it is unavailable.
- Cite the actual course IDs, grades, statuses and numbers given.

OUTPUT
- recommendation: APPROVE, REJECT or MANUAL_REVIEW, exactly as the POLICY rules give.
- reasoning: 3-5 sentences explaining the recommendation and the rule(s) it follows.
- checks.prerequisite: the course conditions and their statuses (course IDs, grades, terms where relevant), or that the course has no prerequisite course, or that it was not evaluated.
- checks.completed_hours: the academic standing conditions — the student's completed credit hours against the required threshold — or that the requirement includes no academic standing condition, or that it was not evaluated.
- checks.capacity: the current, total, additional, maximum and remaining capacity figures and whether a seat remains, or why the capacity could not be confirmed.
Every field must be non-empty. Respond only with the structured JSON object."""


def gemini_evidence(evidence_package: dict) -> dict:
    """The evidence Gemini sees: everything except the student's identity."""
    return {key: value for key, value in evidence_package.items() if key != "student"}


def build_prompt(evidence_package: dict) -> str:
    return (
        "=== POLICY (the approved eligibility policy; do not alter or contradict) ===\n"
        f"{json.dumps(ELIGIBILITY_POLICY, indent=2)}\n\n"
        "=== EVIDENCE (verified facts about this request; the only facts you may use) ===\n"
        f"{json.dumps(gemini_evidence(evidence_package), indent=2, default=str)}\n\n"
        "Using ONLY the POLICY and EVIDENCE above, produce the structured eligibility recommendation."
    )


def reply_problems(decision: EligibilityDecision, permitted: str) -> list[str]:
    problems = []
    if decision.recommendation != permitted:
        problems.append(f"recommendation {decision.recommendation} contradicts the policy for this evidence")
    texts = {"reasoning": decision.reasoning, **decision.checks.model_dump()}
    problems.extend(f"{name} is empty" for name, value in texts.items() if not value.strip())
    return problems


def get_decision(evidence_package: dict) -> dict:
    """The validated decision and the model that produced it. Raises
    GeminiUnavailableError (unreachable) or EligibilityReplyInvalidError
    (every reply invalid); the caller records a failed run."""
    permitted = permitted_recommendation(evidence_package)
    prompt = build_prompt(evidence_package)
    context = f"request {evidence_package.get('request_id')}"
    rejected: list[str] = []
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            parsed, model = generate_structured_with_model(
                prompt, EligibilityDecision, system_instruction=SYSTEM_INSTRUCTION,
                fallback_models=fallback_model_names(), context=context,
            )
        except GeminiUnavailableError as exc:
            if not str(exc).startswith(_UNPARSABLE):
                raise
            rejected.append(f"attempt {attempt}: the reply could not be parsed")
            continue
        problems = reply_problems(parsed, permitted)
        if not problems:
            return {
                "status": "ok",
                "model": model,
                "recommendation": parsed.recommendation,
                "reasoning": parsed.reasoning,
                "checks": parsed.checks.model_dump(),
                "attempts": attempt,
            }
        rejected.append(f"attempt {attempt}: " + "; ".join(problems))
    raise EligibilityReplyInvalidError(
        f"Gemini did not return a valid eligibility recommendation in {MAX_ATTEMPTS} attempts ("
        + " | ".join(rejected) + ")."
    )

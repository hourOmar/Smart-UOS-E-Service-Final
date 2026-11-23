"""
Checks Gemini's per-factor signals against the deterministic evidence before a
result is saved. Python assigns no signal here: it only states which signals the
evidence and the policy's explicit rules allow, and rejects a reply that breaks
them (the run then fails like any other invalid reply; nothing is saved).

Only rules that are already explicit are enforced, with no new thresholds:
- REVIEW exactly when that factor's own evidence is missing, unresolved or
  conflicting, using the same conditions that build_prioritization_evidence
  reports in evidence_quality;
- previous_attempts follows the policy's Previous Attempts rule (never attempted
  -> HIGHER, attempted -> LOWER);
- prerequisite follows the Prerequisite Completion rule (all completed -> HIGHER,
  not completed -> LOWER); with no prerequisite at all the rule does not apply
  (NEUTRAL).
Every other factor's direction (HIGHER, LOWER or NEUTRAL) is Gemini's assessment
under the policy, which compares students and sets no thresholds.

The exact same conditions are given to Gemini in gemini_prompt.py (FACTOR SIGNALS).
"""

from ..schemas.prioritization_evidence import PrioritizationEvidencePackage
from ..schemas.priority_decision import FactorSignals

FACTORS = (
    "graduation",
    "degree_progress",
    "course_requirement",
    "course_availability",
    "previous_attempts",
    "prerequisite",
    "progression",
)

_DIRECTIONS = frozenset({"HIGHER", "LOWER", "NEUTRAL"})
_REVIEW = frozenset({"REVIEW"})


class FactorSignalMismatchError(ValueError):
    """Gemini's factor signals contradict the evidence. The message names the
    factors only (no evidence values), so it is safe to store and show."""

    def __init__(self, factors: list[str]):
        self.factors = factors
        super().__init__(
            "The agent's factor signals did not match the evidence ("
            + ", ".join(factors)
            + "); nothing was saved."
        )


def evidence_problems(evidence: PrioritizationEvidencePackage) -> dict[str, bool]:
    """Per factor: is its own evidence missing, unresolved or conflicting?"""
    graduation = evidence.graduation
    availability = evidence.course_availability
    return {
        "graduation": graduation.expected_graduation_term is None
        or graduation.terms_until_graduation_including_summer is None,
        "degree_progress": evidence.degree_progress.status in ("UNRESOLVED", "ANOMALY"),
        "course_requirement": not evidence.requested_course_requirement.found,
        "course_availability": not availability.found_in_kb or not availability.term_suffix_supported,
        "previous_attempts": False,
        "prerequisite": evidence.prerequisite_completion.status in ("UNRESOLVED", "CONFLICT"),
        "progression": evidence.progression.dependent_courses_missing_from_offerings_kb > 0,
    }


def allowed_signals(evidence: PrioritizationEvidencePackage) -> dict[str, frozenset[str]]:
    """The signals the evidence and the explicit rules allow for each factor."""
    problems = evidence_problems(evidence)
    allowed: dict[str, frozenset[str]] = {
        factor: (_REVIEW if problems[factor] else _DIRECTIONS) for factor in FACTORS
    }

    allowed["previous_attempts"] = frozenset(
        {"LOWER" if evidence.previous_attempts.attempted_before else "HIGHER"}
    )

    if not problems["prerequisite"]:
        prereq = evidence.prerequisite_completion
        if prereq.status == "NOT_SATISFIED":
            allowed["prerequisite"] = frozenset({"LOWER"})
        elif prereq.requirement_expression is None:
            allowed["prerequisite"] = frozenset({"NEUTRAL"})
        else:
            allowed["prerequisite"] = frozenset({"HIGHER"})
    return allowed


def check_factor_signals(signals: FactorSignals, evidence: PrioritizationEvidencePackage) -> None:
    """Raises FactorSignalMismatchError naming every factor whose signal is not allowed."""
    allowed = allowed_signals(evidence)
    wrong = [factor for factor in FACTORS if getattr(signals, factor) not in allowed[factor]]
    if wrong:
        raise FactorSignalMismatchError(wrong)

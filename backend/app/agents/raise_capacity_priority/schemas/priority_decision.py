"""
Pydantic models for Gemini's structured prioritization decision (Phase 6)
and the final agent result. Gemini's raw JSON response is validated
against PriorityDecision — an invalid priority value, missing reasoning,
empty reasoning, or a missing/empty factor explanation all fail Pydantic
validation rather than being silently accepted or guessed at.
"""

from typing import Literal, Optional

from pydantic import BaseModel, Field

Priority = Literal["HIGH", "MEDIUM", "LOW", "MANUAL_REVIEW"]


class FactorExplanations(BaseModel):
    graduation: str = Field(min_length=1)
    degree_progress: str = Field(min_length=1)
    course_requirement: str = Field(min_length=1)
    course_availability: str = Field(min_length=1)
    previous_attempts: str = Field(min_length=1)
    prerequisite: str = Field(min_length=1)
    progression: str = Field(min_length=1)


# Each factor's contribution to the priority assessment (not an eligibility
# pass/fail). HIGHER / LOWER: the factor supports a higher / lower priority under
# the policy; NEUTRAL: it points neither way; REVIEW: that factor's own evidence
# is missing, unresolved or conflicting. Checked against the evidence by
# pipeline/factor_signals.py before anything is saved.
FactorSignal = Literal["HIGHER", "LOWER", "REVIEW", "NEUTRAL"]


class FactorSignals(BaseModel):
    graduation: FactorSignal
    degree_progress: FactorSignal
    course_requirement: FactorSignal
    course_availability: FactorSignal
    previous_attempts: FactorSignal
    prerequisite: FactorSignal
    progression: FactorSignal


class PriorityDecision(BaseModel):
    priority: Priority
    reasoning: str = Field(min_length=1)
    factor_explanations: FactorExplanations
    factor_signals: FactorSignals
    key_evidence: list[str] = Field(default_factory=list)


class FinalAgentResult(BaseModel):
    request_id: str
    priority: Priority
    reasoning: str
    factor_explanations: FactorExplanations
    key_evidence: list[str] = Field(default_factory=list)
    # None only for results saved before factor signals existed (agent 1.0.0).
    factor_signals: Optional[FactorSignals] = None

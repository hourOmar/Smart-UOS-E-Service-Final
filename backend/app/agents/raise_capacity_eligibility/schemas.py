"""Gemini's structured eligibility reply. Every explanation must be non-empty;
a reply that does not validate is retried (decision.py)."""

from typing import Literal

from pydantic import BaseModel, Field

Recommendation = Literal["APPROVE", "REJECT", "MANUAL_REVIEW"]


class CheckExplanations(BaseModel):
    prerequisite: str = Field(min_length=1)
    completed_hours: str = Field(min_length=1)
    capacity: str = Field(min_length=1)


class EligibilityDecision(BaseModel):
    recommendation: Recommendation
    reasoning: str = Field(min_length=1)
    checks: CheckExplanations

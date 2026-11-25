"""
Response handling (decision 6): Python validates only the STRUCTURE of
Gemini's reply and stores a structurally valid recommendation unchanged —
it never overrides or rejects one for academic reasons. Gemini is mocked;
these tests say nothing about the quality of real Gemini reasoning.
"""

import importlib
import json

import pytest
from pydantic import ValidationError

from app.agents.raise_capacity_priority import KNOWLEDGE_DIR, agent
from app.agents.raise_capacity_priority.pipeline.prioritization_policy import load_prioritization_policy
from app.agents.raise_capacity_priority.schemas.priority_decision import (
    FactorExplanations,
    FactorSignals,
    PriorityDecision,
)
from priority_agent.evidence_fixtures import package, takes

FACTORS = ("graduation", "degree_progress", "course_requirement", "course_availability", "previous_attempts",
           "prerequisite", "progression")


def _decision(priority="MEDIUM", **signals):
    values = {f: "NEUTRAL" for f in FACTORS}
    values.update(signals)
    return PriorityDecision(
        priority=priority, reasoning="Because of the evidence.",
        factor_explanations=FactorExplanations(**{f: f"about {f}" for f in FACTORS}),
        factor_signals=FactorSignals(**values), key_evidence=["k"],
    )


def _run(monkeypatch, evidence, decision):
    monkeypatch.setattr(agent, "collect_evidence", lambda rid: evidence)
    monkeypatch.setattr(agent, "get_priority_decision", lambda ev, pol, context="": (decision, "m-1"))
    return agent.prioritize_raise_capacity_request("REQ-1")


@pytest.mark.parametrize("level", ["HIGH", "MEDIUM", "LOW", "MANUAL_REVIEW"])
def test_valid_recommendation_is_stored_unchanged(monkeypatch, level):
    decision = _decision(level, course_availability="LOWER", progression="HIGHER")
    outcome = _run(monkeypatch, package(), decision)
    assert outcome.result.priority == level
    assert outcome.result.reasoning == decision.reasoning
    assert outcome.result.factor_explanations == decision.factor_explanations
    assert outcome.result.factor_signals == decision.factor_signals
    assert outcome.result.key_evidence == ["k"]
    assert outcome.model == "m-1"


def test_signals_that_disagree_with_the_evidence_are_not_rejected(monkeypatch):
    # Prerequisite NOT_SATISFIED and previously attempted, yet Gemini says HIGHER for both
    # and HIGH overall: structurally valid, so it is kept exactly as given.
    evidence = package(transcript=[takes("1501211", "F"), takes("1501215", "D", 202502)])
    assert evidence.prerequisite_completion.status == "NOT_SATISFIED"
    assert evidence.previous_attempts.status == "PREVIOUSLY_ATTEMPTED"
    decision = _decision("HIGH", prerequisite="HIGHER", previous_attempts="HIGHER", graduation="REVIEW")
    outcome = _run(monkeypatch, evidence, decision)
    assert outcome.result.priority == "HIGH"
    assert outcome.result.factor_signals.prerequisite == "HIGHER"
    assert outcome.result.factor_signals.previous_attempts == "HIGHER"
    assert outcome.result.factor_signals.graduation == "REVIEW"


def test_unsupported_program_recommendation_is_not_overridden(monkeypatch):
    # The prompt instructs MANUAL_REVIEW; Python still never replaces Gemini's answer.
    outcome = _run(monkeypatch, package(program_id="1502"), _decision("HIGH"))
    assert outcome.result.priority == "HIGH"


def test_no_academic_enforcement_module_remains():
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("app.agents.raise_capacity_priority.pipeline.factor_signals")


@pytest.mark.parametrize("change", [
    {"priority": "URGENT"},
    {"priority": "high"},
    {"reasoning": ""},
    {"factor_explanations": {f: "x" for f in FACTORS[:-1]}},
    {"factor_explanations": {**{f: "x" for f in FACTORS}, "progression": ""}},
    {"factor_signals": {**{f: "NEUTRAL" for f in FACTORS}, "graduation": "UP"}},
    {"factor_signals": {f: "NEUTRAL" for f in FACTORS[:-1]}},
])
def test_malformed_replies_fail_schema_validation(change):
    reply = {
        "priority": "MEDIUM", "reasoning": "r", "factor_explanations": {f: "x" for f in FACTORS},
        "factor_signals": {f: "NEUTRAL" for f in FACTORS}, "key_evidence": [],
    }
    reply.update(change)
    with pytest.raises(ValidationError):
        PriorityDecision.model_validate(reply)


def test_policy_has_the_eight_agreed_rules_and_four_levels():
    policy = load_prioritization_policy()
    assert [r["name"] for r in policy["raise_capacity_prioritization_rules"]] == [
        "Graduation Proximity", "Degree Progress", "Course Requirement", "Course Availability",
        "Previous Attempts", "Prerequisite Completion", "Academic Progression", "Evidence Quality",
    ]
    assert [r["rule_id"] for r in policy["raise_capacity_prioritization_rules"]] == list(range(1, 9))
    assert policy["priority_levels"] == {
        "HIGH": "Delaying the course presents a significant risk to timely graduation.",
        "MEDIUM": "Delaying the course could affect academic progression but is unlikely to delay graduation.",
        "LOW": "The course can reasonably be delayed without significant academic impact, or verified academic "
               "circumstances justify lower priority.",
        "MANUAL_REVIEW": "Insufficient or conflicting evidence prevents a reliable assessment.",
    }


def test_policy_has_no_scores_weights_or_thresholds():
    text = (KNOWLEDGE_DIR / "prioritization_rules.json").read_text(encoding="utf-8").lower()
    for word in ("score", "weight", "percent", "threshold"):
        assert word not in text
    assert json.loads(text)  # valid JSON

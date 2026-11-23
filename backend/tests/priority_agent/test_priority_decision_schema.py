import pytest
from pydantic import ValidationError

from app.agents.raise_capacity_priority.schemas.priority_decision import (
    FactorExplanations,
    FactorSignals,
    FinalAgentResult,
    PriorityDecision,
)


def _factor_signals(**overrides):
    defaults = dict(
        graduation="HIGHER",
        degree_progress="NEUTRAL",
        course_requirement="HIGHER",
        course_availability="LOWER",
        previous_attempts="HIGHER",
        prerequisite="REVIEW",
        progression="NEUTRAL",
    )
    defaults.update(overrides)
    return defaults


def _factor_explanations(**overrides):
    defaults = dict(
        graduation="g",
        degree_progress="d",
        course_requirement="c",
        course_availability="a",
        previous_attempts="p",
        prerequisite="pr",
        progression="prog",
    )
    defaults.update(overrides)
    return defaults


# 1-4. Each allowed priority accepted
@pytest.mark.parametrize("priority", ["HIGH", "MEDIUM", "LOW", "MANUAL_REVIEW"])
def test_allowed_priority_accepted(priority):
    decision = PriorityDecision(
        priority=priority,
        reasoning="Because of the evidence.",
        factor_explanations=FactorExplanations(**_factor_explanations()),
        factor_signals=FactorSignals(**_factor_signals()),
    )
    assert decision.priority == priority


# 5. Invalid priority rejected
def test_invalid_priority_rejected():
    with pytest.raises(ValidationError):
        PriorityDecision(
            priority="URGENT",
            reasoning="Because of the evidence.",
            factor_explanations=FactorExplanations(**_factor_explanations()),
        )


# 6. Missing reasoning rejected
def test_missing_reasoning_rejected():
    with pytest.raises(ValidationError):
        PriorityDecision(
            priority="HIGH",
            factor_explanations=FactorExplanations(**_factor_explanations()),
        )


def test_empty_reasoning_rejected():
    with pytest.raises(ValidationError):
        PriorityDecision(
            priority="HIGH",
            reasoning="",
            factor_explanations=FactorExplanations(**_factor_explanations()),
        )


# 7. Missing factor explanation rejected
def test_missing_factor_explanation_rejected():
    incomplete = _factor_explanations()
    del incomplete["progression"]
    with pytest.raises(ValidationError):
        FactorExplanations(**incomplete)


def test_empty_factor_explanation_rejected():
    with pytest.raises(ValidationError):
        FactorExplanations(**_factor_explanations(graduation=""))


def test_valid_response_json_parses_via_model_validate_json():
    import json

    payload = {
        "priority": "MEDIUM",
        "reasoning": "Because of the evidence.",
        "factor_explanations": _factor_explanations(),
        "factor_signals": _factor_signals(),
        "key_evidence": ["Remaining credits: 33"],
    }
    decision = PriorityDecision.model_validate_json(json.dumps(payload))
    assert decision.priority == "MEDIUM"
    assert decision.key_evidence == ["Remaining credits: 33"]
    assert decision.factor_signals.course_availability == "LOWER"


# Factor signals: required from Gemini, four values only, all seven factors.
@pytest.mark.parametrize("value", ["HIGHER", "LOWER", "REVIEW", "NEUTRAL"])
def test_each_factor_signal_value_accepted(value):
    assert FactorSignals(**_factor_signals(graduation=value)).graduation == value


@pytest.mark.parametrize("value", ["High", "PASS", "", None, 1])
def test_unknown_factor_signal_rejected(value):
    with pytest.raises(ValidationError):
        FactorSignals(**_factor_signals(graduation=value))


def test_missing_factor_signal_rejected():
    incomplete = _factor_signals()
    del incomplete["progression"]
    with pytest.raises(ValidationError):
        FactorSignals(**incomplete)


def test_decision_without_factor_signals_rejected():
    with pytest.raises(ValidationError):
        PriorityDecision(
            priority="HIGH",
            reasoning="Because of the evidence.",
            factor_explanations=FactorExplanations(**_factor_explanations()),
        )


def test_saved_results_from_before_factor_signals_still_validate():
    old = FinalAgentResult(
        request_id="R-1", priority="LOW", reasoning="r", factor_explanations=FactorExplanations(**_factor_explanations()),
    )
    assert old.factor_signals is None
    assert "factor_signals" not in old.model_dump(mode="json", exclude_none=True)

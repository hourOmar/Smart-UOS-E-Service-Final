"""Per-factor signals: which signals the evidence and the policy's explicit rules
allow, rejection of contradicting replies, how the agent uses the check, and
that the priority decision and policy are untouched. No real Gemini calls."""

import json
from pathlib import Path

import pytest

from app.agents.raise_capacity_priority import agent
from app.agents.raise_capacity_priority.pipeline import gemini_prompt
from app.agents.raise_capacity_priority.pipeline.factor_signals import (
    FACTORS,
    FactorSignalMismatchError,
    allowed_signals,
    check_factor_signals,
)
from app.agents.raise_capacity_priority.schemas.priority_decision import (
    FactorExplanations,
    FactorSignals,
    PriorityDecision,
)
from app.agents.raise_capacity_priority.schemas.uos import PrerequisiteCourseRef
from priority_agent.test_gemini_prompt import _evidence

DIRECTIONS = {"HIGHER", "LOWER", "NEUTRAL"}


def _signals(**overrides):
    # Valid for _evidence(): complete evidence, never attempted, no prerequisite required.
    values = {f: "NEUTRAL" for f in FACTORS}
    values.update(previous_attempts="HIGHER", prerequisite="NEUTRAL")
    values.update(overrides)
    return FactorSignals(**values)


def _with(evidence, section, **changes):
    return evidence.model_copy(update={section: getattr(evidence, section).model_copy(update=changes)})


# -- what the evidence allows -------------------------------------------------------------

def test_complete_evidence_leaves_judgement_factors_to_the_agent():
    allowed = allowed_signals(_evidence())
    for factor in ("graduation", "degree_progress", "course_requirement", "course_availability", "progression"):
        assert allowed[factor] == DIRECTIONS, factor
    assert allowed["previous_attempts"] == {"HIGHER"}  # never attempted (Previous Attempts rule)
    assert allowed["prerequisite"] == {"NEUTRAL"}      # no prerequisite required: rule does not apply


@pytest.mark.parametrize(("factor", "section", "changes"), [
    ("graduation", "graduation", {"expected_graduation_term": None, "terms_until_graduation_including_summer": None}),
    ("graduation", "graduation", {"terms_until_graduation_including_summer": None}),  # conflicting / unsupported terms
    ("degree_progress", "degree_progress", {"status": "UNRESOLVED"}),
    ("degree_progress", "degree_progress", {"status": "ANOMALY"}),  # conflicting credit data
    ("course_requirement", "requested_course_requirement", {"found": False}),
    ("course_availability", "course_availability", {"found_in_kb": False}),
    ("course_availability", "course_availability", {"term_suffix_supported": False}),
    ("prerequisite", "prerequisite_completion", {"status": "UNRESOLVED"}),
    ("prerequisite", "prerequisite_completion", {"status": "CONFLICT", "uos_conflict": True}),
    ("progression", "progression", {"dependent_courses_missing_from_offerings_kb": 2}),
])
def test_missing_or_conflicting_evidence_requires_review(factor, section, changes):
    evidence = _with(_evidence(), section, **changes)
    assert allowed_signals(evidence)[factor] == {"REVIEW"}
    check_factor_signals(_signals(**{factor: "REVIEW"}), evidence)
    for other in DIRECTIONS:
        with pytest.raises(FactorSignalMismatchError) as info:
            check_factor_signals(_signals(**{factor: other}), evidence)
        assert info.value.factors == [factor]


def test_review_is_refused_when_the_evidence_is_complete():
    with pytest.raises(FactorSignalMismatchError) as info:
        check_factor_signals(_signals(graduation="REVIEW", progression="REVIEW"), _evidence())
    assert info.value.factors == ["graduation", "progression"]


def test_previous_attempts_follow_the_policy_rule_only():
    attempted = _with(_evidence(), "previous_attempts", attempted_before=True, number_of_attempts=3,
                      previous_grades=["F", "D", "F"], previous_terms=[202401, 202402, 202501])
    assert allowed_signals(attempted)["previous_attempts"] == {"LOWER"}
    check_factor_signals(_signals(previous_attempts="LOWER"), attempted)
    for wrong in ("HIGHER", "NEUTRAL", "REVIEW"):
        with pytest.raises(FactorSignalMismatchError):
            check_factor_signals(_signals(previous_attempts=wrong), attempted)
    # Never attempted: HIGHER only.
    with pytest.raises(FactorSignalMismatchError):
        check_factor_signals(_signals(previous_attempts="LOWER"), _evidence())


def test_prerequisite_follows_the_completion_rule():
    required = PrerequisiteCourseRef(course_id=1501211, raw_text="1501211")
    satisfied = _with(_evidence(), "prerequisite_completion", status="SATISFIED", requirement_expression=required)
    not_satisfied = _with(_evidence(), "prerequisite_completion", status="NOT_SATISFIED",
                          requirement_expression=required)
    assert allowed_signals(satisfied)["prerequisite"] == {"HIGHER"}
    assert allowed_signals(not_satisfied)["prerequisite"] == {"LOWER"}
    check_factor_signals(_signals(prerequisite="HIGHER"), satisfied)
    check_factor_signals(_signals(prerequisite="LOWER"), not_satisfied)
    with pytest.raises(FactorSignalMismatchError):
        check_factor_signals(_signals(prerequisite="HIGHER"), not_satisfied)
    with pytest.raises(FactorSignalMismatchError):
        check_factor_signals(_signals(prerequisite="HIGHER"), _evidence())  # nothing required


def test_mismatch_message_names_factors_only():
    evidence = _with(_evidence(), "graduation", expected_graduation_term=None,
                     terms_until_graduation_including_summer=None)
    with pytest.raises(FactorSignalMismatchError) as info:
        check_factor_signals(_signals(graduation="HIGHER"), evidence)
    assert str(info.value) == (
        "The agent's factor signals did not match the evidence (graduation); nothing was saved."
    )


# -- the agent ---------------------------------------------------------------------------

def _decision(priority="MEDIUM", **signals):
    return PriorityDecision(
        priority=priority, reasoning="Because of the evidence.",
        factor_explanations=FactorExplanations(**{f: f"about {f}" for f in FACTORS}),
        factor_signals=_signals(**signals), key_evidence=["k"],
    )


@pytest.mark.parametrize("level", ["HIGH", "MEDIUM", "LOW", "MANUAL_REVIEW"])
def test_agent_saves_the_signals_and_never_changes_the_priority(monkeypatch, level):
    monkeypatch.setattr(agent, "collect_evidence", lambda rid: _evidence())
    monkeypatch.setattr(agent, "get_priority_decision", lambda ev, pol, context="":
                        (_decision(level, course_availability="LOWER", progression="HIGHER"), "m-1"))
    outcome = agent.prioritize_raise_capacity_request("REQ-1")
    assert outcome.result.priority == level and outcome.result.reasoning == "Because of the evidence."
    assert outcome.result.factor_signals.course_availability == "LOWER"
    assert outcome.result.factor_signals.progression == "HIGHER"


def test_agent_rejects_contradicting_signals(monkeypatch):
    monkeypatch.setattr(agent, "collect_evidence", lambda rid: _evidence())
    monkeypatch.setattr(agent, "get_priority_decision",
                        lambda ev, pol, context="": (_decision(previous_attempts="LOWER"), "m-1"))
    with pytest.raises(FactorSignalMismatchError):
        agent.prioritize_raise_capacity_request("REQ-1")


# -- prompt and policy unchanged --------------------------------------------------------------

def test_prompt_adds_factor_signals_and_keeps_every_existing_rule():
    text = gemini_prompt.SYSTEM_INSTRUCTION
    start = text.index("FACTOR SIGNALS")
    assert text.index("FACTOR EXPLANATIONS") < start < text.index("OUTPUT\nRespond only")
    # The same REVIEW conditions the code enforces.
    for condition in ("expected_graduation_term is null", "UNRESOLVED or ANOMALY",
                      "requested_course_requirement.found is false", "found_in_kb is false",
                      "term_suffix_supported is false", "UNRESOLVED or CONFLICT",
                      "dependent_courses_missing_from_offerings_kb is greater than 0", "never REVIEW"):
        assert condition in text[start:], condition
    for section in ("ALLOWED DECISIONS", "ANTI-HALLUCINATION RULES", "GRADUATION-DELAY CLAIMS",
                    "DEPENDENT-COURSE INTERPRETATION", "PREVIOUS-ATTEMPT INTERPRETATION", "PRIORITY DECISION",
                    "REASONING STYLE", "FACTOR EXPLANATIONS"):
        assert section in text[:start], section
    assert "do not use MANUAL_REVIEW as an escape from a genuinely close call" in text


def test_prioritization_policy_is_unchanged():
    path = Path(agent.__file__).parent / "knowledge" / "raise_capacity" / "prioritization_rules.json"
    policy = json.loads(path.read_text(encoding="utf-8"))
    assert [r["name"] for r in policy["raise_capacity_prioritization_rules"]] == [
        "Expected Graduation", "Completed Credit Hours", "Prerequisite Completion", "Course Offering Frequency",
        "Impact on Subsequent Courses", "Summer Availability", "Availability in the Next Semester", "Previous Attempts",
    ]
    assert set(policy["priority_levels"]) == {"High", "Medium", "Low"}

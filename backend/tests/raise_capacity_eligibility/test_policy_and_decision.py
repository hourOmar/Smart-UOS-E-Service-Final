"""The eligibility policy, the Gemini prompt and the validated decision (Gemini mocked)."""

import pytest
from pydantic import ValidationError

from app.agents.raise_capacity_eligibility import decision
from app.agents.raise_capacity_eligibility.exceptions import EligibilityReplyInvalidError
from app.agents.raise_capacity_eligibility.policy import ELIGIBILITY_POLICY, permitted_recommendation
from app.agents.raise_capacity_eligibility.schemas import EligibilityDecision
from app.core.gemini import GeminiUnavailableError
from raise_capacity_eligibility.fixtures import decision as reply
from raise_capacity_eligibility.fixtures import evidence, section, take

APPROVABLE = dict(transcript=[take("1501211", "B")])


# -- policy --------------------------------------------------------------------

def test_policy_file_defines_the_three_recommendations_and_rules():
    assert set(ELIGIBILITY_POLICY["recommendations"]) == {"APPROVE", "REJECT", "MANUAL_REVIEW"}
    text = " ".join(ELIGIBILITY_POLICY["rules"])
    assert "Missing evidence alone never justifies rejection." in text
    assert "Program scope takes precedence" in text


@pytest.mark.parametrize("kwargs, expected", [
    (APPROVABLE, "APPROVE"),
    (dict(transcript=[take("1501211", "F")]), "REJECT"),
    (dict(), "REJECT"),
    (dict(transcript=[take("1501211", "W")]), "MANUAL_REVIEW"),
    (dict(course_id="1502232", course_name="Other"), "MANUAL_REVIEW"),
    (dict(**APPROVABLE, sec=section(current=35)), "REJECT"),
    (dict(**APPROVABLE, sec=None, section_problem="No section."), "MANUAL_REVIEW"),
    # A confirmed failure establishes rejection even when capacity is unresolved.
    (dict(transcript=[take("1501211", "F")], sec=None, section_problem="No section."), "REJECT"),
    # Unsupported program scope takes precedence, even over a full section.
    (dict(**APPROVABLE, program="1502", sec=section(current=35)), "MANUAL_REVIEW"),
    (dict(program=None), "MANUAL_REVIEW"),
])
def test_permitted_recommendation(kwargs, expected):
    assert permitted_recommendation(evidence(**kwargs)) == expected


# -- prompt --------------------------------------------------------------------

def test_prompt_keeps_the_student_identity_out_and_includes_policy_and_evidence():
    ev = evidence(**APPROVABLE)
    prompt = decision.build_prompt(ev)
    assert "Distinctname" not in prompt and "U21100001" not in prompt
    assert "=== POLICY" in prompt and "=== EVIDENCE" in prompt
    assert '"academic_requirement"' in prompt and '"REQ-1"' in prompt
    assert ev["student"]["Student_Name"] == "Zaynab Distinctname"  # stored evidence unchanged


def test_system_instruction_rules():
    text = decision.SYSTEM_INSTRUCTION
    for phrase in ("Program scope comes first", "REJECT requires a CONFIRMED failure",
                   "never a failure and never justifies REJECT", "One failed alternative of an OR requirement is NOT a failure",
                   "Do not reinterpret requirement_expression", "Do not invent academic policies",
                   "Every field must be non-empty"):
        assert phrase in text
    assert "UoS website" not in text and "degree page" not in text.lower()


# -- decision with retries -------------------------------------------------------

class FakeGemini:
    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.calls = []

    def __call__(self, prompt, schema, **kwargs):
        self.calls.append(kwargs)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome, "model-a"


@pytest.fixture
def gemini(monkeypatch):
    def install(*outcomes):
        fake = FakeGemini(*outcomes)
        monkeypatch.setattr(decision, "generate_structured_with_model", fake)
        return fake
    return install


def test_valid_reply_on_the_first_attempt(gemini):
    fake = gemini(reply("APPROVE"))
    result = decision.get_decision(evidence(**APPROVABLE))
    assert (result["recommendation"], result["model"], result["attempts"]) == ("APPROVE", "model-a", 1)
    assert fake.calls[0]["system_instruction"] == decision.SYSTEM_INSTRUCTION
    assert "fallback_models" in fake.calls[0]


def test_contradictory_reply_is_retried_and_never_replaced(gemini):
    fake = gemini(reply("APPROVE"), reply("REJECT"))
    result = decision.get_decision(evidence(transcript=[take("1501211", "F")]))
    assert result["recommendation"] == "REJECT" and result["attempts"] == 2
    assert len(fake.calls) == 2


def test_every_reply_contradicting_the_policy_fails_the_run(gemini):
    fake = gemini(reply("APPROVE"), reply("REJECT"), reply("APPROVE"))
    with pytest.raises(EligibilityReplyInvalidError) as raised:
        decision.get_decision(evidence(transcript=[take("1501211", "W")]))  # policy: MANUAL_REVIEW
    assert len(fake.calls) == decision.MAX_ATTEMPTS
    assert "contradicts the policy" in str(raised.value)


def test_unsupported_program_reply_must_be_manual_review(gemini):
    gemini(reply("REJECT"), reply("MANUAL_REVIEW"))
    result = decision.get_decision(evidence(program="1502", sec=section(current=35)))
    assert result["recommendation"] == "MANUAL_REVIEW"


def test_unparsable_reply_is_retried(gemini):
    gemini(GeminiUnavailableError("Gemini's structured response could not be parsed."), reply("APPROVE"))
    assert decision.get_decision(evidence(**APPROVABLE))["attempts"] == 2


def test_gemini_outage_is_raised_at_once_and_never_becomes_a_recommendation(gemini):
    fake = gemini(GeminiUnavailableError("Gemini request failed on every configured model: m: 503"))
    with pytest.raises(GeminiUnavailableError):
        decision.get_decision(evidence(**APPROVABLE))
    assert len(fake.calls) == 1


def test_whitespace_only_explanation_is_invalid(gemini):
    gemini(reply("APPROVE", reasoning="   "), reply("APPROVE"))
    assert decision.get_decision(evidence(**APPROVABLE))["attempts"] == 2


def test_schema_rejects_empty_explanations_and_unknown_recommendations():
    with pytest.raises(ValidationError):
        EligibilityDecision.model_validate({"recommendation": "APPROVE", "reasoning": "",
                                            "checks": {"prerequisite": "a", "completed_hours": "b", "capacity": "c"}})
    with pytest.raises(ValidationError):
        EligibilityDecision.model_validate({"recommendation": "ACCEPT", "reasoning": "r",
                                            "checks": {"prerequisite": "a", "completed_hours": "b", "capacity": "c"}})

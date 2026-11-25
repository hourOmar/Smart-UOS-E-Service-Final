"""Rejection Explanation Agent: keywords from confirmed failures only, three
validated suggestions, template fallback (Gemini mocked)."""

import pytest

from app.agents.raise_capacity_eligibility import rejection_explanation as rx
from app.agents.raise_capacity_eligibility import rejection_gemini
from app.agents.raise_capacity_eligibility.rejection_agent import explain_rejection
from app.agents.raise_capacity_eligibility.rejection_keywords import REJECTION_KNOWLEDGE, detect_rejection_keywords
from raise_capacity_eligibility.fixtures import STUDENT, evidence, section, take


def result(ev, recommendation="REJECT"):
    return {"request_id": "REQ-1", "evidence": ev, "recommendation": recommendation,
            "reasoning": "The requirement is not met.", "checks": {"prerequisite": "p", "completed_hours": "h",
                                                                    "capacity": "c"}}


def kws(ev):
    return [k["keyword"] for k in detect_rejection_keywords(ev)]


# -- keywords --------------------------------------------------------------------

def test_vocabulary_is_exactly_the_approved_keywords():
    assert list(REJECTION_KNOWLEDGE["keywords"]) == [
        "prerequisite_not_completed", "prerequisite_not_passed", "prerequisite_options_not_satisfied",
        "corequisite_not_satisfied", "academic_standing_not_satisfied", "no_remaining_capacity"]


@pytest.mark.parametrize("kwargs, expected", [
    (dict(), ["prerequisite_not_completed"]),
    (dict(transcript=[take("1501211", "F")]), ["prerequisite_not_passed"]),
    (dict(course_id="1501445"), ["prerequisite_options_not_satisfied"]),
    (dict(course_id="1420102"), ["corequisite_not_satisfied"]),
    (dict(course_id="1501344", hours=40), ["academic_standing_not_satisfied"]),
    (dict(transcript=[take("1501211", "A")], sec=section(current=35)), ["no_remaining_capacity"]),
    (dict(sec=section(current=40)), ["prerequisite_not_completed", "no_remaining_capacity"]),
])
def test_keywords_come_from_confirmed_failures(kwargs, expected):
    assert kws(evidence(**kwargs)) == expected


@pytest.mark.parametrize("kwargs", [
    dict(transcript=[take("1501211", "A")]),                                   # satisfied
    dict(transcript=[take("1501211", "W")]),                                   # unresolved
    dict(course_id="1501445", transcript=[take("1501211", "F"), take("1501341", "B")]),  # failed alternative only
    dict(course_id="1501445", transcript=[take("1501211", "I")]),              # alternative unresolved
    dict(transcript=[take("1501211", "A")], sec=None, section_problem="none"),  # capacity unresolved
    dict(program="1502", sec=section(current=40)),                             # unsupported program
])
def test_no_keyword_without_a_confirmed_failure(kwargs):
    assert kws(evidence(**kwargs)) == []


def test_keyword_facts_are_the_verified_values():
    entry = detect_rejection_keywords(evidence(course_id="1501344", hours=40))[0]
    assert entry["facts"] == {"standing": "Junior Standing", "required_credits": 65, "completed_hours": 40}
    assert "65" in entry["plain_reason"] and "40" in entry["plain_reason"]
    passed = detect_rejection_keywords(evidence(transcript=[take("1501211", "F")]))[0]
    assert passed["facts"]["course_list"] == "1501211 (Programming II)" and passed["facts"]["grades"] == "F"


# -- when it runs ------------------------------------------------------------------

@pytest.mark.parametrize("recommendation", ["APPROVE", "MANUAL_REVIEW"])
def test_no_rejection_explanation_unless_reject(recommendation):
    assert explain_rejection(result(evidence(), recommendation)) is None


def test_no_rejection_explanation_for_unsupported_programs():
    assert explain_rejection(result(evidence(program="1502", sec=section(current=40)))) is None


# -- validation ----------------------------------------------------------------------

def _context_and_keywords(**kwargs):
    ev = evidence(**kwargs)
    keywords = detect_rejection_keywords(ev)
    return rx.build_context(result(ev), keywords), keywords


def problems(text, addresses=None, **kwargs):
    context, keywords = _context_and_keywords(**kwargs)
    return rx.reason_problems(text, addresses if addresses is not None else [k["keyword"] for k in keywords],
                              keywords, context, STUDENT)


GOOD = "Your Raise Capacity request for 1501215 does not meet the prerequisite: no passing grade is recorded for 1501211."


def test_a_grounded_reason_is_valid():
    assert problems(GOOD, transcript=[take("1501211", "F")]) == []


@pytest.mark.parametrize("text, expected", [
    ("", "empty"),
    ("x" * 2001, "longer than 2000 characters"),
    ("You need 1501999 first; your prerequisite is not met.", "numbers not in the evidence"),
    ("Your prerequisite 1501211 shows a grade of E.", "grade E is not in the evidence"),
    ("Your prerequisite 1501211 is missing and the section has no seat left.", "mentions requirements that did not fail"),
    ("Your prerequisite 1501211 is missing and you lack Junior Standing.", "mentions requirements that did not fail"),
    ("Zaynab Distinctname, your prerequisite 1501211 is missing.", "identifies the student"),
    ("Student U21100001: your prerequisite 1501211 is missing.", "identifies the student"),
    ("Our AI found that your prerequisite 1501211 is missing.", "refers to AI or an internal agent"),
    ("The eligibility agent found your prerequisite 1501211 missing.", "refers to AI or an internal agent"),
    ("Your request has been rejected because prerequisite 1501211 is missing.", "claims the request has already been rejected"),
])
def test_invalid_reasons_are_dropped(text, expected):
    assert any(expected in p for p in problems(text, transcript=[take("1501211", "F")]))


def test_reason_must_address_exactly_the_detected_keywords():
    assert "does not address exactly the detected keywords" in problems(GOOD, ["prerequisite_not_completed"],
                                                                         transcript=[take("1501211", "F")])


def test_the_request_type_name_is_not_a_capacity_topic():
    assert problems("Your Raise Capacity request does not meet the prerequisite 1501211.",
                    transcript=[take("1501211", "F")]) == []


# -- generation -------------------------------------------------------------------------

def _gemini(monkeypatch, out):
    monkeypatch.setattr(rejection_gemini, "get_rejection_suggestions", lambda context: out)


def _suggestions(texts, keywords):
    return [{"tone": tone, "text": text, "addresses_keywords": keywords} for tone, text in texts.items()]


def test_three_valid_gemini_suggestions(monkeypatch):
    texts = {"formal": GOOD, "concise": "Prerequisite 1501211 not passed.",
             "supportive": "Thank you for your request. A passing grade in prerequisite 1501211 would meet this requirement."}
    _gemini(monkeypatch, {"status": "ok", "error": None, "model": "rej-model",
                          "suggested_reasons": _suggestions(texts, ["prerequisite_not_passed"]), "conflict_note": ""})
    out = explain_rejection(result(evidence(transcript=[take("1501211", "F")])))
    assert out["status"] == "ok" and out["model"] == "rej-model"
    assert [r["tone"] for r in out["suggested_reasons"]] == ["formal", "concise", "supportive"]
    assert {r["source"] for r in out["suggested_reasons"]} == {"gemini"}
    assert [k["keyword"] for k in out["keywords"]] == ["prerequisite_not_passed"]


def test_invalid_suggestion_is_replaced_by_its_template(monkeypatch):
    texts = {"formal": GOOD, "concise": "Your request has been rejected: prerequisite 1501211.",
             "supportive": "A passing grade in prerequisite 1501211 would meet this requirement."}
    _gemini(monkeypatch, {"status": "ok", "error": None, "model": "rej-model",
                          "suggested_reasons": _suggestions(texts, ["prerequisite_not_passed"]), "conflict_note": ""})
    out = explain_rejection(result(evidence(transcript=[take("1501211", "F")])))
    assert out["status"] == "partial_fallback"
    sources = {r["tone"]: r["source"] for r in out["suggested_reasons"]}
    assert sources == {"formal": "gemini", "concise": "template", "supportive": "gemini"}
    assert out["dropped"][0]["tone"] == "concise"


def test_gemini_failure_uses_validated_templates(monkeypatch):
    _gemini(monkeypatch, {"status": "error", "error": "Gemini request failed: 503", "model": None,
                          "suggested_reasons": [], "conflict_note": ""})
    ev = evidence(course_id="1501394", transcript=[take("1501215", "B")], hours=60, sec=section(current=35))
    out = explain_rejection(result(ev))
    assert out["status"] == "fallback" and out["model"] is None
    assert [r["tone"] for r in out["suggested_reasons"]] == ["formal", "concise", "supportive"]
    for reason in out["suggested_reasons"]:
        assert reason["source"] == "template"
        assert rx.reason_problems(reason["text"], reason["addresses_keywords"], out["keywords"],
                                  rx.build_context(result(ev), out["keywords"]), STUDENT) == []
    assert "65" in out["suggested_reasons"][0]["text"] and "Section SEC-1" in out["suggested_reasons"][0]["text"]


@pytest.mark.parametrize("kwargs", [
    dict(), dict(transcript=[take("1501211", "F")]), dict(course_id="1501445"), dict(course_id="1420102"),
    dict(course_id="1501344", hours=40), dict(course_id="1501397", hours=10),
    dict(course_id="1501443", transcript=[take("1501341", "A")]),
    dict(transcript=[take("1501211", "A")], sec=section(current=35)),
    dict(course_id="1501252"), dict(sec=section(current=40)),
])
def test_every_template_passes_its_own_validation(monkeypatch, kwargs):
    _gemini(monkeypatch, {"status": "unavailable", "error": "no key", "model": None, "suggested_reasons": [],
                          "conflict_note": ""})
    out = explain_rejection(result(evidence(**kwargs)))
    assert out["status"] == "fallback"
    assert len(out["suggested_reasons"]) == 3
    assert out["dropped"] == []


def test_a_generation_crash_never_raises(monkeypatch):
    def boom(context):
        raise RuntimeError("unexpected")
    monkeypatch.setattr(rejection_gemini, "get_rejection_suggestions", boom)
    out = explain_rejection(result(evidence()))
    assert out["status"] == "unavailable" and out["suggested_reasons"] == []


def test_gemini_receives_no_student_identity(monkeypatch):
    seen = {}
    monkeypatch.setattr(rejection_gemini, "get_rejection_suggestions", lambda context: seen.setdefault("c", context) and {
        "status": "error", "error": "x", "model": None, "suggested_reasons": [], "conflict_note": ""})
    explain_rejection(result(evidence()))
    text = str(seen["c"])
    assert "Distinctname" not in text and "U21100001" not in text

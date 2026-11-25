"""
Rejection explanation generation and validation (modelled on
app/agents/incomplete_exam/rejection_explanation.py).

Python validates EVERY suggestion — Gemini's and the templates alike:
- non-empty, at most 2000 characters (the decision explanation limit);
- addresses exactly the detected keywords (all of them, nothing else);
- every number is one that appears in the verified context (course IDs,
  credit hours, capacity figures, section, term);
- every grade it names was recorded or is in the approved grade policy;
- it only discusses requirements that failed (topic terms);
- no student name, student ID or e-mail address;
- no reference to AI, Gemini, automation or an agent;
- no claim that the request has already been rejected.

For each tone (formal, concise, supportive) the first valid Gemini suggestion
is kept; otherwise the validated template for that tone is used. A failure here
never affects the eligibility evaluation.
"""

import json
import re

from . import rejection_gemini as gemini_service
from .academic.grade_policy import _FAILING_GRADES, _PASSING_GRADES
from .rejection_keywords import REJECTION_KNOWLEDGE

TONES = ("formal", "concise", "supportive")
MAX_LENGTH = 2000
_NUMBER = re.compile(r"\d+")
_GRADE_TOKEN = r"(A|B\+|B|C\+|C|D\+|D|E|F|WF|FA|W|I|IP)"
_GRADE_MENTIONS = (
    re.compile(r"\bgrades?\s+(?:of\s+|was\s+|is\s+)?\(?" + _GRADE_TOKEN + r"(?![\w+])"),
    re.compile(r"\b(?:an?|the)\s+" + _GRADE_TOKEN + r"\s+grade\b"),
)
_AI = re.compile(
    r"\b(AI|A\.I\.|artificial intelligence|Gemini|automated|automatically|machine learning|language model|"
    r"chatbot|algorithm)\b|\bthe\s+(?:eligibility\s+|rejection\s+)?agent\b", re.IGNORECASE)
_ALREADY_DECIDED = re.compile(
    r"\b(?:has|have|had)\s+been\s+(?:rejected|declined|denied)\b|\b(?:was|were)\s+(?:rejected|declined|denied)\b"
    r"|\bwe\s+(?:have\s+)?(?:rejected|declined|denied)\b|\bis\s+(?:hereby\s+)?(?:rejected|declined|denied)\b"
    r"|\bdecided\s+to\s+(?:reject|decline|deny)\b", re.IGNORECASE)
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
_STUDENT_NUMBER = re.compile(r"\bU\d{6,}\b", re.IGNORECASE)


def build_context(result: dict, keywords: list[dict]) -> dict:
    evidence = result["evidence"]
    return {
        "request_id": result.get("request_id"),
        "course": evidence.get("course"),
        "section_id": evidence.get("section_id"),
        "term": evidence.get("term"),
        "keywords": [
            {k: entry[k] for k in ("keyword", "label", "policy_basis", "plain_reason", "facts")} for entry in keywords
        ],
        "grade_policy": {"passing_grades": sorted(_PASSING_GRADES), "failing_grades": sorted(_FAILING_GRADES)},
        "eligibility_reasoning": result.get("reasoning"),
        "eligibility_check_explanations": result.get("checks"),
    }


def _numbers(value) -> set[str]:
    return set(_NUMBER.findall(json.dumps(value, default=str)))


def _allowed_grades(keywords: list[dict]) -> set[str]:
    recorded = set()
    for entry in keywords:
        recorded |= {g.strip() for g in str(entry["facts"].get("grades", "")).split(",") if g.strip()}
    return recorded | _PASSING_GRADES | _FAILING_GRADES


def _topics_without(text: str, allowed: set[str]) -> list[str]:
    # "Raise Capacity" names the request type, not the capacity requirement.
    lowered = re.sub(r"raise\s+capacity", " ", text.lower())
    return [
        topic for topic, terms in REJECTION_KNOWLEDGE["topic_terms"].items()
        if topic not in allowed and any(term in lowered for term in terms)
    ]


def reason_problems(text: str, addresses: list[str], keywords: list[dict], context: dict, identity: dict) -> list[str]:
    problems: list[str] = []
    if not isinstance(text, str) or not text.strip():
        return ["empty"]
    if len(text) > MAX_LENGTH:
        problems.append("longer than 2000 characters")
    detected = {k["keyword"] for k in keywords}
    if set(addresses) != detected:
        problems.append("does not address exactly the detected keywords")
    unknown_numbers = set(_NUMBER.findall(text)) - _numbers(context)
    if unknown_numbers:
        problems.append(f"numbers not in the evidence: {sorted(unknown_numbers)}")
    allowed_grades = _allowed_grades(keywords)
    for pattern in _GRADE_MENTIONS:
        for grade in pattern.findall(text):
            if grade not in allowed_grades:
                problems.append(f"grade {grade} is not in the evidence")
    allowed_topics = {k["requirement"] for k in keywords}
    if "standing" in allowed_topics:
        allowed_topics.add("prerequisite")  # standing is part of the course's requirement
    for keyword in keywords:
        if keyword["keyword"] == "prerequisite_options_not_satisfied" and "standing" in keyword["facts"].get("options", "").lower():
            allowed_topics.add("standing")
    off_topic = _topics_without(text, allowed_topics)
    if off_topic:
        problems.append(f"mentions requirements that did not fail: {off_topic}")
    lowered = text.lower()
    name = (identity.get("Student_Name") or "").strip()
    student_id = (identity.get("Student_ID") or "").strip()
    if (name and name.lower() in lowered) or (student_id and student_id.lower() in lowered) \
            or _EMAIL.search(text) or _STUDENT_NUMBER.search(text):
        problems.append("identifies the student")
    if _AI.search(text):
        problems.append("refers to AI or an internal agent")
    if _ALREADY_DECIDED.search(text):
        problems.append("claims the request has already been rejected")
    return problems


def template_reasons(result: dict, keywords: list[dict]) -> dict[str, str]:
    evidence = result["evidence"]
    course = evidence.get("course") or {}
    fill = {
        "course_id": course.get("Course_ID", ""),
        "course_name": course.get("Course_Name") or course.get("Course_ID", ""),
        "section_id": evidence.get("section_id", ""),
        "plain_reasons": " ".join(k["plain_reason"] for k in keywords),
        "concise_reasons": "; ".join(k["concise_reason"] for k in keywords),
        "supportive_guidance": " ".join(k["supportive_guidance"] for k in keywords if k["supportive_guidance"]),
    }
    return {tone: " ".join(REJECTION_KNOWLEDGE["templates"][tone].format_map(fill).split()) for tone in TONES}


def generate_rejection_explanations(result: dict, keywords: list[dict], identity: dict) -> dict:
    out = {
        "status": "needs_manual_explanation", "gemini_status": None, "gemini_error": None, "model": None,
        "keywords": keywords, "suggested_reasons": [], "conflict_note": "", "dropped": [],
    }
    if not keywords:
        out["gemini_error"] = "No confirmed failure was found to explain."
        return out

    context = build_context(result, keywords)
    detected = [k["keyword"] for k in keywords]
    raw = gemini_service.get_rejection_suggestions(context)
    out.update(gemini_status=raw["status"], gemini_error=raw["error"], conflict_note=raw.get("conflict_note") or "")

    chosen: dict[str, dict] = {}
    for reason in raw.get("suggested_reasons", []):
        tone = reason.get("tone")
        if tone not in TONES or tone in chosen:
            continue
        problems = reason_problems(reason.get("text", ""), reason.get("addresses_keywords", []), keywords,
                                   context, identity)
        if problems:
            out["dropped"].append({"tone": tone, "problems": problems})
            continue
        chosen[tone] = {"tone": tone, "text": reason["text"].strip(), "addresses_keywords": detected,
                        "source": "gemini"}

    templates = template_reasons(result, keywords)
    for tone in TONES:
        if tone in chosen:
            continue
        text = templates[tone]
        problems = reason_problems(text, detected, keywords, context, identity)
        if problems:
            out["dropped"].append({"tone": tone, "problems": problems, "source": "template"})
            continue
        chosen[tone] = {"tone": tone, "text": text, "addresses_keywords": detected, "source": "template"}

    out["suggested_reasons"] = [chosen[tone] for tone in TONES if tone in chosen]
    sources = {r["source"] for r in out["suggested_reasons"]}
    if not out["suggested_reasons"]:
        out["status"] = "needs_manual_explanation"
    elif sources == {"gemini"} and len(out["suggested_reasons"]) == len(TONES):
        out["status"] = "ok"
    elif "gemini" in sources:
        out["status"] = "partial_fallback"
    else:
        out["status"] = "fallback"
    if "gemini" in sources:
        out["model"] = raw.get("model")
    return out

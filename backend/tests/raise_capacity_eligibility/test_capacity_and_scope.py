"""Section capacity (validated) and program scope."""

import pytest

from app.agents.raise_capacity_eligibility.tools.capacity import evaluate_capacity
from raise_capacity_eligibility.fixtures import evidence, section, take


def test_available_capacity():
    c = evaluate_capacity(section(current=30, total=30, additional=5))
    assert (c["status"], c["satisfied"], c["maximum_allowed_capacity"], c["remaining_raise_capacity"]) == (
        "SATISFIED", True, 35, 5)


def test_full_section():
    c = evaluate_capacity(section(current=35, total=30, additional=5))
    assert (c["status"], c["satisfied"], c["remaining_raise_capacity"]) == ("NOT_SATISFIED", False, 0)


def test_exceeded_section_is_not_satisfied_and_flagged():
    c = evaluate_capacity(section(current=37, total=30, additional=5))
    assert c["status"] == "NOT_SATISFIED" and c["remaining_raise_capacity"] == -2
    assert c["issues"]


def test_no_additional_capacity():
    c = evaluate_capacity(section(current=30, total=30, additional=0))
    assert c["status"] == "NOT_SATISFIED"


@pytest.mark.parametrize("field, value", [
    ("Current_Capacity", None), ("Total_Capacity", -1), ("Additional_Capacity", "5"), ("Current_Capacity", True),
    ("Total_Capacity", 3.5),
])
def test_invalid_capacity_is_unresolved(field, value):
    row = section()
    row[field] = value
    c = evaluate_capacity(row)
    assert (c["status"], c["satisfied"], c["maximum_allowed_capacity"]) == ("UNRESOLVED", None, None)
    assert c["issues"]


def test_missing_section_is_unresolved_not_a_failed_run():
    ev = evidence(sec=None, section_problem="No Section found for Section_ID=SEC-1.")
    c = ev["checks"]["capacity"]
    assert c["status"] == "UNRESOLVED"
    assert c["issues"] == ["No Section found for Section_ID=SEC-1."]


def test_supported_program():
    ev = evidence(transcript=[take("1501211", "A")])
    assert ev["program_scope"]["status"] == "SUPPORTED"
    assert ev["program_scope"]["supported_program_id"] == "1501"


@pytest.mark.parametrize("program, status", [("1502", "UNSUPPORTED_PROGRAM"), ("0302", "UNSUPPORTED_PROGRAM"),
                                             (None, "MISSING_PROGRAM"), ("", "MISSING_PROGRAM")])
def test_unsupported_or_missing_program_applies_no_cs_requirement(program, status):
    ev = evidence(program=program, transcript=[take("1501211", "F")])
    scope = ev["program_scope"]
    assert scope["status"] == status
    assert "MANUAL_REVIEW" in scope["note"]
    assert ev["academic_requirement"]["knowledge_status"] == "NOT_EVALUATED"
    assert ev["academic_requirement"]["confirmed_failures"] == []
    assert ev["checks"]["prerequisite"]["status"] == "NOT_EVALUATED"
    assert ev["checks"]["completed_hours"]["status"] == "NOT_EVALUATED"
    # Capacity is still calculated.
    assert ev["checks"]["capacity"]["status"] == "SATISFIED"


def test_leading_zero_program_id_is_kept():
    assert evidence(program="0302")["program_scope"]["program_id"] == "0302"


def test_evidence_records_the_knowledge_file_versions():
    files = {f["file"] for f in evidence()["knowledge_files"]}
    assert files == {"knowledge_base/course_prerequisites.json", "knowledge_base/grade_policy.json",
                     "knowledge_base/eligibility_policy.json", "knowledge_base/rejection_keywords.json"}

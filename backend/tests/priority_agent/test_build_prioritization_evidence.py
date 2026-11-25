"""
End-to-end evidence package tests (offline): the real pipeline runs against
fake database tables (FakeSupabaseClient) and the agent's real knowledge
files. No database, no network, no Gemini.
"""

import inspect

import pytest

from app.agents.raise_capacity_priority.pipeline import build_prioritization_evidence as pipeline_module
from app.agents.raise_capacity_priority.retrieval.errors import ProgramNotFoundError
from priority_agent.evidence_fixtures import package, takes


def test_complete_package_for_a_cs_student():
    ev = package()
    assert ev.request_context.request_id == "REQ-1"
    assert ev.request_context.course_id == "1501215"
    assert ev.program_scope.status == "SUPPORTED"
    assert ev.evidence_quality.program_in_scope is True
    assert ev.evidence_quality.has_missing_evidence is False
    assert ev.evidence_quality.has_conflicting_evidence is False
    assert ev.evidence_quality.issues == []


# Factor 1 — graduation proximity
def test_graduation_distance_including_and_excluding_summer():
    g = package(expected_graduation=202702).graduation
    assert (g.terms_until_graduation_including_summer, g.terms_until_graduation_excluding_summer) == (4, 3)
    assert g.same_as_expected_graduation_term is False


def test_graduation_in_the_request_term():
    g = package(expected_graduation=202601).graduation
    assert g.same_as_expected_graduation_term is True
    assert g.terms_until_graduation_including_summer == 0


def test_missing_expected_graduation_is_flagged():
    ev = package(expected_graduation=None)
    assert ev.graduation.terms_until_graduation_including_summer is None
    assert ev.evidence_quality.has_missing_evidence is True
    assert "Expected_Graduation_Term is missing" in " ".join(ev.evidence_quality.issues)


def test_expected_graduation_before_request_term_is_conflicting():
    ev = package(expected_graduation=202503)
    assert ev.evidence_quality.has_conflicting_evidence is True


def test_invalid_expected_graduation_suffix_is_flagged():
    ev = package(expected_graduation=202605)
    assert ev.evidence_quality.has_missing_evidence is True
    assert "unsupported semester suffix" in " ".join(ev.evidence_quality.issues)


# Factor 2 — degree progress
def test_degree_progress_from_the_study_plan_total():
    d = package(completed_hours=90).degree_progress
    assert (d.total_required_credits, d.remaining_credits, d.completion_percentage) == (123, 33, 73.2)
    assert d.plan_version == "CS-WEB-2026-10-31"


def test_missing_completed_hours_is_flagged():
    ev = package(completed_hours=None)
    assert ev.degree_progress.status == "UNRESOLVED"
    assert ev.evidence_quality.has_missing_evidence is True


def test_completed_hours_above_total_is_inconsistent():
    ev = package(completed_hours=130)
    assert ev.degree_progress.status == "ANOMALY"
    assert ev.evidence_quality.has_conflicting_evidence is True


# Factor 3 — course requirement
def test_required_course():
    assert package().requested_course_requirement.requirement_type == "REQUIRED"


def test_elective_course():
    ev = package(course_id="1501341", course_name="Web Programming")
    assert ev.requested_course_requirement.requirement_type == "ELECTIVE"


def test_course_not_in_the_study_plan():
    ev = package(course_id="1502232", course_name="Other Course")
    assert ev.requested_course_requirement.requirement_type == "NOT_IN_STUDY_PLAN"
    # Not in the knowledge files either: reported, never guessed.
    assert ev.prerequisite_completion.knowledge_status == "MISSING_FROM_KNOWLEDGE_BASE"
    assert ev.course_availability.found_in_kb is False
    assert ev.evidence_quality.has_missing_evidence is True


def test_missing_study_plan_information():
    ev = package(plan=False)
    assert ev.requested_course_requirement.requirement_type == "UNKNOWN"
    assert ev.degree_progress.status == "UNRESOLVED"
    assert ev.evidence_quality.has_missing_evidence is True


# Factor 4 — availability
def test_once_per_year_course_next_offering_after_graduation():
    ev = package(course_id="1501322", course_name="Ethics", expected_graduation=202602)
    a = ev.course_availability
    assert a.next_known_offering_term == 202701
    assert a.next_known_offering_vs_expected_graduation == "AFTER_EXPECTED_GRADUATION"


def test_unknown_offering_is_flagged_not_treated_as_no():
    ev = package(course_id="1501355", course_name="Computer Architecture",
                 transcript=[takes("1501252", "B")])
    assert ev.course_availability.next_offering_status == "UNDETERMINED"
    assert ev.course_availability.not_offered_semesters == []
    assert ev.evidence_quality.has_missing_evidence is True


# Factor 5 — previous attempts
def test_previous_attempt_before_the_request_term():
    ev = package(transcript=[takes("1501211", "B"), takes("1501215", "F", 202502)])
    assert ev.previous_attempts.status == "PREVIOUSLY_ATTEMPTED"


def test_same_and_future_term_records_are_not_previous_attempts():
    ev = package(transcript=[takes("1501211", "B"), takes("1501215", None, 202601, section="SEC-9"),
                             takes("1501215", "A", 202602)])
    assert ev.previous_attempts.status == "NEVER_ATTEMPTED"
    assert ev.previous_attempts.excluded_same_term_records == 1
    assert ev.previous_attempts.excluded_future_term_records == 1


# Factor 6 — prerequisites
def test_prerequisites_satisfied():
    assert package().prerequisite_completion.status == "SATISFIED"


def test_confirmed_unsatisfied_prerequisite():
    ev = package(transcript=[takes("1501211", "F")])
    assert ev.prerequisite_completion.status == "NOT_SATISFIED"
    assert ev.evidence_quality.has_missing_evidence is False


def test_future_record_cannot_satisfy_a_prerequisite():
    ev = package(transcript=[takes("1501211", "A", 202602)])
    assert ev.prerequisite_completion.status == "NOT_SATISFIED"


def test_unresolved_prerequisite_is_flagged():
    ev = package(transcript=[takes("1501211", "I")])
    assert ev.prerequisite_completion.status == "UNRESOLVED"
    assert ev.evidence_quality.has_missing_evidence is True


def test_standing_prerequisite_uses_completed_hours():
    assert package(course_id="1501344", course_name="2D", completed_hours=64).prerequisite_completion.status == "NOT_SATISFIED"
    assert package(course_id="1501344", course_name="2D", completed_hours=65).prerequisite_completion.status == "SATISFIED"


# Factor 7 — progression
def test_progression_excludes_completed_dependents_and_satisfied_alternatives():
    ev = package(transcript=[takes("1501211", "B"), takes("1501263", "A", 202501), takes("1501214", "B")])
    p = ev.progression
    assert p.total_direct_dependents == 18
    assert p.completed_dependents == 1
    assert p.alternative_route_satisfied_dependents == 3
    assert p.potentially_affected_dependents == 14
    assert p.required_dependents == 11 and p.elective_dependents == 7


# Program scope (decision 7)
def test_unsupported_program_is_identified_and_cs_knowledge_not_applied():
    ev = package(program_id="1502")
    assert ev.program_scope.status == "UNSUPPORTED_PROGRAM"
    assert ev.program_scope.program_name == "Bachelor of Science in Computer Engineering"
    assert ev.evidence_quality.program_in_scope is False
    assert ev.prerequisite_completion.knowledge_status == "NOT_EVALUATED"
    assert ev.course_availability.next_offering_status == "NOT_AVAILABLE"
    assert ev.progression.evaluated is False
    assert any("outside the supported scope" in issue for issue in ev.evidence_quality.issues)
    # Database-only factors still use the student's own program.
    assert ev.degree_progress.total_required_credits == 132


def test_missing_program_is_identified():
    ev = package(program_id=None)
    assert ev.program_scope.status == "MISSING_PROGRAM"
    assert ev.evidence_quality.has_missing_evidence is True
    assert ev.requested_course_requirement.requirement_type == "UNKNOWN"


def test_dangling_program_id_is_fatal():
    with pytest.raises(ProgramNotFoundError):
        package(program_id="9999")


# Identifiers
def test_leading_zero_course_and_program_ids():
    ev = package(course_id="0202213", course_name="Critical Reading and Writing",
                 transcript=[takes("0202213", "D", 202502)])
    assert ev.request_context.course_id == "0202213"
    assert ev.requested_course_requirement.requirement_type == "REQUIRED"
    assert ev.prerequisite_completion.knowledge_status == "NO_PREREQUISITES"
    assert ev.course_availability.found_in_kb is True
    assert ev.previous_attempts.status == "PREVIOUSLY_ATTEMPTED"
    other = package(program_id="0302")
    assert other.program_scope.program_id == "0302"
    assert other.program_scope.status == "UNSUPPORTED_PROGRAM"


# Student-provided reason (decision 10)
def test_reason_is_carried_verbatim_and_changes_no_evidence():
    claim = "I graduate this semester and this is my last course."
    with_claim = package(reason=claim, expected_graduation=202702)
    without = package(reason=None, expected_graduation=202702)
    assert with_claim.request_context.reason == claim
    assert with_claim.model_dump(exclude={"request_context"}) == without.model_dump(exclude={"request_context"})


# Personal data and decisions never appear in the evidence
def test_student_email_and_auth_id_not_present():
    text = package().model_dump_json().lower()
    assert "email" not in text
    assert "auth_user_id" not in text


def test_no_priority_field_exists():
    assert "priority" not in package().model_dump_json().lower()


def test_no_high_medium_low_result_exists():
    text = package().model_dump_json()
    for level in ('"HIGH"', '"MEDIUM"', '"LOW"', '"MANUAL_REVIEW"'):
        assert level not in text


def test_pipeline_uses_no_web_retrieval():
    source = inspect.getsource(pipeline_module)
    assert "uos" not in source.lower()
    assert "requests" not in source

"""
Assembles the final PrioritizationEvidencePackage for one Raise Capacity
request. This is an evidence-BUILDING layer, not a decision layer — nothing
here calls Gemini, computes a score, or produces HIGH/MEDIUM/LOW.

- assemble_prioritization_evidence(...) is a pure function of data already
  retrieved and calculated. No I/O, easy to unit test.
- build_prioritization_evidence(request_id, client) is the orchestrator: it
  reads the database (read-only), loads nothing from the web, runs the
  deterministic calculations and passes the results to the assembler.

Sources: the database (Request, Raise_Capacity, Student, Program, Course,
Section, Takes, Program_Study_Plan_Course, Program_Study_Plan_Total) and the
agent's own knowledge files (course_prerequisites.json,
course_offerings.json, grade_policy.json). The prioritization policy is NOT
embedded here; pipeline/prioritization_policy.py loads it separately.

Error handling: a request that cannot be identified at all (unknown
Request_ID, wrong request type, missing Raise_Capacity/Student/Course/
Section rows, or a dangling Program_ID) is FATAL — the typed retrieval
exceptions propagate unmodified. Legitimately missing, unresolved or
conflicting academic evidence is NOT fatal: the package still builds, with
the problem stated in evidence_quality for Gemini to weigh.
"""

from typing import Any, Optional

from ..deterministic.evidence import build_deterministic_evidence, related_course_ids
from ..deterministic.program_scope import ProgramScopeEvidence, build_program_scope
from ..deterministic.term import calculate_terms_until_graduation, parse_term
from ..retrieval.evidence import get_supabase_evidence
from ..retrieval.prerequisite_history import get_takes_for_courses
from ..schemas.deterministic import DeterministicEvidence
from ..schemas.evidence import SupabaseEvidence
from ..schemas.prioritization_evidence import (
    EvidenceQualitySummary,
    GraduationEvidence,
    PrioritizationEvidencePackage,
    RequestContext,
)


def build_prioritization_evidence(request_id: str, client: Any) -> PrioritizationEvidencePackage:
    supabase_evidence = get_supabase_evidence(request_id, client=client)
    scope = _program_scope(supabase_evidence)
    transcript = []
    if scope.status == "SUPPORTED":
        transcript = get_takes_for_courses(
            client,
            supabase_evidence.student.student_id,
            related_course_ids(supabase_evidence.raise_capacity.course_id),
        )
    deterministic_evidence = build_deterministic_evidence(supabase_evidence, transcript, scope)
    return assemble_prioritization_evidence(supabase_evidence, scope, deterministic_evidence)


def _program_scope(supabase_evidence: SupabaseEvidence) -> ProgramScopeEvidence:
    program = supabase_evidence.program
    return build_program_scope(
        supabase_evidence.student.program_id, program.program_name if program is not None else None
    )


def assemble_prioritization_evidence(
    supabase_evidence: SupabaseEvidence,
    scope: ProgramScopeEvidence,
    deterministic_evidence: DeterministicEvidence,
) -> PrioritizationEvidencePackage:
    graduation = _build_graduation_evidence(supabase_evidence)
    return PrioritizationEvidencePackage(
        request_context=_build_request_context(supabase_evidence),
        program_scope=scope,
        graduation=graduation,
        degree_progress=deterministic_evidence.remaining_credits,
        requested_course_requirement=deterministic_evidence.course_requirement,
        course_availability=deterministic_evidence.requested_course_offering,
        previous_attempts=deterministic_evidence.previous_attempt_summary,
        prerequisite_completion=deterministic_evidence.prerequisite_completion,
        progression=deterministic_evidence.progression_evidence,
        evidence_quality=_build_evidence_quality(scope, graduation, deterministic_evidence),
    )


def _build_request_context(supabase_evidence: SupabaseEvidence) -> RequestContext:
    return RequestContext(
        request_id=supabase_evidence.request.request_id,
        student_id=supabase_evidence.student.student_id,
        request_term=supabase_evidence.raise_capacity.term,
        course_id=supabase_evidence.raise_capacity.course_id,
        course_name=supabase_evidence.course.course_name,
        section_id=supabase_evidence.raise_capacity.section_id,
        reason=supabase_evidence.raise_capacity.reason,
    )


def _build_graduation_evidence(supabase_evidence: SupabaseEvidence) -> GraduationEvidence:
    request_term = supabase_evidence.raise_capacity.term
    expected = supabase_evidence.student.expected_graduation_term
    same_as_expected = request_term == expected if expected is not None else None

    including_summer: Optional[int] = None
    excluding_summer: Optional[int] = None
    if expected is not None:
        distances = calculate_terms_until_graduation(request_term, expected)
        if distances is not None:
            including_summer, excluding_summer = distances

    return GraduationEvidence(
        request_term=request_term,
        expected_graduation_term=expected,
        same_as_expected_graduation_term=same_as_expected,
        terms_until_graduation_including_summer=including_summer,
        terms_until_graduation_excluding_summer=excluding_summer,
    )


def _build_evidence_quality(
    scope: ProgramScopeEvidence,
    graduation: GraduationEvidence,
    deterministic_evidence: DeterministicEvidence,
) -> EvidenceQualitySummary:
    issues: list[str] = []
    has_missing = False
    has_conflicting = False

    if scope.status != "SUPPORTED":
        if scope.status == "MISSING_PROGRAM":
            has_missing = True
        issues.append(scope.note)

    # Factor 1 — graduation proximity
    if graduation.expected_graduation_term is None:
        has_missing = True
        issues.append("Student's Expected_Graduation_Term is missing.")
    elif graduation.terms_until_graduation_including_summer is None:
        if parse_term(graduation.request_term) is None:
            has_missing = True
            issues.append(
                "Could not calculate terms until graduation: request Term "
                f"{graduation.request_term} has an unsupported semester suffix."
            )
        elif parse_term(graduation.expected_graduation_term) is None:
            has_missing = True
            issues.append(
                "Could not calculate terms until graduation: "
                f"Expected_Graduation_Term {graduation.expected_graduation_term} "
                "has an unsupported semester suffix."
            )
        else:
            has_conflicting = True
            issues.append(
                f"Expected_Graduation_Term ({graduation.expected_graduation_term}) "
                f"is chronologically before the request term "
                f"({graduation.request_term}); terms-until-graduation could not "
                "be calculated."
            )

    # Factor 2 — degree progress
    remaining = deterministic_evidence.remaining_credits
    if remaining.status == "UNRESOLVED":
        has_missing = True
        issues.append(f"Degree progress could not be calculated: {remaining.note}")
    elif remaining.status == "ANOMALY":
        has_conflicting = True
        issues.append(f"Degree progress is inconsistent: {remaining.note}")

    # Factor 3 — course requirement
    requirement = deterministic_evidence.course_requirement
    if requirement.requirement_type == "UNKNOWN":
        has_missing = True
        issues.append(f"The requested course's requirement type is unknown: {requirement.note}")

    # Factor 4 — course availability (evaluated programs only)
    offering = deterministic_evidence.requested_course_offering
    if scope.status == "SUPPORTED":
        if not offering.found_in_kb or not offering.term_suffix_supported:
            has_missing = True
            issues.append(f"Course availability could not be calculated: {offering.notes[0]}")
        elif offering.next_offering_status != "KNOWN":
            has_missing = True
            issues.append(
                "The next usual offering of the requested course cannot be determined from the offering "
                f"information ({offering.next_offering_status})."
            )
        elif offering.earlier_unconfirmed_offering_terms:
            issues.append(
                "Offering information is UNKNOWN for term(s) "
                f"{offering.earlier_unconfirmed_offering_terms} before the next known usual offering "
                f"({offering.next_known_offering_term})."
            )

    # Factor 5 — previous attempts
    attempts = deterministic_evidence.previous_attempt_summary
    if attempts.status == "UNKNOWN":
        has_missing = True
        issues.append(
            "Whether the requested course was attempted before cannot be determined: "
            f"{attempts.unknown_term_records} transcript record(s) have a term whose order cannot be determined."
        )

    # Factor 6 — prerequisite completion (evaluated programs only)
    prereq = deterministic_evidence.prerequisite_completion
    if prereq.knowledge_status != "NOT_EVALUATED":
        if prereq.status == "UNRESOLVED":
            has_missing = True
            issues.append(f"Prerequisite completion could not be determined: {prereq.reason}")
        elif prereq.status == "CONFLICT":
            has_conflicting = True
            issues.append(f"Prerequisite information conflicts: {prereq.reason}")

    # Factor 7 — academic progression (evaluated programs only)
    progression = deterministic_evidence.progression_evidence
    if progression.evaluated and progression.unresolved_dependents:
        issues.append(
            f"For {progression.unresolved_dependents} dependent course(s) it cannot be determined whether "
            "delaying the requested course would affect them."
        )

    return EvidenceQualitySummary(
        program_in_scope=scope.status == "SUPPORTED",
        has_missing_evidence=has_missing,
        has_conflicting_evidence=has_conflicting,
        issues=issues,
    )

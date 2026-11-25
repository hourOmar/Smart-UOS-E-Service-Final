"""
Aggregates every deterministic calculation into one DeterministicEvidence
object. No I/O happens here: it is a pure function of data already
retrieved (the database evidence, including the current study plan, and
the student's Takes records for the related courses).

Factors 2, 3 and 5 use only database data and are calculated for every
student. Factors 4, 6 and 7 use the program-specific knowledge files and are
calculated only for a student in the supported program; otherwise they are
reported as not evaluated (approved decision 7).
"""

from ..deterministic.course_offerings import (
    build_requested_course_offering_evidence,
    not_evaluated_offering_evidence,
)
from ..deterministic.course_requirement import build_course_requirement_evidence
from ..deterministic.prerequisite_evaluator import (
    evaluate_prerequisite_completion,
    not_evaluated_prerequisite_evidence,
)
from ..deterministic.prerequisite_knowledge import (
    PREREQUISITE_KNOWLEDGE,
    PrerequisiteKnowledge,
    referenced_course_ids,
)
from ..deterministic.previous_attempts import build_previous_attempt_summary
from ..deterministic.program_scope import ProgramScopeEvidence
from ..deterministic.progression import build_progression_evidence, not_evaluated_progression_evidence
from ..deterministic.remaining_credits import calculate_remaining_credits
from ..schemas.academic_history import TakesRecord
from ..schemas.deterministic import DeterministicEvidence
from ..schemas.evidence import SupabaseEvidence


def related_course_ids(course_id: str, knowledge: PrerequisiteKnowledge = PREREQUISITE_KNOWLEDGE) -> set[str]:
    """Every course whose Takes records the knowledge-file factors need: the
    requested course, its prerequisite courses, its direct dependents and
    the courses in those dependents' requirements."""
    ids = {course_id}
    entry = knowledge.entry(course_id)
    if entry is not None:
        ids |= referenced_course_ids(entry.requirement)
    for dependent_id in knowledge.direct_dependents(course_id):
        ids.add(dependent_id)
        ids |= referenced_course_ids(knowledge.entry(dependent_id).requirement)
    return ids


def build_deterministic_evidence(
    supabase_evidence: SupabaseEvidence,
    transcript: list[TakesRecord],
    scope: ProgramScopeEvidence,
    knowledge: PrerequisiteKnowledge = PREREQUISITE_KNOWLEDGE,
) -> DeterministicEvidence:
    student = supabase_evidence.student
    request = supabase_evidence.raise_capacity
    study_plan = supabase_evidence.study_plan

    remaining_credits = calculate_remaining_credits(student.completed_hours, study_plan)
    course_requirement = build_course_requirement_evidence(
        request.course_id, supabase_evidence.course.course_name, study_plan
    )
    previous_attempt_summary = build_previous_attempt_summary(supabase_evidence.previous_attempts)

    if scope.status == "SUPPORTED":
        prerequisite_completion = evaluate_prerequisite_completion(
            request.course_id, knowledge, transcript, request.term, student.completed_hours
        )
        requested_course_offering = build_requested_course_offering_evidence(
            request.course_id, request.term, student.expected_graduation_term
        )
        progression_evidence = build_progression_evidence(
            request.course_id, knowledge, transcript, request.term, student.completed_hours, study_plan
        )
    else:
        reason = scope.note or "The student's program is outside the supported scope."
        prerequisite_completion = not_evaluated_prerequisite_evidence(request.course_id, reason)
        requested_course_offering = not_evaluated_offering_evidence(request.course_id, reason)
        progression_evidence = not_evaluated_progression_evidence(request.course_id, reason)

    return DeterministicEvidence(
        remaining_credits=remaining_credits,
        course_requirement=course_requirement,
        prerequisite_completion=prerequisite_completion,
        requested_course_offering=requested_course_offering,
        previous_attempt_summary=previous_attempt_summary,
        progression_evidence=progression_evidence,
    )

"""
Aggregated database evidence retrieval for a Raise Capacity request.

get_supabase_evidence(request_id) performs the fixed retrieval flow (Request,
Raise_Capacity, Student, Program, Course, Section, Takes for the requested
course, and the student's current study plan with its total credit hours) and
returns one structured SupabaseEvidence object. This is NOT the final evidence
package — the knowledge-file evaluations and deterministic calculations are
added later; the prioritization policy and Gemini's decision are separate.
"""

from typing import Any

from ..retrieval.academic_history import get_previous_attempts
from ..retrieval.course import get_course
from ..retrieval.program import get_program
from ..retrieval.raise_capacity import get_raise_capacity_details
from ..retrieval.request import get_request
from ..retrieval.section import get_section
from ..retrieval.student import get_student
from ..retrieval.study_plan import get_study_plan
from ..schemas.evidence import SupabaseEvidence


def get_supabase_evidence(request_id: str, client: Any) -> SupabaseEvidence:
    # Ported: `client` is required (the backend passes a read-only database
    # client, see ../db_client.py); there is no Supabase client default.
    request = get_request(client, request_id)
    raise_capacity = get_raise_capacity_details(client, request_id)
    student = get_student(client, request.student_id)
    program = get_program(client, student.program_id, student.program_name)
    course = get_course(client, raise_capacity.course_id)
    section = get_section(
        client,
        raise_capacity.section_id,
        raise_capacity.course_id,
        raise_capacity.term,
    )
    previous_attempts = get_previous_attempts(
        client,
        student_id=student.student_id,
        course_id=raise_capacity.course_id,
        current_term=raise_capacity.term,
    )

    study_plan = get_study_plan(client, student.program_id, student.program_name)
    return SupabaseEvidence(
        request=request,
        raise_capacity=raise_capacity,
        student=student,
        program=program,
        course=course,
        section=section,
        previous_attempts=previous_attempts,
        study_plan=study_plan,
    )

"""Fixed evaluation workflow (Gemini never chooses tools and has no tool access):

    request -> student -> transcript -> course -> section        (ONE read-only transaction)
    -> program scope
    -> complete requirement: prerequisites + academic standing   (knowledge_base/course_prerequisites.json)
    -> section capacity                                          (arithmetic, validated)
    -> evidence package -> Gemini decision (validated against the policy; retried)
    -> after a validated REJECT only: rejection explanation

Nothing is read from the web. A technical failure raises (the run is recorded
as failed); Python never produces a recommendation.
"""

import hashlib
from datetime import datetime, timezone

from app.core.database import read_only

from . import AGENT_VERSION, KNOWLEDGE_DIR
from .academic.program_scope import build_program_scope
from .academic.records import TakesRecord
from .checks import build_academic_checks
from .decision import get_decision
from .exceptions import CourseNotFoundError, SectionCourseMismatchError, SectionNotFoundError
from .rejection_agent import explain_rejection
from .tools.capacity import evaluate_capacity, get_section_capacity
from .tools.course import fetch_course
from .tools.request import get_raise_capacity_request
from .tools.student import get_student_academic_info, get_student_transcript

KNOWLEDGE_FILES = ("course_prerequisites.json", "grade_policy.json", "eligibility_policy.json",
                   "rejection_keywords.json")


def knowledge_file_fingerprints() -> list[dict]:
    return [
        {"file": f"knowledge_base/{name}", "sha256": hashlib.sha256((KNOWLEDGE_DIR / name).read_bytes()).hexdigest()}
        for name in KNOWLEDGE_FILES
    ]


def _records(transcript: list[dict]) -> list[TakesRecord]:
    return [
        TakesRecord(course_id=str(row["Course_ID"]), grade=row["Grade"], section_id=str(row["Section_ID"]),
                    term=row["Term"])
        for row in transcript
    ]


def build_evidence_package(request_id: str) -> dict:
    """Collects and computes all deterministic evidence. Does NOT decide."""
    with read_only() as conn:
        request_data = get_raise_capacity_request(conn, request_id)
        student_id = request_data["Student_ID"]
        course_id = str(request_data["Course_ID"])
        section_id = request_data["Section_ID"]
        term = request_data["Term"]

        student = get_student_academic_info(conn, student_id)
        transcript = get_student_transcript(conn, student_id)

        course = fetch_course(conn, course_id)
        if course is None:
            raise CourseNotFoundError(f"No Course found for Course_ID={course_id}.")

        section, section_problem = None, None
        try:
            section = get_section_capacity(conn, section_id, course_id, term)
        except (SectionNotFoundError, SectionCourseMismatchError) as exc:
            section_problem = str(exc)

    return assemble_evidence_package(request_id, request_data, student, transcript, course, section, section_problem)


def assemble_evidence_package(
    request_id: str, request_data: dict, student: dict, transcript: list[dict], course: dict,
    section: dict | None, section_problem: str | None = None,
) -> dict:
    """Pure: the evidence package from rows already read (no I/O)."""
    course_id = str(request_data["Course_ID"])
    section_id = request_data["Section_ID"]
    term = request_data["Term"]
    scope = build_program_scope(student.get("Program_ID"), student.get("Program_Name"))
    requirement, prerequisite, standing = build_academic_checks(
        course_id, _records(transcript), term, student.get("Completed_Hours"), scope,
    )
    capacity = evaluate_capacity(section, section_problem)

    return {
        "request_id": request_id,
        # Stored with the result for staff; removed before anything is sent to Gemini.
        "student": {"Student_ID": student["Student_ID"], "Student_Name": student["Student_Name"]},
        "course": {"Course_ID": str(course["Course_ID"]), "Course_Name": course["Course_Name"]},
        "section_id": section_id,
        "term": term,
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "program_scope": scope,
        "academic_requirement": requirement,
        "checks": {"prerequisite": prerequisite, "completed_hours": standing, "capacity": capacity},
        "knowledge_files": knowledge_file_fingerprints(),
    }


def evaluate_raise_capacity_request(request_id: str) -> dict:
    evidence_package = build_evidence_package(request_id)
    decision = get_decision(evidence_package)  # raises on a technical failure: the run fails
    evidence_package["gemini_attempts"] = decision["attempts"]
    result = {
        "request_id": request_id,
        "evidence": evidence_package,
        "recommendation": decision["recommendation"],
        "reasoning": decision["reasoning"],
        "checks": decision["checks"],
        "gemini_status": "ok",
        "gemini_error": None,
        "model": decision["model"],
        "agent_version": AGENT_VERSION,
    }
    rejection = explain_rejection(result)  # None unless a validated REJECT; never raises
    result["rejection_explanation"] = rejection
    result["rejection_model"] = rejection.get("model") if rejection else None
    return result

"""
Program scope (approved decision 7). The agent's academic knowledge files
(course_prerequisites.json, course_offerings.json) cover one program, named
by their own program_id. A student outside that program — or with no
Program_ID — is identified in the evidence, and the knowledge-file factors
(availability, prerequisites, progression) are NOT evaluated for them.
Python assigns no priority here: Gemini is instructed to return
MANUAL_REVIEW and explain the scope.
"""

from typing import Literal, Optional

from pydantic import BaseModel

from ..deterministic.course_offerings import OFFERINGS_PROGRAM_ID
from ..deterministic.prerequisite_knowledge import PREREQUISITE_KNOWLEDGE

if PREREQUISITE_KNOWLEDGE.program_id != OFFERINGS_PROGRAM_ID:
    raise ValueError(
        "Knowledge files disagree on the supported program: course_prerequisites.json "
        f"{PREREQUISITE_KNOWLEDGE.program_id!r}, course_offerings.json {OFFERINGS_PROGRAM_ID!r}."
    )

SUPPORTED_PROGRAM_ID = PREREQUISITE_KNOWLEDGE.program_id


class ProgramScopeEvidence(BaseModel):
    program_id: Optional[str]
    program_name: Optional[str]
    supported_program_id: str
    status: Literal["SUPPORTED", "UNSUPPORTED_PROGRAM", "MISSING_PROGRAM"]
    note: Optional[str]


def build_program_scope(program_id: Optional[str], program_name: Optional[str]) -> ProgramScopeEvidence:
    if program_id is None:
        status = "MISSING_PROGRAM"
        note = ("Student.Program_ID is missing; the program-specific knowledge files were not applied. "
                "The recommendation must be MANUAL_REVIEW.")
    elif program_id != SUPPORTED_PROGRAM_ID:
        status = "UNSUPPORTED_PROGRAM"
        note = (f"Program {program_id} is outside the supported scope (program {SUPPORTED_PROGRAM_ID}); the "
                "program-specific knowledge files were not applied. The recommendation must be MANUAL_REVIEW.")
    else:
        status, note = "SUPPORTED", None
    return ProgramScopeEvidence(
        program_id=program_id, program_name=program_name, supported_program_id=SUPPORTED_PROGRAM_ID,
        status=status, note=note,
    )

"""
Program scope. The validated prerequisite knowledge covers one program, named
by the file's own program_id (Computer Science, 1501). A student in another
program, or with no Program_ID, is identified here and no program-specific
academic requirement is applied to them; the policy then requires
MANUAL_REVIEW (Gemini recommends it; Python never assigns it).
"""

from typing import Optional

from .prerequisite_knowledge import PREREQUISITE_KNOWLEDGE

SUPPORTED_PROGRAM_ID = PREREQUISITE_KNOWLEDGE.program_id


def build_program_scope(program_id: Optional[str], program_name: Optional[str]) -> dict:
    program_id = str(program_id).strip() if program_id is not None else None
    if not program_id:
        status = "MISSING_PROGRAM"
        note = ("The student's program is not recorded, so the program-specific prerequisite and academic standing "
                "requirements cannot be applied. The recommendation must be MANUAL_REVIEW.")
        program_id = None
    elif program_id != SUPPORTED_PROGRAM_ID:
        status = "UNSUPPORTED_PROGRAM"
        note = (f"Program {program_id} is outside the supported scope (program {SUPPORTED_PROGRAM_ID}); its "
                "prerequisite and academic standing requirements are not available, so none were applied. "
                "The recommendation must be MANUAL_REVIEW.")
    else:
        status, note = "SUPPORTED", None
    return {
        "program_id": program_id,
        "program_name": program_name,
        "supported_program_id": SUPPORTED_PROGRAM_ID,
        "status": status,
        "note": note,
    }

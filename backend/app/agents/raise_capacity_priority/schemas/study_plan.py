"""
The student's program study plan as read from the database
(Program_Study_Plan_Course for the current plan version, and
Program_Study_Plan_Total for that version's total credit hours).
"""

from typing import Literal, Optional

from pydantic import BaseModel

from ..schemas.deterministic import RequirementType


class StudyPlanInfo(BaseModel):
    program_id: Optional[str]
    status: Literal["OK", "NO_PROGRAM", "NO_CURRENT_PLAN", "MULTIPLE_CURRENT_PLANS"]
    plan_version: Optional[str]
    # Course_ID -> REQUIRED / ELECTIVE (UNKNOWN for an unexpected stored value).
    requirement_types: dict[str, Literal["REQUIRED", "ELECTIVE", "UNKNOWN"]]
    total_required_credits: Optional[int]
    total_status: Literal["OK", "NOT_FOUND", "MULTIPLE", "INVALID", "NOT_APPLICABLE"]
    notes: list[str]

    def requirement_type(self, course_id: str) -> RequirementType:
        if self.status != "OK":
            return "UNKNOWN"
        return self.requirement_types.get(course_id, "NOT_IN_STUDY_PLAN")

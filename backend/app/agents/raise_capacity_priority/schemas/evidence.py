"""
Aggregated Supabase evidence for a single Raise Capacity request.

This is NOT the final evidence package — it is only the database portion
(including the student's current study plan and its total credit hours).
Later steps add the knowledge-file evaluations and deterministic
calculations.
"""

from typing import Optional

from pydantic import BaseModel

from ..schemas.academic_history import PreviousAttemptsSummary
from ..schemas.course import CourseInfo
from ..schemas.program import ProgramInfo
from ..schemas.raise_capacity import RaiseCapacityDetails
from ..schemas.request import RequestRecord
from ..schemas.section import SectionInfo
from ..schemas.student import StudentAcademicProfile
from ..schemas.study_plan import StudyPlanInfo


class SupabaseEvidence(BaseModel):
    request: RequestRecord
    raise_capacity: RaiseCapacityDetails
    student: StudentAcademicProfile
    program: Optional[ProgramInfo]
    course: CourseInfo
    section: SectionInfo
    previous_attempts: PreviousAttemptsSummary
    study_plan: StudyPlanInfo

"""
Factor 3 — course requirement: REQUIRED / ELECTIVE / NOT_IN_STUDY_PLAN /
UNKNOWN for the requested course in the student's current study plan
(Program_Study_Plan_Course). No local copy of this information is kept.
"""

from ..schemas.deterministic import CourseRequirementEvidence
from ..schemas.study_plan import StudyPlanInfo

SOURCE = "Program_Study_Plan_Course (current plan version)"


def build_course_requirement_evidence(
    course_id: str, course_name: str, study_plan: StudyPlanInfo
) -> CourseRequirementEvidence:
    requirement_type = study_plan.requirement_type(course_id)
    if study_plan.status != "OK":
        note = "; ".join(study_plan.notes) or f"Study plan status {study_plan.status}."
    elif requirement_type == "NOT_IN_STUDY_PLAN":
        note = f"The course is not listed in the current study plan {study_plan.plan_version}."
    elif requirement_type == "UNKNOWN":
        note = "The study plan records an unexpected requirement type for this course."
    else:
        note = None
    return CourseRequirementEvidence(
        course_id=course_id, course_name=course_name, program_id=study_plan.program_id,
        plan_version=study_plan.plan_version, requirement_type=requirement_type, note=note, source=SOURCE,
    )

"""
Pydantic models for the final prioritization evidence package — the single
structured object handed to Gemini alongside the (separately loaded)
prioritization policy. No field here is a priority judgment.

Sections (one per factor, plus scope and evidence quality):
  request_context            identification + the student's free-text reason
                             (unverified, student-provided)
  program_scope              whether the student's program is supported
  graduation                 factor 1
  degree_progress            factor 2
  requested_course_requirement  factor 3
  course_availability        factor 4
  previous_attempts          factor 5
  prerequisite_completion    factor 6
  progression                factor 7
  evidence_quality           missing / invalid / incomplete / conflicting
                             evidence found by Python (a safeguard, not a
                             weighted factor)
"""

from typing import Optional

from pydantic import BaseModel

from ..deterministic.program_scope import ProgramScopeEvidence
from ..schemas.deterministic import (
    CourseRequirementEvidence,
    PreviousAttemptSummaryEvidence,
    PrerequisiteCompletionEvidence,
    ProgressionEvidence,
    RemainingCreditsEvidence,
    RequestedCourseOfferingEvidence,
)


class RequestContext(BaseModel):
    request_id: str
    student_id: str
    request_term: int
    course_id: str
    course_name: str
    section_id: str
    # Student-provided and unverified; never a prioritization factor.
    reason: Optional[str]


class GraduationEvidence(BaseModel):
    request_term: int
    expected_graduation_term: Optional[int]
    same_as_expected_graduation_term: Optional[bool]
    # Term transitions strictly after request_term, up to and including
    # expected_graduation_term. None when expected_graduation_term is
    # missing, either term's semester suffix is unsupported, or
    # expected_graduation_term precedes request_term.
    terms_until_graduation_including_summer: Optional[int]
    terms_until_graduation_excluding_summer: Optional[int]


class EvidenceQualitySummary(BaseModel):
    program_in_scope: bool
    has_missing_evidence: bool
    has_conflicting_evidence: bool
    issues: list[str]


class PrioritizationEvidencePackage(BaseModel):
    request_context: RequestContext
    program_scope: ProgramScopeEvidence
    graduation: GraduationEvidence
    degree_progress: RemainingCreditsEvidence
    requested_course_requirement: CourseRequirementEvidence
    course_availability: RequestedCourseOfferingEvidence
    previous_attempts: PreviousAttemptSummaryEvidence
    prerequisite_completion: PrerequisiteCompletionEvidence
    progression: ProgressionEvidence
    evidence_quality: EvidenceQualitySummary

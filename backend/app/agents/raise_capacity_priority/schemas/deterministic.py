"""
Pydantic models for the deterministic evaluation results. Every field here
is a FACT Python computed or a FACT it could not compute (explicitly
represented as missing/unresolved/unknown) — never a priority judgment.
No field named priority/HIGH/MEDIUM/LOW exists anywhere in this module,
deliberately.

Course IDs are 7-digit text (leading zeros preserved), exactly as stored in
the database and the knowledge files.
"""

from typing import Literal, Optional

from pydantic import BaseModel

from ..deterministic.grade_policy import GradeStatus
from ..deterministic.term import Semester
from ..schemas.prerequisites import RequirementNode

OfferingStatus = Literal["YES", "NO", "UNKNOWN"]
RequirementType = Literal["REQUIRED", "ELECTIVE", "NOT_IN_STUDY_PLAN", "UNKNOWN"]
PrerequisiteStatus = Literal["SATISFIED", "NOT_SATISFIED", "UNRESOLVED", "CONFLICT"]
LeafStatus = Literal["SATISFIED", "NOT_SATISFIED", "UNRESOLVED"]
PrerequisiteMode = Literal["PRE", "CO", "PRE_OR_CO"]
# Where a transcript record sits relative to the requested academic term.
TermRelation = Literal["BEFORE_REQUEST_TERM", "REQUEST_TERM", "AFTER_REQUEST_TERM", "UNKNOWN_TERM"]


class RemainingCreditsEvidence(BaseModel):
    completed_hours: Optional[int]
    total_required_credits: Optional[int]
    remaining_credits: Optional[int]
    # completed_hours / total_required_credits * 100, rounded to one decimal.
    completion_percentage: Optional[float]
    status: Literal["OK", "UNRESOLVED", "ANOMALY"]
    note: Optional[str]
    plan_version: Optional[str]
    source: str


class CourseRequirementEvidence(BaseModel):
    course_id: str
    course_name: str
    program_id: Optional[str]
    plan_version: Optional[str]
    requirement_type: RequirementType
    note: Optional[str]
    source: str


class TakesRecordEvaluation(BaseModel):
    course_id: str
    grade: Optional[str]
    term: int
    term_relation: TermRelation
    grade_status: GradeStatus


class PrerequisiteLeafEvaluation(BaseModel):
    kind: Literal["COURSE", "STANDING"]
    course_id: Optional[str]
    mode: Optional[PrerequisiteMode]
    standing_text: Optional[str]
    required_earned_credits: Optional[int]
    completed_hours: Optional[int]
    status: LeafStatus
    reason: str
    matched_takes_records: list[TakesRecordEvaluation]


class PrerequisiteCompletionEvidence(BaseModel):
    course_id: str
    status: PrerequisiteStatus
    # Distinguishes "explicitly no prerequisite" from missing or unusable
    # prerequisite knowledge.
    knowledge_status: Literal[
        "NO_PREREQUISITES",
        "REQUIREMENT_DEFINED",
        "MISSING_FROM_KNOWLEDGE_BASE",
        "NOT_VERIFIED",
        "CONFLICTING",
        "NOT_EVALUATED",
    ]
    reason: str
    requirement_expression: Optional[RequirementNode]
    leaf_evaluations: list[PrerequisiteLeafEvaluation]
    source: str


class RequestedCourseOfferingEvidence(BaseModel):
    course_id: str
    found_in_kb: bool
    # Usual offering per semester: YES, NO or UNKNOWN (UNKNOWN is never NO).
    fall: Optional[OfferingStatus]
    spring: Optional[OfferingStatus]
    summer: Optional[OfferingStatus]
    usually_offered_semesters: list[Semester]
    not_offered_semesters: list[Semester]
    unknown_offering_semesters: list[Semester]
    request_semester: Optional[Semester]
    term_suffix_supported: bool
    next_term: Optional[int]
    next_term_offering: Optional[OfferingStatus]
    # KNOWN: a usual (YES) offering exists within the next three terms;
    # UNDETERMINED: no YES, at least one UNKNOWN; NO_USUAL_OFFERING_LISTED:
    # every semester is NO; NOT_AVAILABLE: course not in the knowledge
    # file, not evaluated, or the request term cannot be parsed.
    next_offering_status: Literal["KNOWN", "UNDETERMINED", "NO_USUAL_OFFERING_LISTED", "NOT_AVAILABLE"]
    next_known_offering_term: Optional[int]
    next_known_offering_semester: Optional[Semester]
    # Terms with UNKNOWN offering that come before the next known offering:
    # possible, but unconfirmed, earlier opportunities.
    earlier_unconfirmed_offering_terms: list[int]
    waiting_terms_including_summer: Optional[int]
    waiting_terms_excluding_summer: Optional[int]
    next_known_offering_vs_expected_graduation: Literal[
        "BEFORE_EXPECTED_GRADUATION", "SAME_AS_EXPECTED_GRADUATION", "AFTER_EXPECTED_GRADUATION", "UNKNOWN"
    ]
    availability_uncertain: bool
    notes: list[str]
    source: str


class PreviousAttemptSummaryEvidence(BaseModel):
    status: Literal["NEVER_ATTEMPTED", "PREVIOUSLY_ATTEMPTED", "UNKNOWN"]
    # None when status is UNKNOWN.
    attempted_before: Optional[bool]
    # Recorded for transparency only; they must not influence priority.
    number_of_attempts: int
    previous_grades: list[Optional[str]]
    previous_terms: list[int]
    excluded_same_term_records: int
    excluded_future_term_records: int
    unknown_term_records: int


class DependentCourseEvidence(BaseModel):
    course_id: str
    course_name: str
    requirement_type: RequirementType
    # MANDATORY: every route through the dependent's requirement needs the
    # requested course; ALTERNATIVE: another route exists.
    requested_course_role: Literal["MANDATORY", "ALTERNATIVE"]
    completion_status: Literal["COMPLETED", "NOT_COMPLETED", "UNRESOLVED"]
    # The dependent's requirement is already met without the requested
    # course (None when that cannot be determined).
    alternative_route_already_satisfied: Optional[bool]
    # True only when the dependent is not completed and its requirement
    # cannot be met without the requested course; None when unresolved.
    potentially_affected_by_delay: Optional[bool]
    note: str
    fall: Optional[OfferingStatus]
    spring: Optional[OfferingStatus]
    summer: Optional[OfferingStatus]


class ProgressionEvidence(BaseModel):
    requested_course_id: str
    evaluated: bool
    not_evaluated_reason: Optional[str]
    # A pass recorded before the requested term: delaying the request cannot
    # block dependents, whose requirement already counts the course as met.
    requested_course_already_passed: bool
    total_direct_dependents: int
    required_dependents: int
    elective_dependents: int
    not_in_study_plan_dependents: int
    unknown_requirement_dependents: int
    completed_dependents: int
    alternative_route_satisfied_dependents: int
    potentially_affected_dependents: int
    potentially_affected_required_dependents: int
    unresolved_dependents: int
    dependent_courses: list[DependentCourseEvidence]
    source: str


class DeterministicEvidence(BaseModel):
    remaining_credits: RemainingCreditsEvidence
    course_requirement: CourseRequirementEvidence
    prerequisite_completion: PrerequisiteCompletionEvidence
    requested_course_offering: RequestedCourseOfferingEvidence
    previous_attempt_summary: PreviousAttemptSummaryEvidence
    progression_evidence: ProgressionEvidence

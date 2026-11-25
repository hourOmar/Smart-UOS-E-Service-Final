# Copied from app/agents/raise_capacity_priority: schemas/academic_history.py (TakesRecord),
# retrieval/academic_history.py (term_relation) and schemas/deterministic.py (the
# prerequisite evidence models). Validated definitions; only imports changed.
"""
Transcript records and the prerequisite evidence models used by the copied
evaluator. Course IDs are 7-digit text (leading zeros preserved).

Every record's term_relation to the requested academic term:
- BEFORE_REQUEST_TERM: an earlier record (can complete a prerequisite);
- REQUEST_TERM: the requested term itself (current enrolment);
- AFTER_REQUEST_TERM: a future record (ignored);
- UNKNOWN_TERM: the order cannot be determined (unsupported semester suffix).
"""

from typing import Literal, Optional

from pydantic import BaseModel

from .grade_policy import GradeStatus
from .prerequisite_schemas import RequirementNode
from .term import compare_terms

TermRelation = Literal["BEFORE_REQUEST_TERM", "REQUEST_TERM", "AFTER_REQUEST_TERM", "UNKNOWN_TERM"]
PrerequisiteStatus = Literal["SATISFIED", "NOT_SATISFIED", "UNRESOLVED", "CONFLICT"]
LeafStatus = Literal["SATISFIED", "NOT_SATISFIED", "UNRESOLVED"]
PrerequisiteMode = Literal["PRE", "CO", "PRE_OR_CO"]

_RELATION = {-1: "BEFORE_REQUEST_TERM", 0: "REQUEST_TERM", 1: "AFTER_REQUEST_TERM", None: "UNKNOWN_TERM"}


def term_relation(term: int, request_term: int) -> str:
    return _RELATION[compare_terms(term, request_term)]


class TakesRecord(BaseModel):
    """A raw Takes row for any course."""

    course_id: str  # text, leading zeros preserved
    grade: Optional[str]
    section_id: str
    term: int


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

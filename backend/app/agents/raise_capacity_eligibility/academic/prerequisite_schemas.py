# Copied from app/agents/raise_capacity_priority/schemas/prerequisites.py (validated logic; only imports and paths changed).
"""
Pydantic models for knowledge/course_prerequisites.json, mirroring its
structure exactly so the validated, owner-confirmed requirements are
loaded without reinterpretation.

A requirement is a tree of:
- COURSE: one course; concurrent_allowed=False means it must be completed
  before the requested term (PRE), True means completion before OR
  enrolment in the requested term (PRE_OR_CO);
- STANDING: an academic standing named in standing_definitions;
- ALL_OF / ANY_OF: AND / OR groups of two or more nodes (nestable).

requirement=None means "no prerequisite" only when prerequisite_status is
VERIFIED; otherwise the requirement is unknown.
"""

from typing import Annotated, Literal, Optional, Union

from pydantic import BaseModel, Field

COURSE_ID_PATTERN = r"^[0-9]{7}$"


class CourseRequirement(BaseModel):
    type: Literal["COURSE"]
    course_id: str = Field(pattern=COURSE_ID_PATTERN)
    concurrent_allowed: bool


class StandingRequirement(BaseModel):
    type: Literal["STANDING"]
    text: str = Field(min_length=1)


class RequirementGroup(BaseModel):
    type: Literal["ALL_OF", "ANY_OF"]
    items: list["RequirementNode"] = Field(min_length=2)


RequirementNode = Annotated[
    Union[CourseRequirement, StandingRequirement, RequirementGroup],
    Field(discriminator="type"),
]
RequirementGroup.model_rebuild()

PrerequisiteKnowledgeStatus = Literal["VERIFIED", "UNVERIFIED", "CONFLICTING", "NOT_COLLECTED"]


class PrerequisiteKnowledgeEntry(BaseModel):
    course_name: str
    prerequisite_status: PrerequisiteKnowledgeStatus
    requirement: Optional[RequirementNode]
    source_requirement_variants: list[str] = Field(default_factory=list)
    review_status: Optional[str] = None
    review_note: Optional[str] = None


class StandingDefinition(BaseModel):
    classification_min_earned_credits: int = Field(ge=0)
    classification_max_earned_credits: Optional[int] = Field(default=None, ge=0)
    prerequisite_min_earned_credits: int = Field(ge=0)


class PrerequisiteKnowledgeBase(BaseModel):
    schema_version: str
    status: str
    program_id: str = Field(min_length=1)
    courses: dict[str, PrerequisiteKnowledgeEntry]
    standing_definitions: dict[str, StandingDefinition]

"""Pydantic schema for a Supabase Section row."""

from pydantic import BaseModel


class SectionInfo(BaseModel):
    section_id: str  # character varying
    course_id: str  # text, 7 digits, leading zeros preserved
    term: int
    current_capacity: int
    total_capacity: int
    additional_capacity: int

"""Pydantic schema for a Supabase Course row."""

from pydantic import BaseModel


class CourseInfo(BaseModel):
    course_id: str  # text, 7 digits, leading zeros preserved
    course_name: str
    credit_hours: int

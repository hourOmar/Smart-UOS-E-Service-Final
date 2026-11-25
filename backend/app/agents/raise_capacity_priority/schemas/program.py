"""Pydantic schema for a Supabase Program row."""

from pydantic import BaseModel


class ProgramInfo(BaseModel):
    program_id: str  # text, leading zeros preserved
    program_name: str
    college_name: str

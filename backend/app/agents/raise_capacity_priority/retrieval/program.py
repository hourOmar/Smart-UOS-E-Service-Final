"""
Supabase retrieval for the Program table (Step 4 of the retrieval flow).

Program's primary key is (Program_ID, Program_Name): one Program_ID is a
department code shared by several programs (1501 is Computer Science,
Artificial Intelligence, Biomedical Informatics and IT - Multimedia), and
every foreign key to Program (Student, study plans, ...) uses both columns.
The student's program is therefore looked up by BOTH Student.Program_ID and
Student.Program_Name — never by the ID alone, which would return an arbitrary
one of the programs sharing it.

Student.Program_ID can legitimately be null — in that case there is no
program to fetch, and this returns None rather than treating it as an
error. If the student's (Program_ID, Program_Name) points at no row, that is
a real data problem and raises ProgramNotFoundError. A student with a
Program_ID but no Program_Name is identified by the ID only when exactly one
program has it; otherwise the program cannot be identified and None is
returned (no program is guessed).
"""

from typing import Any, Optional

from ..retrieval._query import select_rows
from ..retrieval.errors import ProgramNotFoundError
from ..schemas.program import ProgramInfo

_COLUMNS = "Program_ID, Program_Name, College_Name"


def get_program(client: Any, program_id: Optional[str], program_name: Optional[str] = None) -> Optional[ProgramInfo]:
    if program_id is None:
        return None

    filters = {"Program_ID": program_id}
    if program_name is not None:
        filters["Program_Name"] = program_name
    rows = select_rows(client, "Program", _COLUMNS, filters)
    if not rows:
        named = f", Program_Name={program_name!r}" if program_name is not None else ""
        raise ProgramNotFoundError(
            f"Student.Program_ID={program_id!r}{named} does not match any Program row."
        )
    if len(rows) > 1:
        # Only reachable without a Program_Name: several programs share this ID.
        return None

    row = rows[0]
    return ProgramInfo(
        program_id=row["Program_ID"],
        program_name=row["Program_Name"],
        college_name=row["College_Name"],
    )

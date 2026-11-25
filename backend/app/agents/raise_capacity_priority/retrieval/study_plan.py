"""
Retrieval of the student's current study plan from the database:

- Program_Study_Plan_Course: the courses of the program's CURRENT plan
  version (Is_Current) with their Requirement_Type (Required / Elective);
- Program_Study_Plan_Total: the total credit hours of that plan version.

Nothing is hardcoded or duplicated locally (e.g. no 123-credit total).
Missing or inconsistent data is reported in the result, never guessed:
no Program_ID, no current plan, more than one current plan version, or a
missing / duplicated / invalid total.
"""

from typing import Any, Optional

from ..retrieval._query import select_rows
from ..schemas.study_plan import StudyPlanInfo

_PLAN_COLUMNS = "Program_ID, Plan_Version, Course_ID, Requirement_Type, Is_Current"
_TOTAL_COLUMNS = "Program_ID, Plan_Version, Total_Credit_Hours"
_TYPES = {"Required": "REQUIRED", "Elective": "ELECTIVE"}


def get_study_plan(client: Any, program_id: Optional[str]) -> StudyPlanInfo:
    if program_id is None:
        return StudyPlanInfo(
            program_id=None, status="NO_PROGRAM", plan_version=None, requirement_types={},
            total_required_credits=None, total_status="NOT_APPLICABLE",
            notes=["Student.Program_ID is missing; no study plan can be identified."],
        )

    rows = select_rows(client, "Program_Study_Plan_Course", _PLAN_COLUMNS, {"Program_ID": program_id})
    current = [row for row in rows if row["Is_Current"] is True]
    versions = sorted({row["Plan_Version"] for row in current})
    if not versions:
        return StudyPlanInfo(
            program_id=program_id, status="NO_CURRENT_PLAN", plan_version=None, requirement_types={},
            total_required_credits=None, total_status="NOT_APPLICABLE",
            notes=[f"No current study plan is recorded for program {program_id}."],
        )
    if len(versions) > 1:
        return StudyPlanInfo(
            program_id=program_id, status="MULTIPLE_CURRENT_PLANS", plan_version=None, requirement_types={},
            total_required_credits=None, total_status="NOT_APPLICABLE",
            notes=[f"More than one current study plan version is recorded for program {program_id}: {versions}."],
        )

    version = versions[0]
    notes: list[str] = []
    requirement_types: dict[str, str] = {}
    for row in current:
        mapped = _TYPES.get(row["Requirement_Type"], "UNKNOWN")
        if mapped == "UNKNOWN":
            notes.append(f"Course {row['Course_ID']} has an unexpected Requirement_Type {row['Requirement_Type']!r}.")
        requirement_types[row["Course_ID"]] = mapped

    totals = select_rows(
        client, "Program_Study_Plan_Total", _TOTAL_COLUMNS, {"Program_ID": program_id, "Plan_Version": version}
    )
    total: Optional[int] = None
    if not totals:
        total_status = "NOT_FOUND"
        notes.append(f"No total credit hours are recorded for plan {version}.")
    elif len({row["Total_Credit_Hours"] for row in totals}) > 1:
        total_status = "MULTIPLE"
        notes.append(f"Conflicting total credit hours are recorded for plan {version}.")
    else:
        value = totals[0]["Total_Credit_Hours"]
        if isinstance(value, int) and not isinstance(value, bool) and value > 0:
            total, total_status = value, "OK"
        else:
            total_status = "INVALID"
            notes.append(f"The total credit hours recorded for plan {version} are invalid ({value!r}).")

    return StudyPlanInfo(
        program_id=program_id, status="OK", plan_version=version, requirement_types=requirement_types,
        total_required_credits=total, total_status=total_status, notes=notes,
    )

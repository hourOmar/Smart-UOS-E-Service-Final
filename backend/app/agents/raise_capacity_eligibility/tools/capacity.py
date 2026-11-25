from sqlalchemy import text
from sqlalchemy.engine import Connection

from ..exceptions import SectionCourseMismatchError, SectionNotFoundError


def get_section_capacity(conn: Connection, section_id: str, course_id: str, term: int) -> dict:
    """Section_ID alone is NOT a unique key -- the same section number is reused across
    courses and terms. The real key is (Section_ID, Course_ID, Term), exactly what
    Raise_Capacity stores."""
    row = conn.execute(
        text(
            'SELECT "Section_ID", "Course_ID", "Term", "Current_Capacity", '
            '"Total_Capacity", "Additional_Capacity" FROM public."Section" '
            'WHERE "Section_ID" = :sid AND "Course_ID" = :cid AND "Term" = :term'
        ),
        {"sid": section_id, "cid": course_id, "term": term},
    ).mappings().first()
    if row is not None:
        return dict(row)

    # No exact match: say "wrong course" when the section exists for another course.
    other = conn.execute(
        text('SELECT "Course_ID" FROM public."Section" WHERE "Section_ID" = :sid AND "Term" = :term'),
        {"sid": section_id, "term": term},
    ).mappings().first()

    if other is not None:
        raise SectionCourseMismatchError(
            f"Section_ID={section_id} in Term={term} belongs to Course_ID={other['Course_ID']}, "
            f"not the requested Course_ID={course_id}."
        )
    raise SectionNotFoundError(f"No Section found for Section_ID={section_id}, Course_ID={course_id}, Term={term}.")


_FIELDS = (("Current_Capacity", "current capacity"), ("Total_Capacity", "total capacity"),
           ("Additional_Capacity", "additional capacity"))


def evaluate_capacity(capacity_data: dict | None, missing_reason: str | None = None) -> dict:
    """All values come directly from the Section row; nothing is estimated.

    Same rule as the database's decide_raise_capacity_request, which enforces it
    again when an approval is saved (it refuses when Current_Capacity >=
    Total_Capacity + Additional_Capacity, and otherwise adds one seat):
        maximum_allowed_capacity = Total_Capacity + Additional_Capacity
        remaining_raise_capacity = maximum_allowed_capacity - Current_Capacity
    status SATISFIED when a seat remains, NOT_SATISFIED when the maximum is
    reached or exceeded, UNRESOLVED when a value is missing or invalid (not a
    whole number, or negative) or the section could not be found."""
    issues: list[str] = []
    values: dict[str, int | None] = {}
    if capacity_data is None:
        issues.append(missing_reason or "The section's capacity record could not be found.")
    else:
        for column, label in _FIELDS:
            value = capacity_data.get(column)
            if isinstance(value, bool) or not isinstance(value, int):
                issues.append(f"The {label} is missing or not a whole number.")
                value = None
            elif value < 0:
                issues.append(f"The {label} is negative ({value}).")
                value = None
            values[column] = value

    current = values.get("Current_Capacity")
    total = values.get("Total_Capacity")
    additional = values.get("Additional_Capacity")
    if issues:
        return {
            "current_capacity": current, "total_capacity": total, "additional_capacity": additional,
            "maximum_allowed_capacity": None, "remaining_raise_capacity": None,
            "status": "UNRESOLVED", "satisfied": None, "issues": issues,
        }

    maximum_allowed_capacity = total + additional
    remaining_raise_capacity = maximum_allowed_capacity - current
    available = current < maximum_allowed_capacity
    if current > maximum_allowed_capacity:
        issues.append("The current capacity exceeds the maximum allowed capacity.")
    return {
        "current_capacity": current,
        "total_capacity": total,
        "additional_capacity": additional,
        "maximum_allowed_capacity": maximum_allowed_capacity,
        "remaining_raise_capacity": remaining_raise_capacity,
        "status": "SATISFIED" if available else "NOT_SATISFIED",
        "satisfied": available,
        "issues": issues,
    }

"""
Factor 2 — degree progress.

remaining_credits = total_required_credits - completed_hours
completion_percentage = completed_hours / total_required_credits * 100

completed_hours is Student.Completed_Hours (earned credit hours); the total
is Program_Study_Plan_Total.Total_Credit_Hours for the student's current
plan version. Either can be missing (UNRESOLVED — never defaulted to 0).
Negative completed hours, or completed hours above the total, are flagged
ANOMALY; a negative remainder is preserved rather than clamped, so the data
problem stays visible.
"""

from typing import Optional

from ..schemas.deterministic import RemainingCreditsEvidence
from ..schemas.study_plan import StudyPlanInfo

SOURCE = "Student.Completed_Hours; Program_Study_Plan_Total.Total_Credit_Hours"


def calculate_remaining_credits(completed_hours: Optional[int], study_plan: StudyPlanInfo) -> RemainingCreditsEvidence:
    total = study_plan.total_required_credits

    def evidence(remaining, percentage, status, note):
        return RemainingCreditsEvidence(
            completed_hours=completed_hours, total_required_credits=total, remaining_credits=remaining,
            completion_percentage=percentage, status=status, note=note, plan_version=study_plan.plan_version,
            source=SOURCE,
        )

    if completed_hours is None or total is None:
        missing = []
        if completed_hours is None:
            missing.append("Student.Completed_Hours")
        if total is None:
            reason = "; ".join(study_plan.notes) or f"study plan status {study_plan.status}"
            missing.append(f"total required credit hours ({reason})")
        return evidence(None, None, "UNRESOLVED", f"Missing input(s): {', '.join(missing)}.")

    if completed_hours < 0:
        return evidence(None, None, "ANOMALY", "Student.Completed_Hours is negative (invalid).")

    remaining = total - completed_hours
    percentage = round(completed_hours / total * 100, 1)
    if remaining < 0:
        return evidence(
            remaining, percentage, "ANOMALY",
            "Completed_Hours exceeds the total required credit hours; the negative value is preserved "
            "rather than clamped to zero so this can be reviewed.",
        )
    return evidence(remaining, percentage, "OK", None)

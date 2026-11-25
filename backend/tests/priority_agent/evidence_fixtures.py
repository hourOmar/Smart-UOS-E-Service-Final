"""
Offline fixtures: fake database tables for one Raise Capacity request and a
helper that builds the real evidence package from them through the real
pipeline (FakeSupabaseClient — no database, no network, no Gemini).

The study plan mirrors the current CS plan (CS-WEB-2026-10-31: 37 Required,
21 Elective, 123 credit hours). Terms use YYYYSS (01 Fall, 02 Spring,
03 Summer); 202601 is the request term.
"""

import copy

from app.agents.raise_capacity_priority.pipeline.build_prioritization_evidence import build_prioritization_evidence
from priority_agent.fakes import FakeSupabaseClient

CS_REQUIRED = [
    "0201102", "0202112", "1440131", "1430110", "1430116", "1501116", "1440132", "1420101", "1420102", "1501211",
    "1440281", "1501279", "1502201", "0302200", "0204102", "1501215", "1501246", "1501252", "1502202", "1440211",
    "1501330", "1501263", "1501371", "1501366", "0202213", "1501319", "1501352", "1501372", "1501394", "1501397",
    "1501322", "1501459", "1501454", "1501494", "1501100", "0104100", "1501250",
]
CS_ELECTIVE = [f"1501{n}" for n in (341, 342, 343, 344, 355, 365, 370, 433, 440, 441, 442, 443, 444, 445, 451, 458,
                                     465, 474, 490, 491, 492)]
PLAN_VERSION = "CS-WEB-2026-10-31"
REQUEST_TERM = 202601


def takes(course_id, grade, term=202502, student="S1", section="1"):
    return {"Student_ID": student, "Course_ID": course_id, "Grade": grade, "Section_ID": section, "Term": term}


def tables(course_id="1501215", course_name="Data Structures", completed_hours=90, expected_graduation=202702,
           program_id="1501", reason="I need this course to graduate.", transcript=None, plan=True, total=123):
    if transcript is None:
        transcript = [takes("1501116", "A", 202501), takes("1501211", "B", 202502)]
    plan_rows = []
    if plan:
        plan_rows = (
            [{"Program_ID": "1501", "Plan_Version": PLAN_VERSION, "Course_ID": c, "Requirement_Type": "Required",
              "Is_Current": True} for c in CS_REQUIRED]
            + [{"Program_ID": "1501", "Plan_Version": PLAN_VERSION, "Course_ID": c, "Requirement_Type": "Elective",
                "Is_Current": True} for c in CS_ELECTIVE]
            + [{"Program_ID": "1502", "Plan_Version": "CPE-WEB-2026-10-31", "Course_ID": "1501215",
                "Requirement_Type": "Required", "Is_Current": True}]
        )
    return {
        "Request": [{
            "Request_ID": "REQ-1", "Request_Type": "Raise Capacity", "Request_Date": "2026-09-01",
            "Submission_Time": "09:00:00", "Description": None, "Current_Status": "In Progress", "Student_ID": "S1",
        }],
        "Raise_Capacity": [{"Request_ID": "REQ-1", "Reason": reason, "Course_ID": course_id, "Section_ID": "SEC-1",
                            "Term": REQUEST_TERM}],
        "Student": [{"Student_ID": "S1", "Student_Name": "Test Student", "CGPA": 3.1,
                     "Completed_Hours": completed_hours, "Program_ID": program_id,
                     "Expected_Graduation_Term": expected_graduation}],
        "Program": [
            {"Program_ID": "1501", "Program_Name": "Bachelor of Science in Computer Science", "College_Name": "CCI"},
            {"Program_ID": "1502", "Program_Name": "Bachelor of Science in Computer Engineering", "College_Name": "CE"},
            {"Program_ID": "0302", "Program_Name": "Other Program", "College_Name": "Other"},
        ],
        "Course": [{"Course_ID": course_id, "Course_Name": course_name, "Credit_Hours": 3}],
        "Section": [{"Section_ID": "SEC-1", "Course_ID": course_id, "Term": REQUEST_TERM, "Current_Capacity": 30,
                     "Total_Capacity": 30, "Additional_Capacity": 0}],
        "Takes": copy.deepcopy(transcript),
        "Program_Study_Plan_Course": plan_rows,
        "Program_Study_Plan_Total": [
            {"Program_ID": "1501", "Plan_Version": PLAN_VERSION, "Total_Credit_Hours": total},
            {"Program_ID": "1502", "Plan_Version": "CPE-WEB-2026-10-31", "Total_Credit_Hours": 132},
        ],
    }


def package(**kwargs):
    return build_prioritization_evidence("REQ-1", FakeSupabaseClient(tables(**kwargs)))

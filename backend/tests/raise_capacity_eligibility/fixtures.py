"""Offline fixtures: rows as the database returns them, assembled into a real
evidence package by the agent's own pure assembler (no database, no Gemini)."""

from app.agents.raise_capacity_eligibility.schemas import CheckExplanations, EligibilityDecision
from app.agents.raise_capacity_eligibility.workflow import assemble_evidence_package

REQUEST_TERM = 202601
STUDENT = {"Student_ID": "U21100001", "Student_Name": "Zaynab Distinctname"}


def take(course_id, grade, term=202502, section="1"):
    return {"Course_ID": course_id, "Course_Name": None, "Grade": grade, "Term": term, "Section_ID": section}


def section(current=30, total=30, additional=5):
    return {"Section_ID": "SEC-1", "Course_ID": "x", "Term": REQUEST_TERM, "Current_Capacity": current,
            "Total_Capacity": total, "Additional_Capacity": additional}


def evidence(course_id="1501215", transcript=(), hours=70, program="1501", sec="default", section_problem=None,
             course_name="Data Structures"):
    request = {"Request_ID": "REQ-1", "Student_ID": STUDENT["Student_ID"], "Course_ID": course_id,
               "Section_ID": "SEC-1", "Term": REQUEST_TERM}
    student = {**STUDENT, "CGPA": 3.0, "Completed_Hours": hours, "Program_ID": program,
               "Program_Name": "Bachelor of Science in Computer Science" if program == "1501" else "Other"}
    course = {"Course_ID": course_id, "Course_Name": course_name, "Credit_Hours": 3}
    row = section() if sec == "default" else sec
    return assemble_evidence_package("REQ-1", request, student, list(transcript), course, row, section_problem)


def decision(recommendation, reasoning="Because of the verified evidence.", **checks):
    texts = {"prerequisite": "Prerequisite explained.", "completed_hours": "Standing explained.",
             "capacity": "Capacity explained.", **checks}
    return EligibilityDecision(recommendation=recommendation, reasoning=reasoning, checks=CheckExplanations(**texts))

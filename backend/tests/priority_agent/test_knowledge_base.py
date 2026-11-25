"""
The agent's four knowledge files are present directly in knowledge/, are
valid, and hold the agreed content. Nothing here changes a file.
"""

import json

from app.agents.raise_capacity_priority import KNOWLEDGE_DIR as KB_DIR

FILES = ("course_offerings.json", "course_prerequisites.json", "grade_policy.json", "prioritization_rules.json")


def _load(name):
    return json.loads((KB_DIR / name).read_text(encoding="utf-8"))


def test_exactly_the_four_knowledge_files_sit_directly_in_the_folder():
    assert sorted(p.name for p in KB_DIR.iterdir() if p.is_file()) == sorted(FILES)
    assert not (KB_DIR / "raise_capacity").exists()


def test_offerings_and_prerequisites_cover_the_same_58_courses_of_one_program():
    offerings = _load("course_offerings.json")
    prerequisites = _load("course_prerequisites.json")
    offering_ids = [c["course_id"] for c in offerings["courses"]]
    assert len(offering_ids) == len(set(offering_ids)) == 58
    assert set(offering_ids) == set(prerequisites["courses"])
    assert offerings["program_id"] == prerequisites["program_id"] == "1501"


def test_offerings_use_yes_no_unknown_only():
    for course in _load("course_offerings.json")["courses"]:
        assert set(course["offerings"]) == {"fall", "spring", "summer"}
        assert set(course["offerings"].values()) <= {"YES", "NO", "UNKNOWN"}


def test_grade_policy_is_the_approved_policy():
    policy = _load("grade_policy.json")
    assert policy["passing_grades"] == ["A", "B+", "B", "C+", "C", "D+", "D"]
    assert policy["failing_grades"] == ["F", "WF", "FA"]


def test_standing_definitions():
    standing = _load("course_prerequisites.json")["standing_definitions"]
    assert standing["Junior Standing"]["prerequisite_min_earned_credits"] == 65
    assert standing["Senior Standing"]["prerequisite_min_earned_credits"] == 99


def test_prioritization_rules_have_eight_rules_and_four_levels():
    policy = _load("prioritization_rules.json")
    assert len(policy["raise_capacity_prioritization_rules"]) == 8
    assert set(policy["priority_levels"]) == {"HIGH", "MEDIUM", "LOW", "MANUAL_REVIEW"}
    previous = next(r for r in policy["raise_capacity_prioritization_rules"] if r["name"] == "Previous Attempts")
    assert previous["description"] == (
        "Students who have never attempted the requested course receive greater consideration on this factor."
    )

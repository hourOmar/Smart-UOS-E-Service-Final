"""
Both Raise Capacity agents evaluate prerequisites identically: the Eligibility
agent's academic/ package is a copy of the Prioritization agent's validated
logic (only imports and paths changed), its knowledge files are byte-identical,
and every course in the knowledge file gives the same result in both agents
for the same evidence. The Eligibility agent never imports the Prioritization
agent at run time (this test imports both, only to compare them).
"""

import inspect
from pathlib import Path

import pytest

from app.agents.raise_capacity_eligibility import KNOWLEDGE_DIR as E_KB
from app.agents.raise_capacity_eligibility.academic import prerequisite_evaluator as E
from app.agents.raise_capacity_eligibility.academic import prerequisite_knowledge as EK
from app.agents.raise_capacity_eligibility.academic import term as ET
from app.agents.raise_capacity_eligibility.academic.records import TakesRecord as ETakes
from app.agents.raise_capacity_priority import KNOWLEDGE_DIR as P_KB
from app.agents.raise_capacity_priority.deterministic import prerequisite_evaluator as P
from app.agents.raise_capacity_priority.deterministic import prerequisite_knowledge as PK
from app.agents.raise_capacity_priority.deterministic import term as PT
from app.agents.raise_capacity_priority.schemas.academic_history import TakesRecord as PTakes

REQUEST_TERM = 202601
ACADEMIC = Path(E.__file__).parent


@pytest.mark.parametrize("name", ["combine", "mode_for", "evaluate_course_leaf", "evaluate_standing_leaf",
                                  "evaluate_requirement", "evaluate_prerequisite_completion",
                                  "not_evaluated_prerequisite_evidence"])
def test_evaluator_functions_are_identical_copies(name):
    assert inspect.getsource(getattr(E, name)) == inspect.getsource(getattr(P, name))


@pytest.mark.parametrize("name", ["parse_term", "next_semester", "term_index", "term_from_index", "compare_terms",
                                  "following_terms", "calculate_terms_until_graduation"])
def test_term_helpers_are_identical_copies(name):
    assert inspect.getsource(getattr(ET, name)) == inspect.getsource(getattr(PT, name))


@pytest.mark.parametrize("name", ["iter_nodes", "referenced_course_ids", "_validate", "load_prerequisite_knowledge"])
def test_knowledge_loader_is_an_identical_copy(name):
    assert inspect.getsource(getattr(EK, name)) == inspect.getsource(getattr(PK, name))


@pytest.mark.parametrize("name", ["course_prerequisites.json", "grade_policy.json"])
def test_knowledge_files_are_byte_identical(name):
    assert (E_KB / name).read_bytes() == (P_KB / name).read_bytes()


def test_the_eligibility_agent_never_imports_the_prioritization_agent():
    package = ACADEMIC.parent
    for path in package.rglob("*.py"):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.lstrip().startswith(("import ", "from ")):
                assert "raise_capacity_priority" not in line, f"{path.name}: {line}"


def _transcripts():
    ids = sorted({cid for entry in PK.PREREQUISITE_KNOWLEDGE.courses.values()
                  for cid in PK.referenced_course_ids(entry.requirement)})
    scenarios = [[]]
    for grade in ("A", "D", "F", "WF", "W", "I", None, "XYZ"):
        for term in (202502, REQUEST_TERM, 202602, 202509):
            scenarios.append([(cid, grade, term) for cid in ids])
    # Mixed: alternate passes and missing records, and a pass after an earlier fail.
    scenarios.append([(cid, "B", 202502) for cid in ids[::2]])
    scenarios.append([(cid, "F", 202501) for cid in ids] + [(cid, "C", 202503) for cid in ids[1::3]])
    return scenarios


@pytest.mark.parametrize("hours", [None, 0, 64, 65, 98, 99, 130])
def test_every_course_gives_the_same_result_in_both_agents(hours):
    for scenario in _transcripts():
        e_records = [ETakes(course_id=c, grade=g, section_id="1", term=t) for c, g, t in scenario]
        p_records = [PTakes(course_id=c, grade=g, section_id="1", term=t) for c, g, t in scenario]
        for course_id in list(PK.PREREQUISITE_KNOWLEDGE.courses) + ["9999999"]:
            e = E.evaluate_prerequisite_completion(course_id, EK.PREREQUISITE_KNOWLEDGE, e_records, REQUEST_TERM, hours)
            p = P.evaluate_prerequisite_completion(course_id, PK.PREREQUISITE_KNOWLEDGE, p_records, REQUEST_TERM, hours)
            e_dump = e.model_dump(mode="json", exclude={"source"})
            p_dump = p.model_dump(mode="json", exclude={"source"})
            assert e_dump == p_dump, (course_id, hours, scenario[:2])

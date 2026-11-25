# Copied from app/agents/raise_capacity_priority/deterministic/prerequisite_knowledge.py (validated logic; only imports and paths changed).
"""
Loads and validates knowledge/course_prerequisites.json — the
owner-confirmed prerequisite requirements for the supported program — and
derives the reverse lookup of DIRECT dependent courses from it (no separate
dependency file is kept).

Validation (a malformed file fails loudly when loaded):
- the structure matches schemas/prerequisites.py (7-digit text course IDs,
  groups of two or more items, known node types);
- no duplicate keys anywhere in the JSON;
- every course key is a 7-digit text ID;
- every STANDING node names a defined standing;
- no course requires itself and the requirements contain no cycle.

A VERIFIED entry with requirement null is the explicit "no prerequisite"
form. Standing thresholds (prerequisite_min_earned_credits) come only from
the file; nothing here hardcodes them.
"""

import json
import re
from pathlib import Path
from typing import Iterator, Optional

from .. import KNOWLEDGE_DIR
from .prerequisite_schemas import (
    CourseRequirement,
    PrerequisiteKnowledgeBase,
    PrerequisiteKnowledgeEntry,
    RequirementGroup,
    RequirementNode,
    StandingRequirement,
)

_KB_PATH = KNOWLEDGE_DIR / "course_prerequisites.json"
SOURCE = "knowledge_base/course_prerequisites.json"
_COURSE_ID = re.compile(r"^[0-9]{7}$")


def iter_nodes(node: Optional[RequirementNode]) -> Iterator[RequirementNode]:
    if node is None:
        return
    yield node
    if isinstance(node, RequirementGroup):
        for item in node.items:
            yield from iter_nodes(item)


def referenced_course_ids(node: Optional[RequirementNode]) -> set[str]:
    return {n.course_id for n in iter_nodes(node) if isinstance(n, CourseRequirement)}


class PrerequisiteKnowledge:
    def __init__(self, kb: PrerequisiteKnowledgeBase):
        self.program_id = kb.program_id
        self.courses: dict[str, PrerequisiteKnowledgeEntry] = dict(kb.courses)
        self.standing_definitions = dict(kb.standing_definitions)
        dependents: dict[str, set[str]] = {}
        for course_id, entry in self.courses.items():
            for referenced in referenced_course_ids(entry.requirement):
                dependents.setdefault(referenced, set()).add(course_id)
        self._dependents = {k: sorted(v) for k, v in dependents.items()}

    def entry(self, course_id: str) -> Optional[PrerequisiteKnowledgeEntry]:
        return self.courses.get(course_id)

    def standing_threshold(self, standing_text: str) -> Optional[int]:
        definition = self.standing_definitions.get(standing_text)
        return definition.prerequisite_min_earned_credits if definition is not None else None

    def direct_dependents(self, course_id: str) -> list[str]:
        """Courses whose own requirement references course_id directly."""
        return list(self._dependents.get(course_id, []))


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict:
    keys = [k for k, _ in pairs]
    duplicates = {k for k in keys if keys.count(k) > 1}
    if duplicates:
        raise ValueError(f"course_prerequisites.json: duplicate key(s) {sorted(duplicates)}.")
    return dict(pairs)


def _validate(kb: PrerequisiteKnowledgeBase) -> None:
    for course_id, entry in kb.courses.items():
        if not _COURSE_ID.match(course_id):
            raise ValueError(f"course_prerequisites.json: invalid course ID key {course_id!r}.")
        for node in iter_nodes(entry.requirement):
            if isinstance(node, StandingRequirement) and node.text not in kb.standing_definitions:
                raise ValueError(f"course_prerequisites.json: {course_id} uses undefined standing {node.text!r}.")
        if course_id in referenced_course_ids(entry.requirement):
            raise ValueError(f"course_prerequisites.json: {course_id} requires itself.")

    graph = {cid: referenced_course_ids(e.requirement) for cid, e in kb.courses.items()}
    visiting: set[str] = set()
    done: set[str] = set()

    def visit(course_id: str, path: list[str]) -> None:
        if course_id in done or course_id not in graph:
            return
        if course_id in visiting:
            cycle = path[path.index(course_id):] + [course_id]
            raise ValueError(f"course_prerequisites.json: circular requirement {' -> '.join(cycle)}.")
        visiting.add(course_id)
        for referenced in sorted(graph[course_id]):
            visit(referenced, path + [course_id])
        visiting.discard(course_id)
        done.add(course_id)

    for course_id in sorted(graph):
        visit(course_id, [])


def load_prerequisite_knowledge(path: Path = _KB_PATH) -> PrerequisiteKnowledge:
    with open(path, encoding="utf-8") as f:
        data = json.load(f, object_pairs_hook=_reject_duplicate_keys)
    kb = PrerequisiteKnowledgeBase.model_validate(data)
    _validate(kb)
    return PrerequisiteKnowledge(kb)


PREREQUISITE_KNOWLEDGE = load_prerequisite_knowledge()

"""Loading and validating knowledge/course_prerequisites.json (read-only: the file is never changed)."""

import json

import pytest

from app.agents.raise_capacity_priority import KNOWLEDGE_DIR
from app.agents.raise_capacity_priority.deterministic.prerequisite_knowledge import (
    PREREQUISITE_KNOWLEDGE,
    load_prerequisite_knowledge,
)

KB_FILE = KNOWLEDGE_DIR / "course_prerequisites.json"


def _data():
    return json.loads(KB_FILE.read_text(encoding="utf-8"))


def _load(tmp_path, data=None, text=None):
    path = tmp_path / "kb.json"
    path.write_text(text if text is not None else json.dumps(data), encoding="utf-8")
    return load_prerequisite_knowledge(path)


def test_all_58_courses_load_with_text_ids():
    assert PREREQUISITE_KNOWLEDGE.program_id == "1501"
    assert len(PREREQUISITE_KNOWLEDGE.courses) == 58
    for cid in ("0201102", "0104100", "1501100", "1502201", "1502202"):
        assert PREREQUISITE_KNOWLEDGE.entry(cid) is not None


def test_standing_thresholds_are_read_from_the_file():
    assert PREREQUISITE_KNOWLEDGE.standing_threshold("Junior Standing") == 65
    assert PREREQUISITE_KNOWLEDGE.standing_threshold("Senior Standing") == 99
    assert PREREQUISITE_KNOWLEDGE.standing_threshold("Sophomore Standing") is None


def test_direct_dependents_are_derived_from_the_requirements():
    dependents = PREREQUISITE_KNOWLEDGE.direct_dependents("1501215")
    assert len(dependents) == 18
    assert {"1501250", "1501263", "1501371", "1501394", "1501458", "1501490"} <= set(dependents)
    assert "1501494" not in dependents  # depends on 1501394, i.e. indirect only
    assert PREREQUISITE_KNOWLEDGE.direct_dependents("1501214") == ["1501250", "1501458", "1501490"]
    assert PREREQUISITE_KNOWLEDGE.direct_dependents("1501494") == []


def test_alternative_ids_outside_the_file_are_kept():
    referenced = {d for d in ("0403201", "1430115", "1501214", "1501247") if PREREQUISITE_KNOWLEDGE.direct_dependents(d)}
    assert referenced == {"0403201", "1430115", "1501214", "1501247"}


def test_the_file_on_disk_is_unchanged_by_loading():
    before = KB_FILE.read_bytes()
    load_prerequisite_knowledge()
    assert KB_FILE.read_bytes() == before


def test_cycle_is_rejected(tmp_path):
    data = _data()
    data["courses"]["1501116"]["requirement"] = {"type": "COURSE", "course_id": "1501211", "concurrent_allowed": False}
    with pytest.raises(ValueError, match="circular"):
        _load(tmp_path, data)


def test_self_reference_is_rejected(tmp_path):
    data = _data()
    data["courses"]["1501116"]["requirement"] = {"type": "COURSE", "course_id": "1501116", "concurrent_allowed": False}
    with pytest.raises(ValueError, match="requires itself"):
        _load(tmp_path, data)


def test_undefined_standing_is_rejected(tmp_path):
    data = _data()
    data["courses"]["1501344"]["requirement"] = {"type": "STANDING", "text": "Sophomore Standing"}
    with pytest.raises(ValueError, match="undefined standing"):
        _load(tmp_path, data)


def test_numeric_course_id_is_rejected(tmp_path):
    data = _data()
    data["courses"]["1501211"]["requirement"] = {"type": "COURSE", "course_id": 1501116, "concurrent_allowed": False}
    with pytest.raises(Exception):
        _load(tmp_path, data)


def test_single_item_group_is_rejected(tmp_path):
    data = _data()
    data["courses"]["1501211"]["requirement"] = {"type": "ANY_OF", "items": [
        {"type": "COURSE", "course_id": "1501116", "concurrent_allowed": False}]}
    with pytest.raises(Exception):
        _load(tmp_path, data)


def test_duplicate_keys_are_rejected(tmp_path):
    text = KB_FILE.read_text(encoding="utf-8").replace(
        '"0202112": {', '"0201102": {"course_name": "x", "prerequisite_status": "VERIFIED", "requirement": null},\n    "0202112": {', 1)
    with pytest.raises(ValueError, match="duplicate"):
        _load(tmp_path, text=text)

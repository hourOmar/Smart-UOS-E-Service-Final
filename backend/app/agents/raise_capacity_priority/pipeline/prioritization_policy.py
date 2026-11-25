"""
Loads the approved prioritization policy (knowledge/prioritization_rules.json) unchanged, to pass
to Gemini ALONGSIDE the evidence package — not embedded inside it. See
app/pipeline/build_prioritization_evidence.py's module docstring for the
reasoning.
"""

import json

from .. import KNOWLEDGE_DIR

_POLICY_PATH = KNOWLEDGE_DIR / "prioritization_rules.json"


def load_prioritization_policy() -> dict:
    with open(_POLICY_PATH, encoding="utf-8") as f:
        return json.load(f)

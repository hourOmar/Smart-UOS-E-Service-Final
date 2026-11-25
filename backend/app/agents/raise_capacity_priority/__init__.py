"""Raise Capacity Request Prioritization Agent.

Assesses the academic urgency of a Raise Capacity request and recommends HIGH,
MEDIUM, LOW or MANUAL_REVIEW to the administrator. It never determines
eligibility, approves or rejects a request, or changes a request.

- Python prepares the evidence: database records (read-only, through the
  backend's own role — db_client.py) and the agent's own validated knowledge
  files in knowledge/ (course_prerequisites.json, course_offerings.json,
  grade_policy.json, prioritization_rules.json). Nothing is read from the web.
- Gemini (through app.core.gemini, with the configured fallback models only
  after a temporary 429/503 error) evaluates the seven factors under the eight
  policy rules and returns the priority, reasoning, seven factor explanations
  and seven factor signals.
- Python validates only the reply's structure and stores a valid reply
  unchanged; it never overrides a recommendation for academic reasons.
  Technical failures are errors, never a priority.

Scope: the knowledge files cover the Computer Science program (1501); a
student in another program (or with none) is identified in the evidence and
Gemini is instructed to return MANUAL_REVIEW.
"""

from pathlib import Path

AGENT_NAME = "raise_capacity_priority"
# The agent's knowledge files (course_offerings.json, grade_policy.json,
# prioritization_rules.json, course_prerequisites.json) live directly here.
KNOWLEDGE_DIR = Path(__file__).resolve().parent / "knowledge"
# 1.1.0: per-factor signals (factor_signals) in the saved result.
# 2.0.0: database study plan and validated local knowledge files replace the
#        UoS web page; text course/program IDs; YES/NO/UNKNOWN availability;
#        no academic enforcement of Gemini's reply.
# 2.0.1: the student's Program row and study plan are selected by
#        (Program_ID, Program_Name), Program's real key, instead of the shared
#        Program_ID alone (which returned an arbitrary program's name).
AGENT_VERSION = "2.0.1"

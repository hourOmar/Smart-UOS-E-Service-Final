"""Raise Capacity Academic Eligibility Evaluation Agent (with its Rejection
Explanation Agent).

Given a Raise Capacity request, Python collects and verifies the evidence and
Gemini recommends APPROVE, REJECT or MANUAL_REVIEW under the agent's own
eligibility policy (knowledge_base/eligibility_policy.json). The recommendation
is advisory: it never changes a request; the administrator decides.

- Evidence: the request, the student (program, completed hours), the
  transcript, the course and the section, read in ONE read-only transaction.
- Three checks: prerequisites and academic standing — evaluated together as ONE
  requirement from the validated knowledge_base/course_prerequisites.json, with
  the evaluator copied from the Raise Capacity Prioritization agent (academic/),
  so both agents evaluate prerequisites identically — and section capacity.
- Program scope: the knowledge covers one program (its program_id); any other
  or missing program is evaluated as MANUAL_REVIEW with no program-specific
  requirement applied.
- Gemini's reply is validated (structure, non-empty explanations, and that the
  recommendation follows the policy for the verified evidence); an invalid
  reply is retried, and a run whose replies all fail is a FAILED run — Python
  never produces a recommendation itself.
- After a validated REJECT, the Rejection Explanation Agent suggests three
  student-facing reasons (formal, concise, supportive) from the confirmed
  failures only; validated template reasons are used if Gemini's are unusable.

Nothing is read from the web. The student's identity is never sent to Gemini.
"""

from pathlib import Path

AGENT_NAME = "raise_capacity_eligibility"
# 2.0.0: validated prerequisite knowledge (no web page), standing from the same
#        requirement, capacity validation, program scope, policy-validated Gemini
#        replies (technical failures are failed runs), rejection explanations.
AGENT_VERSION = "2.0.0"
KNOWLEDGE_DIR = Path(__file__).resolve().parent / "knowledge_base"

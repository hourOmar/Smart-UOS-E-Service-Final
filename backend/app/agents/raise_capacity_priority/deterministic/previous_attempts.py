"""
Factor 5 — previous attempts, derived purely from the PreviousAttemptsSummary
already retrieved (no new query). Only records from terms before the
requested term are previous attempts; same-term and future-term records are
counted separately and never treated as attempts. Grades and the number of
attempts are recorded for transparency only — they must not influence
priority (the prompt says so explicitly).
"""

from ..schemas.academic_history import PreviousAttemptsSummary
from ..schemas.deterministic import PreviousAttemptSummaryEvidence


def build_previous_attempt_summary(
    previous_attempts: PreviousAttemptsSummary,
) -> PreviousAttemptSummaryEvidence:
    records = previous_attempts.records
    earlier = [r for r in records if r.term_relation == "BEFORE_REQUEST_TERM"]
    return PreviousAttemptSummaryEvidence(
        status=previous_attempts.status,
        attempted_before=previous_attempts.attempted_before,
        number_of_attempts=previous_attempts.number_of_attempts,
        previous_grades=[r.grade for r in earlier],
        previous_terms=[r.term for r in earlier],
        excluded_same_term_records=sum(r.term_relation == "REQUEST_TERM" for r in records),
        excluded_future_term_records=sum(r.term_relation == "AFTER_REQUEST_TERM" for r in records),
        unknown_term_records=sum(r.term_relation == "UNKNOWN_TERM" for r in records),
    )

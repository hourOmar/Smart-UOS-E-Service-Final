"""Workflow, failed-run handling and storage (no database, no Gemini)."""

from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from sqlalchemy.exc import DBAPIError

from app.agents.raise_capacity_eligibility import decision, rejection_gemini, repository, review, service, workflow
from app.agents.raise_capacity_eligibility.exceptions import EligibilityReplyInvalidError
from app.core.auth import StaffIdentity
from app.core.gemini import GeminiUnavailableError
from raise_capacity_eligibility.fixtures import decision as reply
from raise_capacity_eligibility.fixtures import evidence, take

STAFF = StaffIdentity(auth_user_id="00000000-0000-0000-0000-0000000000b1", staff_id=100001)
NO_GEMINI_REJECTION = {"status": "unavailable", "error": "no key", "model": None, "suggested_reasons": [],
                       "conflict_note": ""}


def _patch_agent(monkeypatch, ev, *replies):
    monkeypatch.setattr(workflow, "build_evidence_package", lambda rid: ev)
    outcomes = list(replies)

    def fake(prompt, schema, **kwargs):
        outcome = outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome, "model-a"
    monkeypatch.setattr(decision, "generate_structured_with_model", fake)
    monkeypatch.setattr(rejection_gemini, "get_rejection_suggestions", lambda context: NO_GEMINI_REJECTION)


# -- workflow ------------------------------------------------------------------------

def test_reject_result_includes_the_rejection_explanation(monkeypatch):
    _patch_agent(monkeypatch, evidence(transcript=[take("1501211", "F")]), reply("REJECT"))
    result = workflow.evaluate_raise_capacity_request("REQ-1")
    assert result["recommendation"] == "REJECT" and result["gemini_status"] == "ok"
    assert result["rejection_explanation"]["status"] == "fallback"
    assert len(result["rejection_explanation"]["suggested_reasons"]) == 3
    assert result["rejection_model"] is None
    assert result["agent_version"] == "2.0.0"
    assert result["evidence"]["gemini_attempts"] == 1


@pytest.mark.parametrize("kwargs, recommendation", [
    (dict(transcript=[take("1501211", "A")]), "APPROVE"),
    (dict(transcript=[take("1501211", "W")]), "MANUAL_REVIEW"),
    (dict(program="1502"), "MANUAL_REVIEW"),
])
def test_no_rejection_explanation_for_other_recommendations(monkeypatch, kwargs, recommendation):
    _patch_agent(monkeypatch, evidence(**kwargs), reply(recommendation))
    result = workflow.evaluate_raise_capacity_request("REQ-1")
    assert result["recommendation"] == recommendation
    assert result["rejection_explanation"] is None and result["rejection_model"] is None


def test_invalid_replies_raise_and_no_rejection_runs(monkeypatch):
    called = []
    _patch_agent(monkeypatch, evidence(transcript=[take("1501211", "F")]), *[reply("APPROVE")] * 3)
    monkeypatch.setattr(rejection_gemini, "get_rejection_suggestions", lambda c: called.append(c))
    with pytest.raises(EligibilityReplyInvalidError):
        workflow.evaluate_raise_capacity_request("REQ-1")
    assert called == []


# -- service: failed runs ------------------------------------------------------------

class Store:
    def __init__(self):
        self.completed, self.failed = [], []
        self.refuse = None


@pytest.fixture
def store(monkeypatch):
    s = Store()

    @contextmanager
    def tx():
        yield SimpleNamespace()
    monkeypatch.setattr(service, "write_transaction", tx)
    monkeypatch.setattr(service, "check_request", lambda rid: {})
    monkeypatch.setattr(service, "_claim_run", lambda rid, staff, rerun: 7)

    def complete(conn, run_id, result):
        if s.refuse:
            raise s.refuse
        s.completed.append((run_id, result))
        return True

    def fail(conn, run_id, message):
        s.failed.append((run_id, message))
        return True
    monkeypatch.setattr(service.repo, "complete_run", complete)
    monkeypatch.setattr(service.repo, "fail_run", fail)
    return s


def test_gemini_outage_is_a_failed_run_without_a_recommendation(store, monkeypatch):
    def boom(rid):
        raise GeminiUnavailableError("Gemini request failed on every configured model: m: 503")
    monkeypatch.setattr(service, "evaluate_raise_capacity_request", boom)
    outcome = service.ensure_evaluation("REQ-1", STAFF, rerun=True)
    assert outcome.started is True
    assert store.completed == []
    assert store.failed == [(7, "Gemini request failed on every configured model: m: 503")]


def test_invalid_replies_are_a_failed_run(store, monkeypatch):
    def boom(rid):
        raise EligibilityReplyInvalidError("Gemini did not return a valid eligibility recommendation in 3 attempts.")
    monkeypatch.setattr(service, "evaluate_raise_capacity_request", boom)
    service.ensure_evaluation("REQ-1", STAFF, rerun=True)
    assert store.completed == [] and "3 attempts" in store.failed[0][1]


def test_successful_reject_is_saved_with_its_rejection_explanation(store, monkeypatch):
    _patch_agent(monkeypatch, evidence(transcript=[take("1501211", "F")]), reply("REJECT"))
    service.ensure_evaluation("REQ-1", STAFF, rerun=False)
    run_id, result = store.completed[0]
    assert run_id == 7 and result["recommendation"] == "REJECT"
    assert result["rejection_explanation"]["suggested_reasons"]


class _Orig(Exception):
    def __init__(self, sqlstate):
        self.sqlstate = sqlstate
        self.diag = SimpleNamespace(message_primary="column \"rejection_explanation\" does not exist")


def test_missing_rejection_storage_is_reported_as_a_failed_run(store, monkeypatch):
    store.refuse = DBAPIError("UPDATE", {}, _Orig("42703"))
    _patch_agent(monkeypatch, evidence(transcript=[take("1501211", "F")]), reply("REJECT"))
    service.ensure_evaluation("REQ-1", STAFF, rerun=False)
    assert store.completed == []
    assert "rejection explanation storage is not installed" in store.failed[0][1]


def test_other_database_refusals_are_failed_runs_too(store, monkeypatch):
    store.refuse = DBAPIError("UPDATE", {}, _Orig("23514"))
    _patch_agent(monkeypatch, evidence(transcript=[take("1501211", "A")]), reply("APPROVE"))
    service.ensure_evaluation("REQ-1", STAFF, rerun=False)
    assert store.failed[0][1].startswith("The result was not saved: the database refused it")


def test_failed_rerun_keeps_the_previous_successful_result():
    runs = [{"id": 3, "run_status": "failed", "gemini_status": None, "interrupted": False},
            {"id": 2, "run_status": "completed", "gemini_status": "ok", "interrupted": False}]
    summary = service.summarize_runs(runs)
    assert summary["current"]["id"] == 2 and summary["latest_attempt"]["id"] == 3


# -- repository SQL ------------------------------------------------------------------

class FakeConn:
    def __init__(self):
        self.sql, self.params = None, None

    def execute(self, statement, params):
        self.sql, self.params = str(statement), params
        return SimpleNamespace(rowcount=1, mappings=lambda: SimpleNamespace(all=lambda: []))


def _result(recommendation, rejection=None):
    return {"recommendation": recommendation, "reasoning": "r", "checks": {}, "evidence": {}, "gemini_status": "ok",
            "gemini_error": None, "model": "m", "rejection_explanation": rejection, "rejection_model": None}


def test_reject_is_stored_with_the_rejection_columns():
    conn = FakeConn()
    repository.complete_run(conn, 7, _result("REJECT", {"status": "fallback"}))
    assert "rejection_explanation = CAST(:rejection_explanation AS jsonb)" in conn.sql
    assert "rejection_model = :rejection_model" in conn.sql


@pytest.mark.parametrize("recommendation", ["APPROVE", "MANUAL_REVIEW"])
def test_other_results_never_reference_the_rejection_columns(recommendation):
    conn = FakeConn()
    repository.complete_run(conn, 7, _result(recommendation))
    assert "rejection" not in conn.sql


def test_runs_are_listed_even_before_the_rejection_storage_exists():
    conn = FakeConn()
    repository.list_runs(conn, "REQ-1")
    assert "to_jsonb(r) -> 'rejection_explanation'" in conn.sql
    assert "rejection" not in repository._COLUMNS  # never selected as a plain column


# -- review ----------------------------------------------------------------------------

def test_relevant_courses_keep_leading_zeros():
    ev = evidence(course_id="1501252", transcript=[take("0403201", "B")])
    ids = review._relevant_course_ids({"Course_ID": "1501252"}, {"evidence": ev})
    assert ids == ["0403201", "1501252", "1502201"]


def test_relevant_courses_of_runs_stored_before_2_0_0():
    old = {"evidence": {"checks": {"prerequisite": {"required_prerequisite_groups": [[1501211]]}}}}
    assert review._relevant_course_ids({"Course_ID": "1501215"}, old) == ["1501211", "1501215"]


def test_run_view_includes_the_rejection_fields():
    run = {"id": 1, "interrupted": False, "run_status": "completed", "run_trigger": "rerun", "started_at": None,
           "finished_at": None, "recommendation": "REJECT", "reasoning": "r", "check_explanations": {},
           "evidence": {}, "gemini_status": "ok", "gemini_error": None, "model": "m", "agent_version": "2.0.0",
           "error_message": None, "rejection_explanation": {"status": "ok"}, "rejection_model": "rm"}
    view = review._run_view(run)
    assert view["rejection_explanation"] == {"status": "ok"} and view["rejection_model"] == "rm"
    old = {k: v for k, v in run.items() if not k.startswith("rejection")}
    assert review._run_view(old)["rejection_explanation"] is None

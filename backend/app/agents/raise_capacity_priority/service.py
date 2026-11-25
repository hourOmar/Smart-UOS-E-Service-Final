"""Priority behaviour for the staff request list.

States per request (build_state):
  saved            both priority fields hold a valid result (agent-saved or older)
  needs_attention  partial or malformed fields, or an earlier run finished but the
                   fields are empty again: shown as is, never run or overwritten
  running          a run is in progress
  failed           the latest run failed or was interrupted: manual retry only
  not_started      no saved value and no run yet
  not_found        unknown ID or not a Raise Capacity request

- Automatic runs: only In Progress requests with both fields NULL and NO previous
  run of any kind. A read failure raises (503); it never counts as "missing".
- Retry: only after a failed or interrupted run, for In Progress requests.
- Re-evaluation (rerun): only when a valid priority is saved, the request is
  In Progress and no run is in progress. The saved priority stays in place (and
  is shown) until the new run is saved; a failed or discarded re-evaluation
  leaves it unchanged. Needs database/maintenance/raise-capacity-priority/
  04_factor_signals_rerun_install.sql.
- One run per request across all backend processes: the decision to start is
  made under a Postgres advisory lock, and a unique index allows only one
  'running' row per request. Interrupted runs ('running' past the timeout) are
  marked failed during the next claim.
- Results are saved only by agents.save_raise_capacity_priority, which writes
  both fields and completes the run in one transaction: for automatic runs and
  retries only when both fields are NULL; for a re-evaluation only while the
  request is still In Progress (the replaced value is kept on the run).
- Nothing here changes a request's status or decision.
- Each backend process runs at most MAX_PARALLEL_RUNS at once; further eligible
  requests stay not_started and are claimed by a later call.
"""

import logging
import threading
import traceback
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from pydantic import ValidationError
from sqlalchemy.exc import DBAPIError, IntegrityError, SQLAlchemyError

from app.core.auth import StaffIdentity
from app.core.database import DatabaseUnavailableError, is_unique_violation, read_only, write_transaction
from app.core.gemini import GeminiUnavailableError, describe_failure, sanitize

from . import AGENT_VERSION
from . import agent
from . import repository as repo
from .retrieval.errors import RetrievalError
from .schemas.priority_decision import FinalAgentResult

log = logging.getLogger(__name__)

RAISE_CAPACITY = "Raise Capacity"
IN_PROGRESS = "In Progress"
VALID_LEVELS = ("HIGH", "MEDIUM", "LOW", "MANUAL_REVIEW")
MAX_PARALLEL_RUNS = 2

_slots = threading.BoundedSemaphore(MAX_PARALLEL_RUNS)
_executor = ThreadPoolExecutor(max_workers=MAX_PARALLEL_RUNS, thread_name_prefix="priority-run")


class RetryRefusedError(Exception):
    def __init__(self, message: str, state: dict):
        super().__init__(message)
        self.state = state


class BusyError(Exception):
    """This backend process is already running its maximum number of checks."""


class RerunUnavailableError(Exception):
    """The database does not accept re-evaluation runs yet (its update is not installed)."""


# Postgres check_violation: the run-trigger constraint without 'rerun'.
_CHECK_VIOLATION = "23514"


# -- saved fields and state ------------------------------------------------------

def classify_saved(request_id: str, level, result) -> tuple[str, str | None]:
    """('empty' | 'saved' | 'attention', reason)."""
    if level is None and result is None:
        return "empty", None
    if level is None or result is None:
        return "attention", "Only one of the two saved priority fields is filled."
    if level not in VALID_LEVELS:
        return "attention", "The saved priority level is not HIGH, MEDIUM, LOW or MANUAL_REVIEW."
    if not isinstance(result, dict):
        return "attention", "The saved priority details are not a JSON object."
    try:
        # factor_signals are display-only and optional (none before agent 1.1.0);
        # the page checks each one, so they never decide whether a priority shows.
        parsed = FinalAgentResult.model_validate({k: v for k, v in result.items() if k != "factor_signals"})
    except ValidationError:
        return "attention", "The saved priority details are incomplete or malformed."
    if parsed.priority != level:
        return "attention", "The saved priority details do not match the saved priority level."
    if parsed.request_id != request_id:
        return "attention", "The saved priority details belong to a different request."
    return "saved", None


def _run_summary(run: dict) -> dict:
    interrupted = bool(run.get("interrupted"))
    return {
        "id": run["id"],
        "status": "interrupted" if interrupted else run["run_status"],
        "trigger": run["run_trigger"],
        "started_at": run["started_at"],
        "finished_at": run["finished_at"],
        "error_message": repo.INTERRUPTED_MESSAGE if interrupted else run["error_message"],
        "model": run["model"],
        "agent_version": run["agent_version"],
    }


def build_state(request_id: str, record: dict | None, runs: list[dict]) -> dict:
    state = {
        "request_id": request_id, "state": "not_found", "priority": None, "result": None,
        "attention_reason": None, "request_status": None, "can_retry": False, "auto_eligible": False,
        "can_rerun": False, "last_run": _run_summary(runs[0]) if runs else None,
    }
    if record is None or record["request_type"] != RAISE_CAPACITY or not record["has_raise_capacity"]:
        return state
    state["request_status"] = record["current_status"]
    in_progress_request = record["current_status"] == IN_PROGRESS
    active = any(r["run_status"] == "running" and not r["interrupted"] for r in runs)

    kind, reason = classify_saved(request_id, record["priority_level"], record["priority_result"])
    if kind == "saved":
        # A re-evaluation in progress (last_run) leaves the saved result in place.
        return {**state, "state": "saved", "priority": record["priority_level"], "result": record["priority_result"],
                "can_rerun": in_progress_request and not active}
    if kind == "attention":
        return {**state, "state": "needs_attention", "attention_reason": reason}

    if active:
        return {**state, "state": "running"}
    if not runs:
        return {**state, "state": "not_started", "auto_eligible": in_progress_request}
    latest = runs[0]
    if latest["run_status"] == "failed" or (latest["run_status"] == "running" and latest["interrupted"]):
        return {**state, "state": "failed", "can_retry": in_progress_request}
    return {**state, "state": "needs_attention",
            "attention_reason": "An earlier check finished, but both saved priority fields are empty now."}


def _unique(request_ids: list[str]) -> list[str]:
    return list(dict.fromkeys(request_ids))


def read_states(request_ids: list[str]) -> list[dict]:
    """Raises on any read failure; never reports an unreadable request as missing."""
    ids = _unique(request_ids)
    with read_only() as conn:
        records = repo.read_requests(conn, ids)
        runs = repo.list_runs(conn, ids)
    return [build_state(rid, records.get(rid), runs.get(rid, [])) for rid in ids]


# -- starting runs ------------------------------------------------------------------

def _claim(request_id: str, staff: StaffIdentity, trigger: str) -> tuple[int | None, dict | None]:
    """Under the request's lock: (new run id, None) when the run may start, else
    (None, the state that refused it)."""
    try:
        with write_transaction() as conn:
            repo.lock_request(conn, request_id)
            repo.expire_interrupted_runs(conn, request_id)
            record = repo.read_requests(conn, [request_id]).get(request_id)
            runs = repo.list_runs(conn, [request_id]).get(request_id, [])
            state = build_state(request_id, record, runs)
            allowed = {"automatic": state["auto_eligible"], "retry": state["can_retry"],
                       "rerun": state["can_rerun"]}[trigger]
            if not allowed:
                return None, state
            return repo.start_run(conn, request_id, trigger, staff.auth_user_id, staff.staff_id, AGENT_VERSION), None
    except IntegrityError as exc:
        # Another process claimed it between our check and insert (cannot happen while
        # every caller takes the lock, but the unique index makes it safe regardless).
        if is_unique_violation(exc):
            return None, None
        if trigger == "rerun" and getattr(getattr(exc, "orig", None), "sqlstate", None) == _CHECK_VIOLATION:
            raise RerunUnavailableError(
                "Priority re-evaluation is not available yet: the database update for it is not installed."
            ) from exc
        raise


def _dispatch(run_id: int, request_id: str) -> None:
    _executor.submit(_execute_and_release, run_id, request_id)


def _execute_and_release(run_id: int, request_id: str) -> None:
    try:
        execute_run(run_id, request_id)
    finally:
        _slots.release()


def start_automatic(request_ids: list[str], staff: StaffIdentity) -> dict:
    """Starts runs for eligible requests (up to the free slots); returns every
    request's state afterwards and the IDs started by this call."""
    ids = _unique(request_ids)
    started: list[str] = []
    for state in read_states(ids):
        if not state["auto_eligible"]:
            continue
        if not _slots.acquire(blocking=False):
            break
        try:
            run_id, _refused = _claim(state["request_id"], staff, "automatic")
        except BaseException:
            _slots.release()
            raise
        if run_id is None:
            _slots.release()
            continue
        started.append(state["request_id"])
        _dispatch(run_id, state["request_id"])
    return {"priorities": read_states(ids), "started": started}


def _start_manual(request_id: str, staff: StaffIdentity, trigger: str) -> dict:
    """A staff-requested run ('retry' or 'rerun'); raises when it may not start."""
    if not _slots.acquire(blocking=False):
        raise BusyError("Other priority checks are still running. Try again shortly.")
    try:
        run_id, refused = _claim(request_id, staff, trigger)
    except BaseException:
        _slots.release()
        raise
    if run_id is None:
        _slots.release()
        state = refused or read_states([request_id])[0]
        raise RetryRefusedError(_rerun_refusal(state) if trigger == "rerun" else _refusal(state), state)
    _dispatch(run_id, request_id)
    return read_states([request_id])[0]


def retry(request_id: str, staff: StaffIdentity) -> dict:
    """Manual retry after a failed or interrupted run."""
    return _start_manual(request_id, staff, "retry")


def rerun(request_id: str, staff: StaffIdentity) -> dict:
    """Re-evaluates a saved priority (In Progress requests only). The saved
    priority stays in place until the new result is saved."""
    return _start_manual(request_id, staff, "rerun")


def _rerun_refusal(state: dict) -> str:
    if state["state"] == "running" or (state["state"] == "saved" and state["request_status"] == IN_PROGRESS):
        return "A priority check is already running for this request."
    if state["state"] in ("saved", "failed", "not_started") and state["request_status"] != IN_PROGRESS:
        return "Only In Progress requests are re-evaluated."
    if state["state"] == "failed":
        return "The latest priority check failed; use Retry instead."
    if state["state"] == "needs_attention":
        return "The saved priority needs attention; it is never rerun or overwritten automatically."
    return "This request has no saved priority to re-evaluate."


def _refusal(state: dict) -> str:
    match state["state"]:
        case "saved":
            return "A priority is already saved for this request."
        case "needs_attention":
            return "The saved priority needs attention; it is never rerun or overwritten automatically."
        case "running":
            return "A priority check is already running for this request."
        case "not_started" if state["auto_eligible"]:
            return "This request has not been checked yet; it is checked automatically."
    if state["request_status"] != IN_PROGRESS:
        return "Only In Progress requests are checked."
    return "This request cannot be retried now."


# -- running ----------------------------------------------------------------------

def _failure_message(exc: Exception, run_id: int, request_id: str) -> str:
    """Safe to store and show to staff: sanitized, no evidence values."""
    if isinstance(exc, GeminiUnavailableError):
        return str(exc)
    if isinstance(exc, RetrievalError):
        return f"Evidence could not be collected: {sanitize(str(exc))}"
    if isinstance(exc, ValidationError):
        fields = ", ".join(".".join(str(p) for p in e["loc"]) for e in exc.errors()[:3])
        return f"Evidence did not have the expected shape ({fields})."
    if isinstance(exc, DatabaseUnavailableError):
        return "The database could not be reached while collecting evidence."
    if isinstance(exc, SQLAlchemyError):
        return f"The database refused a read while collecting evidence ({type(exc).__name__})."
    # Code locations only: a full traceback could carry evidence values.
    frames = traceback.extract_tb(exc.__traceback__)[-4:]
    where = " <- ".join(f"{Path(f.filename).name}:{f.lineno} {f.name}" for f in reversed(frames))
    log.error("Priority run %s for %s failed unexpectedly: %s at %s", run_id, request_id, describe_failure(exc), where)
    return f"Unexpected error during the priority check ({type(exc).__name__})."


def _record_failure(run_id: int, request_id: str, message: str) -> None:
    try:
        with write_transaction() as conn:
            stored = repo.fail_run(conn, run_id, message)
    except Exception as exc:  # noqa: BLE001 - the run will show as interrupted after the timeout
        log.error("Priority run %s for %s: failure could not be recorded (%s)", run_id, request_id, describe_failure(exc))
        return
    if not stored:
        log.warning("Priority run %s for %s was no longer running when it failed.", run_id, request_id)


def execute_run(run_id: int, request_id: str) -> str:
    """Runs the agent for a claimed run and records the outcome: 'saved',
    'discarded', 'not_running' or 'failed'."""
    try:
        outcome = agent.prioritize_raise_capacity_request(request_id)
    except Exception as exc:  # noqa: BLE001 - recorded as a failed run, never left 'running'
        message = _failure_message(exc, run_id, request_id)
        log.warning("Priority run %s for %s failed: %s", run_id, request_id, message)
        _record_failure(run_id, request_id, message)
        return "failed"

    try:
        with write_transaction() as conn:
            saved = repo.save_result(
                # exclude_none: a result without signals is saved without the key
                # (the database accepts it absent, never as null).
                conn, run_id, outcome.result.priority, outcome.result.model_dump(mode="json", exclude_none=True),
                outcome.evidence.model_dump(mode="json"), outcome.model,
            )
    except DBAPIError as exc:
        diag = getattr(getattr(exc, "orig", None), "diag", None)
        detail = sanitize(getattr(diag, "message_primary", None) or type(exc).__name__)
        message = f"The result was not saved: the database refused it ({detail})."
        log.warning("Priority run %s for %s: %s", run_id, request_id, message)
        _record_failure(run_id, request_id, message)
        return "failed"
    except DatabaseUnavailableError:
        message = "The result was not saved: the database could not be reached."
        log.warning("Priority run %s for %s: %s", run_id, request_id, message)
        _record_failure(run_id, request_id, message)
        return "failed"

    if saved == "discarded":
        log.info("Priority run %s for %s: a value was already present; it was kept.", run_id, request_id)
    elif saved == "not_running":
        log.warning("Priority run %s for %s was no longer running when it finished; result discarded.",
                    run_id, request_id)
    return saved

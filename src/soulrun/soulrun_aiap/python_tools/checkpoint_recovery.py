"""ACP transport recovery policy for the v7 engine (host contract: soulbot.engine_hooks).

  find_cache_dir(root, session_id, include_terminal=False) -> Path | None
  handle_runner_recovery(root, request, resume_mode=None) -> dict(action, reason, failure_point_id, recovery_token,
                                               attempt, max_attempts, delay_seconds, prompt, question_id, public_text, next_probe_seconds, supply)

Phases (soulbot.agents.recovery): plan -> start -> complete | cancel | delivered. Policy (doc 01 §4.2 crash
re-entry; AIAP.md runtime.crash_recovery): three attempts with 10 / 30 / 60 second backoff; a fourth
interruption never marks the run FAILED (alpha.105, doc 259). The resume switch decides (prepare_cache.RESUME_INTERRUPTED_ENV;
resume_mode, passed by the host; default = prepare_cache.resume_interrupted_enabled): true - the run
waits and the host probes and re-enters by itself (action "wait"); false - a supply question is opened
for the human (action "ask"); while a wait is on, a failed probe holds (action "hold") until the host
probes again. State lives in the machine index (run_state) plus a sidecar _recovery.json; the resume
prompt only tells the model to call next-node again, because the engine holds every byte of run state.
"""
from __future__ import annotations

import json
import re
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib import engine_core  # noqa: E402
from lib.run_store import RunStore, RunStoreError, atomic_write_bytes, dumps, now_iso  # noqa: E402

CACHE_DIRNAME = ".execution_cache"
RECOVERY_FILE = "_recovery.json"
MAX_ATTEMPTS = 3
BACKOFF_SECONDS = (10.0, 30.0, 60.0)
TERMINAL = ("COMPLETED", "ABANDONED", "FAILED")
MID_RUN_TURN_END_ERROR_CODE = "TURN_ENDED_MID_RUN"   # alpha.104 (doc 255 final_plan §3.8): not a transport error - a stopped judge / question turn is never replayed for it


def _stop_status(cache_dir: Path) -> dict:
    """alpha.104 (doc 255 final_plan §3.5 E4, doc 256 E4): the engine's read-only view of a human Stop; never open on any error."""
    try:
        from lib import stop_state  # noqa: PLC0415 - imported lazily to keep this module light (as prepare_cache does for this one)
        return stop_state.stop_status(cache_dir)
    except Exception:  # noqa: BLE001 - a broken lifecycle must not break the recovery policy
        return {"open": False, "stop_id": None, "state": None, "judge_id": None, "gate": None, "gate_delivered": False}


def _supply_status(cache_dir: Path) -> dict | None:
    """alpha.105 (doc 259 spec §1.8): the engine's read-only view of the run's supply record; None on any error (as _stop_status)."""
    try:
        from lib import stop_state  # noqa: PLC0415
        return stop_state.supply_status(cache_dir)
    except Exception:  # noqa: BLE001
        return None


def _lifecycle_entry_mode(cache_dir: Path) -> str | None:
    """alpha.105: the lifecycle's entry_mode of the last bootstrap (supply_wait / supply_hold name the text-only turns); None on any error."""
    try:
        from lib import stop_state  # noqa: PLC0415
        return stop_state.read_lifecycle(cache_dir).get("entry_mode")
    except Exception:  # noqa: BLE001
        return None


def _resume_mode_default() -> bool:
    """Use the Engine reader; missing or broken policy cannot grant re-entry."""
    try:
        from lib import supply_flow  # noqa: PLC0415
        return supply_flow.resume_mode_default() is True
    except Exception:  # noqa: BLE001
        return False


def _open_reason(stopped: dict) -> str:
    """alpha.105: a run fenced by a question the host opened (supply / restart) is not "stopped by the human"; the human stop string is unchanged."""
    return "run_question_open" if stopped.get("requested_by") in ("supply", "restart") else "run_stopped_by_human"


def _stop_replay_allowed(stopped: dict, state: dict, error_code: str) -> dict | None:
    """final_plan §3.8: a judge turn (JUDGING) or an undelivered stop question (GATED) that died of a transport error is replayed once per
    judge / question: the marker returned here is kept on the attempt, and a second attempt with the same marker is refused.
    alpha.105 (doc 259 spec §4.2 S-6): a supply / restart question was posted by the host itself, not by a turn that died - never replayed."""
    if error_code == MID_RUN_TURN_END_ERROR_CODE or stopped.get("requested_by") in ("supply", "restart"):
        return None
    if not (stopped.get("state") == "JUDGING" or (stopped.get("state") == "GATED" and not stopped.get("gate_delivered"))):
        return None
    marker = {"stop_id": stopped.get("stop_id"), "judge_id": stopped.get("judge_id"), "question_id": (stopped.get("gate") or {}).get("question_id")}
    if any(a.get("stop_replay") == marker for a in state["attempts"]):
        return None
    return marker


def _index(cache_dir: Path) -> dict | None:
    try:
        return RunStore(cache_dir).read_index()
    except RunStoreError:
        return None


def find_cache_dir(root: str | Path, session_id: str, include_terminal: bool = False, *, recovery_token: str | None = None) -> Path | None:
    cache_root = Path(root).resolve() / CACHE_DIRNAME
    if not cache_root.is_dir():
        return None
    dirs = sorted((p for p in cache_root.iterdir() if p.is_dir() and re.fullmatch(r"\d+", p.name)), key=lambda p: int(p.name))
    for path in reversed(dirs):
        index = _index(path)
        if not index or index.get("session_id") != session_id:
            continue
        if not include_terminal and index["run_state"] in TERMINAL:
            continue
        if recovery_token and not any(a.get("token") == recovery_token for a in _read_state(path)["attempts"]):
            continue
        return path
    return None


def _read_state(cache_dir: Path) -> dict:
    try:
        return json.loads((cache_dir / RECOVERY_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"attempts": [], "active_token": None}


def _write_state(cache_dir: Path, state: dict) -> None:
    atomic_write_bytes(cache_dir / RECOVERY_FILE, dumps(state).encode("utf-8"))


def _progress_mark(index: dict) -> dict:
    """Where the run stands (doc 18 §1.3): committed-node count plus the current occurrence. Two recovery attempts
    planned against the same mark made no progress between them; a different mark means the previous re-entry
    advanced the run and the attempt budget starts again."""
    return {"completed": len(index.get("completed") or []), "node": index["current"]["name"], "visit": index["current"]["visit"]}


def _decision(action: str, reason: str, **fields) -> dict:
    base = {"action": action, "reason": reason, "failure_point_id": None, "recovery_token": None,
            "attempt": 0, "max_attempts": MAX_ATTEMPTS, "delay_seconds": 0.0, "prompt": "",
            "question_id": None, "public_text": "", "next_probe_seconds": None, "supply": None}   # alpha.105 (doc 259 spec §1.8): the host maps these four
    base.update(fields)
    return base


def _first_attempt_at_mark(state: dict, mark: dict) -> str | None:
    """alpha.105: scheduled_at of the oldest attempt at this progress mark - the run has been dead since that first quick retry was scheduled."""
    return next((a.get("scheduled_at") for a in state["attempts"] if a.get("progress_mark") == mark), None)


def _supply_exhausted(cache_dir, index, state, *, error_code, request, node, attempt, resume_mode: bool) -> dict:
    """alpha.105 (doc 259 spec §1.8): the quick retries are exhausted at this mark - never fatal. A record already waiting at the same mark
    (a probe, a re-entry) is one more failed probe -> `hold` with backoff; otherwise the mode decides: true -> an AUTHORIZED record and `wait`
    (one notice, no question), false -> a supply question and `ask`. A fourth TURN_ENDED_MID_RUN takes the same exits with kind turn_ended."""
    from lib import supply_flow, stop_state  # noqa: PLC0415
    details = dict(getattr(request, "error_details", None) or {})
    human_turn = str((details.get("host_turn") or {}).get("type") or "user") not in supply_flow.MACHINE_TURN_TYPES
    invocation_id = str(getattr(request, "invocation_id", "") or "")
    supply = stop_state.supply_status(cache_dir)          # carries progress_mark (spec §1.1)
    mark = _progress_mark(index)
    if supply and supply["state"] in stop_state.SUPPLY_WAITING_STATES and supply.get("progress_mark") == mark:   # a probe (or a re-entry) failed while a wait is on: either mode
        outcome = supply_flow.record_probe_failure(cache_dir, error_code=error_code, invocation_id=invocation_id, human_turn=human_turn)
        if error_code == MID_RUN_TURN_END_ERROR_CODE and outcome.get('attempts',0) >= MAX_ATTEMPTS:
            opened=supply_flow.ask_no_progress(cache_dir,index,attempts=outcome['attempts'],
                invocation_id=invocation_id,since=supply.get('since'))
            return _decision('ask','ENGINE_NO_PROGRESS',failure_point_id=node,attempt=attempt,
                question_id=opened.get('question_id'),public_text=opened.get('public_block_ref',''),supply=stop_state.supply_status(cache_dir))
        text = supply_flow.hold_notice(cache_dir, outcome) if (human_turn or outcome["state"] == "WAIT_EXPIRED") else ""   # the wait_expired notice is posted whoever's turn expired the wait
        return _decision("hold", "SUPPLY_WAITING" if outcome["state"] == "AUTHORIZED" else "SUPPLY_WAIT_EXPIRED", failure_point_id=node, attempt=attempt,
                         question_id=supply.get("question_id"), public_text=text, next_probe_seconds=outcome.get("next_probe_seconds"), supply=stop_state.supply_status(cache_dir))
    since = _first_attempt_at_mark(state, mark) or index.get("updated_at")
    if error_code == MID_RUN_TURN_END_ERROR_CODE:      # alpha.105: four mid-run turn ends at one mark - no transport error, same exit, never fatal
        details = {**details, "supply_kind": supply_flow.TURN_ENDED_KIND, "supply_text": None, "supply_reset_text": None}
    if resume_mode:   # ---- mode true (doc 259 §1): wait and re-enter by itself; one notice, no question
        waiting = supply_flow.open_supply_wait(cache_dir, index, error_code=error_code, error_details=details, invocation_id=invocation_id,
                                               attempts=MAX_ATTEMPTS, progress_mark=mark, since=since)
        if waiting["status"] != "WAITING":   # a stop was opened meanwhile (a human Stop during the quick retries): the human decides
            return _decision("hold", "SUPPLY_QUESTION_OPEN", failure_point_id=node, attempt=attempt, question_id=waiting.get("question_id"))
        return _decision("wait", "SUPPLY_WAITING", failure_point_id=node, attempt=attempt, question_id=None,
                         public_text=waiting["public_text"], next_probe_seconds=waiting["next_probe_seconds"], supply=waiting["supply"])
    # ---- mode false: ask the human
    opened = supply_flow.open_supply_question(cache_dir, index, error_code=error_code, error_details=details, invocation_id=invocation_id,
                                              attempts=MAX_ATTEMPTS, progress_mark=mark, since=since)
    if opened["status"] != "OPENED":   # a stop or question was opened meanwhile: hold, re-post nothing
        return _decision("hold", "SUPPLY_QUESTION_OPEN", failure_point_id=node, attempt=attempt, question_id=opened.get("question_id"))
    return _decision("ask", "SUPPLY_INTERRUPTED", failure_point_id=node, attempt=attempt, question_id=opened["question_id"],
                     public_text=opened["public_block_ref"], supply=opened["supply"])


def build_resume_prompt(cache_dir: Path, engine_dir: Path, index: dict, error_code: str, attempt: int) -> str:
    return (
        "[EXECUTE ENGINE RECOVERY]\n"
        f"engine_dir: {engine_dir}\n"
        f"cache_dir: {cache_dir}\n"
        f"interrupted_by: {error_code} (attempt {attempt}/{MAX_ATTEMPTS})\n"
        f"current_node: {index['current']['name']} (visit {index['current']['visit']})\n"
        "The engine kept every byte of run state. Do not restart and do not summarise. "
        f"FIRST ACTION: run python {engine_dir / 'python_tools' / 'next_node.py'} --cache-dir {cache_dir} ; "
        "follow its actual resume.kind and serve_no: an unserved successor may be fresh/1, not re_serve. "
        "Never replay a committed node. Execute only the returned node's remaining steps, then node-commit. "
        "If the reply is WAITING_USER, re-present its public prompt and end the turn."
    )


def handle_runner_recovery(root: str | Path, request, *, resume_mode: bool | None = None) -> dict:
    """resume_mode (alpha.105, doc 259 §0.0): the resume switch (prepare_cache.RESUME_INTERRUPTED_ENV) as the host read it; None -> the
    engine's own reader. Used only by the exhaustion branch (_supply_exhausted); every other phase and return is unchanged."""
    engine_dir = Path(root).resolve()
    phase = getattr(request, "phase", "plan")
    session_id = getattr(request, "session_id", "") or ""
    error_code = getattr(request, "error_code", "") or "ACP_UNKNOWN"
    mode = _resume_mode_default() if resume_mode is None else resume_mode is True
    token_in = getattr(request, "recovery_token", None)
    settling = phase in ("complete", "cancel")
    cache_dir = find_cache_dir(engine_dir, session_id, include_terminal=settling,
                              recovery_token=token_in if settling else None)
    if cache_dir is None:
        return _decision("stop", "no_active_engine_run")
    index = _index(cache_dir)
    if index is None:
        return _decision("stop", "engine_index_unreadable")
    try:
        engine_core.program_guard.assert_run_version(index)
    except engine_core.EngineError as exc:
        return _decision('stop', exc.code, message=exc.message)
    state = _read_state(cache_dir)
    node = index["current"]["name"]
    stopped = _stop_status(cache_dir)

    if phase == "plan":
        from lib import tool_faults
        fault_question=tool_faults.pending_question(cache_dir,index,str(getattr(request,'invocation_id','') or ''))
        if fault_question:
            return _decision('ask','ENGINE_FAULT_PAUSED',failure_point_id=node,question_id=fault_question['question_id'],
                public_text=fault_question['public_block_ref'],supply=_supply_status(cache_dir))
        supply_view = _supply_status(cache_dir) or {}
        if error_code == MID_RUN_TURN_END_ERROR_CODE and supply_view.get("state") in ("AUTHORIZED", "WAIT_EXPIRED") \
                and _lifecycle_entry_mode(cache_dir) in ("supply_wait", "supply_hold"):   # alpha.105: a text-only wait / hold turn is not a mid-run end (supply_flow.TEXT_ONLY_ENTRY_MODES)
            return _decision("stop", "supply_wait_pending", failure_point_id=node)
        replay = None
        if stopped["open"] and index["run_state"] in ("RUNNING", "WAITING_USER"):   # alpha.104 (doc 256 E4): a stopped run waits for the human
            replay = _stop_replay_allowed(stopped, state, error_code)
            if not replay:
                return _decision("stop", _open_reason(stopped), failure_point_id=node)
        if index["run_state"] == "WAITING_USER" and not replay:   # unchanged decision for an unstopped run at a gate
            return _decision("stop", "run_waiting_for_human_answer", failure_point_id=node)
        mark = _progress_mark(index)
        consecutive = 0   # doc 18: count only the attempts made at this very point of progress, newest first
        for prior in reversed(state["attempts"]):
            if prior.get("progress_mark") == mark:
                consecutive += 1
            else:
                break
        attempt = consecutive + 1
        if stopped["open"]:   # alpha.104 (final_plan §3.8): a stopped run is never terminated by the host - past the budget it just waits for the human
            if attempt > MAX_ATTEMPTS:
                return _decision("stop", _open_reason(stopped), failure_point_id=node, attempt=attempt)
        elif attempt > MAX_ATTEMPTS:   # alpha.105 (doc 259): never fatal - wait by itself (mode true), ask the human (mode false), or hold while a wait is on
            state["exhausted_at"] = now_iso()
            _write_state(cache_dir, state)
            return _supply_exhausted(cache_dir, index, state, error_code=error_code, request=request, node=node, attempt=attempt, resume_mode=mode)
        token = f"rt-{secrets.token_hex(6)}"
        delay = BACKOFF_SECONDS[min(attempt, len(BACKOFF_SECONDS)) - 1]
        state["attempts"].append({"token": token, "attempt": attempt, "error_code": error_code, "scheduled_at": now_iso(),
                                  "node": node, "delay_seconds": delay, "outcome": None, "progress_mark": mark, "stop_replay": replay})
        state["active_token"] = token
        _write_state(cache_dir, state)
        return _decision("resume", f"engine_checkpoint_resume:{node}", failure_point_id=node, recovery_token=token,
                         attempt=attempt, delay_seconds=delay)

    entry = next((a for a in reversed(state["attempts"]) if a["token"] == token_in), None) if token_in else None
    if phase == "start":
        if entry is None:
            return _decision("stop", "recovery_token_unknown")
        if stopped["open"] and not entry.get("stop_replay"):   # alpha.104 (doc 256 E4)
            return _decision("stop", _open_reason(stopped), failure_point_id=node)
        if index["run_state"] == "WAITING_USER" and not entry.get("stop_replay"):   # a stopped WAITING_USER run with an undelivered stop menu is the replay case
            return _decision("stop", "run_waiting_for_human_answer", failure_point_id=node)
        if index["run_state"] in TERMINAL:
            return _decision("stop", f"run_already_{index['run_state'].lower()}")
        entry["started_at"] = now_iso()
        _write_state(cache_dir, state)
        return _decision("resume", f"engine_checkpoint_start:{node}", failure_point_id=node, recovery_token=token_in,
                         attempt=entry["attempt"], prompt=build_resume_prompt(cache_dir, engine_dir, index, error_code, entry["attempt"]))
    if phase == "complete":
        if entry is not None and entry.get("outcome") is None:
            entry["outcome"] = "completed"
            entry["completed_at"] = now_iso()
            if state["active_token"] == token_in:
                state["active_token"] = None
            _write_state(cache_dir, state)
        return _decision("completed", "engine_checkpoint_recovered", failure_point_id=node, recovery_token=token_in,
                         attempt=entry["attempt"] if entry else 0)
    if phase == "cancel":
        if entry is not None and entry.get("outcome") is None:
            entry["outcome"] = f"cancelled:{getattr(request, 'cancel_reason', None) or 'unspecified'}"
            entry["cancelled_at"] = now_iso()
            if state["active_token"] == token_in:
                state["active_token"] = None
            _write_state(cache_dir, state)
        return _decision("stop", f"recovery_cancelled:{getattr(request, 'cancel_reason', None) or 'unspecified'}",
                         failure_point_id=node, recovery_token=token_in)
    if phase == "delivered":   # alpha.105 (doc 259 spec §1.8): the runner posted the question's menu reference - stamp its delivery
        qid = str((getattr(request, "error_details", None) or {}).get("question_id") or "")
        if stopped["open"] and (stopped.get("gate") or {}).get("question_id") == qid:
            from lib import stop_flow  # noqa: PLC0415
            marked = stop_flow.mark_stop_menu_delivered(cache_dir, stopped["stop_id"])
            return _decision("completed", f"question_delivered:{marked.get('status')}", failure_point_id=node, question_id=qid)
        return _decision("stop", "question_not_open", failure_point_id=node, question_id=qid)
    return _decision("stop", f"unknown_phase:{phase}")

"""alpha.104 (04 series doc 255 final_plan §2.2, doc 256 E0): the read-only view of a human Stop on a run.

A Web UI Stop no longer terminates the engine run: the host writes a stop record into the run's `_host_lifecycle.json` under
"stop" (resolved records under "stops"), the run stays RUNNING / WAITING_USER, and the executor's decision for the current judge
lives in `_stop/<stop_id>.<judge_id>.json`. This module computes the EFFECTIVE state (the recorded state with that decision file
applied, never written back) for prepare_cache, next_node, node_commit, checkpoint_recovery and the host's engine_view.

Standard library only and never writes: the host loads it by path from the app's own engine dir, so no `lib.*` import may appear here.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

HOST_LIFECYCLE = "_host_lifecycle.json"      # the same file prepare_cache.HOST_LIFECYCLE names
STOP_KEY = "stop"
STOPS_KEY = "stops"
STOP_DIR = "_stop"                            # <cache_dir>/_stop/<stop_id>.<judge_id>.json
OPEN_STATES = ("OPEN", "JUDGING", "GATED", "HANDOVER")
STOP_ID_RE = re.compile(r"^s-\d+$")
JUDGE_ID_RE = re.compile(r"^j\d+$")
FENCE_CODE = "RUN_STOPPED_BY_HUMAN"
SUPPLY_KEY = "supply"                         # alpha.105 (doc 259 spec §1.3): the supply record of a run whose model supply was interrupted
SUPPLIES_KEY = "supplies"                     # ... its closed records (max 20)
QUESTION_SOURCES = ("supply_doubt", "restart_doubt", "execution_doubt")
SUPPLY_STATES = ("ASKED", "AUTHORIZED", "RESUMED", "ENDED", "WAIT_EXPIRED")
SUPPLY_WAITING_STATES = ("AUTHORIZED", "WAIT_EXPIRED")
_GATE_VIEW_KEYS = ("question_id", "state", "delivered_at", "form", "opened_by", "source", "opened_at")
_PROBE_VIEW_KEYS = ("attempts", "next_at", "started_at", "last_error_code", "last_failed_at")


def _read_json(path: Path) -> dict | None:
    """One read_text, parsed; None on any error or a non-object. Safe against the atomic replace the writers use."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def read_lifecycle(cache_dir) -> dict:
    return _read_json(Path(cache_dir) / HOST_LIFECYCLE) or {}


def read_index_plain(cache_dir) -> dict | None:
    """The run index as plain JSON (never schema-validated, never through the engine lock)."""
    return _read_json(Path(cache_dir) / "_index.json")


def decision_path(cache_dir, stop_id: str, judge_id: str) -> Path:
    return Path(cache_dir) / STOP_DIR / f"{stop_id}.{judge_id}.json"


def read_decision(cache_dir, stop_id, judge_id) -> dict | None:
    """The executor's decision file for (stop_id, judge_id); None when absent, unreadable or the ids are malformed."""
    if not (isinstance(stop_id, str) and STOP_ID_RE.match(stop_id) and isinstance(judge_id, str) and JUDGE_ID_RE.match(judge_id)):
        return None
    return _read_json(decision_path(cache_dir, stop_id, judge_id))


def _resolved(life: dict) -> list[dict]:
    rows = []
    for r in life.get(STOPS_KEY) or []:
        if not isinstance(r, dict):
            continue
        res = r.get("resolution") if isinstance(r.get("resolution"), dict) else {}
        rows.append({"stop_id": r.get("stop_id"), "kind": res.get("kind"), "by": res.get("by"), "at": res.get("at"),
                     "question_id": res.get("question_id"), "judge_id": res.get("judge_id")})
    return rows


def stop_status(cache_dir) -> dict:
    """The effective stop state of a run (doc 256 E0). `open` is true for a recorded OPEN / JUDGING / GATED / HANDOVER stop, except
    JUDGING whose current judge was accepted `continue` (the run went on; the next lifecycle writer resolves the record); JUDGING with an
    accepted `ask` reads as GATED with that gate. Every key is present; None / [] / False when unknown."""
    life = read_lifecycle(cache_dir)
    stop = life.get(STOP_KEY)
    stop = stop if isinstance(stop, dict) else None
    recorded_state = stop.get("state") if stop else None
    judge = (stop.get("judge") if stop else None) or {}
    judge_id = judge.get("judge_id") if isinstance(judge, dict) else None
    gate = stop.get("gate") if stop else None
    decision = None
    state = recorded_state if recorded_state in OPEN_STATES else None
    if state == "JUDGING" and judge_id:
        acc = (read_decision(cache_dir, stop.get("stop_id"), judge_id) or {}).get("accepted")
        if isinstance(acc, dict):
            decision = {"judge_id": judge_id, "decision": acc.get("decision"), "accepted_at": acc.get("at"), "recommendation": acc.get("recommendation")}
            if acc.get("decision") == "continue":
                state = None
            elif acc.get("decision") == "ask":
                state = "GATED"
                if gate is None:
                    gate = acc.get("gate")
    gate = gate if isinstance(gate, dict) else None
    stop = stop or {}
    return {
        "open": state in OPEN_STATES,
        "stop_id": stop.get("stop_id"),
        "state": state,
        "recorded_state": recorded_state,
        "judge_id": judge_id,
        "decision": decision,
        "gate": {k: gate.get(k) for k in _GATE_VIEW_KEYS} if gate else None,
        "gate_delivered": bool(gate.get("delivered_at")) if gate else False,
        "run_state_at_stop": stop.get("run_state_at_stop"),
        "requested_at": stop.get("requested_at"),
        "node": stop.get("node"),
        "visit": stop.get("visit"),
        "restops": int(stop.get("restops") or 0),
        "host_run_ids": list(stop.get("host_run_ids") or []),
        "write_after_stop": stop.get("write_after_stop"),
        "machine_messages": len(stop.get("machine_messages") or []),
        "resolved": _resolved(life),
        # alpha.105 (doc 259 spec §1.1): who requested the stop ("host" = the human, "supply" / "restart" = a question the host opened), the
        # interruption anchor of a question, and the question's source while it is GATED
        "requested_by": stop.get("requested_by"),
        "wait_since": stop.get("wait_since"),
        "question_source": gate.get("source") if (state == "GATED" and gate and gate.get("source") in QUESTION_SOURCES) else None,
    }


def supply_status(cache_dir) -> dict | None:
    """alpha.105 (doc 259 spec §1.1): the read-only projection of the run's supply record (lifecycle "supply"), exactly 19 keys; None when the
    run never lost its supply. `progress_mark` is what checkpoint_recovery compares with the current mark (a different mark = a new incident);
    `authorized_by` ("switch" / "human:<question_id>" / "human:wait") and `resume_mode` (the switch in force when the record was written) tell
    who authorized the wait. Missing fields read as None / 0."""
    life = read_lifecycle(cache_dir)
    supply = life.get(SUPPLY_KEY)
    if not isinstance(supply, dict):
        return None
    probe = supply.get("probe") if isinstance(supply.get("probe"), dict) else {}
    mark = supply.get("progress_mark")
    return {
        "state": supply.get("state"),
        "since": supply.get("since"),
        "kind": supply.get("kind"),
        "text": supply.get("text"),
        "error_code": supply.get("error_code"),
        **({'error_summary': supply['error_summary']} if supply.get('error_summary') else {}),
        "reset_at": supply.get("reset_at"),
        "attempts": int(supply.get("attempts") or 0),
        "question_id": supply.get("question_id"),
        "progress_mark": dict(mark) if isinstance(mark, dict) else None,
        "restart_question_id": supply.get("restart_question_id"),
        "authorized_at": supply.get("authorized_at"),
        "authorized_by": supply.get("authorized_by"),
        "resume_mode": supply.get("resume_mode") if isinstance(supply.get("resume_mode"), bool) else None,
        "probe": {k: (int(probe.get(k) or 0) if k == "attempts" else probe.get(k)) for k in _PROBE_VIEW_KEYS},
        "resumed_at": supply.get("resumed_at"),
        "ended_at": supply.get("ended_at"),
        "expired_at": supply.get("expired_at"),
        "pending_notes": len(supply.get("pending_notes") or []),
        "history": len(life.get(SUPPLIES_KEY) or []),
    }


def stop_fence(cache_dir) -> dict | None:
    """doc 256 E3: the refusal next_node / node_commit raise while a stop is open; None when the run is not stopped."""
    s = stop_status(cache_dir)
    if not s["open"]:
        return None
    qid = (s.get("gate") or {}).get("question_id")
    if (s.get('gate') or {}).get('source')=='execution_doubt':
        message=f"Execution conditions require the human's decision (question {qid}); no node is served or committed before an answer and recheck."
    elif s.get("requested_by") == "supply":   # alpha.105 (doc 259 spec §1.1): the message names who fences the run
        message = (f"the model supply was interrupted on this run (question {qid} open, stop {s['stop_id']}); no node is served or committed "
                   "until the human answers the question. Present the menu reference and end the turn.")
    elif s.get("requested_by") == "restart":
        message = (f"the host restarted while this run was RUNNING (question {qid} open, stop {s['stop_id']}); no node is served or committed "
                   "until the human answers whether to continue. Present the menu reference and end the turn.")
    else:
        message = (f"the human stopped this run (stop {s['stop_id']}, state {s['state']}); no node is served or committed until the "
                   "human's next message decides. In a [RUN STOPPED - JUDGE] turn run stop_decision.py first; in a stop-question turn "
                   "present the menu reference and end the turn.")
    return {"code": FENCE_CODE, "stop_id": s["stop_id"], "state": s["state"], "message": message}

"""alpha.104 (04 series doc 255 final_plan §2-§3, doc 256 E1): Stop is "stop execution, resumable".

The host marks a human Stop here (`mark_stop`: a record in `_host_lifecycle.json`, run_state untouched, gates and tickets kept) and
routes the human's next message through `stopped_turn`: deterministic rules first (final_plan §3.1 - a repeated recorded answer,
continue words, the engine gate's own options, the stop word, a conflicting or bare number), then the executor's judgement
(`_prepare_judge` -> the model runs stop_decision.py -> `decide_stop`: continue | ask), and, when in doubt, the resume-doubt gate
(final_plan §3.3, rendered to `_public/menu.stop-N.txt`, answered by `_answer_stop_gate`). A new-task answer hands the original
message to a fresh run (`_handover_new_task`, healed at every entry when the process died mid-way).

Writers of the lifecycle are the host process only (final_plan §2.2): `decide_stop` (the CLI) writes the decision file, the menu and,
on continue, the index through the engine lock - never the lifecycle. `stop_state` holds the read side; this module must not import
prepare_cache at module level (prepare_cache imports it) - the helpers that need it import it lazily.
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from pathlib import Path

from . import engine_core, hsaw_gate, render, stop_state, menu_history, gate_reply
from .run_store import RunStore, RunStoreError, atomic_write_bytes, dumps, now_iso

STOP_EXECUTOR_MAY_START_NEW_TASK = False   # final_plan Q2 乙: the executor never starts a new task by itself - it recommends it through `ask`
STOP_CONTEXT_LIMIT = 1500                  # final_plan §3.2: the judge context the host puts in the prompt (archived, sha256 in the prompt)
REPLIES_HISTORY_MAX = 5
MACHINE_MESSAGES_MAX = 5
STOPS_MAX = 20
SUPPLIES_MAX = 20                          # alpha.105 (doc 259 spec §1.3): closed supply records kept under "supplies"
GATE_SOURCE = "resume_doubt"               # final_plan Q1 甲: the stop question lives in the lifecycle only, never in the index gate history
_STOP_WORD_RE = re.compile(r"^\s*(?:停止|stop)[\s。！!.]*$", re.I)   # the Stop button's own words (final_plan Q3)
_DIGITS_RE = re.compile(r"\d+")
_GATE_TRIGGERS_TWO_FORM = ("SHORT_REPLY", "REPLY_MATCHES_RUN_GATE", "GATE_ON_SCREEN", "GATE_NOT_DELIVERED")
_MENU_KEYS = ("question_id", "node", "source", "question", "options", "closing", "recommendation", "advice", "explanation")

TEXTS = {
    "zh": {
        "question": "你点了停止，这一场停在 {node}（第 {k}/{N} 步）。之后你回复了「{reply80}」。这是接着上一场，还是一个新任务？",
        "t2": "停止前你已选 {n}「{label}」，这个选择不能再改。",
        "boundary": "上一场停在 {node}（第 {visit} 次）；你选择之前不执行任何节点。",
        "explanation_rule": "这道门由规则打开：{reason}。",
        "reason_stop_word": "你输入了「停止」",
        "reason_bare_number": "你的回复是一个对不上任何待用选项的数字",
        "reason_reply_conflicts_recorded_answer": "你的回复对上了同一道门的另一个选项",
        "reason_cancel_word_gate_unseen": "你回复了取消类的词，但停止前的问题还没有展示给你",
        "advice_rule": "引擎不推荐任何选项，由你决定。",
        "two_form_hint": "要开新任务，请选 2，然后直接发新请求。",
        "label_continue": "继续上一场",
        "note_continue": "从 {node} 接着执行；已记录的选择都保留；你刚才的消息作为补充说明交给这个节点。",
        "label_back": "回到原来的问题",
        "note_back": "重新展示停止前正在等待的问题；已记录的选择都保留。",
        "label_new_task": "作为新任务",
        "note_new_task": "结束停着的这一场（不能再续跑，已完成的节点保留在记录里），用你刚才的原话新开一场，不用重打。",
        "label_end": "结束上一场",
        "note_end": "结束这一场，不开始新任务。",
        "invalid_hint": "未识别的回复 {reply!r}；请回复编号 1-{n}、选项名或 intent。",
        "failed_new_task": "新任务没能开始：{code}。",
    },
    "en": {
        "question": "You pressed Stop; this run stopped at {node} (step {k}/{N}). You then replied \"{reply80}\". Does that continue the previous run, or is it a new task?",
        "t2": "Before the stop you had chosen {n} \"{label}\"; that choice can no longer be changed.",
        "boundary": "The previous run stopped at {node} (visit {visit}); no node runs before you choose.",
        "explanation_rule": "This gate was opened by a rule: {reason}.",
        "reason_stop_word": "you typed \"stop\"",
        "reason_bare_number": "your reply is a number that matches no pending option",
        "reason_reply_conflicts_recorded_answer": "your reply matched another option of the same gate",
        "reason_cancel_word_gate_unseen": "you replied with a cancel word, but the question pending before the stop was never shown to you",
        "advice_rule": "The engine recommends no option; the decision is yours.",
        "two_form_hint": "To start a new task, choose 2 and then send the new request directly.",
        "label_continue": "Continue the previous run",
        "note_continue": "Continue from {node}; every recorded choice is kept; the message you just sent is handed to that node as a supplementary note.",
        "label_back": "Back to the pending question",
        "note_back": "Show the question that was waiting before the stop again; every recorded choice is kept.",
        "label_new_task": "As a new task",
        "note_new_task": "End the stopped run (it cannot be resumed; the completed nodes stay in the record) and start a fresh run from your original words, no retyping.",
        "label_end": "End the previous run",
        "note_end": "End this run without starting a new task.",
        "invalid_hint": "Unrecognised reply {reply!r}; reply with a number 1-{n}, an option label or an intent.",
        "failed_new_task": "The new task could not start: {code}.",
    },
}

NOTES = {   # final_plan Q12: the public notes the model prints verbatim
    "zh": {
        "repeat_recorded": "已按上一场继续：你的回复「{reply}」与停止前记录的选择「{label}」一致。",
        "continue_run": "已按上一场继续，从 {node} 接着执行。",
        "continue_gate": "已按上一场继续；这是停止前正在等待的问题：",
        "not_an_answer": "你的回复「{reply}」没有当作答案；这是停止前还没展示给你的问题：",
        "executor_continue": "已按上一场继续（执行者判断：{reason}）。",
        "human_continue": "已按上一场继续（你在续跑问题 {qid} 选了「{label}」）。",
        "new_task": "上一场（cache/{old}）已按你的选择结束；这是用你的原话新开的一场。",
        "hold_machine": "这个会话有一场已停止的运行，等你回复；这条定时/agent 消息没有执行。",
        "hold_recovery": "这一场已由你停止，等你的下一条消息决定是接着做还是新任务。",
        "ended": "这一场已结束（停止后由你结束）。",
    },
    "en": {
        "repeat_recorded": "Continued the previous run: your reply \"{reply}\" matches the choice \"{label}\" recorded before the stop.",
        "continue_run": "Continued the previous run from {node}.",
        "continue_gate": "Continued the previous run; this is the question that was waiting before the stop:",
        "not_an_answer": "Your reply \"{reply}\" was not taken as an answer; this is the question that had not been shown to you before the stop:",
        "executor_continue": "Continued the previous run (executor's judgement: {reason}).",
        "human_continue": "Continued the previous run (you chose \"{label}\" at the resume question {qid}).",
        "new_task": "The previous run (cache/{old}) was ended as you chose; this is a fresh run from your original words.",
        "hold_machine": "This session has a stopped run waiting for your reply; this scheduled / agent message was not executed.",
        "hold_recovery": "You stopped this run; your next message decides whether it continues or is a new task.",
        "ended": "This run has ended (ended by you after the stop).",
    },
}
_ALIASES = {"continue_run": ["继续", "接着", "continue"], "new_task": ["新任务", "new"],
            "end_run": ["结束", "取消", "终止", "停止", "放弃", "不做了", "cancel", "stop", "end", "quit", "abort", "terminate"]}


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------

def _lang(index: dict | None) -> str:
    return hsaw_gate._lang((index or {}).get("user_language"))


def _low(text) -> str:
    return (text or "").strip().lower()


def _sha(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def _is_short_reply(text: str) -> bool:
    """final_plan §3.1: pure digits, or at most 4 characters after stripping punctuation, with no whitespace inside."""
    t = (text or "").strip()
    if _DIGITS_RE.fullmatch(t):
        return True
    if re.search(r"\s", t):
        return False
    core = "".join(ch for ch in t if not unicodedata.category(ch).startswith("P"))
    return len(core) <= 4


def _is_open(stop) -> bool:
    return isinstance(stop, dict) and stop.get("state") in stop_state.OPEN_STATES


def _one_line(value) -> str:
    return re.sub(r"[\r\n]+", " ", "-" if value is None else str(value))


def _matches_any_option(options: list, low: str) -> bool:
    """A reply that equals a label, an intent or an alias of any option, case-insensitively (T3 / A7 / G1)."""
    if not low:
        return False
    for opt in options or []:
        if low == _low(opt.get("label")) or low == _low(opt.get("intent")) or low in [_low(a) for a in opt.get("aliases") or []]:
            return True
    return False


def read_lifecycle(cache_dir) -> dict:
    return stop_state.read_lifecycle(cache_dir)


def write_lifecycle(cache_dir, **fields) -> dict:
    """Identical in effect to prepare_cache._write_lifecycle: read-modify-write with an atomic replace; a None value is written as null."""
    from .run_store import lifecycle_lock
    with lifecycle_lock(cache_dir):
        data = read_lifecycle(cache_dir)
        data.update(fields)
        atomic_write_bytes(Path(cache_dir) / stop_state.HOST_LIFECYCLE, dumps(data).encode("utf-8"))
        return data


def _write_life(cache_dir, life: dict, **fields) -> dict:
    """Persist the stop record and the resolved list of the in-memory lifecycle plus explicit fields (nothing else of the copy)."""
    return write_lifecycle(cache_dir, stop=life.get(stop_state.STOP_KEY), stops=life.get(stop_state.STOPS_KEY) or [], **fields)


def _snapshot(life: dict) -> str:
    """The lifecycle as one string, so an in-place change by the heal / merge helpers is detected (a shallow copy would share the record)."""
    return json.dumps(life, sort_keys=True, ensure_ascii=False, default=str)


def _identity_mismatch(index: dict, life: dict, session_id) -> dict | None:
    """The identity check of engine_hooks (eh:336-344): None when the index and the lifecycle name this session and one trace."""
    identity = {"index_session": index.get("session_id"), "lifecycle_session": life.get("session_id"),
                "index_trace": index.get("trace_id"), "lifecycle_trace": life.get("trace_id")}
    ok = (identity["index_session"] == identity["lifecycle_session"] == str(session_id)
          and identity["index_trace"] and identity["index_trace"] == identity["lifecycle_trace"])
    return None if ok else identity


def _push_history(stop: dict, key: str, item: dict, limit: int) -> None:
    rows = [r for r in (stop.get(key) or []) if isinstance(r, dict)]
    rows.append(item)
    stop[key] = rows[-limit:]


def _reply_record(message: str, *, host: dict, host_turn_id) -> dict:
    return {"text": message, "sha256": _sha(message), "received_at": now_iso(),
            "host_turn": {"invocation_id": host_turn_id, "origin_channel": host.get("origin_channel"), "requested_model": host.get("requested_model"),
                          "host_fences": host.get("fences"), "host_tools": host.get("tools"), "user_id": host.get("user_id")}}


def _remember(life: dict, stop_id: str, host_turn_id, ctx: dict) -> None:
    """final_plan §3.7 / doc 256 §2.4 step 5: the ctx handed to the host, kept on the open stop or on the record it resolved into
    (the replay guard returns it when the same host turn is bootstrapped twice). `index_updated_at` is the index time after this
    bootstrap's own host-field write, so the next write_after_stop check does not mistake it for a late commit (S5)."""
    entry = {"invocation_id": host_turn_id, "at": now_iso(), "ctx": ctx,
             "index_updated_at": (stop_state.read_index_plain(Path(ctx.get("cache_dir") or "")) or {}).get("updated_at")}
    stop = life.get("stop")
    if isinstance(stop, dict) and stop.get("stop_id") == stop_id:
        stop["last_bootstrap"] = entry
        return
    for r in reversed(life.get("stops") or []):
        if isinstance(r, dict) and r.get("stop_id") == stop_id:
            r["last_bootstrap"] = entry
            return


def _host_fields(host: dict, entry_mode: str, **extra) -> dict:
    """The index host group fields prepare_cache writes on every turn (pc:337-338), for this entry mode."""
    return dict(last_turn_at=now_iso(), origin_channel=host.get("origin_channel") or None, requested_model=host.get("requested_model"),
                host_fences=host.get("fences"), host_tools=host.get("tools"), entry_mode=entry_mode, **extra)


def _ctx(cache_dir: Path, entry_mode: str, host: dict, extra: dict) -> dict:
    import prepare_cache as pc  # noqa: PLC0415 - prepare_cache imports this module; its ctx helper is borrowed lazily
    return pc._ctx(cache_dir, pc.engine_core_index(cache_dir), entry_mode, host.get("requested_model"), extra)


def _uid(host: dict) -> dict:
    return {"user_id": str(host["user_id"])} if host.get("user_id") else {}


# ---------------------------------------------------------------------------
# the record: resolve, merge the executor's decision, heal a half handover
# ---------------------------------------------------------------------------

def _resolve_stop(life: dict, *, kind: str, by: str, rule: str | None = None, judge_id: str | None = None, question_id: str | None = None,
                  superseded_by: str | None = None, note: str | None = None) -> dict:
    """Move life["stop"] into life["stops"] with its resolution (max STOPS_MAX, oldest dropped); the caller writes the lifecycle."""
    record = dict(life["stop"])
    record["resolution"] = {"kind": kind, "by": by, "at": now_iso(), "rule": rule, "judge_id": judge_id, "question_id": question_id,
                            "superseded_by": superseded_by, "note": note}
    rows = [r for r in (life.get("stops") or []) if isinstance(r, dict)]
    rows.append(record)
    life["stops"] = rows[-STOPS_MAX:]
    life["stop"] = None
    return record


def _close_supply(life: dict, state: str, **stamps) -> dict | None:
    """alpha.105 (doc 259 spec §1.3): move life["supply"] into life["supplies"] with `state` and its terminal stamps (max SUPPLIES_MAX, oldest
    dropped); the caller writes. Its one home is here (next to _resolve_stop) because end_stopped_run needs it without importing supply_flow.
    None when no record is on file."""
    supply = life.get(stop_state.SUPPLY_KEY)
    if not isinstance(supply, dict):
        return None
    record = dict(supply)
    record["state"] = state
    record.update(stamps)
    rows = [r for r in (life.get(stop_state.SUPPLIES_KEY) or []) if isinstance(r, dict)]
    rows.append(record)
    life[stop_state.SUPPLIES_KEY] = rows[-SUPPLIES_MAX:]
    life[stop_state.SUPPLY_KEY] = None
    return record


def _hold_note(index: dict, stop: dict) -> str:
    """alpha.105 (doc 259 spec §1.5): the hold text for a recovery marker / machine message on an open stop - the question's own text when the
    host opened it (supply / restart), else the alpha.104 hold_recovery text."""
    lang = _lang(index)
    by = stop.get("requested_by")
    if by in ("supply", "restart"):
        from . import supply_flow  # noqa: PLC0415 - supply_flow imports this module; the hook imports it lazily
        qid = (stop.get("gate") or {}).get("question_id")
        return supply_flow.NOTES_Q[lang]["hold_supply_question" if by == "supply" else "hold_restart_question"].format(qid=qid)
    return NOTES[lang]["hold_recovery"]


def _merge_stop_files(cache_dir, life: dict) -> dict:
    """final_plan §3.2 (last step): apply the decision file of the CURRENT judge to a JUDGING stop - `continue` resolves it (by the executor),
    `ask` turns it into GATED with the composed gate (a gate already merged is kept so its delivered_at / invalid_answers survive).
    Files of other judge ids are ignored (S7). Returns the possibly changed life; the caller writes it."""
    stop = life.get("stop")
    if not isinstance(stop, dict) or stop.get("state") != "JUDGING":
        return life
    judge_id = (stop.get("judge") or {}).get("judge_id")
    if not judge_id:
        return life
    acc = (stop_state.read_decision(cache_dir, stop.get("stop_id"), judge_id) or {}).get("accepted")
    if not isinstance(acc, dict):
        return life
    if acc.get("decision") == "continue":
        _resolve_stop(life, kind="continue", by="executor", judge_id=judge_id, note=acc.get("public_note"))
    elif acc.get("decision") == "ask":
        stop["state"] = "GATED"
        if stop.get("gate") is None:
            stop["gate"] = acc.get("gate")
    return life


def _finish_handover(cache_dir: Path, life: dict, new_cache_name: str, by: str) -> None:
    """final_plan §3.6 steps 3-4: end the old run (by the human; no new termination kind - an unknown kind maps to COMPLETED) and
    resolve its stop as new_task, both lifecycles linked. terminate_run is idempotent (ALREADY_TERMINAL on a terminal run)."""
    stop = life["stop"]
    stop_id = stop["stop_id"]
    qid = (stop.get("gate") or {}).get("question_id")
    engine_core.terminate_run(cache_dir, kind="human_termination", by=by, reason=f"superseded by new task {new_cache_name} after stop {stop_id}")
    _resolve_stop(life, kind="new_task", by=by, question_id=qid, superseded_by=new_cache_name)
    _write_life(cache_dir, life, superseded_by=new_cache_name, entry_mode="terminal")
    engine_core.set_host_fields(cache_dir, entry_mode="terminal", last_turn_at=now_iso())


def _numbered_dirs(root: Path) -> list[Path]:
    if not root.is_dir():
        return []
    return sorted((p for p in root.iterdir() if p.is_dir() and re.fullmatch(r"\d+", p.name)), key=lambda p: int(p.name))


def _heal_handover(cache_dir, life: dict) -> dict:
    """final_plan §3.6 step 5: a HANDOVER left by a process death. When the new cache exists (its lifecycle names this cache and stop in
    superseded_from and it has both files) the handover is finished; otherwise the stop goes back to GATED (or OPEN without a gate) and
    the original message stays in gate.pending_message / reply.text. Only a process death leaves a half handover (prepare is synchronous)."""
    cache_dir = Path(cache_dir)
    stop = life.get("stop")
    if not isinstance(stop, dict) or stop.get("state") != "HANDOVER":
        return life
    try:
        own = int(cache_dir.name)
    except ValueError:
        own = -1
    found = None
    for path in _numbered_dirs(cache_dir.parent):
        if int(path.name) <= own or not (path / "_index.json").is_file() or not (path / stop_state.HOST_LIFECYCLE).is_file():
            continue
        sf = stop_state.read_lifecycle(path).get("superseded_from")
        if isinstance(sf, dict) and sf.get("cache") == cache_dir.name and sf.get("stop_id") == stop.get("stop_id"):
            found = path
            break
    if found is not None:
        _finish_handover(cache_dir, life, found.name, (stop.get("handover") or {}).get("by") or "human")
    else:
        stop["state"] = "GATED" if isinstance(stop.get("gate"), dict) else "OPEN"
        stop["handover"] = None
    return life


def heal_all(root) -> list[str]:
    """Startup: heal every numbered cache under `root` whose stop is HANDOVER and merge the current judge's decision file into every
    recorded stop (doc 256 §2.6: heal_all is one of the merging writers); returns the healed cache names. A cache whose index the
    engine cannot terminate is skipped (the next entry tries again)."""
    healed: list[str] = []
    for path in _numbered_dirs(Path(root)):
        life = read_lifecycle(path)
        stop = life.get("stop")
        if not isinstance(stop, dict):
            continue
        handover = stop.get("state") == "HANDOVER"
        before = _snapshot(life)
        try:
            life = _merge_stop_files(path, _heal_handover(path, life))
            if handover or _snapshot(life) != before:
                _write_life(path, life)
        except (RunStoreError, engine_core.EngineError, OSError, ValueError):
            continue
        if handover:
            healed.append(path.name)
    return healed


def resolve_terminal_stop(cache_dir) -> dict | None:
    """The run ended while a stop record was on file (a concurrent end, a lost lifecycle write, or an executor `continue` whose run then
    ended in the same turn): heal, merge and close the record so a fresh run starts as today. Returns the run_terminal record, or None
    when the merge alone resolved the stop (kind continue, by the executor); the file is written only when the record changed."""
    cache_dir = Path(cache_dir)
    life = read_lifecycle(cache_dir)
    before = _snapshot(life)
    life = _merge_stop_files(cache_dir, _heal_handover(cache_dir, life))
    record = _resolve_stop(life, kind="run_terminal", by="host") if _is_open(life.get("stop")) else None
    if record is not None or _snapshot(life) != before:
        _write_life(cache_dir, life)
    return record


def note_host_index_write(cache_dir) -> dict | None:
    """After the host's own index write at the end of a turn (prepare.finalize_execution_context: response_persisted / reconciled_at):
    refresh `stop.last_bootstrap.index_updated_at` so the next stopped_turn does not report that host-only write as a write_after_stop
    (final_plan S5 names commits the CLI fence did not see, not the host's bookkeeping). Nothing else of the record changes; None when
    no open stop with a last_bootstrap is on file."""
    cache_dir = Path(cache_dir)
    life = read_lifecycle(cache_dir)
    stop = life.get("stop")
    if not _is_open(stop) or not isinstance(stop.get("last_bootstrap"), dict):
        return None
    updated = (stop_state.read_index_plain(cache_dir) or {}).get("updated_at")
    if not isinstance(updated, str) or stop["last_bootstrap"].get("index_updated_at") == updated:
        return None
    stop["last_bootstrap"]["index_updated_at"] = updated
    _write_life(cache_dir, life)
    return {"stop_id": stop.get("stop_id"), "index_updated_at": updated}


# ---------------------------------------------------------------------------
# mark_stop (the host's Stop), end_stopped_run, mark_stop_menu_delivered
# ---------------------------------------------------------------------------

def mark_stop(cache_dir: str | Path, host_run_id: str, error_code: str = "RUN_CANCELLED", phase: str = "request",
              *, session_id: str | None = None) -> dict:
    """final_plan §2.1 S1-S9: record the human's Stop. Never takes the engine lock, reads the index as plain JSON, writes only the
    lifecycle; a terminal run is never rewritten (skipped). A second Stop from the same host run is ALREADY_STOPPED; from another host run
    RESTOPPED (S7: a pending judge is void, a GATED question stays)."""
    cache_dir = Path(cache_dir)
    out = {"action": "skipped", "reason": None, "run_state": None, "cache_dir": str(cache_dir), "stop_id": None}
    index = stop_state.read_index_plain(cache_dir)
    if index is None:
        return dict(out, reason="index unreadable")
    engine_core.program_guard.assert_run_version(index)
    out["run_state"] = index.get("run_state")
    if index.get("run_state") not in ("RUNNING", "WAITING_USER"):
        return dict(out, reason="run already terminal")
    life = read_lifecycle(cache_dir)
    if session_id is not None:
        mismatch = _identity_mismatch(index, life, session_id)
        if mismatch is not None:
            return dict(out, action="identity_mismatch", reason=mismatch)
    life = _merge_stop_files(cache_dir, life)
    now = now_iso()
    stop = life.get("stop")
    if _is_open(stop):
        out["stop_id"] = stop.get("stop_id")
        if host_run_id in (stop.get("host_run_ids") or []) or stop.get("state") == "HANDOVER":
            return dict(out, action="ALREADY_STOPPED", state=stop.get("state"), restops=int(stop.get("restops") or 0))
        stop["restops"] = int(stop.get("restops") or 0) + 1
        stop["restop_at"] = now
        stop["host_run_ids"] = list(stop.get("host_run_ids") or []) + [host_run_id]
        if stop.get("state") == "JUDGING":   # S7: the pending judge_id is void - stop_decision for it is refused with STOP_NOT_PENDING
            stop["judge"] = None
            if isinstance(stop.get("reply"), dict):
                _push_history(stop, "replies_history", stop["reply"], REPLIES_HISTORY_MAX)
                stop["reply"] = None
            stop["state"] = "OPEN"
        _write_life(cache_dir, life)
        return dict(out, action="RESTOPPED", state=stop["state"], restops=stop["restops"])
    gate = index.get("gate") if isinstance(index.get("gate"), dict) else {}
    waiting = gate.get("state") == "WAITING_USER"
    current = index.get("current") if isinstance(index.get("current"), dict) else {}
    record = {"stop_id": f"s-{len(life.get('stops') or []) + 1}", "state": "OPEN", "requested_at": now, "requested_by": "host", "phase": phase,
              "host_run_ids": [host_run_id], "error_code": error_code, "run_state_at_stop": index["run_state"],
              "node": current.get("name"), "visit": current.get("visit"),
              "gate_question_id": gate.get("question_id") if waiting else None,
              "gate_delivered_at_stop": gate.get("delivered_at") if waiting else None,
              "gate_presented_at_stop": gate.get("presented_at") if waiting else None,
              "index_updated_at": index.get("updated_at"), "restops": 0, "restop_at": None, "reply": None, "replies_history": [],
              "machine_messages": [], "judge": None, "judge_seq": 0, "gate": None, "write_after_stop": None, "recovery_replays": 0,
              "last_bootstrap": None}
    life["stop"] = record
    _write_life(cache_dir, life)
    return dict(out, action="STOPPED", stop_id=record["stop_id"], state="OPEN", restops=0)


def end_stopped_run(cache_dir: str | Path, by: str = "human", *, session_id: str | None = None) -> dict:
    """final_plan Q15 / doc 256 H5: the human ends a stopped run explicitly (the EngineView button, the session delete). terminate_run
    holds the engine lock and is idempotent; a lifecycle resolution lost to a concurrent writer is closed as run_terminal by the next prepare."""
    cache_dir = Path(cache_dir)
    index = stop_state.read_index_plain(cache_dir) or {}
    engine_core.program_guard.assert_run_version(index)
    life = read_lifecycle(cache_dir)
    before = _snapshot(life)
    life = _merge_stop_files(cache_dir, _heal_handover(cache_dir, life))
    stop = life.get("stop")
    if not _is_open(stop):
        if _snapshot(life) != before:
            _write_life(cache_dir, life)
        return {"status": "NOT_STOPPED", "run_state": index.get("run_state"), "stop_id": None}
    if session_id is not None:
        mismatch = _identity_mismatch(index, life, session_id)
        if mismatch is not None:
            return {"status": "IDENTITY_MISMATCH", "reason": mismatch, "stop_id": stop.get("stop_id")}
    stop_id = stop["stop_id"]
    result = engine_core.terminate_run(cache_dir, kind="human_termination", by=by, reason=f"ended at stop {stop_id} by {by} via end_stopped_run")
    _resolve_stop(life, kind="ended", by=by)
    supply = life.get(stop_state.SUPPLY_KEY)   # alpha.105 (doc 259 spec §1.9): an open supply record (a question, a wait) ends with the run
    closed = _close_supply(life, "ENDED", ended_at=now_iso()) if isinstance(supply, dict) and supply.get("state") in ("ASKED", "AUTHORIZED", "WAIT_EXPIRED") else None
    extra = {stop_state.SUPPLY_KEY: life.get(stop_state.SUPPLY_KEY), stop_state.SUPPLIES_KEY: life.get(stop_state.SUPPLIES_KEY) or []} if closed else {}
    _write_life(cache_dir, life, ended_at=now_iso(), entry_mode="terminal", **extra)
    if result["status"] == "TERMINATED":
        engine_core.set_host_fields(cache_dir, entry_mode="terminal")
    return {"status": "ENDED" if result["status"] == "TERMINATED" else "ALREADY_TERMINAL", "stop_id": stop_id,
            "run_state": result["run_state"], "cache_name": cache_dir.name}


def mark_stop_menu_delivered(cache_dir: str | Path, stop_id: str, *, question_id=None, event_id=None,
                             session_id=None, trace_id=None) -> dict:
    """final_plan §3.3 送达记录 (doc 256 H1): the host's after-agent callback saw the menu reference in the reply. The merge is needed
    because the CLI's `ask` is still only in the decision file when the callback runs."""
    cache_dir = Path(cache_dir)
    from .run_store import lifecycle_lock
    with lifecycle_lock(cache_dir):
        return _mark_stop_menu_delivered(cache_dir, stop_id, question_id=question_id, event_id=event_id,
            session_id=session_id, trace_id=trace_id)


def _mark_stop_menu_delivered(cache_dir, stop_id, *, question_id, event_id, session_id, trace_id):
    engine_core.program_guard.assert_run_version(stop_state.read_index_plain(cache_dir) or {})
    life = _merge_stop_files(cache_dir, read_lifecycle(cache_dir))
    stop = life.get("stop")
    if not _is_open(stop):
        return {"status": "NOT_GATED", "stop_id": None}
    if stop.get("stop_id") != stop_id:
        return {"status": "STOP_MISMATCH", "stop_id": stop.get("stop_id")}
    if stop.get("state") != "GATED" or not isinstance(stop.get("gate"), dict):
        return {"status": "NOT_GATED", "stop_id": stop_id, "state": stop.get("state")}
    gate = stop["gate"]
    if (question_id is not None and gate.get('question_id') != question_id) or \
            (session_id is not None and life.get('session_id') != session_id) or \
            (trace_id is not None and life.get('trace_id') != trace_id):
        return {'status':'DELIVERY_IDENTITY_MISMATCH'}
    if gate.get("delivered_at"):
        return {"status": "ALREADY_DELIVERED", "question_id": gate.get("question_id"), "delivered_at": gate["delivered_at"]}
    gate["delivered_at"] = now_iso()
    if event_id:
        gate['delivery_evidence'] = dict(basis='host_posted_event', event_id=str(event_id),
            session_id=session_id, trace_id=trace_id, question_id=gate.get('question_id'))
    _write_life(cache_dir, life)
    return {"status": "DELIVERED", "question_id": gate.get("question_id"), "delivered_at": gate["delivered_at"]}


# ---------------------------------------------------------------------------
# the judge context
# ---------------------------------------------------------------------------

def _plain_json(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _last_gate_line(cache_dir: Path, index: dict) -> str:
    history = [h for h in ((index.get("gate") or {}).get("history") or []) if isinstance(h, dict) and h.get("resolution_kind") != "invalid_retry"]
    if not history:
        return "-"
    qid = history[-1].get("question_id")
    rec = _plain_json(RunStore(cache_dir).gate_path(qid)) if qid else None
    if not rec:
        return _one_line(qid)
    options = "; ".join(f"{i}. {o.get('label')} [{o.get('intent')}]" for i, o in enumerate(rec.get("options") or [], start=1))
    answered = bool(rec.get("answered_at"))
    return (f"{qid} | question: {_one_line(rec.get('question'))} | options: {options} | recommendation: {_one_line(rec.get('recommendation'))}"
            f" | state: {'answered' if answered else 'waiting'} | answer: \"{_one_line(rec.get('answer_text') or '')}\" -> {rec.get('chosen_label') or '-'}"
            f" | consumed: {'yes' if rec.get('consumed_by_commit') else 'no'} | delivered: {'yes' if rec.get('delivered_at') else 'no'}")


def _last_summary(cache_dir: Path, index: dict) -> str:
    completed = [c for c in (index.get("completed") or []) if isinstance(c, dict)]
    if not completed:
        return "-"
    name, visit = completed[-1].get("name"), int(completed[-1].get("visit") or 1)
    store = RunStore(cache_dir)
    entry = engine_core._catalog_entry(index,name)
    candidates = []
    if entry and entry.get("kind") == "sub" and entry.get("parent"):
        candidates.append(store.sub_cache_path(entry["parent"], str(name).rsplit("/", 1)[-1], visit))
    program = (index.get("program") or {}).get("name") or "engine"
    candidates += [store.node_cache_path(program, name, visit), store.node_cache_path("engine", name, visit)]
    for path in candidates:
        cache = _plain_json(path)
        if not cache:
            continue
        try:
            summary = engine_core._latest_payload(cache).get("user_summary")
        except (KeyError, TypeError, AttributeError, IndexError):
            continue
        if isinstance(summary, str) and summary.strip():
            return _one_line(summary[:300])
        break
    return "-"


def stopped_run_summary(cache_dir, stop: dict, reply_text: str) -> tuple[str, str]:
    """final_plan §3.2: the run summary the executor judges from - read-only over plain JSON, one `key: value` line per item, at most
    STOP_CONTEXT_LIMIT characters (the longest values are cut first, each cut marked with …). Returns (text, sha256 of the utf-8 text);
    the archived bytes equal what the model saw."""
    cache_dir = Path(cache_dir)
    index = stop_state.read_index_plain(cache_dir) or {}
    run_input = _plain_json(cache_dir / engine_core.RUN_INPUT) or {}
    catalog = [e for e in (index.get("catalog") or []) if isinstance(e, dict)]
    current = index.get("current") if isinstance(index.get("current"), dict) else {}
    names = [e.get("name") for e in catalog]
    k = names.index(current.get("name")) + 1 if current.get("name") in names else 0
    age = engine_core._ms_between(stop.get("requested_at"), now_iso())
    completed = [c.get("name") for c in (index.get("completed") or [])[-3:] if isinstance(c, dict)]
    was = stop.get("write_after_stop") if isinstance(stop.get("write_after_stop"), dict) else None
    earlier = [r.get("text") for r in (stop.get("replies_history") or [])[-2:] if isinstance(r, dict)]
    machine = [m for m in (stop.get("machine_messages") or []) if isinstance(m, dict)]
    values = {
        "program": _one_line((index.get("program") or {}).get("name") or (index.get("route") or {}).get("package") or "-"),
        "request": _one_line(str(run_input.get("user_message") or "")[:200]),
        "stopped_at": (f"{current.get('name') or '-'} (visit {current.get('visit') or 0}), step {k}/{len(catalog)}, run_state {stop.get('run_state_at_stop')}, "
                       f"{(age or 0) // 1000} s ago"),
        "recent_nodes": ", ".join(str(n) for n in completed) if completed else "-",
        "last_gate": _last_gate_line(cache_dir, index),
        "last_summary": _last_summary(cache_dir, index),
        "write_after_stop": f"yes (index updated at {was.get('index_updated_at')})" if was else "no",
        "earlier_replies": "; ".join(f"\"{_one_line(t)}\"" for t in earlier) if earlier else "-",
        "machine_messages": f"{len(machine)} (last: \"{_one_line(machine[-1].get('text'))}\")" if machine else "0",
        "reply": f"\"{_one_line(reply_text)}\"",
    }

    def text_of() -> str:
        return "\n".join(f"{key}: {value}" for key, value in values.items())

    text = text_of()
    floor = 8
    while len(text) > STOP_CONTEXT_LIMIT:
        excess = len(text) - STOP_CONTEXT_LIMIT
        first = [key for key in ("request", "last_summary", "last_gate") if len(values[key]) > floor]
        rest = sorted((key for key in values if key not in ("request", "last_summary", "last_gate") and len(values[key]) > floor),
                      key=lambda key: -len(values[key]))
        if not first and not rest:
            break
        key = (first or rest)[0]
        keep = max(floor - 1, len(values[key]) - excess - 1)
        values[key] = values[key][:keep].rstrip() + "…"
        text = text_of()
    return text, _sha(text)


# ---------------------------------------------------------------------------
# judge preparation, the decision (CLI side), the resume-doubt gate
# ---------------------------------------------------------------------------

def _prepare_judge(cache_dir: Path, index: dict, life: dict, message: str, *, allowed: list, triggers: list, host: dict, host_turn_id,
                   abandon: bool = True, lifecycle_extra: dict | None = None) -> dict:
    """final_plan §3.2 准备: a new judge_id, the reply and its context recorded, state JUDGING, then the stop_judge ctx for the
    [RUN STOPPED - JUDGE] block. `abandon` is False for the recovery-marker re-judge (final_plan §3.8: no ticket is invalidated).
    docs/05SoulRun 90 round 4 (ledger decision 184): nothing is abandoned either for a run that looks RUNNING only because an engine
    stop was cut off before its index write (engine_core.unindexed_stop, read-only) - the run that never stopped waits at that stop,
    where nothing is abandoned; the stop is installed by the next next-node, never here."""
    stop = life["stop"]
    stop_id = stop["stop_id"]
    if abandon and index.get("run_state") == "RUNNING" and not engine_core.unindexed_stop(cache_dir):
        engine_core.abandon_dispatch(cache_dir, reason=f"human stop {stop_id}: judge")
    stop["judge_seq"] = int(stop.get("judge_seq") or 0) + 1
    judge_id = f"j{stop['judge_seq']}"
    if isinstance(stop.get("reply"), dict):
        _push_history(stop, "replies_history", stop["reply"], REPLIES_HISTORY_MAX)
    stop["reply"] = _reply_record(message, host=host, host_turn_id=host_turn_id)
    context, sha = stopped_run_summary(cache_dir, stop, message)
    stop["judge"] = {"judge_id": judge_id, "context_sha256": sha, "context": context, "allowed": list(allowed), "triggers": list(triggers),
                     "prepared_at": now_iso(), "reply_sha256": stop["reply"]["sha256"]}
    stop["state"] = "JUDGING"
    engine_core.set_host_fields(cache_dir, **_host_fields(host, "stopped_judge"))
    ctx = _ctx(cache_dir, "stopped_judge", host, {"stop_judge": True, "stop_id": stop_id, "judge_id": judge_id, "human_message": message,
                                                  "allowed": list(allowed), "triggers": list(triggers), "context_sha256": sha, "context": context,
                                                  "run_state_at_stop": stop.get("run_state_at_stop"), "stopped_node": stop.get("node"),
                                                  "stopped_visit": stop.get("visit")})
    _remember(life, stop_id, host_turn_id, ctx)
    _write_life(cache_dir, life, last_turn_at=now_iso(), entry_mode="stopped_judge", **_uid(host), **(lifecycle_extra or {}))
    return ctx


def _step_position(index: dict) -> tuple[int, int]:
    catalog = [e for e in (index.get("catalog") or []) if isinstance(e, dict)]
    names = [e.get("name") for e in catalog]
    name = (index.get("current") or {}).get("name")
    return (names.index(name) + 1 if name in names else 0), len(catalog)


def render_stop_menu(cache_dir, index: dict, gate: dict, hint: str | None = None) -> Path:
    """The stop question as a robot menu block (render.menu_block, the fixed last line kept - final_plan Q13) under _public/menu.stop-N.txt."""
    text = render.menu_block({k: gate.get(k) for k in _MENU_KEYS}, hint=hint, user_language=index.get("user_language"))
    return RunStore(cache_dir).write_public(f"menu.{gate['question_id']}.txt", text)


def _question_ctx(cache_dir: Path, life: dict, host: dict, host_turn_id, *, public_note: str | None, opened_by: str,
                  lifecycle_extra: dict | None = None) -> dict:
    """Write the stopped_question turn: index entry mode, the stop_question ctx, last_bootstrap, lifecycle."""
    stop = life["stop"]
    qid = stop["gate"]["question_id"]
    engine_core.set_host_fields(cache_dir, **_host_fields(host, "stopped_question"))
    ctx = _ctx(cache_dir, "stopped_question", host, {"stop_question": True, "stop_id": stop["stop_id"], "question_id": qid,
                                                     "public_block_ref": menu_history.ref(cache_dir, f"menu.{qid}.txt"),
                                                     "public_note": public_note, "opened_by": opened_by,
                                                     "question_source": stop["gate"].get("source")})   # alpha.105 (doc 259 spec §1.10): resume_doubt / supply_doubt / restart_doubt
    _remember(life, stop["stop_id"], host_turn_id, ctx)
    _write_life(cache_dir, life, last_turn_at=now_iso(), entry_mode="stopped_question", **_uid(host), **(lifecycle_extra or {}))
    return ctx


def _open_stop_gate(cache_dir: Path, index: dict, life: dict, message: str, *, form: str, opened_by: str, recommendation: str | None = "none",
                    advice: str | None = None, explanation: str | None = None, extra_question: str | None = None, host: dict | None = None,
                    host_turn_id=None, persist: bool = True, lifecycle_extra: dict | None = None) -> dict:
    """final_plan §3.3: compose the resume-doubt gate (five parts: question + explanation, a note per option, recommendation or none with
    advice, resume_boundary, the HSAW closing). `persist=False` (decide_stop, the CLI) writes the menu only and returns the gate object and
    the reference for the decision file; otherwise the record becomes GATED and the stop_question ctx is returned. `lifecycle_extra`
    (record 90 round 7): fields the turn's lifecycle write carries besides (_question_ctx)."""
    cache_dir = Path(cache_dir)
    stop = life["stop"]
    lang = _lang(index)
    texts = TEXTS[lang]
    qid = f"stop-{stop['stop_id'].split('-', 1)[1]}"
    node = stop.get("node") or "-"
    k, total = _step_position(index)
    question = texts["question"].format(node=node, k=k, N=total, reply80=_one_line(message)[:80])
    if extra_question:
        question += " " + extra_question   # one space in both languages (doc 256 §2.7 gate example)
    # round 6 ('vc 2' defect 3): the run cut off at its engine stop waits at that stop, as the run that never stopped does
    waiting = index.get("run_state") == "WAITING_USER" or _cut_off_stop(cache_dir, index) is not None
    options = [{"kind": "execute", "label": texts["label_back"] if waiting else texts["label_continue"], "intent": "continue_run",
                "aliases": list(_ALIASES["continue_run"]), "note": texts["note_back"] if waiting else texts["note_continue"].format(node=node)}]
    if form == "three":
        options.append({"kind": "execute", "label": texts["label_new_task"], "intent": "new_task", "aliases": list(_ALIASES["new_task"]),
                        "note": texts["note_new_task"]})
    end_note = texts["note_end"] if form == "three" else texts["note_end"] + (" " if lang == "en" else "") + texts["two_form_hint"]
    options.append({"kind": "cancel", "label": texts["label_end"], "intent": "end_run", "aliases": list(_ALIASES["end_run"]), "note": end_note})
    rule_key = opened_by.split(":", 1)[1] if opened_by.startswith("rule:") else None
    if rule_key is not None:
        explanation = explanation or texts["explanation_rule"].format(reason=texts.get(f"reason_{rule_key}", rule_key))
        advice = advice or texts["advice_rule"]
    gate = {"question_id": qid, "node": node, "source": GATE_SOURCE, "question": question, "options": options, "closing": hsaw_gate.CLOSING[lang],
            "recommendation": recommendation or "none", "advice": advice, "explanation": explanation,
            "resume_boundary": texts["boundary"].format(node=node, visit=stop.get("visit")),
            "form": form, "opened_by": opened_by, "opened_at": now_iso(), "delivered_at": None,
            "pending_message": message, "pending_sha256": _sha(message), "invalid_answers": [], "state": "WAITING", "answer": None}
    render_stop_menu(cache_dir, index, gate)
    ref = menu_history.ref(cache_dir, f"menu.{qid}.txt")
    if not persist:
        return {"gate": gate, "question_id": qid, "public_block_ref": ref}
    stop["gate"] = gate
    stop["state"] = "GATED"
    if not (isinstance(stop.get("reply"), dict) and stop["reply"].get("text") == message):
        if isinstance(stop.get("reply"), dict):
            _push_history(stop, "replies_history", stop["reply"], REPLIES_HISTORY_MAX)
        stop["reply"] = _reply_record(message, host=host or {}, host_turn_id=host_turn_id)
    return _question_ctx(cache_dir, life, host or {}, host_turn_id, public_note=None, opened_by=opened_by, lifecycle_extra=lifecycle_extra)


_ACCEPTED_ONLY_KEYS = ("gate", "public_block_ref", "public_note", "wait")   # doc 256 §2.6: under `accepted`, not in the attempt copy


def _archive_attempt(cache_dir: Path, stop_id: str, judge_id: str, dec: dict, attempt: dict) -> None:
    dec.setdefault("attempts", []).append(attempt)
    atomic_write_bytes(stop_state.decision_path(cache_dir, stop_id, judge_id), dumps(dec).encode("utf-8"))


def _accepted_attempt(accepted: dict) -> dict:
    """The archived copy of an accepted decision: its fields minus the gate / reference / note / wait that live under `accepted` only."""
    return dict({k: v for k, v in accepted.items() if k not in _ACCEPTED_ONLY_KEYS}, accepted=True)


def decide_stop(cache_dir, stop_id: str, judge_id: str, decision: str, *, recommendation=None, explanation=None, advice=None, reason: str = "") -> dict:
    """final_plan §3.2 命令行: the executor's decision for the pending judge. Never writes the lifecycle: the decision file (every attempt,
    accepted or rejected), the menu on `ask`, and on `continue` the index through the engine lock (HUMAN_STOP_WAIT, entry_mode)."""
    cache_dir = Path(cache_dir)
    if not (isinstance(stop_id, str) and stop_state.STOP_ID_RE.match(stop_id) and isinstance(judge_id, str) and stop_state.JUDGE_ID_RE.match(judge_id)):
        return {"status": "REJECTED", "code": "STOP_NOT_PENDING", "stop_id": stop_id, "judge_id": judge_id, "current": None,
                "message": "stop_id must look like s-N and judge_id like jK"}
    status = stop_state.stop_status(cache_dir)
    life = read_lifecycle(cache_dir)
    index = stop_state.read_index_plain(cache_dir)
    engine_core.program_guard.assert_run_version(index)
    stop = life.get("stop") if isinstance(life.get("stop"), dict) else {}
    current = {"stop_id": status["stop_id"], "state": status["recorded_state"], "judge_id": status["judge_id"]}
    dec = stop_state.read_decision(cache_dir, stop_id, judge_id) or {"stop_id": stop_id, "judge_id": judge_id, "cache": cache_dir.name,
                                                                         "attempts": [], "accepted": None}
    now = now_iso()
    given = {k: v for k, v in (("recommendation", recommendation), ("explanation", explanation), ("advice", advice)) if v is not None}

    def reject(code: str, message: str, **extra) -> dict:
        _archive_attempt(cache_dir, stop_id, judge_id, dec, {"at": now, "decision": decision, **given, "reason": reason, "accepted": False, "code": code,
                                                             **{k: v for k, v in extra.items() if k in ("allowed", "triggers", "field", "expected")}})
        return {"status": "REJECTED", "code": code, "stop_id": stop_id, "judge_id": judge_id, "message": message, **extra}

    if (index is None or not status["open"] or status["recorded_state"] != "JUDGING" or stop_id != status["stop_id"]
            or judge_id != status["judge_id"] or isinstance(dec.get("accepted"), dict)):
        return reject("STOP_NOT_PENDING", f"no judgement is pending for {stop_id}/{judge_id} (current: {current})", current=current)
    judge = stop.get("judge") or {}
    allowed, triggers = list(judge.get("allowed") or []), list(judge.get("triggers") or [])
    if decision not in allowed:
        return reject("STOP_DECISION_NOT_ALLOWED", f"decision {decision!r} is not allowed here; choose one of {allowed}", allowed=allowed, triggers=triggers)
    lang = _lang(index)
    if decision == "ask":
        form = "two" if any(t in triggers for t in _GATE_TRIGGERS_TWO_FORM) else "three"
        intents = ["continue_run", "new_task", "end_run"] if form == "three" else ["continue_run", "end_run"]
        if recommendation not in intents + ["none"]:
            return reject("STOP_GATE_FIELDS", f"--recommendation must be one of {intents + ['none']}", field="recommendation", expected=intents + ["none"])
        if not (explanation or "").strip():
            return reject("STOP_GATE_FIELDS", "--explanation is required for ask", field="explanation", expected=["a non-empty explanation in the user's language"])
        if recommendation == "none" and not (advice or "").strip():
            return reject("STOP_GATE_FIELDS", "--advice is required when the recommendation is none", field="advice",
                          expected=["a non-empty advice in the user's language"])
        opened = _open_stop_gate(cache_dir, index, life, (stop.get("reply") or {}).get("text") or "", form=form, opened_by=f"executor:{judge_id}",
                                 recommendation=recommendation, advice=advice, explanation=explanation, persist=False)
        accepted = {"at": now, "decision": "ask", "recommendation": recommendation, "explanation": explanation, "advice": advice, "reason": reason,
                    "gate": opened["gate"], "public_block_ref": opened["public_block_ref"]}
        dec["accepted"] = accepted
        _archive_attempt(cache_dir, stop_id, judge_id, dec, _accepted_attempt(accepted))
        return {"status": "GATE", "stop_id": stop_id, "judge_id": judge_id, "question_id": opened["question_id"],
                "public_block_ref": opened["public_block_ref"], "form": form}
    try:
        wait = None
        # docs/05SoulRun 90 round 4 (ledger decision 184): no wait for a run whose engine stop was cut off before its index write - the
        # run that never stopped waits at that stop (WAITING_USER), where none is recorded (as for _prepare_judge's abandonment)
        if index.get("run_state") == "RUNNING" and not engine_core.unindexed_stop(cache_dir):
            wait = engine_core.record_transport_wait(cache_dir, since=stop.get("requested_at"), reason=f"human stop {stop_id} (executor {judge_id})",
                                                     code="HUMAN_STOP_WAIT")
        engine_core.set_host_fields(cache_dir, entry_mode="stopped_continue")
    except (engine_core.EngineError, RunStoreError) as exc:
        _archive_attempt(cache_dir, stop_id, judge_id, dec, {"at": now, "decision": decision, "reason": reason, "accepted": False, "code": exc.code})
        raise
    public_note = NOTES[lang]["executor_continue"].format(reason=reason)
    accepted = {"at": now, "decision": "continue", "reason": reason, "public_note": public_note, "wait": wait}
    dec["accepted"] = accepted
    _archive_attempt(cache_dir, stop_id, judge_id, dec, _accepted_attempt(accepted))
    engine_dir = engine_core._engine_dir()   # docs/05SoulRun 90 (problem 31): the engine that runs, never a path inferred from the run folder
    return {"status": "CONTINUE", "stop_id": stop_id, "judge_id": judge_id, "cache_dir": str(cache_dir), "public_note": public_note,
            "next_action": f"python {engine_dir / 'python_tools' / 'next_node.py'} --cache-dir {cache_dir}", "run_state": index.get("run_state")}


# ---------------------------------------------------------------------------
# continue, end, hand over
# ---------------------------------------------------------------------------

def _continue_run(cache_dir: Path, index: dict, life: dict, *, rule: str | None = None, continued_by: str | None = None, human_note: str, note: str,
                  recorded_choice_label: str | None = None, host: dict, question_id: str | None = None, judge_id: str | None = None,
                  host_turn_id=None, wait_code: str = "HUMAN_STOP_WAIT") -> dict:
    """final_plan §3.4: the ONLY prepare-side resolver with kind continue (the executor's continue is resolved by _merge_stop_files). The
    pause is recorded as HUMAN_STOP_WAIT through the H3 re-entry, so _active_elapsed_ms still deducts it from the node budget (Q7).
    alpha.105 (doc 259 spec §1.5): a restart question's continue records RESTART_WAIT (`wait_code`) since the question's `wait_since`."""
    stop = life["stop"]
    stop_id, since = stop["stop_id"], stop.get("wait_since") or stop.get("requested_at")
    by = "human" if continued_by is None or continued_by.startswith(("rule:", "human:")) else "executor"
    _resolve_stop(life, kind="continue", by=by, rule=rule, question_id=question_id, judge_id=judge_id, note=note)
    _write_life(cache_dir, life)
    import prepare_cache as pc  # noqa: PLC0415
    ctx = pc._reenter_interrupted(cache_dir, since=since, reason=f"human stop {stop_id} ({continued_by or rule})",
                                  entry_mode="stopped_continue", message=human_note, origin_channel=host.get("origin_channel") or "",
                                  requested_model=host.get("requested_model"), fences=host.get("fences"), tools=host.get("tools"), user_id=host.get("user_id"),
                                  code=wait_code, abandon_reason=f"host re-entry after human stop {stop_id}",
                                  extras={"stop_continue": True, "stop_id": stop_id, "continued_by": continued_by or rule,
                                          "public_note": note, "recorded_choice_label": recorded_choice_label})
    _remember(life, stop_id, host_turn_id, ctx)
    _write_life(cache_dir, life)
    return ctx


def _end_by_cancel_word(cache_dir: Path, index: dict, life: dict, message: str, *, host: dict, host_turn_id) -> dict:
    """final_plan §3.1 (RUNNING, an H3 cancel word): the three calls of the H3 cancel branch (pc:349-353) plus the stop's resolution."""
    stop = life["stop"]
    stop_id = stop["stop_id"]
    lang = _lang(index)
    engine_core.terminate_run(cache_dir, kind="human_termination", by="host", reason="cancelled by the human after an interruption")
    engine_core.set_host_fields(cache_dir, **_host_fields(host, "terminal"))
    _resolve_stop(life, kind="cancel_word", by="human", rule="rule:cancel_word")
    ctx = _ctx(cache_dir, "terminal", host, {"interrupted_cancel": True, "human_note": message, "stop_ended": True, "stop_id": stop_id,
                                             "ended_by": "cancel word", "public_note": NOTES[lang]["ended"]})
    _remember(life, stop_id, host_turn_id, ctx)
    _write_life(cache_dir, life, last_turn_at=now_iso(), entry_mode="terminal", cancelled_at=now_iso(), cancel_text=message, **_uid(host))
    return ctx


def _handover_new_task(cache_dir: Path, index: dict, life: dict, *, host: dict, host_turn_id, by: str = "human", answer_text: str | None = None) -> dict:
    """final_plan §3.6: the human chose "as a new task" at the stop question - a fresh run from the ORIGINAL message (never the "2"),
    the old run ended by the human, both lifecycles linked. Synchronous inside prepare; a failed init_run puts the question back."""
    stop = life["stop"]
    stop_id = stop["stop_id"]
    gate = stop.get("gate") if isinstance(stop.get("gate"), dict) else {}
    original = gate.get("pending_message") or (stop.get("reply") or {}).get("text") or ""
    stop["state"] = "HANDOVER"
    stop["handover"] = {"started_at": now_iso(), "by": by}
    _write_life(cache_dir, life)
    import prepare_cache as pc  # noqa: PLC0415
    new_ctx = pc._fresh_run(host["root"], host["engine_dir"], host["agent_dir"], original, host.get("session_id"), host.get("origin_channel") or "",
                            host.get("requested_model"), host.get("fences"), host.get("tools"), host.get("user_id"),
                            lifecycle_extra={"superseded_from": {"cache": cache_dir.name, "stop_id": stop_id, "trace_id": index.get("trace_id")}})
    if new_ctx.get("entry_mode") == "engine_unavailable":   # no program: the cache made for it is taken back (docs/05SoulRun 90, problem 28); any other init failure leaves its half-made cache with init_error, as before
        stop["state"] = "GATED"
        stop["handover"] = None
        hint = TEXTS[_lang(index)]["failed_new_task"].format(code=(new_ctx.get("init_error") or {}).get("code"))
        render_stop_menu(cache_dir, index, stop["gate"], hint=hint)
        return _question_ctx(cache_dir, life, host, host_turn_id, public_note=hint, opened_by=stop["gate"].get("opened_by") or "")
    if gate and answer_text is not None:
        gate["state"] = "ANSWERED"
        gate["answer"] = {"text": answer_text, "at": now_iso(), "intent": "new_task"}
    _finish_handover(cache_dir, life, new_ctx["cache_name"], by)
    ctx = dict(new_ctx, stop_new_task=True, superseded_from=cache_dir.name, stop_id=stop_id, public_note=NOTES[_lang(index)]["new_task"].format(old=cache_dir.name))
    _remember(life, stop_id, host_turn_id, ctx)
    _write_life(cache_dir, life)
    return ctx


# ---------------------------------------------------------------------------
# the stop question answered
# ---------------------------------------------------------------------------

def _recorded_choice_label(cache_dir: Path, index: dict) -> str | None:
    """The engine-gate choice recorded before the stop, when any (the incident's "1"): the unconsumed answer of the current occurrence,
    else the alpha.88 cancel-to-report choice."""
    pending = _pending_answer(cache_dir, index)
    if pending:
        return pending.get("chosen_label")
    cancelled = index.get("cancelled")
    return cancelled.get("chosen_label") if isinstance(cancelled, dict) else None


def _answer_stop_gate(cache_dir: Path, index: dict, life: dict, message: str, *, host: dict, host_turn_id) -> dict:
    """final_plan §3.3 各种回答的结果 (GATED): the human's reply to the stop question."""
    stop = life["stop"]
    gate = stop["gate"]
    if gate.get("source") in stop_state.QUESTION_SOURCES:   # alpha.105 (doc 259): a supply / restart question has its own answer table
        from . import supply_flow  # noqa: PLC0415
        return supply_flow.answer_question(cache_dir, index, life, message, host=host, host_turn_id=host_turn_id)
    qid = gate["question_id"]
    opt = engine_core._match_option(gate["options"], message, engine_aliases=True)
    low = _low(message)
    now = now_iso()
    if gate.get("delivered_at") is None and (opt is not None or _DIGITS_RE.fullmatch(message.strip()) or _matches_any_option(gate["options"], low)):
        render_stop_menu(cache_dir, index, gate)   # G1: the menu the human never saw is shown again; nothing is recorded as an answer
        return _question_ctx(cache_dir, life, host, host_turn_id, public_note=None, opened_by=gate.get("opened_by") or "")
    if opt is not None and opt["intent"] == "continue_run":   # G2
        gate["state"] = "ANSWERED"
        gate["answer"] = {"text": message, "at": now, "intent": "continue_run"}
        return _continue_run(cache_dir, index, life, continued_by=f"human:{qid}", question_id=qid, human_note=gate.get("pending_message") or "",
                             note=NOTES[_lang(index)]["human_continue"].format(qid=qid, label=opt["label"]),
                             recorded_choice_label=_recorded_choice_label(cache_dir, index), host=host, host_turn_id=host_turn_id)
    if opt is not None and opt["intent"] == "new_task":   # G3 (the answer is recorded once the fresh run exists; a failed init puts the question back)
        return _handover_new_task(cache_dir, index, life, host=host, host_turn_id=host_turn_id, by="human", answer_text=message)
    if (opt is not None and opt["intent"] == "end_run") or (opt is None and (low in engine_core.TERMINATE_WORDS or _is_cancel_message(message)
                                                                            or low in ("cancel", "取消"))):   # G4 (no / 否 stay invalid, final_plan §3.3)
        engine_core.terminate_run(cache_dir, kind="human_termination", by="human", reason=f"ended by the human at stop question {qid}")
        gate["state"] = "ANSWERED"
        gate["answer"] = {"text": message, "at": now, "intent": "end_run"}
        _resolve_stop(life, kind="end_run", by="human", question_id=qid)
        engine_core.set_host_fields(cache_dir, **_host_fields(host, "terminal"))
        ctx = _ctx(cache_dir, "terminal", host, {"stop_ended": True, "interrupted_cancel": True, "human_note": message, "stop_id": stop["stop_id"],
                                                 "ended_by": f"human:{qid}", "public_note": NOTES[_lang(index)]["ended"]})
        _remember(life, stop["stop_id"], host_turn_id, ctx)
        _write_life(cache_dir, life, last_turn_at=now_iso(), entry_mode="terminal", cancelled_at=now, cancel_text=message, **_uid(host))
        return ctx
    gate.setdefault("invalid_answers", []).append({"at": now, "text": message})   # G5: never guessed for the human
    render_stop_menu(cache_dir, index, gate, hint=TEXTS[_lang(index)]["invalid_hint"].format(reply=message.strip(), n=len(gate["options"])))
    return _question_ctx(cache_dir, life, host, host_turn_id, public_note=None, opened_by=gate.get("opened_by") or "")


# ---------------------------------------------------------------------------
# the rule table for the human's next message
# ---------------------------------------------------------------------------

def _is_cancel_message(text: str) -> bool:
    import prepare_cache as pc  # noqa: PLC0415
    return pc.is_cancel_message(text)


def _is_continue_message(text: str) -> bool:
    import prepare_cache as pc  # noqa: PLC0415
    return pc.is_continue_message(text)


def _engine_gate(cache_dir: Path, index: dict) -> dict | None:
    gate = index.get("gate") if isinstance(index.get("gate"), dict) else {}
    if gate.get("state") != "WAITING_USER" or not gate.get("question_id"):
        return None
    return _plain_json(RunStore(cache_dir).gate_path(gate["question_id"]))


def _cut_off_stop(cache_dir: Path, index: dict) -> dict | None:
    """docs/05SoulRun 90 round 6 ('vc 2' defect 3, ledger decision 185): for a RUNNING run, the record of the engine stop cut
    off before its index write that the next engine call installs (prepare_cache._cut_off_stop_id: read-only, under the run
    lock; None also where the check cannot be made), else None. The run that never stopped waits at that stop, never shown:
    the human's message after a Stop is routed by rule A as at that undelivered gate (_stopped_reply), and the stop question
    offers to go back to it (_open_stop_gate). Nothing is installed or written here.
    Round 7 (line C, C6; 'line-C-holds_1' defect 5): for a run waiting at a gate too - problem 91's window, the program-integrity
    stop cut off over that gate (program_guard.orphan_stop, the one stop recognised there): the run that never stopped waits
    at the integrity stop, never shown, so rule A routes at it as undelivered, not at the gate the index names."""
    if index.get("run_state") not in ("RUNNING", "WAITING_USER"):
        return None
    import prepare_cache as pc  # noqa: PLC0415
    qid = pc._cut_off_stop_id(Path(cache_dir))
    return _plain_json(RunStore(cache_dir).gate_path(qid)) if qid else None


def _pending_answer(cache_dir: Path, index: dict) -> dict | None:
    """engine_core._pending_gate_answer over the plain index (read-only); None when nothing is recorded or a record is unreadable."""
    current = index.get("current") if isinstance(index.get("current"), dict) else {}
    if not current.get("name") or not isinstance((index.get("gate") or {}).get("history"), list):
        return None
    try:
        return engine_core._pending_gate_answer(RunStore(cache_dir), index, current["name"], int(current.get("visit") or 1))
    except (RunStoreError, KeyError, TypeError, ValueError):
        return None


def _run_gate_options(cache_dir: Path, index: dict) -> list[dict]:
    """Every option of every gate this run recorded (T3: a reply that literally matches an earlier gate is judged, never auto-answered)."""
    store = RunStore(cache_dir)
    options: list[dict] = []
    seen: set[str] = set()
    for h in (index.get("gate") or {}).get("history") or []:
        qid = h.get("question_id") if isinstance(h, dict) else None
        if not qid or qid in seen:
            continue
        seen.add(qid)
        rec = _plain_json(store.gate_path(qid))
        options.extend(o for o in ((rec or {}).get("options") or []) if isinstance(o, dict))
    return options


def _asked_again_unseen(cache_dir: Path, qid: str) -> dict | None:
    """docs/05SoulRun 90 round 7 (line C, C4): after A4's gate-answer at `qid`, the index as it now reads when the run waits at a
    stop asked again over `qid` (its record's supersedes link names `qid`: record 88's recovery completed the answer recorded
    there; the word given now was not used) that the human has not been shown (engine_core._unshown_stop); else None. Reads only."""
    store = RunStore(cache_dir)
    try:
        index = store.read_index()
        gate = index.get("gate") or {}
        if index.get("run_state") != "WAITING_USER" or gate.get("state") != "WAITING_USER" or gate.get("question_id") in (None, qid):
            return None
        now = store.read_json(store.gate_path(gate["question_id"]))
        if (now.get("supersedes") or {}).get("question_id") != qid or not engine_core._unshown_stop(store, index, now):
            return None
    except (RunStoreError, OSError, ValueError, KeyError, TypeError, AttributeError):
        return None
    return index


def _invalid_answer_turn(cache_dir: Path, index: dict, life: dict, message: str, rec: dict, *, host: dict, host_turn_id) -> dict:
    """A4 (final_plan §3.1 row 放弃 / 不做了 / abandon at a delivered gate): the engine gate answers as today (answer_gate by the host ->
    invalid_retry, entry_mode resume_invalid_answer) and the stop stays OPEN. Because next_node is fenced while the stop is open, the
    menu cannot be re-presented through a serve: the ctx carries the stop_question shape (text-only turn, doc 256 H3) with the gate's own
    menu reference and the engine's hint as public_note. Should the gate accept the word after all, the stop is resolved as a gate answer
    (A2 / A3) and the ordinary ctx is returned.
    docs/05SoulRun 90 round 7 (line C, C4; ledger decision 186 (3)): should the gate-answer instead complete the answer recorded at the gate
    before (record 88's recovery: the word is not used) and ask again at a stop the human has not been shown (_asked_again_unseen), the
    word is routed as at that unseen stop - A8, the stop question with its way back to the question the run now waits at, which the
    main executor's next-node then shows first - never A4's line beside the retired stop's menu. Record 90 (ledger decision
    190): A4's line itself states what was done and calls no reply valid."""
    stop = life["stop"]
    stop_id = stop["stop_id"]
    qid = rec.get("question_id") or (index.get("gate") or {}).get("question_id")
    answer = engine_core.answer_gate(cache_dir, qid, message, by=f"host:{host.get('origin_channel') or 'chat'}")
    status = answer.get("status")
    entry_mode = gate_reply.entry_mode(answer)
    extra = {"gate_answer": gate_reply.context(answer, qid)}
    asked = _asked_again_unseen(cache_dir, qid) if status == "WAITING_USER" else None
    if asked is not None:   # A8 at the stop asked again, as for any stop never shown; the engine's reply kept in the lifecycle
        return _open_stop_gate(cache_dir, asked, life, message, form="two", opened_by="rule:cancel_word_gate_unseen", host=host,
                               host_turn_id=host_turn_id, lifecycle_extra={"gate_answer": answer})
    if status == "WAITING_USER":
        valid_wait = gate_reply.valid_wait(answer)
        # record 90 (ledger decision 190): the stop is asked again - what was done, never 'valid reply'
        hint = (('复核已执行；当时条件未满足，请再答一次。' if _lang(index) == 'zh'
                 else 'Recheck executed; conditions were not met then. Please answer again.') if valid_wait
                else TEXTS[_lang(index)]["invalid_hint"].format(reply=message.strip(), n=len(rec.get("options") or [])))
        extra.update({"stop_question": True, "stop_id": stop_id, "question_id": qid, "public_block_ref": menu_history.ref(cache_dir, f"menu.{qid}.txt"),
                      "public_note": hint, "opened_by": "rule:valid_recheck_gate_seen" if valid_wait else "rule:invalid_answer_gate_seen"})
    else:
        _resolve_stop(life, kind="gate_terminate" if status in ("TERMINATED", "REJECTED_BY_USER") else "gate_answer", by="human",
                      rule="rule:gate_answer", question_id=qid)
    engine_core.set_host_fields(cache_dir, **_host_fields(host, entry_mode, gate_answer_status=status))
    ctx = _ctx(cache_dir, entry_mode, host, extra)
    _remember(life, stop_id, host_turn_id, ctx)
    _write_life(cache_dir, life, last_turn_at=now_iso(), entry_mode=entry_mode, gate_answer=answer, **_uid(host))
    return ctx


def _stopped_reply(cache_dir: Path, index: dict, life: dict, message: str, *, host: dict, host_turn_id) -> dict | None:
    """final_plan §3.1: the deterministic rule table (doc 256 §2.5 A1-A10 / B1-B10). Returns a ctx, or None when the stop was resolved and
    the unchanged WAITING_USER / RUNNING branch must now run on the same message (A2, A3, B1). A4 (a cancel word the engine gate does not
    know) answers the gate here and returns a text-only ctx with the stop left open (_invalid_answer_turn)."""
    stop = life["stop"]
    lang = _lang(index)
    if stop.get("state") == "JUDGING":   # the judge turn died or produced nothing: the new message is judged afresh
        if isinstance(stop.get("reply"), dict):
            _push_history(stop, "replies_history", stop["reply"], REPLIES_HISTORY_MAX)
            stop["reply"] = None
        stop["judge"] = None
        stop["state"] = "OPEN"
    if stop.get("state") == "GATED":
        return _answer_stop_gate(cache_dir, index, life, message, host=host, host_turn_id=host_turn_id)
    low = _low(message)
    bare_number = bool(_DIGITS_RE.fullmatch(message.strip()))
    # docs/05SoulRun 90 round 6 ('vc 2' defect 3, ledger decision 185): a RUNNING run whose engine stop was cut off before its
    # index write is routed as the run that never stopped, waiting at that stop it was never shown - rule A with that stop
    # undelivered (A1, A7-A10), never the RUNNING rules (B4's cancel would end the run, B8 would ask one more question).
    # Round 7 (C6): a run waiting at a gate with the program-integrity stop cut off over it is routed at that stop, undelivered
    cut_off = _cut_off_stop(cache_dir, index)
    if index.get("run_state") == "WAITING_USER" or cut_off is not None:   # A: an engine gate is pending
        gate_seen = cut_off is None and stop.get("gate_delivered_at_stop") is not None and (
            stop.get("gate_presented_at_stop") is None or stop["gate_presented_at_stop"] <= (stop.get("requested_at") or ""))   # S3 / S3′
        rec = cut_off or _engine_gate(cache_dir, index) or {}
        qid = rec.get("question_id") or (index.get("gate") or {}).get("question_id")
        opt = engine_core._match_option(rec.get("options") or [], message) if rec.get("options") else None
        if _STOP_WORD_RE.match(message):   # A1
            return _open_stop_gate(cache_dir, index, life, message, form="two", opened_by="rule:stop_word", host=host, host_turn_id=host_turn_id)
        if gate_seen:
            if opt is not None or low in engine_core.CANCEL_WORDS:   # A2: the unchanged WAITING_USER branch answers the gate
                _resolve_stop(life, kind="gate_answer", by="human", rule="rule:gate_answer", question_id=qid)
                _write_life(cache_dir, life)
                return None
            if low in engine_core.TERMINATE_WORDS:   # A3: answer_gate -> TERMINATED
                _resolve_stop(life, kind="gate_terminate", by="human", rule="rule:gate_answer", question_id=qid)
                _write_life(cache_dir, life)
                return None
            if _is_cancel_message(message):   # A4: invalid_retry at the engine gate, the stop stays OPEN - a text-only turn
                return _invalid_answer_turn(cache_dir, index, life, message, rec, host=host, host_turn_id=host_turn_id)
            if _is_continue_message(message):   # A5: the gate is re-presented, not answered
                return _continue_run(cache_dir, index, life, rule="rule:continue_word", human_note=message, note=NOTES[lang]["continue_gate"], host=host,
                                     host_turn_id=host_turn_id)
            return _prepare_judge(cache_dir, index, life, message, allowed=["continue", "ask"], triggers=["GATE_ON_SCREEN"], host=host, host_turn_id=host_turn_id)   # A6
        # A8 before A7 (doc 256 §8.2 C-5, final_plan S3′): a cancel / terminate word on a question the human never saw asks, even when the
        # gate's own cancel option is labelled with that word (the test fixture's 取消) - it must not be re-shown as if nothing was said
        if low in engine_core.CANCEL_WORDS or low in engine_core.TERMINATE_WORDS or _is_cancel_message(message):   # A8
            return _open_stop_gate(cache_dir, index, life, message, form="two", opened_by="rule:cancel_word_gate_unseen", host=host, host_turn_id=host_turn_id)
        if opt is not None or bare_number or _matches_any_option(rec.get("options") or [], low):   # A7: not an answer to a question never shown
            return _continue_run(cache_dir, index, life, rule="rule:gate_not_delivered_reshow", human_note=message,
                                 note=NOTES[lang]["not_an_answer"].format(reply=message.strip()), host=host, host_turn_id=host_turn_id)
        if _is_continue_message(message):   # A9: as A7 with the continue-word rule
            return _continue_run(cache_dir, index, life, rule="rule:continue_word", human_note=message,
                                 note=NOTES[lang]["not_an_answer"].format(reply=message.strip()), host=host, host_turn_id=host_turn_id)
        return _prepare_judge(cache_dir, index, life, message, allowed=["continue", "ask"], triggers=["GATE_NOT_DELIVERED"], host=host, host_turn_id=host_turn_id)   # A10
    # B: RUNNING
    import prepare_cache as pc  # noqa: PLC0415
    pending = _pending_answer(cache_dir, index)
    prec = _plain_json(RunStore(cache_dir).gate_path(pending["question_id"])) if pending else None
    popt = engine_core._match_option(prec.get("options") or [], message) if prec else None
    cancelled = index.get("cancelled") if isinstance(index.get("cancelled"), dict) else None
    if pc._same_turn_rebootstrap(cache_dir, index, message):   # B1: the unchanged RUNNING branch returns the rebootstrap ctx
        _resolve_stop(life, kind="same_turn_rebootstrap", by="host", rule="rule:same_turn_rebootstrap")
        _write_life(cache_dir, life)
        return None
    if cancelled and low and (low in engine_core.CANCEL_WORDS or low == _low(cancelled.get("chosen_label")) or low == _low(cancelled.get("answer_text"))):   # B2
        label = cancelled.get("chosen_label") or cancelled.get("answer_text") or "-"
        return _continue_run(cache_dir, index, life, rule="rule:repeat_recorded_answer", human_note=message,
                             note=NOTES[lang]["repeat_recorded"].format(reply=message.strip(), label=label), recorded_choice_label=cancelled.get("chosen_label"),
                             host=host, host_turn_id=host_turn_id)
    if _STOP_WORD_RE.match(message):   # B3
        return _open_stop_gate(cache_dir, index, life, message, form="two", opened_by="rule:stop_word", host=host, host_turn_id=host_turn_id)
    if _is_cancel_message(message):   # B4: the H3 cancel, and the stop is resolved with it
        return _end_by_cancel_word(cache_dir, index, life, message, host=host, host_turn_id=host_turn_id)
    if _is_continue_message(message):   # B5
        return _continue_run(cache_dir, index, life, rule="rule:continue_word", human_note=message,
                             note=NOTES[lang]["continue_run"].format(node=stop.get("node") or "-"), host=host, host_turn_id=host_turn_id)
    if pending and popt is not None:
        if popt.get("intent") == pending.get("chosen_intent"):   # B6 (T1): the incident - the recorded answer repeated
            return _continue_run(cache_dir, index, life, rule="rule:repeat_recorded_answer", human_note=message,
                                 note=NOTES[lang]["repeat_recorded"].format(reply=message.strip(), label=pending.get("chosen_label") or "-"),
                                 recorded_choice_label=pending.get("chosen_label"), host=host, host_turn_id=host_turn_id)
        n = next((i for i, o in enumerate(prec.get("options") or [], start=1) if o.get("intent") == pending.get("chosen_intent")), 0)   # B7 (T2)
        return _open_stop_gate(cache_dir, index, life, message, form="two", opened_by="rule:reply_conflicts_recorded_answer",
                               extra_question=TEXTS[lang]["t2"].format(n=n, label=pending.get("chosen_label") or "-"), host=host, host_turn_id=host_turn_id)
    if bare_number:   # B8 (T4)
        return _open_stop_gate(cache_dir, index, life, message, form="two", opened_by="rule:bare_number", host=host, host_turn_id=host_turn_id)
    if _matches_any_option(_run_gate_options(cache_dir, index), low):   # B9 (T3)
        return _prepare_judge(cache_dir, index, life, message, allowed=["continue", "ask"], triggers=["REPLY_MATCHES_RUN_GATE"], host=host, host_turn_id=host_turn_id)
    short = _is_short_reply(message)   # B10
    allowed = ["continue", "ask"] + (["new_task"] if STOP_EXECUTOR_MAY_START_NEW_TASK and not short else [])
    return _prepare_judge(cache_dir, index, life, message, allowed=allowed, triggers=["SHORT_REPLY"] if short else [], host=host, host_turn_id=host_turn_id)


# ---------------------------------------------------------------------------
# entry points from prepare_execution_context
# ---------------------------------------------------------------------------

def _hold_ctx(cache_dir: Path, life: dict, host: dict, host_turn_id, *, hold_reason: str, public_note: str, lifecycle_extra: dict | None = None) -> dict:
    stop = life["stop"]
    engine_core.set_host_fields(cache_dir, last_turn_at=now_iso(), entry_mode="stopped_hold")
    ctx = _ctx(cache_dir, "stopped_hold", host, {"stop_hold": True, "stop_id": stop["stop_id"], "stop_state": stop.get("state"),
                                                 "hold_reason": hold_reason, "public_note": public_note})
    _remember(life, stop["stop_id"], host_turn_id, ctx)
    _write_life(cache_dir, life, last_turn_at=now_iso(), entry_mode="stopped_hold", **(lifecycle_extra or {}))
    return ctx


def _stop_replay(cache_dir: Path, life: dict, host: dict) -> dict:
    """final_plan §3.7: the same host turn bootstrapped twice - no write; an accepted `ask` of the stored judge is answered with its
    reference, otherwise the stored ctx is returned unchanged."""
    stop = life["stop"]
    stored = dict((stop.get("last_bootstrap") or {}).get("ctx") or {})
    judge_id = stored.get("judge_id")
    acc = (stop_state.read_decision(cache_dir, stop.get("stop_id"), judge_id) or {}).get("accepted") if judge_id else None
    if isinstance(acc, dict) and acc.get("decision") == "ask":
        qid = ((acc.get("gate") or {}).get("question_id")) or f"stop-{stop['stop_id'].split('-', 1)[1]}"
        return _ctx(cache_dir, "stopped_question", dict(host, requested_model=stored.get("requested_model", host.get("requested_model"))),
                    {"stop_question": True, "stop_id": stop["stop_id"], "question_id": qid, "public_block_ref": acc.get("public_block_ref"),
                     "public_note": None, "opened_by": f"executor:{judge_id}"})
    return stored


def stopped_turn(cache_dir, index: dict, message: str, *, host: dict, human_turn: bool, host_turn_id: str | None) -> dict | None:
    """doc 255 final_plan §2.3 step 3 (doc 256 E1): the human's (or a machine's) next message on a run with a stop record. Returns a ctx, or
    None = no open stop after healing / the stop is resolved and the unchanged branches run on the same message."""
    engine_core.program_guard.assert_run_version(index)
    cache_dir = Path(cache_dir)
    life = read_lifecycle(cache_dir)
    before = _snapshot(life)
    life = _merge_stop_files(cache_dir, _heal_handover(cache_dir, life))
    stop = life.get("stop")
    if not _is_open(stop):
        if _snapshot(life) != before:
            _write_life(cache_dir, life)
        return None
    updated, at_stop = index.get("updated_at"), stop.get("index_updated_at")
    own = (stop.get("last_bootstrap") or {}).get("index_updated_at")   # prepare's own host-field write of the previous bootstrap is not a late commit
    baseline = max(at_stop or "", own or "") if isinstance(at_stop, str) else None
    if stop.get("write_after_stop") is None and isinstance(updated, str) and baseline and updated > baseline:   # S5, once
        stop["write_after_stop"] = {"index_updated_at": updated, "detected_at": now_iso()}
    if host_turn_id and isinstance(stop.get("last_bootstrap"), dict) and stop["last_bootstrap"].get("invocation_id") == host_turn_id:
        return _stop_replay(cache_dir, life, host)
    if not human_turn:   # final_plan §3.9 (Q16 甲): recorded, never executed; the stop, the tickets and the gate are untouched
        _push_history(stop, "machine_messages", {"text": message, "sha256": _sha(message), "received_at": now_iso(), "type": host.get("origin_type"),
                                                 "origin_channel": host.get("origin_channel"), "user_id": host.get("user_id")}, MACHINE_MESSAGES_MAX)
        note = NOTES[_lang(index)]["hold_machine"] if stop.get("requested_by") in (None, "host") else _hold_note(index, stop)   # alpha.105: a question names itself
        return _hold_ctx(cache_dir, life, host, host_turn_id, hold_reason="machine_message", public_note=note)
    return _stopped_reply(cache_dir, index, life, message, host=host, host_turn_id=host_turn_id)


def _stop_replays_on_file(cache_dir: Path) -> int:
    import prepare_cache as pc  # noqa: PLC0415
    state = _plain_json(cache_dir / pc.RECOVERY_FILE) or {}
    return len([a for a in (state.get("attempts") or []) if isinstance(a, dict) and a.get("stop_replay")])


def recovery_into_stopped_run(cache_dir, index: dict, *, host: dict, host_turn_id) -> dict | None:
    """doc 255 final_plan §2.3 step 2 / §3.8 (doc 256 E1): the host's recovery re-prompt names a stopped run. No wait is recorded and no
    ticket is invalidated: JUDGING -> a fresh judge block, GATED with an undelivered menu -> the menu again, everything else -> hold.
    Returns None when healing / the merge closed the stop (the ordinary recovery branch then applies)."""
    engine_core.program_guard.assert_run_version(index)
    cache_dir = Path(cache_dir)
    life = read_lifecycle(cache_dir)
    before = _snapshot(life)
    life = _merge_stop_files(cache_dir, _heal_handover(cache_dir, life))
    stop = life.get("stop")
    if not _is_open(stop):
        if _snapshot(life) != before:
            _write_life(cache_dir, life)
        return None
    stop["recovery_replays"] = _stop_replays_on_file(cache_dir)
    extra = {"recovery_reentries": int(life.get("recovery_reentries") or 0) + 1}
    if stop.get("state") == "JUDGING":
        judge = stop.get("judge") or {}
        return _prepare_judge(cache_dir, index, life, (stop.get("reply") or {}).get("text") or "", allowed=list(judge.get("allowed") or ["continue", "ask"]),
                              triggers=list(judge.get("triggers") or []), host=host, host_turn_id=host_turn_id, abandon=False, lifecycle_extra=extra)
    gate = stop.get("gate") if isinstance(stop.get("gate"), dict) else None
    if stop.get("state") == "GATED" and gate is not None and gate.get("delivered_at") is None:
        render_stop_menu(cache_dir, index, gate)
        return _question_ctx(cache_dir, life, host, host_turn_id, public_note=None, opened_by=gate.get("opened_by") or "", lifecycle_extra=extra)
    return _hold_ctx(cache_dir, life, host, host_turn_id, hold_reason="recovery_marker", public_note=_hold_note(index, stop), lifecycle_extra=extra)

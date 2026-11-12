"""alpha.105 (04 series doc 258 analysis, doc 259 plan; spec §1.2-§1.6): after a supply interruption the switch decides, never fatal.

A supply interruption (quota, 5xx / 529, network, CLI death, a fourth mid-run turn end) past the three quick retries no longer terminates
the run. `checkpoint_recovery` writes a `supply` record into the run's `_host_lifecycle.json` (spec §1.3) and, by the mode the host
passed down (the resume switch prepare_cache.RESUME_INTERRUPTED_ENV, read once by prepare_cache.resume_interrupted_enabled): with the switch on
(`open_supply_wait`) the record is born AUTHORIZED by the switch and the host probes and re-enters by itself, nobody asked; with it off
(`open_supply_question`) a supply question (`supply-N`, source `supply_doubt`) is opened as a stop record and the human's `continue`
authorizes the host's probe re-entry (`answer_question` Q2s). After a host restart the mode-false scan opens a restart question
(`open_restart_question_record`, `restart-N`, source `restart_doubt`) instead of re-entering, suspending a pending wait until the human
answers again (Q2r-s). While a wait is on, a failed probe holds with backoff (`record_probe_failure`, `note_probe_end`), the authorized
probe re-entry goes through `resume_authorized` (recovery marker + AUTHORIZED record + a `supply_probe` turn) and closes the record on its
final response (`note_turn_end`); a human message during the wait never re-enters (`wait_turn` / `host_answer`): a cancel word ends the
run, a continue word is acknowledged, free text is kept as a note for the node, a machine message is held.

Writers stay "host process only" (spec §0.2 item 3): every write goes through `_write_supply`; `stop_flow._close_supply` is the one home of
the archive move. `stop_flow` must not import this module at module level (its two hooks import it lazily); `prepare_cache` is imported
lazily here (the pc:178 pattern). The clock is read through `_now()` so tests can freeze it.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import zoneinfo
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import engine_core, hsaw_gate, render, stop_flow, stop_state, menu_history
from .run_store import RunStore, RunStoreError, atomic_write_bytes, dumps, now_iso  # noqa: F401 - the run_store surface the spec names (§1.2)

SUPPLY_WAIT_MAX_ENV = "SOULBOT_SUPPLY_WAIT_MAX_SECONDS"
SUPPLY_WAIT_MAX_DEFAULT = 21_600                     # 6 h (doc 258 §3 甲 example, doc 259 §3 row B)
PROBE_BACKOFF_SECONDS = (120.0, 300.0, 600.0)        # 2 / 5 / 10 min, then every 10 min
PROBE_RESET_GRACE_SECONDS = 30.0                      # the first probe after a parsed reset time waits this much past it
PROBE_TURN_TYPES = ("supply_probe", "engine_recovery")
MACHINE_TURN_TYPES = ("scheduled", "message") + PROBE_TURN_TYPES
SUPPLY_WAIT_CODE = "SUPPLY_WAIT"                      # record_transport_wait code for the dead time of a supply interruption
RESTART_WAIT_CODE = "RESTART_WAIT"                    # ... of a host restart answered by continue
TURN_ENDED_KIND = "turn_ended"                        # supply.kind when the exhausted code is TURN_ENDED_MID_RUN (no transport error, spec §1.8)
TEXT_ONLY_ENTRY_MODES = ("supply_wait", "supply_hold") # lifecycle entry_mode of the turns that print a notice and never call the engine (spec §1.8 guard)
AUTHORIZED_BY_SWITCH = "switch"                        # supply.authorized_by in mode true; the human sources are "human:<question_id>" / "human:wait" (spec §0.4)
FIRST_PROBE_AFTER_SWITCH_SECONDS = 120.0               # mode true: the first probe 2 min after the quick retries failed (spec §0.3), unless a parsed reset time is later
RESTART_QUESTION_NEW_TASK = True                       # spec §0.3 (taken as recommended): the restart question carries the alpha.104 new_task option (form three); False = two options
PENDING_NOTES_MAX = 5
CONTINUE_ALIASES = ["继续", "接着", "continue", "resume", "是", "好", "好的", "yes", "y", "ok"]   # spec §1.5: the alpha.104 three plus the alpha.61 continue words
_PROBE_KEYS = ("attempts", "next_at", "started_at", "last_error_code", "last_failed_at")
_DIGITS_RE = re.compile(r"\d+")
_RESET_AT_RE = re.compile(
    r"resets?\s+(?:at\s+)?(?P<h>\d{1,2})(?::(?P<m>\d{2}))?\s*(?P<ap>am|pm)?"
    r"(?:\s*\((?P<tz>[A-Za-z][A-Za-z0-9_+\-]*(?:/[A-Za-z0-9_+\-]+)+)\))?", re.I)
_RESET_IN_RE = re.compile(r"resets?\s+in\s+(?:(?P<h>\d+)\s*h(?:ours?|rs?)?)?\s*(?:(?P<m>\d+)\s*m(?:in(?:ute)?s?)?)?", re.I)

TEXTS_Q = {   # spec §1.5: the two questions' texts (zh binding, en a plain translation)
    "zh": {
        "supply_question": "模型供给中断（{reason}），这一场停在 {node}（第 {k}/{N} 步），已自动重试 {attempts} 次未成功{eta}。恢复后是否继续这一场？",
        "turn_ended_question": "模型多次中途结束回合（{error_code}），这一场停在 {node}（第 {k}/{N} 步），已自动接回 {attempts} 次未成功。是否继续这一场？",
        "supply_explanation": "这道门由供给中断打开：{error_code}，快速重试 {attempts} 次都失败；引擎不会自己重试。",
        "turn_ended_explanation": "这道门由模型多次中途结束回合打开：{error_code}，自动接回 {attempts} 次都没有推进；引擎不会自己重试。",
        "supply_boundary": "这一场停在 {node}（第 {visit} 次）；你选择之前不执行任何节点，供给恢复也不会自动接回。",
        "supply_note_continue": "视为授权：供给恢复后由宿主自动接回同一场，不再问第二次；已记录的选择都保留。",
        "supply_note_end": "结束这一场，不再等待；已完成的节点保留在记录里。",
        "restart_question": "宿主重启前这一场停在 {node}（第 {k}/{N} 步），最后一次引擎写入在 {since_local}。是否继续这一场？",
        "restart_explanation": "这道门由宿主重启打开：上一进程留下的运行没有自动重入。",
        "restart_explanation_supply": "这道门由宿主重启打开：重启前{authorized_how}供给恢复，重启后不再自动探测，需要你再答一次。",
        "authorized_how_human": "你已授权继续等待",
        "authorized_how_switch": "按设置在自动等待",
        "restart_boundary": "这一场停在 {node}（第 {visit} 次）；你选择之前不执行任何节点。",
        "restart_note_continue": "从 {node} 接着执行；已记录的选择都保留。",
        "restart_note_continue_supply": "重新授权：供给恢复后由宿主自动接回同一场，不再问第二次；已记录的选择都保留。",
        "restart_note_new_task": "结束这一场（不能再续跑，已完成的节点保留在记录里），用这一场的原始请求新开一场，不用重打。",
        "restart_note_end": "结束这一场，不开始新任务；已完成的节点保留在记录里。",
        "label_continue": "继续这一场",
        "label_new_task": "作为新任务",
        "label_end": "结束这一场",
        "advice": "引擎不推荐任何选项，由你决定；不回答就什么都不跑。",
        "eta": "，预计 {hhmm} 恢复",
        "eta_probe": "，{minutes} 分钟后首次探测",
        "why_supply": "供给中断后",
        "why_restart": "宿主重启后",
    },
    "en": {
        "supply_question": "The model supply was interrupted ({reason}); this run stopped at {node} (step {k}/{N}) after {attempts} automatic retries failed{eta}. Continue this run once the supply is back?",
        "turn_ended_question": "The model ended its turn mid-run repeatedly ({error_code}); this run stopped at {node} (step {k}/{N}) after {attempts} automatic re-entries failed. Continue this run?",
        "supply_explanation": "This gate was opened by a supply interruption: {error_code}; all {attempts} quick retries failed; the engine will not retry by itself.",
        "turn_ended_explanation": "This gate was opened by repeated mid-run turn ends: {error_code}; {attempts} automatic re-entries made no progress; the engine will not retry by itself.",
        "supply_boundary": "This run stopped at {node} (visit {visit}); no node runs before you choose, and a returning supply does not re-enter it by itself.",
        "supply_note_continue": "Taken as an authorization: the host re-enters this same run once the supply is back, without asking again; every recorded choice is kept.",
        "supply_note_end": "End this run and stop waiting; the completed nodes stay in the record.",
        "restart_question": "Before the host restarted this run stopped at {node} (step {k}/{N}); the last engine write was at {since_local}. Continue this run?",
        "restart_explanation": "This gate was opened by a host restart: the run left by the previous process was not re-entered automatically.",
        "restart_explanation_supply": "This gate was opened by a host restart: before it this run was waiting for its supply ({authorized_how}); after the restart nothing probes until you answer again.",
        "authorized_how_human": "you had authorized the wait",
        "authorized_how_switch": "the setting waited automatically at the time",
        "restart_boundary": "This run stopped at {node} (visit {visit}); no node runs before you choose.",
        "restart_note_continue": "Continue from {node}; every recorded choice is kept.",
        "restart_note_continue_supply": "Re-authorize: the host re-enters this same run once the supply is back, without asking again; every recorded choice is kept.",
        "restart_note_new_task": "End this run (it cannot be resumed; the completed nodes stay in the record) and start a fresh run from this run's original request, no retyping.",
        "restart_note_end": "End this run without starting a new task; the completed nodes stay in the record.",
        "label_continue": "Continue this run",
        "label_new_task": "As a new task",
        "label_end": "End this run",
        "advice": "The engine recommends no option; the decision is yours. Nothing runs until you answer.",
        "eta": ", expected back at {hhmm}",
        "eta_probe": ", first probe in {minutes} min",
        "why_supply": "after the supply interruption, ",
        "why_restart": "after the host restart, ",
    },
}

NOTES_Q = {   # spec §1.5: the host-posted or model-printed replies; every text is formatted by the function that returns it
    "zh": {
        "authorized": "已授权继续：供给恢复后自动接回这一场{eta}，不再问第二次。随时可回复「结束」结束这一场。",
        "reauthorized": "已再次授权：继续等待供给恢复{eta}。",
        "ended": "这一场已结束（{why}由你结束）。",
        "still_down": "供给仍未恢复{eta}；已授权，恢复后自动接回。你这条消息已记为补充说明，接回时交给当前节点。",
        "wait_expired": "等待已超过 {hours} 小时，不再自动探测。回复「继续」再等一轮，回复「结束」结束这一场。",
        "hold_supply_question": "这一场因模型供给中断在等你回答（问题 {qid}）；回答后才动。",
        "hold_restart_question": "宿主重启后这一场在等你回答是否继续（问题 {qid}）；回答后才动。",
        "hold_wait_machine": "这一场在等待供给恢复（已授权）；这条机器消息已记录，不执行。",
        "probe_resumed": "供给已恢复，已按你的授权接回这一场，从 {node} 接着执行。",
        "wait_auto": ("模型供给中断（{reason}），这一场停在 {node}（第 {k}/{N} 步），已自动重试 {attempts} 次未成功{eta}。"
                      "按设置（{env}=true）自动等待，供给恢复后自动接回这一场，不再询问；随时可回复「结束」结束这一场，或在引擎视图点「结束这一场」。"),
        "turn_ended_wait_auto": ("模型多次中途结束回合（{error_code}），这一场停在 {node}（第 {k}/{N} 步），已自动接回 {attempts} 次未成功。"
                                 "按设置自动等待，{minutes} 分钟后再试；随时可回复「结束」结束这一场。"),
        "still_down_auto": "供给仍未恢复{eta}；按设置自动等待，恢复后自动接回。你这条消息已记为补充说明，接回时交给当前节点。",
        "probe_resumed_auto": "供给已恢复，已按设置自动接回这一场，从 {node} 接着执行。",
    },
    "en": {
        "authorized": "Authorized: this run is re-entered automatically once the supply is back{eta}, without asking again. Reply \"end\" at any time to end this run.",
        "reauthorized": "Re-authorized: waiting for the supply to return{eta}.",
        "ended": "This run has ended ({why}ended by you).",
        "still_down": "The supply is still down{eta}; authorized, the run is re-entered automatically once it is back. Your message was kept as a note and is handed to the current node at re-entry.",
        "wait_expired": "The wait has exceeded {hours} hours; no more automatic probes. Reply \"continue\" for another round or \"end\" to end this run.",
        "hold_supply_question": "This run is waiting for your answer after a supply interruption (question {qid}); nothing runs until you answer.",
        "hold_restart_question": "After the host restart this run is waiting for your answer whether to continue (question {qid}); nothing runs until you answer.",
        "hold_wait_machine": "This run is waiting for its supply to return (authorized); this machine message was recorded, not executed.",
        "probe_resumed": "The supply is back; this run was re-entered as you authorized, continuing from {node}.",
        "wait_auto": ("The model supply was interrupted ({reason}); this run stopped at {node} (step {k}/{N}) after {attempts} automatic retries failed{eta}. "
                      "By the setting ({env}=true) the host waits and re-enters this run automatically once the supply is back, without asking; "
                      "reply \"end\" at any time to end this run, or use \"end this run\" in the engine view."),
        "turn_ended_wait_auto": ("The model ended its turn mid-run repeatedly ({error_code}); this run stopped at {node} (step {k}/{N}) after {attempts} automatic re-entries failed. "
                                 "By the setting the host waits and retries in {minutes} min; reply \"end\" at any time to end this run."),
        "still_down_auto": "The supply is still down{eta}; by the setting the host keeps waiting and re-enters automatically once it is back. Your message was kept as a note and is handed to the current node at re-entry.",
        "probe_resumed_auto": "The supply is back; this run was re-entered automatically by the setting, continuing from {node}.",
    },
}


# ---------------------------------------------------------------------------
# clock, environment, small helpers
# ---------------------------------------------------------------------------

def _now() -> datetime:
    """The one clock of this module (UTC aware); tests monkeypatch it (spec §4.2 time control)."""
    return datetime.now(timezone.utc)


def _now_iso(now: datetime | None = None) -> str:
    return reset_iso(now or _now())


def _parse_iso(value) -> datetime | None:
    """A now_iso()-format stamp as an aware datetime; None for anything else."""
    if not isinstance(value, str) or not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def max_wait_seconds() -> int:
    """SOULBOT_SUPPLY_WAIT_MAX_SECONDS (doc 259 §2): the cap of the automatic probing; ValueError or < 60 -> the 6 h default."""
    try:
        value = int(os.getenv(SUPPLY_WAIT_MAX_ENV, SUPPLY_WAIT_MAX_DEFAULT))
    except ValueError:
        return SUPPLY_WAIT_MAX_DEFAULT
    return value if value >= 60 else SUPPLY_WAIT_MAX_DEFAULT


def resume_mode_default() -> bool:
    """spec §0.0: the switch as the engine's existing reader parses it (prepare_cache.resume_interrupted_enabled) - the ONLY place the mode
    is read from the environment; used by handle_runner_recovery / open_restart_question when a caller passes resume_mode=None."""
    import prepare_cache as pc  # noqa: PLC0415 - sibling tool on the same path; imported lazily (prepare_cache imports lib.*)
    return bool(pc.resume_interrupted_enabled())


def _lang(index: dict | None) -> str:
    return hsaw_gate._lang((index or {}).get("user_language"))


def _sha(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def _auto(supply: dict | None) -> bool:
    """spec §1.5: the switch authorized this wait (mode true) - the human was never asked, so no note may say 已授权."""
    return isinstance(supply, dict) and supply.get("authorized_by") == AUTHORIZED_BY_SWITCH


def _execution(supply):
    return bool(supply and supply.get('kind') in ('engine_fault','no_progress',TURN_ENDED_KIND))


def _notes(lang,supply):
    notes=NOTES_Q[lang]
    if not _execution(supply):return notes
    zh=lang=='zh';notes=dict(notes)
    notes.update(authorized='已授权一轮有限执行恢复；仍无推进会再次停机。' if zh else 'One bounded execution recovery round authorized; no progress pauses again.',
        reauthorized='已再次授权一轮有限执行恢复。' if zh else 'One bounded execution recovery round re-authorized.',
        probe_resumed='已按你的授权接回执行，从 {node} 继续；不代表故障已修复。' if zh else 'Execution re-entered as authorized at {node}; no claim the fault is fixed.',
        probe_resumed_auto='按现有设置接回执行，从 {node} 继续；不代表根因已解决。' if zh else 'Execution re-entered by the setting at {node}; cause unresolved.',
        still_down='执行仍未推进；你这条消息保留为补充，不代替执行授权。' if zh else 'Execution remains stalled; your message is a note, not execution authorization.',
        still_down_auto='执行仍未推进，按有限恢复策略等待；你这条消息保留为补充。' if zh else 'Execution remains stalled under bounded recovery; your message is retained.',
        hold_wait_machine='执行恢复正在等待；机器消息已记录，不执行。' if zh else 'Execution recovery is waiting; machine message retained without execution.',
        hold_supply_question='执行条件有疑惑，问题 {qid} 等你回答；未答不执行。' if zh else 'Execution conditions require your answer to {qid}; no execution without it.')
    return notes


def _write_supply(cache_dir, life: dict, *, accepting_question=None, **fields) -> dict:
    """spec §1.3: the one writer of the supply record - the stop record, the supply record and both archives of the in-memory lifecycle
    plus explicit fields (nothing else of the copy), through stop_flow.write_lifecycle's read-modify-write."""
    from .run_store import lifecycle_lock
    with lifecycle_lock(cache_dir):
        latest=stop_flow.read_lifecycle(cache_dir)
        proposed=life.get('fault_reentry') or {}
        previous=latest.get('fault_reentry') or {}
        if proposed.get('state')=='AUTHORIZED_ONE_ROUND' and stop_state.read_index_plain(cache_dir).get('run_state') not in ('RUNNING','WAITING_USER'):
            raise engine_core.EngineError('ENGINE_FAULT_AUTHORIZATION_CHANGED','Run already terminal; stale recovery answer cannot reopen it.')
        if proposed.get('state')=='REVOKED_BY_HUMAN' and previous.get('state')=='CONSUMED' \
                and proposed.get('fault_sha256')==previous.get('fault_sha256'):
            life=dict(life,fault_reentry=previous)
        if proposed.get('state')=='AUTHORIZED_ONE_ROUND' and previous.get('fault_sha256')==proposed.get('fault_sha256'):
            if previous.get('state') in ('CONSUMED','REVOKED_BY_HUMAN'):
                raise engine_core.EngineError('ENGINE_FAULT_AUTHORIZATION_CHANGED','Recovery decision already consumed or revoked; never grant another round.')
            if previous.get('state')=='AUTHORIZED_ONE_ROUND' and latest.get('stop') is None \
                    and accepting_question==previous.get('question_id'):
                return latest
        return stop_flow.write_lifecycle(cache_dir, stop=life.get(stop_state.STOP_KEY), stops=life.get(stop_state.STOPS_KEY) or [],
            supply=life.get(stop_state.SUPPLY_KEY), supplies=life.get(stop_state.SUPPLIES_KEY) or [],
            **({'fault_reentry':life['fault_reentry']} if 'fault_reentry' in life else {}), **fields)


def _healed(cache_dir: Path) -> dict:
    """The lifecycle with a half handover healed and the current judge's decision merged (stop_flow.heal_all semantics, in memory)."""
    life = stop_flow.read_lifecycle(cache_dir)
    return stop_flow._merge_stop_files(cache_dir, stop_flow._heal_handover(cache_dir, life))


def _stop_open_result(stop: dict) -> dict:
    return {"status": "STOP_OPEN", "stop_id": stop.get("stop_id"), "question_id": (stop.get("gate") or {}).get("question_id"),
            "requested_by": stop.get("requested_by")}


def _node_and_visit(index: dict) -> tuple[str, int | None]:
    current = index.get("current") if isinstance(index.get("current"), dict) else {}
    return current.get("name") or "-", current.get("visit")


def _push_note(supply: dict, note: dict) -> None:
    rows = [n for n in (supply.get("pending_notes") or []) if isinstance(n, dict)]
    rows.append(note)
    supply["pending_notes"] = rows[-PENDING_NOTES_MAX:]


# ---------------------------------------------------------------------------
# the reset time (spec §1.4)
# ---------------------------------------------------------------------------

def _zone(name: str | None, local_tz):
    if not name:
        return local_tz
    try:
        return zoneinfo.ZoneInfo(name)
    except (zoneinfo.ZoneInfoNotFoundError, ValueError, OSError):
        return local_tz


RESET_ZONE_UNREADABLE_CODE = "SUPPLY_RESET_ZONE_UNREADABLE"   # docs/05SoulRun 90 (problem 21)


def _unreadable_zone(*texts) -> str | None:
    """docs/05SoulRun 90 (problem 21): the time zone a reset time names (`resets 2pm (America/New_York)`) when it cannot be read
    here - an unknown zone name, or no time-zone data (e.g. a Windows Python without the tzdata package); _zone then uses the
    machine's local zone. None when every named zone reads (or none is named)."""
    for text in texts:
        m = _RESET_AT_RE.search(text or "")
        if m and m.group("h") is not None and m.group("tz") and _zone(m.group("tz"), None) is None:
            return m.group("tz")
    return None


def _note_unreadable_zone(cache_dir: Path, index: dict, record: dict) -> dict:
    """docs/05SoulRun 90 (problem 21): a reset time computed in the machine's local zone because its named zone cannot be read is
    recorded in the run index (SUPPLY_RESET_ZONE_UNREADABLE), so the run and its report say so; the index as written is returned
    (a stop record made after it is anchored after this write). Nothing is recorded, and `index` is returned, otherwise."""
    zone = _unreadable_zone(record.get("text"), record.get("reset_text")) if record.get("reset_at") else None
    if zone is None:
        return index
    local = datetime.now().astimezone().isoformat()[-6:]
    # round 2 of docs/05SoulRun 90: the cause worded neutrally - a misspelt or unknown zone name fails the same way as missing data
    text = (f"the interruption names its reset time in time zone {zone} ({record.get('reset_text') or record.get('text')!r}), which "
            f"cannot be read here (an unknown zone name, or no time-zone data: on Windows install the tzdata package); reset_at "
            f"{record['reset_at']} and the waits were computed in the machine's local zone (UTC{local}) instead and can be off by the difference")
    try:
        return engine_core.record_run_observation(cache_dir, code=RESET_ZONE_UNREADABLE_CODE, text=text) or index
    except (engine_core.EngineError, RunStoreError, OSError):   # an index that cannot take it must not stop the question / the wait
        return index


def _reset_match(text: str | None, *, now: datetime | None = None, local_tz=None) -> tuple[datetime | None, str | None]:
    """(the next moment the text names, the substring that named it); (None, None) when the text names no time."""
    if not text:
        return None, None
    now = now or _now()
    local_tz = local_tz or datetime.now().astimezone().tzinfo
    m = _RESET_AT_RE.search(text)
    if m and m.group("h") is not None:
        hour, minute, ap = int(m.group("h")), int(m.group("m") or 0), (m.group("ap") or "").lower()
        if ap:
            hour = (hour % 12) + (12 if ap == "pm" else 0)   # 12am -> 0, 12pm -> 12
        if hour > 23 or minute > 59:
            return None, None
        tz = _zone(m.group("tz"), local_tz)
        today = now.astimezone(tz)
        candidate = datetime(today.year, today.month, today.day, hour, minute, tzinfo=tz)
        if candidate < now - timedelta(seconds=60):   # a clock time more than a minute ago names tomorrow; one just passed is today's (spec §1.4 step 2)
            candidate = candidate + timedelta(days=1)
        return candidate, m.group(0)
    m = _RESET_IN_RE.search(text)
    if m and (m.group("h") or m.group("m")):
        return now + timedelta(hours=int(m.group("h") or 0), minutes=int(m.group("m") or 0)), m.group(0)
    return None, None


def parse_supply_reset(text: str | None, *, now: datetime | None = None, local_tz=None) -> datetime | None:
    """spec §1.4: an aware datetime of the next moment the interruption text names (`resets 2:50pm (America/New_York)`, `resets 14:50`,
    `resets in 2h 15m`), or None. An unknown zone falls back to the host's local zone (a supply record made from it says so in
    the run index: SUPPLY_RESET_ZONE_UNREADABLE, docs/05SoulRun 90); no time -> None."""
    return _reset_match(text, now=now, local_tz=local_tz)[0]


def reset_iso(dt: datetime | None) -> str | None:
    return dt.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z") if dt is not None else None


def reset_local_label(dt: datetime, index: dict | None = None) -> str:
    """The clock the human reads (the zone the text named, i.e. the CLI's own clock): `14:50`."""
    return dt.strftime("%H:%M")


def _reset_label(supply: dict) -> str:
    """reset_at rendered in the zone the interruption text named (re-read from reset_text), else the host's local zone."""
    dt = _parse_iso(supply.get("reset_at"))
    if dt is None:
        return "-"
    m = _RESET_AT_RE.search(supply.get("reset_text") or "")
    tz = _zone(m.group("tz") if m else None, datetime.now().astimezone().tzinfo)
    return reset_local_label(dt.astimezone(tz))


def _eta(lang: str, supply: dict, *, now: datetime | None = None, future_only: bool = True) -> str:
    """`，预计 {hhmm} 恢复` when the reset time is known (and, for the notes, still in the future); else empty."""
    reset = _parse_iso(supply.get("reset_at"))
    if reset is None or (future_only and reset <= (now or _now())):
        return ""
    return TEXTS_Q[lang]["eta"].format(hhmm=_reset_label(supply))


# ---------------------------------------------------------------------------
# the supply record (spec §1.3) and the two questions (spec §1.5)
# ---------------------------------------------------------------------------

def _close_stale(life: dict, progress_mark: dict | None, now: str) -> None:
    """spec §1.5: a record left on file by an earlier incident is archived first - AUTHORIZED / WAIT_EXPIRED at a different mark as RESUMED
    (the run progressed after the re-entry), any other record as is."""
    supply = life.get(stop_state.SUPPLY_KEY)
    if not isinstance(supply, dict):
        return
    if supply.get("state") in stop_state.SUPPLY_WAITING_STATES and supply.get("progress_mark") != progress_mark:
        stop_flow._close_supply(life, "RESUMED", resumed_at=now)
    else:
        stop_flow._close_supply(life, supply.get("state") or "ENDED")


def _new_record(index: dict, *, mode: bool, error_code: str, details: dict, invocation_id: str, attempts: int, progress_mark: dict | None,
                since: str | None, now: datetime) -> dict:
    text = details.get("supply_text")
    reset, matched = _reset_match(text, now=now)
    return {**({'engine_fault':details['engine_fault']} if details.get('supply_kind')=='engine_fault' else {}),
            "state": "ASKED", "resume_mode": bool(mode), "since": since or index.get("updated_at"), "error_code": error_code,
            **({'error_category':details['error_class']} if details.get('error_class') in ('prompt_deadline_exceeded','stream_inactivity_timeout','transport_outcome_unknown','partial_response_interrupted','protocol_lifecycle_error') else {}),
            "kind": details.get("supply_kind"), "text": text, "error_summary": error_excerpt(details.get('provider_error_message')),
            "reset_text": details.get("supply_reset_text") or matched, "reset_at": reset_iso(reset),
            "attempts": int(attempts), "progress_mark": dict(progress_mark) if isinstance(progress_mark, dict) else None,
            "invocation_ids": [invocation_id] if invocation_id else [], "question_id": None, "stop_id": None, "opened_at": None,
            "authorized_at": None, "authorized_by": None, "authorizations": [],
            "probe": {"attempts": 0, "next_at": None, "started_at": None, "last_error_code": None, "last_failed_at": None},
            "pending_notes": [], "resumed_at": None, "ended_at": None, "expired_at": None, "human_stop_ids": [], "restart_question_id": None}


def error_excerpt(value):
    if not isinstance(value, str) or not value.strip():
        return None
    import html
    value = re.sub(r'''(?i)\b(token|api[_-]?key|password|authorization)["']?\s*[:=]\s*(?:Bearer\s+)?(?:"[^"]*"|'[^']*'|[^\s,;]+)''', r'\1=[redacted]', value)
    value = re.sub(r'(?i)\bBearer\s+[^\s,;]+|\bsk-[A-Za-z0-9_-]{12,}', '[redacted]', value)
    value = ''.join(c if c in '\n\t' or ord(c) >= 32 else f'\\x{ord(c):02x}' for c in value)
    return html.escape(value[:1200], quote=False)


def _question_gate(index: dict, *, qid: str, source: str, question: str, options: list, explanation: str, boundary: str, opened_by: str,
                   form: str, pending_message: str = "") -> dict:
    """The alpha.104 gate shape (spec104 §2.7) with the question's own source, texts and form; recommendation none (spec §1.5)."""
    lang = _lang(index)
    node, _visit = _node_and_visit(index)
    return {"question_id": qid, "node": node, "source": source, "question": question, "options": options, "closing": hsaw_gate.CLOSING[lang],
            "recommendation": "none", "advice": TEXTS_Q[lang]["advice"], "explanation": explanation, "resume_boundary": boundary,
            "form": form, "opened_by": opened_by, "opened_at": now_iso(), "delivered_at": None,
            "pending_message": pending_message, "pending_sha256": _sha(pending_message), "invalid_answers": [], "state": "WAITING", "answer": None}


def _question_stop(index: dict, *, stop_id: str, requested_by: str, error_code: str, invocation_ids: list, wait_since: str | None, gate: dict) -> dict:
    """The stop record a question opens (spec §1.5; the spec104 §2.1 shape plus invocation_ids and wait_since)."""
    node, visit = _node_and_visit(index)
    igate = index.get("gate") if isinstance(index.get("gate"), dict) else {}
    waiting = igate.get("state") == "WAITING_USER"
    return {"stop_id": stop_id, "state": "GATED", "requested_at": now_iso(), "requested_by": requested_by, "phase": requested_by,
            "host_run_ids": [], "invocation_ids": list(invocation_ids), "error_code": error_code, "run_state_at_stop": index.get("run_state"),
            "node": node if node != "-" else None, "visit": visit,
            "gate_question_id": igate.get("question_id") if waiting else None,
            "gate_delivered_at_stop": igate.get("delivered_at") if waiting else None,
            "gate_presented_at_stop": igate.get("presented_at") if waiting else None,
            "index_updated_at": index.get("updated_at"), "restops": 0, "restop_at": None, "reply": None, "replies_history": [],
            "machine_messages": [], "judge": None, "judge_seq": 0, "gate": gate, "write_after_stop": None, "recovery_replays": 0,
            "last_bootstrap": None, "wait_since": wait_since}


def _option(kind: str, label: str, intent: str, aliases: list, note: str) -> dict:
    return {"kind": kind, "label": label, "intent": intent, "aliases": list(aliases), "note": note}


def _open_supply(cache_dir, index: dict, *, mode: bool, error_code: str, error_details: dict, invocation_id: str, attempts: int,
                 progress_mark: dict, since: str | None):
    """The shared head of open_supply_question / open_supply_wait: heal + merge, the open-stop check, the stale close, the new record.
    Returns (stop_open_result, None, None, index) or (None, life, record, index) - the index as the caller goes on with it: after the
    SUPPLY_RESET_ZONE_UNREADABLE observation when one was written (docs/05SoulRun 90, problem 21), else the one passed in."""
    cache_dir = Path(cache_dir)
    life = _healed(cache_dir)
    stop = life.get(stop_state.STOP_KEY)
    if stop_flow._is_open(stop):
        return _stop_open_result(stop), None, None, index
    now = _now()
    _close_stale(life, dict(progress_mark) if isinstance(progress_mark, dict) else None, _now_iso(now))
    record = _new_record(index, mode=mode, error_code=error_code, details=dict(error_details or {}), invocation_id=invocation_id,
                         attempts=attempts, progress_mark=progress_mark, since=since, now=now)
    life[stop_state.SUPPLY_KEY] = record
    return None, life, record, _note_unreadable_zone(cache_dir, index, record)


def open_supply_question(cache_dir, index: dict, *, error_code: str, error_details: dict, invocation_id: str, attempts: int,
                         progress_mark: dict, since: str | None) -> dict:
    """spec §1.5, mode false (called by checkpoint_recovery only): the quick retries are exhausted - write the ASKED supply record, open the
    supply question (stop record s-N GATED, gate source supply_doubt, menu.supply-N.txt) and fence the run. No index write (the engine lock
    is not taken here), except the SUPPLY_RESET_ZONE_UNREADABLE observation before the stop record (docs/05SoulRun 90, problem 21).
    STOP_OPEN when a human stop or an earlier question already fences the run."""
    cache_dir = Path(cache_dir)
    stop_open, life, record, index = _open_supply(cache_dir, index, mode=False, error_code=error_code, error_details=error_details,
                                                  invocation_id=invocation_id, attempts=attempts, progress_mark=progress_mark, since=since)
    if stop_open is not None:
        return stop_open
    lang = _lang(index)
    texts = TEXTS_Q[lang]
    n = len(life.get(stop_state.STOPS_KEY) or []) + 1
    stop_id, qid = f"s-{n}", f"supply-{n}"
    node, visit = _node_and_visit(index)
    k, total = stop_flow._step_position(index)
    if record.get('kind')=='engine_fault':
        from . import tool_faults
        fault=record['engine_fault']['error']
        question=('引擎报告不可自动重试的执行条件错误，已停机。请先核对证据，再决定复核或结束。' if lang=='zh' else
            'The Engine reported a non-retryable execution condition. Paused; inspect evidence before recheck or end.')
        from . import fault_reentry
        explanation, safe_reentry=tool_faults.fault_description(record['engine_fault'],lang,
            assessment=fault_reentry.evaluate(cache_dir,index,record['engine_fault']))
    elif record.get('kind')=='no_progress':
        question=(f"同一节点 {node}（第{visit}次）恢复{attempts}次仍没有账本推进，执行已暂停。是否先核对诊断，再授权一轮有限恢复？" if lang=='zh' else
                  f"No accepted progress at {node} (visit {visit}) after {attempts} recovery probes. Inspect diagnostics before authorizing one bounded recovery round?")
        explanation=('原因不能仅凭模型回合结束判断为模型或供给。建议先核对保留的工具诊断；已完成工作不重放，未回答不再自动执行。' if lang=='zh' else
                     'A turn ending cannot classify the cause as model or supply. Inspect preserved tool diagnostics first; completed work is not replayed and no answer means no execution.')
        explanation+='\n\nENGINE_NO_PROGRESS'
    elif record.get("kind") == TURN_ENDED_KIND:
        question = texts["turn_ended_question"].format(error_code=error_code, node=node, k=k, N=total, attempts=attempts)
        explanation = texts["turn_ended_explanation"].format(error_code=error_code, attempts=attempts)
    else:
        question = texts["supply_question"].format(reason=record.get("text") or error_code, node=node, k=k, N=total, attempts=attempts,
                                                   eta=_eta(lang, record, future_only=False))
        explanation = texts["supply_explanation"].format(error_code=error_code, attempts=attempts)
        if record.get('error_summary'):
            explanation += '\n\n' + ('宿主脱敏错误摘要（非原文）：' if lang == 'zh' else 'Host-redacted error excerpt, not the original: ') + record['error_summary']
        category=record.get('error_category') or record.get('kind')
        if category:explanation+='\n'+('宿主结构化类别：' if lang=='zh' else 'Host structured category: ')+str(category)
    options = [_option("execute", texts["label_continue"], "continue_run", CONTINUE_ALIASES, texts["supply_note_continue"]),
               _option("cancel", texts["label_end"], "end_run", stop_flow._ALIASES["end_run"], texts["supply_note_end"])]
    if record.get('kind')=='no_progress':
        options[0]['note']=('只授权一轮有限恢复；不证明根因已修复，不重放已完成工作。' if lang=='zh' else
                            'Authorize one bounded round only; no claim that the cause is fixed and no replay of completed work.')
    execution=record.get('kind') in ('engine_fault','no_progress',TURN_ENDED_KIND)
    if record.get('kind')=='engine_fault':
        options[0].update(label='复核条件后继续' if lang=='zh' else 'Recheck before continuing',note='未修复仍停机，不额外授权修改缓存或程序。' if lang=='zh' else 'Remains paused if unresolved; no new permission to edit caches or programs.')
        if record['engine_fault']['error'].get('code')=='GATE_TEXT_DELIVERY_EXHAUSTED':
            options[0].update(label='授权再补送一次完整题面' if lang=='zh' else 'Allow one further original-menu delivery',
                note='只允许执行者补送原题面，不回答原业务门、不执行其选项。' if lang=='zh' else 'Delivery only; this does not answer or execute any business choice.')
        if record['engine_fault']['error'].get('code')=='ENGINE_UNEXPECTED_EXCEPTION':
            if not safe_reentry:
                options[0].update(label='仅复核条件（本次不能安全继续）' if lang=='zh' else 'Recheck only (cannot continue safely)')
                options[0]['note']=('只复核，不继续、不覆盖旧临时文件；请选择结束或保留现场排查。' if lang=='zh' else
                    'Recheck only, not continuation or installation of old temporary files. End or preserve the scene for diagnosis.')
            else:
                options[0]['label']='核对后，让刚才那一步再做一次' if lang=='zh' else 'Verify, then complete the interrupted Engine step once'
                options[0]['note']=('明确授权最多一轮安全重入；身份、提交状态或安全边界不满足仍停机，不授权改缓存或程序。' if lang=='zh' else
                    'Authorize at most one safe re-entry; identity, commit or safety failure stays paused. No cache or program edits authorized.')
        if record['engine_fault']['error'].get('code')=='ENGINE_ORPHAN_COMMIT_INTERRUPTED':
            options[0].update(label='核对后补完原提交记账' if lang=='zh' else 'Verify and complete original bookkeeping',
                note='只补一次原 Engine 转换，不重做业务、不增发代理、不回答原业务门；核验不通过仍停机。' if lang=='zh' else
                'Forward the original Engine transition once; no business replay, new agent or business gate answer. Failed verification stays paused.')
            if not safe_reentry:
                options[0].update(label='仅复核（原提交尚不可安全补完）' if lang=='zh' else 'Recheck only (original transition is unproven)')
    gate = _question_gate(index, qid=qid, source="execution_doubt" if execution else "supply_doubt", question=question, options=options, explanation=explanation,
                          boundary=texts["supply_boundary"].format(node=node, visit=visit), opened_by=f"supply:{error_code}", form="two")
    record.update(question_id=qid, stop_id=stop_id, opened_at=now_iso())
    life[stop_state.STOP_KEY] = _question_stop(index, stop_id=stop_id, requested_by="supply", error_code=error_code,
                                               invocation_ids=record["invocation_ids"], wait_since=record["since"], gate=gate)
    menu_path = stop_flow.render_stop_menu(cache_dir, index, gate)
    _write_supply(cache_dir, life, entry_mode="supply_question", last_turn_at=now_iso())
    return {"status": "OPENED", "stop_id": stop_id, "question_id": qid, "public_block_ref": menu_history.ref(cache_dir, f"menu.{qid}.txt"),
            "menu_path": str(menu_path), "supply": stop_state.supply_status(cache_dir)}


def open_supply_wait(cache_dir, index: dict, *, error_code: str, error_details: dict, invocation_id: str, attempts: int,
                     progress_mark: dict, since: str | None) -> dict:
    """spec §1.5, mode true (the twin of open_supply_question): the record is born AUTHORIZED by the switch, the first probe 2 min after the
    exhaustion or at the parsed reset time + grace; no stop record, no gate, no menu file (nothing fences, spec §0.2 item 2). No index write,
    except the SUPPLY_RESET_ZONE_UNREADABLE observation (docs/05SoulRun 90, problem 21)."""
    cache_dir = Path(cache_dir)
    stop_open, life, record, index = _open_supply(cache_dir, index, mode=True, error_code=error_code, error_details=error_details,
                                                  invocation_id=invocation_id, attempts=attempts, progress_mark=progress_mark, since=since)
    if stop_open is not None:
        return stop_open
    auth = _authorize(life, by=AUTHORIZED_BY_SWITCH, answer_text=None, question_id=None, first_delay=FIRST_PROBE_AFTER_SWITCH_SECONDS)
    _write_supply(cache_dir, life, entry_mode="supply_wait", last_turn_at=now_iso())
    return {"status": "WAITING", "question_id": None, "public_text": wait_notice(cache_dir, index, record),
            "next_probe_seconds": auth["next_probe_seconds"], "next_at": auth["next_at"], "supply": stop_state.supply_status(cache_dir)}


def open_restart_question_record(cache_dir, index: dict, *, since: str | None, reason: str = "host restart") -> dict:
    """spec §1.5, mode false only (prepare_cache.open_restart_question adds the instance-start guard and mark_interrupted): the restart question
    (stop record s-N GATED, gate source restart_doubt, menu.restart-N.txt). A pending supply wait is SUSPENDED in the same write (probe.next_at
    / started_at None, restart_question_id) so no probe runs until the human answers again (spec §0.3); no supply record is created. The
    new_task option (spec §0.3, taken as recommended) hands the run's ORIGINAL request to a fresh run through the alpha.104 handover."""
    cache_dir = Path(cache_dir)
    life = _healed(cache_dir)
    stop = life.get(stop_state.STOP_KEY)
    if stop_flow._is_open(stop):
        return _stop_open_result(stop)
    lang = _lang(index)
    texts = TEXTS_Q[lang]
    supply = life.get(stop_state.SUPPLY_KEY)
    suspended = isinstance(supply, dict) and supply.get("state") in stop_state.SUPPLY_WAITING_STATES
    n = len(life.get(stop_state.STOPS_KEY) or []) + 1
    stop_id, qid = f"s-{n}", f"restart-{n}"
    wait_since = since or index.get("updated_at")
    since_dt = _parse_iso(wait_since)
    node, visit = _node_and_visit(index)
    k, total = stop_flow._step_position(index)
    question = texts["restart_question"].format(node=node, k=k, N=total, since_local=since_dt.astimezone().strftime("%m-%d %H:%M") if since_dt else "-")
    if suspended:
        how = texts["authorized_how_human"] if str(supply.get("authorized_by") or "").startswith("human:") else texts["authorized_how_switch"]
        explanation = texts["restart_explanation_supply"].format(authorized_how=how)
        note_continue = texts["restart_note_continue_supply"]
    else:
        explanation = texts["restart_explanation"]
        note_continue = texts["restart_note_continue"].format(node=node)
    import prepare_cache as pc  # noqa: PLC0415
    original = pc._run_input_message(cache_dir) or ""
    options = [_option("execute", texts["label_continue"], "continue_run", CONTINUE_ALIASES, note_continue)]
    if RESTART_QUESTION_NEW_TASK:
        options.append(_option("execute", texts["label_new_task"], "new_task", stop_flow._ALIASES["new_task"], texts["restart_note_new_task"]))
    options.append(_option("cancel", texts["label_end"], "end_run", stop_flow._ALIASES["end_run"], texts["restart_note_end"]))
    gate = _question_gate(index, qid=qid, source="restart_doubt", question=question, options=options, explanation=explanation,
                          boundary=texts["restart_boundary"].format(node=node, visit=visit), opened_by=f"restart:{reason}",
                          form="three" if RESTART_QUESTION_NEW_TASK else "two", pending_message=original if RESTART_QUESTION_NEW_TASK else "")
    life[stop_state.STOP_KEY] = _question_stop(index, stop_id=stop_id, requested_by="restart", error_code="HOST_RESTART", invocation_ids=[],
                                               wait_since=wait_since, gate=gate)
    if suspended:
        probe = supply.get("probe") if isinstance(supply.get("probe"), dict) else {}
        probe.update(next_at=None, started_at=None)
        supply["probe"] = probe
        supply["restart_question_id"] = qid
    menu_path = stop_flow.render_stop_menu(cache_dir, index, gate)
    _write_supply(cache_dir, life, entry_mode="restart_question", last_turn_at=now_iso())
    return {"status": "OPENED", "stop_id": stop_id, "question_id": qid, "public_block_ref": menu_history.ref(cache_dir, f"menu.{qid}.txt"),
            "menu_path": str(menu_path), "supply_suspended": bool(suspended)}


# ---------------------------------------------------------------------------
# answering a question (spec §1.5 Q1 / Q2s / Q2r / Q2r-s / Q3r / Q4 / Q5)
# ---------------------------------------------------------------------------

def classify_answer(gate: dict, message: str) -> str | None:
    """"continue_run" | "end_run" | "new_task" | "invalid"; None when the gate is not a supply / restart question. The end set is the G4
    set of spec104 §2.8, the continue set the option's aliases plus prepare_cache.is_continue_message."""
    if not isinstance(gate, dict) or gate.get("source") not in stop_state.QUESTION_SOURCES:
        return None
    opt = engine_core._match_option(gate.get("options") or [], message or "", engine_aliases=True)
    if opt is not None:
        return opt.get("intent")
    low = stop_flow._low(message)
    import prepare_cache as pc  # noqa: PLC0415
    if low in engine_core.TERMINATE_WORDS or pc.is_cancel_message(message) or low in ("cancel", "取消"):
        return "end_run"
    if pc.is_continue_message(message):
        return "continue_run"
    return "invalid"


def _suspended_by(supply, qid: str) -> bool:
    return isinstance(supply, dict) and supply.get("state") in stop_state.SUPPLY_WAITING_STATES and supply.get("restart_question_id") == qid


def _authorize_at_question(cache_dir: Path, index: dict, life: dict, message: str, *, host: dict, host_turn_id, kind: str, note_key: str) -> dict:
    """Q2s / Q2r-s: the answer is an AUTHORIZATION, not a re-entry - the stop resolves as continue (resume_when_supply_returns), the record
    becomes AUTHORIZED by human:<question_id>, the host's probe does the re-entry later (spec §0.3). A text-only turn."""
    stop = life[stop_state.STOP_KEY]
    gate = stop["gate"]
    qid, stop_id = gate["question_id"], stop["stop_id"]
    supply = life[stop_state.SUPPLY_KEY]
    lang = _lang(index)
    now = _now()
    note = _notes(lang,supply)[note_key].format(eta=_eta(lang, supply, now=now))
    facts=supply.get('condition_recheck') or {}
    if facts.get('condition_result')=='PASSED':
        note+='\n'+('目录条件复核已通过；故障根因仍未确定，接回不等于根因已修复。' if lang=='zh' else
                     'Catalog conditions passed recheck; the root cause remains undetermined. Re-entry is not proof of root-cause repair.')
    if supply.get('kind')=='no_progress':
        note=('已授权一轮有限恢复；若仍无推进会再次停机，已完成写入不重放。' if lang=='zh' else
              'One bounded recovery round authorized; continued lack of progress pauses again. Completed writes are not replayed.')
    gate["state"] = "ANSWERED"
    gate["answer"] = {"text": message, "at": now_iso(), "intent": "continue_run"}
    record = stop_flow._resolve_stop(life, kind="continue", by="human", question_id=qid, note=note)
    record["resolution"].update({"resume_when_supply_returns": True, "resume_at": supply.get("reset_at")})
    auth = _authorize(life, by=f"human:{qid}", answer_text=message, question_id=qid, now=_now_iso(now))
    ctx = stop_flow._ctx(cache_dir, "supply_wait", host, {"supply_authorized": True, "kind": kind, "stop_id": stop_id, "question_id": qid,
                                                        "authorized_by": supply.get("authorized_by"), "resume_mode": supply.get("resume_mode"),
                                                         "public_note": note, "resume_at": supply.get("reset_at"), "probe_now": auth["probe_now"]})
    if supply.get('condition_recheck'):ctx['condition_recheck']=supply['condition_recheck']
    stop_flow._remember(life, stop_id, host_turn_id, ctx)
    _write_supply(cache_dir, life, accepting_question=qid, last_turn_at=now_iso(), entry_mode="supply_wait", **stop_flow._uid(host))
    engine_core.set_host_fields(cache_dir, **stop_flow._host_fields(host, "supply_wait"))
    return ctx


def answer_question(cache_dir, index: dict, life: dict, message: str, *, host: dict, host_turn_id) -> dict:
    """spec §1.5: the human's reply to an open supply / restart question (life["stop"] GATED, gate.source in QUESTION_SOURCES - the caller
    checked). Q1 undelivered menu -> shown again; Q2s continue on a supply question -> authorization; Q2r continue on a restart question ->
    the alpha.104 re-entry (RESTART_WAIT); Q2r-s continue on a restart question with a suspended wait -> re-authorization; Q3r new task on a
    restart question -> the alpha.104 handover of the original request; Q4 end -> ended by the human; Q5 anything else -> the menu with a hint."""
    cache_dir = Path(cache_dir)
    stop = life[stop_state.STOP_KEY]
    gate = stop["gate"]
    qid, stop_id, source = gate["question_id"], stop["stop_id"], gate.get("source")
    lang = _lang(index)
    texts, notes = TEXTS_Q[lang], _notes(lang,life.get(stop_state.SUPPLY_KEY))
    opt = engine_core._match_option(gate["options"], message, engine_aliases=True)
    intent = classify_answer(gate, message)
    now = now_iso()
    supply = life.get(stop_state.SUPPLY_KEY) if isinstance(life.get(stop_state.SUPPLY_KEY), dict) else None
    if gate.get("delivered_at") is None and (intent in ("continue_run", "end_run", "new_task") or _DIGITS_RE.fullmatch(message.strip())):   # Q1 (G1)
        stop_flow.render_stop_menu(cache_dir, index, gate)
        return stop_flow._question_ctx(cache_dir, life, host, host_turn_id, public_note=None, opened_by=gate.get("opened_by") or "")
    if intent=='continue_run' and source=='execution_doubt' and supply and supply.get('kind')=='engine_fault':
        from . import tool_faults
        passed=tool_faults.resolved(index,supply['engine_fault'])
        authorized=not passed and tool_faults.authorize_retry(cache_dir,index,supply['engine_fault'],qid,message,life=life)
        facts=tool_faults.recheck_facts(index,supply['engine_fault'],authorized=authorized)
        supply['condition_recheck']=facts
        gate.setdefault('recheck_attempts',[]).append(dict(at=now,answer_text_original=message,**facts))
        if not passed and not authorized:
            stop_flow.render_stop_menu(cache_dir,index,gate,hint='条件仍未修复，保持停机。' if lang=='zh' else 'Conditions remain unresolved; still paused.')
            _write_supply(cache_dir,life)
            return stop_flow._question_ctx(cache_dir,life,host,host_turn_id,public_note=None,opened_by=gate['opened_by'])
    if intent == "continue_run" and source in ("supply_doubt","execution_doubt"):
        return _authorize_at_question(cache_dir, index, life, message, host=host, host_turn_id=host_turn_id, kind="authorized", note_key="authorized")
    if intent == "continue_run" and _suspended_by(supply, qid):   # Q2r-s: the supply may still be down after the restart - no model turn
        return _authorize_at_question(cache_dir, index, life, message, host=host, host_turn_id=host_turn_id, kind="reauthorized", note_key="reauthorized")
    if intent == "continue_run":   # Q2r (G2): the model is available after a plain restart
        label = opt["label"] if opt is not None else next((o.get("label") for o in gate["options"] if o.get("intent") == "continue_run"), "")
        gate["state"] = "ANSWERED"
        gate["answer"] = {"text": message, "at": now, "intent": "continue_run"}
        return stop_flow._continue_run(cache_dir, index, life, continued_by=f"human:{qid}", question_id=qid, human_note="" if opt is not None else message,
                                       note=stop_flow.NOTES[lang]["human_continue"].format(qid=qid, label=label),
                                       recorded_choice_label=stop_flow._recorded_choice_label(cache_dir, index), host=host, host_turn_id=host_turn_id,
                                       wait_code=RESTART_WAIT_CODE)
    if intent == "new_task" and source == "restart_doubt":   # Q3r (G3, spec §0.3 as recommended): a fresh run from the original request
        ctx = stop_flow._handover_new_task(cache_dir, index, life, host=host, host_turn_id=host_turn_id, by="human", answer_text=message)
        if ctx.get("stop_new_task"):   # the old run ended by the human: a suspended wait ends with it
            after = stop_flow.read_lifecycle(cache_dir)
            if isinstance(after.get(stop_state.SUPPLY_KEY), dict) and after[stop_state.SUPPLY_KEY].get("state") in ("ASKED", "AUTHORIZED", "WAIT_EXPIRED"):
                stop_flow._close_supply(after, "ENDED", ended_at=_now_iso())
                _write_supply(cache_dir, after)
        return ctx
    if intent == "end_run":   # Q4 (G4)
        permit=life.get('fault_reentry') or {}
        if permit.get('state')=='AUTHORIZED_ONE_ROUND':
            permit.update(state='REVOKED_BY_HUMAN',revoked_at=now,revocation_answer=message)
            life['fault_reentry']=permit
        engine_core.terminate_run(cache_dir, kind="human_termination", by="human", reason=f"ended by the human at question {qid}")
        gate["state"] = "ANSWERED"
        gate["answer"] = {"text": message, "at": now, "intent": "end_run"}
        stop_flow._resolve_stop(life, kind="end_run", by="human", question_id=qid)
        if supply is not None and supply.get("state") in ("ASKED", "AUTHORIZED", "WAIT_EXPIRED"):
            stop_flow._close_supply(life, "ENDED", ended_at=_now_iso())
        engine_core.set_host_fields(cache_dir, **stop_flow._host_fields(host, "terminal"))
        why = texts["why_supply" if source == "supply_doubt" else "why_restart"]
        if source=='execution_doubt':why='执行条件未满足，' if lang=='zh' else 'execution conditions unresolved; '
        ctx = stop_flow._ctx(cache_dir, "terminal", host, {"stop_ended": True, "interrupted_cancel": True, "human_note": message, "stop_id": stop_id,
                                                         "question_id": qid, "ended_by": f"human:{qid}", "public_note": notes["ended"].format(why=why)})
        stop_flow._remember(life, stop_id, host_turn_id, ctx)
        _write_supply(cache_dir, life, last_turn_at=now_iso(), entry_mode="terminal", cancelled_at=now, cancel_text=message, **stop_flow._uid(host))
        return ctx
    gate.setdefault("invalid_answers", []).append({"at": now, "text": message})   # Q5 (G5): never guessed for the human
    stop_flow.render_stop_menu(cache_dir, index, gate, hint=stop_flow.TEXTS[lang]["invalid_hint"].format(reply=message.strip(), n=len(gate["options"])))
    return stop_flow._question_ctx(cache_dir, life, host, host_turn_id, public_note=None, opened_by=gate.get("opened_by") or "")


# ---------------------------------------------------------------------------
# authorization, the probe schedule, the wait (spec §1.6)
# ---------------------------------------------------------------------------

def _authorize(life: dict, *, by: str, answer_text: str | None, question_id: str | None, first_delay: float = 0.0, now: str | None = None) -> dict:
    """spec §1.6: life["supply"] becomes AUTHORIZED by `by` (the switch, or human:<question_id> / human:wait); the probe schedule restarts.
    First probe = reset_at + grace when the reset is in the future, else now + first_delay (0 for a human: time passed while they decided;
    2 min for the switch: the supply just failed four times). The caller writes. Returns probe_now / next_at / next_probe_seconds."""
    supply = life[stop_state.SUPPLY_KEY]
    now_dt = _parse_iso(now) or _now()
    now_s = _now_iso(now_dt)
    reset = _parse_iso(supply.get("reset_at"))
    first = reset + timedelta(seconds=PROBE_RESET_GRACE_SECONDS) if reset is not None and reset > now_dt else now_dt + timedelta(seconds=first_delay)
    supply["state"] = "AUTHORIZED"
    supply["authorized_at"] = now_s
    supply["authorized_by"] = by
    rows = [a for a in (supply.get("authorizations") or []) if isinstance(a, dict)]
    rows.append({"at": now_s, "by": by, "question_id": question_id, "answer_text": answer_text, "resume_at": supply.get("reset_at")})
    supply["authorizations"] = rows
    supply["probe"] = {"attempts": 0, "next_at": reset_iso(first), "started_at": None, "last_error_code": None, "last_failed_at": None}
    supply["restart_question_id"] = None
    supply["expired_at"] = None
    return {"probe_now": first <= now_dt, "next_at": reset_iso(first), "next_probe_seconds": max(0.0, (first - now_dt).total_seconds())}


def next_probe_delay(supply: dict, *, now: datetime | None = None) -> float | None:
    """spec §1.6: seconds until the host may probe again after the failure being booked, or None when nothing may be probed (not AUTHORIZED,
    or the cap SOULBOT_SUPPLY_WAIT_MAX_SECONDS since authorized_at is reached). Backoff 2 / 5 / 10 / 10 ... min by the failed probes on file;
    the switch's own first probe (2 min after the exhaustion, doc 259 §2 "2、5、10 分钟") was the first slot, so its failures take 5 / 10 min
    (spec §0.3, S-21) while a human authorization probes at once and its failures take 2 / 5 / 10 min (S-8). A reset time still in the future
    postpones the probe to reset_at + grace."""
    if not isinstance(supply, dict) or supply.get("state") != "AUTHORIZED":
        return None
    now_dt = now or _now()
    authorized = _parse_iso(supply.get("authorized_at"))
    if authorized is None or (now_dt - authorized).total_seconds() > max_wait_seconds():
        return None
    n = int((supply.get("probe") or {}).get("attempts") or 0) + (1 if _auto(supply) else 0)
    delay = PROBE_BACKOFF_SECONDS[min(n, len(PROBE_BACKOFF_SECONDS) - 1)]
    reset = _parse_iso(supply.get("reset_at"))
    if reset is not None and reset > now_dt:
        delay = max(delay, (reset - now_dt).total_seconds() + PROBE_RESET_GRACE_SECONDS)
    return float(delay)


def _note_human_stops(life: dict, supply: dict) -> None:
    """spec §1.9 (bookkeeping only): a human Stop resolved after the authorization is remembered on the record."""
    rows = [r for r in (life.get(stop_state.STOPS_KEY) or []) if isinstance(r, dict)]
    last = rows[-1] if rows else None
    if not last or last.get("requested_by") != "host" or not last.get("stop_id"):
        return
    if ((last.get("resolution") or {}).get("at") or "") > (supply.get("authorized_at") or "") and last["stop_id"] not in (supply.get("human_stop_ids") or []):
        supply["human_stop_ids"] = list(supply.get("human_stop_ids") or []) + [last["stop_id"]]


def _book_failure(life: dict, supply: dict, *, error_code: str, invocation_id: str) -> dict:
    """The bookkeeping record_probe_failure and note_probe_end share: one more failed probe, the next backoff or WAIT_EXPIRED at the cap."""
    now_dt = _now()
    now_s = _now_iso(now_dt)
    probe = supply.get("probe") if isinstance(supply.get("probe"), dict) else {}
    delay = next_probe_delay(supply, now=now_dt)   # by the failures on file before this one (spec §1.6 backoff slots)
    probe["attempts"] = int(probe.get("attempts") or 0) + 1
    probe["last_error_code"] = error_code
    probe["last_failed_at"] = now_s
    probe["started_at"] = None
    if invocation_id:
        supply["invocation_ids"] = list(supply.get("invocation_ids") or []) + [invocation_id]
    _note_human_stops(life, supply)
    if delay is None:
        supply["state"] = "WAIT_EXPIRED"
        supply["expired_at"] = supply.get("expired_at") or now_s
        probe["next_at"] = None
    else:
        probe["next_at"] = reset_iso(now_dt + timedelta(seconds=delay))
    supply["probe"] = probe
    return {"state": supply["state"], "next_probe_seconds": delay, "next_at": probe["next_at"], "attempts": probe["attempts"], "cap_seconds": max_wait_seconds()}


def record_probe_failure(cache_dir, *, error_code: str, invocation_id: str, human_turn: bool) -> dict:
    """spec §1.6 (called by checkpoint_recovery at exhaustion while a record is AUTHORIZED / WAIT_EXPIRED at the same mark): a probe or a
    re-entry failed while the wait is on - one more attempt, the next backoff, or WAIT_EXPIRED at the cap. `human_turn` only selects the
    caller's notice (spec §1.8); the schedule is the same whoever's turn failed."""
    cache_dir = Path(cache_dir)
    life = stop_flow.read_lifecycle(cache_dir)
    supply = life.get(stop_state.SUPPLY_KEY)
    if not isinstance(supply, dict) or supply.get("state") not in stop_state.SUPPLY_WAITING_STATES:
        return {"state": supply.get("state") if isinstance(supply, dict) else None, "next_probe_seconds": None, "next_at": None, "attempts": 0,
                "cap_seconds": max_wait_seconds()}
    outcome = _book_failure(life, supply, error_code=error_code, invocation_id=invocation_id)
    _write_supply(cache_dir, life)
    return outcome


def note_probe_end(cache_dir, *, run_status: str, error_code: str | None, run_id: str | None = None) -> dict | None:
    """spec §1.6, the third probe outcome (the host waiter after the probe's host run is terminal; the startup scan / waiter with
    run_status="HOST_RESTART" for a probe that died with an earlier process): a probe run that ended with the record still AUTHORIZED and
    probe.started_at set is booked as one failed probe with backoff (or WAIT_EXPIRED at the cap, whose notice the caller posts). None when
    there is nothing to account (the record was closed by note_turn_end, or held by record_probe_failure)."""
    cache_dir = Path(cache_dir)
    life = stop_flow.read_lifecycle(cache_dir)
    supply = life.get(stop_state.SUPPLY_KEY)
    if not isinstance(supply, dict) or supply.get("state") != "AUTHORIZED" or not (supply.get("probe") or {}).get("started_at"):
        return None
    outcome = _book_failure(life, supply, error_code=error_code or f"PROBE_ENDED_{run_status}", invocation_id=run_id or "")
    _write_supply(cache_dir, life)
    if supply.get('kind')=='engine_fault' and not _run_progressed(cache_dir,supply):
        opened=ask_no_progress(cache_dir,stop_state.read_index_plain(cache_dir),attempts=outcome['attempts'],
            invocation_id=run_id or '',since=supply.get('since'))
        return dict(outcome,state='ASKED',next_probe_seconds=None,next_at=None,reason='ENGINE_NO_PROGRESS',
            question_id=opened.get('question_id'),public_text=opened.get('public_block_ref',''))
    if run_status=='COMPLETED' and not error_code:
        import checkpoint_recovery as ck
        if outcome['attempts']>=ck.MAX_ATTEMPTS and not _run_progressed(cache_dir,supply):
            opened=ask_no_progress(cache_dir,stop_state.read_index_plain(cache_dir),attempts=outcome['attempts'],
                invocation_id=run_id or '',since=supply.get('since'))
            return dict(outcome,state='ASKED',next_probe_seconds=None,next_at=None,reason='ENGINE_NO_PROGRESS',
                question_id=opened.get('question_id'),public_text=opened.get('public_block_ref',''))
    outcome["public_text"] = _hold_text(stop_state.read_index_plain(cache_dir) or {}, supply, outcome) if outcome["state"] == "WAIT_EXPIRED" else ""
    return outcome


def ask_no_progress(cache_dir,index,*,attempts,invocation_id,since):
    import checkpoint_recovery as ck
    return open_supply_question(cache_dir,index,error_code='ENGINE_NO_PROGRESS',error_details={
        'supply_kind':'no_progress','provider_error_message':
        'Repeated non-transport turn endings at the same accepted progress mark; inspect preserved tool diagnostics before retrying.'},
        invocation_id=invocation_id,attempts=attempts,progress_mark=ck._progress_mark(index),since=since)


def _run_progressed(cache_dir: Path, supply: dict) -> bool:
    """spec §1.3 progress_mark rule (as _close_stale applies it at the next exhaustion): the run stands past the mark the record was
    written at - engine nodes were served and committed since, so the supply is evidently back. False when either mark is unknown."""
    mark = supply.get("progress_mark")
    index = stop_state.read_index_plain(cache_dir)
    if not isinstance(mark, dict) or not index or not isinstance(index.get("current"), dict):
        return False
    if index.get('run_state') in engine_core.TERMINAL_STATES:
        return True
    if index.get('run_state')=='WAITING_USER' and (index.get('gate') or {}).get('state')=='WAITING_USER':
        return True
    import checkpoint_recovery as ck  # noqa: PLC0415 - sibling tool on the same path (the pc:178 pattern); the one definition of the mark
    return ck._progress_mark(index) != mark


def note_turn_end(cache_dir) -> dict | None:
    """Close a wait only after accepted progress, a real business gate or a terminal state.
    Re-entry and a final response alone leave the original wait clock and counter intact."""
    cache_dir = Path(cache_dir)
    life = stop_flow.read_lifecycle(cache_dir)
    supply = life.get(stop_state.SUPPLY_KEY)
    if not isinstance(supply, dict) or supply.get("state") not in stop_state.SUPPLY_WAITING_STATES:
        return None
    if not _run_progressed(cache_dir, supply):
        return None
    closed = stop_flow._close_supply(life, "RESUMED", resumed_at=_now_iso())
    _write_supply(cache_dir, life)
    return closed


def resume_authorized(cache_dir, index: dict, *, host: dict) -> dict:
    """spec §1.6 (the recovery-marker branch of prepare_execution_context, only for the host probe's first re-entry: AUTHORIZED / WAIT_EXPIRED,
    no open stop, origin_type supply_probe, probe.started_at None): the re-entry of the same run through _reenter_interrupted - the dead time
    since the last failed probe (never twice from the original anchor) is SUPPLY_WAIT, the pending notes become the node's human_note."""
    cache_dir = Path(cache_dir)
    life = stop_flow.read_lifecycle(cache_dir)
    supply = life[stop_state.SUPPLY_KEY]
    lang = _lang(index)
    node, _visit = _node_and_visit(index)
    pending = [n for n in (supply.get("pending_notes") or []) if isinstance(n, dict)]
    notes = "\n".join(str(n.get("text") or "") for n in pending if n.get("text"))
    probe = supply.get("probe") if isinstance(supply.get("probe"), dict) else {}
    anchor = probe.get("last_failed_at") or supply.get("since")
    probe["started_at"] = _now_iso()
    supply["probe"] = probe
    supply["delivered_notes"] = ([n for n in (supply.get("delivered_notes") or []) if isinstance(n, dict)] + pending)[-PENDING_NOTES_MAX:]
    supply["pending_notes"] = []
    _write_supply(cache_dir, life)
    import prepare_cache as pc  # noqa: PLC0415
    category=supply.get('kind')
    wait_code='ENGINE_FAULT_WAIT' if category=='engine_fault' else 'ENGINE_NO_PROGRESS_WAIT' if category in ('no_progress',TURN_ENDED_KIND) else SUPPLY_WAIT_CODE
    wait_reason='engine execution fault' if category=='engine_fault' else 'engine no accepted progress' if wait_code=='ENGINE_NO_PROGRESS_WAIT' else f"supply wait ({category or supply.get('error_code')})"
    public_note=_notes(lang,supply)["probe_resumed_auto" if _auto(supply) else "probe_resumed"].format(node=node)
    if (supply.get('condition_recheck') or {}).get('condition_result')=='PASSED':
        public_note+='\n'+('目录条件复核已通过；根因未确定。' if lang=='zh' else 'Catalog conditions passed recheck; root cause undetermined.')
    return pc._reenter_interrupted(cache_dir, since=anchor, reason=wait_reason,
                                   entry_mode="supply_resume", message=notes, origin_channel=host.get("origin_channel") or "",
                                   requested_model=host.get("requested_model"), fences=host.get("fences"), tools=host.get("tools"), user_id=host.get("user_id"),
                                   code=wait_code, abandon_reason="host re-entry after a classified wait",
                                   preserve_dispatch=category=='engine_fault',
                                    extras={"supply_resume": True, "question_id": supply.get("question_id"), "authorized_by": supply.get("authorized_by"),
                                            "condition_recheck":supply.get('condition_recheck'),
                                            "public_note": public_note})


def _wait_ctx(cache_dir: Path, host: dict, supply: dict, *, kind: str, note: str, probe_now: bool) -> dict:
    return stop_flow._ctx(cache_dir, "supply_wait", host, {"supply_authorized": True, "kind": kind, "stop_id": None, "question_id": supply.get("question_id"),
                                                         "authorized_by": supply.get("authorized_by"), "resume_mode": supply.get("resume_mode"),
                                                         "public_note": note, "resume_at": supply.get("reset_at"), "probe_now": bool(probe_now)})


def wait_turn(cache_dir, index: dict, message: str, *, host: dict, human_turn: bool, host_turn_id) -> dict | None:
    """spec §1.6 (the RUNNING branch of prepare_execution_context, a run with no open stop): a message during an AUTHORIZED / WAIT_EXPIRED wait
    never re-enters the run. Machine message -> held as a note (supply_hold); a cancel word -> the run ends by the human; a continue word ->
    re-authorizes an expired wait, is acknowledged during an authorized one; free text -> a note for the node. None when no such record,
    and None for a run that is not RUNNING: a WAITING_USER run's message answers its gate (prepare's branch order), never a wait note."""
    cache_dir = Path(cache_dir)
    life = stop_flow.read_lifecycle(cache_dir)
    supply = life.get(stop_state.SUPPLY_KEY)
    if not isinstance(supply, dict) or supply.get("state") not in stop_state.SUPPLY_WAITING_STATES or index.get("run_state") != "RUNNING":
        return None
    lang = _lang(index)
    notes = _notes(lang,supply)
    now_dt = _now()
    note_row = {"text": message, "at": _now_iso(now_dt), "sha256": _sha(message), "type": host.get("origin_type")}   # None for a human message
    if not human_turn:   # a scheduled / agent message (MACHINE_TURN_TYPES): recorded, never executed
        _push_note(supply, note_row)
        engine_core.set_host_fields(cache_dir, **stop_flow._host_fields(host, "supply_hold"))
        _write_supply(cache_dir, life, last_turn_at=now_iso(), entry_mode="supply_hold", **stop_flow._uid(host))
        return stop_flow._ctx(cache_dir, "supply_hold", host, {"supply_hold": True, "hold_reason": "supply_wait_machine_message",
                                                             "question_id": supply.get("question_id"), "authorized_by": supply.get("authorized_by"),
                                                             "resume_mode": supply.get("resume_mode"), "public_note": notes["hold_wait_machine"]})
    import prepare_cache as pc  # noqa: PLC0415
    low = stop_flow._low(message)
    if pc.is_cancel_message(message) or low in engine_core.TERMINATE_WORDS or low in stop_flow._ALIASES["end_run"]:   # 结束 / end work without a menu
        ended = end_wait(cache_dir, by="human", reason="cancelled by the human during a supply wait")
        stop_flow.write_lifecycle(cache_dir, last_turn_at=now_iso(), cancelled_at=now_iso(), cancel_text=message, **stop_flow._uid(host))
        return stop_flow._ctx(cache_dir, "terminal", host, {"stop_ended": True, "supply_ended": True, "interrupted_cancel": True, "human_note": message,
                                                          "stop_id": None, "question_id": supply.get("question_id"), "ended_by": "human:wait",
                                                          "supply_state": ended.get("supply_state"), "authorized_by": supply.get("authorized_by"),
                                                          "resume_mode": supply.get("resume_mode"), "public_note": notes["ended"].format(why=('执行停顿，' if lang=='zh' else 'execution stalled; ') if _execution(supply) else TEXTS_Q[lang]["why_supply"])})
    expired = supply.get("state") == "WAIT_EXPIRED"
    if expired and pc.is_continue_message(message):   # past the cap the human decides, in either mode (spec §0.0)
        auth = _authorize(life, by="human:wait", answer_text=message, question_id=supply.get("question_id"), now=_now_iso(now_dt))
        engine_core.set_host_fields(cache_dir, **stop_flow._host_fields(host, "supply_wait"))
        _write_supply(cache_dir, life, last_turn_at=now_iso(), entry_mode="supply_wait", **stop_flow._uid(host))
        return _wait_ctx(cache_dir, host, supply, kind="reauthorized", note=notes["reauthorized"].format(eta=_eta(lang, supply, now=now_dt)), probe_now=auth["probe_now"])
    if not (pc.is_continue_message(message) and not expired):   # a continue word during an authorized wait is not a note
        _push_note(supply, note_row)
    engine_core.set_host_fields(cache_dir, **stop_flow._host_fields(host, "supply_wait"))
    _write_supply(cache_dir, life, last_turn_at=now_iso(), entry_mode="supply_wait", **stop_flow._uid(host))
    if expired:
        return _wait_ctx(cache_dir, host, supply, kind="noted", note=notes["wait_expired"].format(hours=max_wait_seconds() // 3600), probe_now=False)
    next_at = _parse_iso((supply.get("probe") or {}).get("next_at"))
    return _wait_ctx(cache_dir, host, supply, kind="noted", note=notes["still_down_auto" if _auto(supply) else "still_down"].format(eta=_eta(lang, supply, now=now_dt)),
                     probe_now=next_at is not None and next_at <= now_dt)


def _menu_text(cache_dir: Path, index: dict, gate: dict) -> str:
    path = RunStore(cache_dir).public_dir / f"menu.{gate['question_id']}.txt"
    if not path.is_file():
        path = stop_flow.render_stop_menu(cache_dir, index, gate)
    return path.read_text(encoding="utf-8")


def _answer_result(kind: str, reply: str, *, question_id=None, stop_id=None, menu_ref=None, probe_now=None) -> dict:
    return {"handled": True, "kind": kind, "reply": reply, "menu_ref": menu_ref, "question_id": question_id, "stop_id": stop_id, "probe_now": probe_now}


def host_answer(cache_dir, message: str, *, host: dict, host_turn_id, human_turn: bool) -> dict | None:
    """spec §1.6: the single entry of the host's question shortcut (engine_hooks.build_engine_question_callback) - a human message that
    answers an open supply / restart question or arrives during a wait is answered WITHOUT a model call (the model may be what is down).
    None when the message is not for a question or a wait (the ordinary turn proceeds): a machine turn, a human stop, a run without a
    question or a wait, a WAITING_USER run's message during a wait left on file (its gate answer, spec §1.7 branch order), and - dry -
    continue / new task on a restart question without a suspended wait (the model turn re-enters through stopped_turn -> _answer_stop_gate).
    The same rules as wait_turn / answer_question through the host's door; the same lifecycle records."""
    cache_dir = Path(cache_dir)
    index = stop_state.read_index_plain(cache_dir)
    if not index or index.get("run_state") not in ("RUNNING", "WAITING_USER") or not human_turn:
        return None
    try:
        engine_core.program_guard.assert_run_version(index)
    except engine_core.EngineError as exc:
        if exc.code != 'RUN_ENGINE_VERSION_MISMATCH':
            raise
        required, loaded = index.get('engine_version'), engine_core.ENGINE_VERSION
        if _lang(index) == 'zh':
            note = (f'此运行绑定 {required}，当前引擎为 {loaded}，不能在当前版本续跑或终止。'
                    '原停止状态与全部证据保持不变；请在新会话开始新运行。'
                    '\n\nRUN_ENGINE_VERSION_MISMATCH（只读说明，未执行任何业务节点）')
        else:
            note = (f'This run requires {required}; the loaded engine is {loaded}. It cannot resume or terminate here. '
                    'Its stopped state and evidence remain unchanged. Start a new run in a new conversation.'
                    '\n\nRUN_ENGINE_VERSION_MISMATCH (read-only notice; no business node executed)')
        return _answer_result('version_blocked', render.robot_frame(note, index.get('user_language')))
    life = stop_flow.read_lifecycle(cache_dir)
    before = stop_flow._snapshot(life)
    life = stop_flow._merge_stop_files(cache_dir, stop_flow._heal_handover(cache_dir, life))
    if stop_flow._snapshot(life) != before:
        stop_flow._write_life(cache_dir, life)
    stop = life.get(stop_state.STOP_KEY)
    if stop_flow._is_open(stop):
        if stop.get("requested_by") in (None, "host"):
            return None   # a human stop: the alpha.104 rules run through the model turn
        gate = stop.get("gate") if isinstance(stop.get("gate"), dict) else None
        if stop.get("state") != "GATED" or gate is None or gate.get("source") not in stop_state.QUESTION_SOURCES:
            return None
        qid, stop_id = gate.get("question_id"), stop.get("stop_id")
        intent = classify_answer(gate, message)
        if gate.get("delivered_at") is None and (intent in ("continue_run", "end_run", "new_task") or _DIGITS_RE.fullmatch(message.strip())):
            return _answer_result("reshow", _menu_text(cache_dir, index, gate), question_id=qid, stop_id=stop_id,
                                  menu_ref=menu_history.ref(cache_dir, f"menu.{qid}.txt"))   # the host shows the menu itself and stamps delivery
        suspended = _suspended_by(life.get(stop_state.SUPPLY_KEY), qid)
        if gate.get("source") == "restart_doubt" and intent in ("continue_run", "new_task") and not (intent == "continue_run" and suspended):
            return None   # dry: a re-entry / handover is a model turn, and the model is available after a plain restart
        ctx = answer_question(cache_dir, index, life, message, host=host, host_turn_id=host_turn_id)
        if ctx.get("supply_authorized"):
            return _answer_result(ctx["kind"], ctx.get("public_note") or "", question_id=qid, stop_id=stop_id, probe_now=ctx.get("probe_now"))
        if ctx.get("stop_ended"):
            return _answer_result("ended", ctx.get("public_note") or "", question_id=qid, stop_id=stop_id)
        if ctx.get("stop_question"):
            return _answer_result("invalid", _menu_text(cache_dir, index, gate), question_id=qid, stop_id=stop_id, menu_ref=ctx.get("public_block_ref"))
        return None
    supply = life.get(stop_state.SUPPLY_KEY)
    permit=life.get('fault_reentry') or {}
    if not stop_flow._is_open(stop) and permit.get('state')=='AUTHORIZED_ONE_ROUND' and isinstance(supply,dict) \
            and supply.get('state')=='AUTHORIZED' and supply.get('kind')=='engine_fault':
        prior=next((s for s in reversed(life.get('stops') or []) if (s.get('gate') or {}).get('question_id')==permit.get('question_id')),None)
        if prior:
            intent=classify_answer(prior.get('gate') or {},message)
            if intent=='end_run':
                ended=end_wait(cache_dir,by='human',reason='later human answer ended the unused recovery round')
                return _answer_result('ended',_notes(_lang(index),supply)['ended'].format(why=''),question_id=permit['question_id'])
            if intent=='continue_run':
                engine_core.set_host_fields(cache_dir,**stop_flow._host_fields(host,'supply_wait'))
                return _answer_result('authorized',_notes(_lang(index),supply)['authorized'].format(eta=''),
                    question_id=permit['question_id'],probe_now=True)
    if index.get("run_state") == "RUNNING" and isinstance(supply, dict) and supply.get("state") in stop_state.SUPPLY_WAITING_STATES:   # step 5: the wait of a RUNNING run
        ctx = wait_turn(cache_dir, index, message, host=host, human_turn=True, host_turn_id=host_turn_id)
        if ctx is None:
            return None
        if ctx.get("supply_ended"):
            return _answer_result("ended", ctx.get("public_note") or "", question_id=supply.get("question_id"))
        if ctx.get("supply_authorized"):
            return _answer_result(ctx["kind"], ctx.get("public_note") or "", question_id=supply.get("question_id"), probe_now=ctx.get("probe_now"))
    return None


def end_wait(cache_dir, *, by: str = "human", reason: str | None = None) -> dict:
    """spec §1.6: the human ends a run whose supply wait is on (a cancel word during the wait, the engine view's end button): the run is
    terminated by the human (idempotent) and the record archived as ENDED. NOT_WAITING when no AUTHORIZED / WAIT_EXPIRED record exists."""
    cache_dir = Path(cache_dir)
    life = stop_flow.read_lifecycle(cache_dir)
    supply = life.get(stop_state.SUPPLY_KEY)
    if not isinstance(supply, dict) or supply.get("state") not in stop_state.SUPPLY_WAITING_STATES:
        return {"status": "NOT_WAITING"}
    result = engine_core.terminate_run(cache_dir, kind="human_termination", by=by, reason=reason or "ended by the human during a supply wait")
    permit=life.get('fault_reentry') or {}
    if permit.get('state')=='AUTHORIZED_ONE_ROUND':
        permit.update(state='REVOKED_BY_HUMAN',revoked_at=now_iso(),revoked_by=by)
        life['fault_reentry']=permit
    stop_flow._close_supply(life, "ENDED", ended_at=_now_iso())
    _write_supply(cache_dir, life, entry_mode="terminal", ended_at=now_iso())
    if result["status"] == "TERMINATED":
        engine_core.set_host_fields(cache_dir, entry_mode="terminal")
    return {"status": "ENDED" if result["status"] == "TERMINATED" else "ALREADY_TERMINAL", "run_state": result["run_state"], "cache_name": cache_dir.name,
            "supply_state": "ENDED"}


def _hold_text(index: dict, supply: dict, outcome: dict) -> str:
    lang = _lang(index)
    if outcome.get("state") == "WAIT_EXPIRED":
        return NOTES_Q[lang]["wait_expired"].format(hours=int(outcome.get("cap_seconds") or max_wait_seconds()) // 3600)
    return _notes(lang,supply)["still_down_auto" if _auto(supply) else "still_down"].format(eta=_eta(lang, supply))


def hold_notice(cache_dir, outcome: dict) -> str:
    """spec §1.8: the text of a hold - still_down (still_down_auto when the switch authorized) for AUTHORIZED, wait_expired for WAIT_EXPIRED."""
    cache_dir = Path(cache_dir)
    supply = stop_flow.read_lifecycle(cache_dir).get(stop_state.SUPPLY_KEY)
    return _hold_text(stop_state.read_index_plain(cache_dir) or {}, supply if isinstance(supply, dict) else {}, outcome)


def wait_notice(cache_dir, index: dict, supply: dict) -> str:
    """spec §1.6: the one human-facing message of a mode-true interruption (the reason, the expected recovery time, the mode) - wait_auto, or
    turn_ended_wait_auto when the exhausted code was TURN_ENDED_MID_RUN."""
    lang = _lang(index)
    node, _visit = _node_and_visit(index)
    k, total = stop_flow._step_position(index)
    now_dt = _now()
    next_at = _parse_iso((supply.get("probe") or {}).get("next_at"))
    minutes = max(1, round((next_at - now_dt).total_seconds() / 60)) if next_at is not None else max(1, round(FIRST_PROBE_AFTER_SWITCH_SECONDS / 60))
    attempts = int(supply.get("attempts") or 0)
    if supply.get("kind") == TURN_ENDED_KIND:
        return NOTES_Q[lang]["turn_ended_wait_auto"].format(error_code=supply.get("error_code"), node=node, k=k, N=total, attempts=attempts, minutes=minutes)
    eta = _eta(lang, supply, now=now_dt) or TEXTS_Q[lang]["eta_probe"].format(minutes=minutes)
    import prepare_cache as pc  # noqa: PLC0415 - the switch's name is defined once, next to its one reader
    note = NOTES_Q[lang]["wait_auto"].format(reason=supply.get("text") or supply.get("error_code"), node=node, k=k, N=total, attempts=attempts, eta=eta,
                                            env=pc.RESUME_INTERRUPTED_ENV)
    if supply.get('error_summary'):
        note += '\n\n' + ('原始错误摘要：' if lang == 'zh' else 'Original error excerpt: ') + supply['error_summary']
    return note

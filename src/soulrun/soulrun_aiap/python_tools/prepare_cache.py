"""Host bootstrap for the v7 engine: create the run cache before the model's turn starts.

Host contract (SoulBot agent.py / engine_hooks, unchanged host code):
  prepare_execution_context(user_message, engine_aiap_dir=..., session_id=..., origin_channel=..., requested_model=...)
      -> {turn_id, cache_dir, cache_name, trace_id, session_id, entry_mode, user_language, requested_model} | None
  finalize_execution_context(cache_dir, response_persisted=True) -> dict

v7 semantics (04 series doc 01 §9, doc 02 §11):
  * a new user turn while the session's latest run is WAITING_USER is the human's answer to the
    gate -> gate-answer (host authority), entry_mode "resume" (or "resume_waiting_conditions" / "resume_invalid_answer" /
    "terminal"); the model then re-enters through next-node (same_occurrence). A message the host marks as not the
    human's (human_turn False) never answers it: kept, entry_mode "gate_hold" (docs/05SoulRun 90, problem 30). Nor does any
    message answer an engine stop the human has not been shown (engine_core.answer_gate, docs/05SoulRun 90 round 4, problem 90):
    entry_mode "resume_invalid_answer", and next-node shows the stop
  * a new user turn while an older run is still RUNNING re-enters that run (H3 below: an interrupted
    run is never superseded) - and since alpha.104 a run the human STOPPED (a stop record in its lifecycle,
    doc 255 final_plan §2.3 / doc 256 E1) is first routed by lib.stop_flow: rules, the executor's judgement
    or the resume-doubt question decide whether the message continues it, ends it or starts a new task
  * EXCEPT a repeated bootstrap of the same turn (alpha.21, doc 41 §7.7): same session, same
    user_message, latest run RUNNING with zero commits and younger than REBOOTSTRAP_WINDOW_S ->
    the same cache is returned (lifecycle rebootstraps += 1); nothing is superseded
  * every fresh run records the session's previously routed package as previous_route
    (alpha.21, doc 41 §7.3) so Router.match can list and recommend it, never choose it
  * EXCEPT the host's own recovery re-prompt (checkpoint_recovery.build_resume_prompt, first line
    "[EXECUTE ENGINE RECOVERY]", names cache_dir): agent.py hands it to us as the latest user text,
    so it is recognised by its marker and re-enters the SAME run (entry_mode "recovery"); nothing is
    superseded and no directory is created (doc 04 §7 追记: 2026-09-06 network interruption). Only a run of the
    same session: a marker naming another conversation's run is ordinary words (docs/05SoulRun 90, problem 27)
  * H3 (alpha.60, 04 series doc 130 / 131): the host serialises turns per session, so a run that is
    still RUNNING when a new user message is bootstrapped is an INTERRUPTED run (its turn died: host
    restart, power cut, a crashed process), not a rival. With SOULBOT_RESUME_INTERRUPTED_RUNS=true
    (the default) that message re-enters the same run (entry_mode "recovery", the text kept as
    human_note for the model); only an explicit cancel word (取消 / 放弃 / 停止 / 终止 / cancel /
    abandon / stop / quit) terminates it. With "false" (alpha.61, doc 132) a continue word (继续 /
    接着 / 恢复 / 续跑 / 是 / 好 / continue / resume / yes / ok) re-enters, a cancel word terminates,
    and any other message is not executed: entry_mode "interrupted_confirm" tells the host to remind
    the human that the run is unfinished and to wait for 继续 / 取消. Nothing is superseded either way.
    docs/05SoulRun 90 round 4 (ledger decision 184): with "false", a run that looks RUNNING only because an engine stop was cut
    off before its index write is re-entered on any human message (no reminder, no cancel), so that next-node shows that stop first.
    Round 5 (ledger decision 185): a message not the human's (human_turn False) to such a run is held as the run waiting at that
    stop holds it (entry_mode "gate_hold", problem 30); problem 89's branch below is for runs genuinely interrupted. Round 7
    (line C, C2): and so is one to a run that check cannot read (_cut_off_stop_id's `undecided`: the lock a killed process left,
    a record unreadable), unless a live process holds the lock (run_store.lock_holder_alive).
    interrupted_runs / mark_interrupted / resume_prompt_for serve the host's startup scan.
    alpha.105 (doc 259): the same switch now also decides the two interruption exits. true: a supply
    interruption past the quick retries writes an AUTHORIZED supply record (lib.supply_flow.open_supply_wait)
    and the host probes and re-enters by itself, nobody asked; after a host restart the startup scan
    re-enters as before and hands a pending supply wait to the host waiter. false: the exhaustion opens a
    supply question, the restart scan opens a restart question (open_restart_question) instead of
    re-entering and suspends a pending wait; the human's "continue" authorizes the host's probe re-entry
    (recovery marker + an AUTHORIZED supply record + a supply_probe turn -> resume_authorized). Either way
    a message during a wait is held or noted (wait_turn), never re-entered, and nothing is ever fatal.
  * every fresh run is initialised here (registry roots = <agent_dir>/aiap and /aisp), so the
    model's first tool action after reading main.aisop.json is next-node --cache-dir <dir>
  * cache directories are .execution_cache/<N> under the engine dir; CACHE_NUM (default 100)
    bounds how many are kept; runs that are WAITING_USER or RUNNING are never evicted
CLI: python python_tools/prepare_cache.py --engine-dir DIR --user-message TEXT [--session-id ID]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import shutil
import stat
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib import engine_core  # noqa: E402
from lib.run_store import RunStore, RunStoreError, atomic_write_bytes, dumps, now_iso, read_bytes  # noqa: E402
from lib import stop_flow, stop_state, gate_reply  # noqa: E402

CACHE_DIRNAME = ".execution_cache"
HOST_LIFECYCLE = "_host_lifecycle.json"
DEFAULT_CACHE_NUM = 100
PROTECTED_STATES = ("RUNNING", "WAITING_USER")
REBOOTSTRAP_WINDOW_S = 120   # alpha.21 (doc 41 §7.7): production cache/12 -> 13 were 1 s apart in one host run
RECOVERY_MARKER = "[EXECUTE ENGINE RECOVERY]"
RESUME_INTERRUPTED_ENV = "SOULBOT_RESUME_INTERRUPTED_RUNS"
_CANCEL_WORDS = ("取消", "放弃", "停止", "终止", "不做了", "cancel", "abandon", "stop", "quit")
_CANCEL_RE = re.compile(r"^\s*(?:" + "|".join(re.escape(w) for w in _CANCEL_WORDS) + r")[\s。！!.]*$", re.I)
_CONTINUE_WORDS = ("继续", "继续执行", "接着", "接着做", "恢复", "续跑", "是", "好", "好的", "continue", "resume", "go on", "yes", "y", "ok")   # alpha.61
_CONTINUE_RE = re.compile(r"^\s*(?:" + "|".join(re.escape(w) for w in _CONTINUE_WORDS) + r")[\s。！!.，,]*$", re.I)
_RECOVERY_CACHE_RE = re.compile(r"^cache_dir:\s*(.+?)\s*$", re.M)


RECOVERY_FILE = "_recovery.json"
_ATTEMPT_FRESH_MS = 120_000


def interruption_anchor(cache_dir: Path) -> tuple[str | None, str]:
    """When the wait started: the latest open recovery attempt's scheduled_at when the host just started it
    (automatic ACP recovery); otherwise None, meaning 'the last engine write' (host restart / manual re-entry)."""
    try:
        state = json.loads((cache_dir / RECOVERY_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None, "host_restart_or_manual_recovery"
    attempts = [a for a in (state.get("attempts") or []) if isinstance(a, dict)]
    last = attempts[-1] if attempts else None
    if last and last.get("outcome") is None and last.get("started_at") and last.get("scheduled_at"):
        age = engine_core._ms_between(last["started_at"], now_iso())
        if age is not None and age <= _ATTEMPT_FRESH_MS:
            return last["scheduled_at"], f"acp_interruption attempt {last.get('attempt')} ({last.get('error_code')})"
    return None, "host_restart_or_manual_recovery"


def recovery_reentry_dir(message: str, root: Path) -> Path | None:
    """The cache dir named by the host's recovery re-prompt, when the message is one and the dir is
    a numbered cache under `root`; None for ordinary user text."""
    if not (message or "").lstrip().startswith(RECOVERY_MARKER):
        return None
    m = _RECOVERY_CACHE_RE.search(message)
    if not m:
        return None
    try:
        candidate = Path(m.group(1)).resolve()
    except OSError:
        return None
    if candidate.parent != root.resolve() or not re.fullmatch(r"\d+", candidate.name) or not candidate.is_dir():
        return None
    return candidate


def cache_root(engine_aiap_dir: str | Path) -> Path:
    return Path(engine_aiap_dir).resolve() / CACHE_DIRNAME


def resume_interrupted_policy() -> dict:
    """An explicit setting grants automatic re-entry, never business gate authority."""
    try:
        value = os.getenv(RESUME_INTERRUPTED_ENV)
    except Exception as exc:
        return dict(enabled=False, source='policy_read_error', error_type=type(exc).__name__)
    if value is None:
        return dict(enabled=False, source='default')
    if not isinstance(value, str):
        return dict(enabled=False, source='policy_read_error', error_type='InvalidPolicyValue')
    normalized = value.strip().casefold()
    if normalized in ('true', '1', 'yes', 'on'):
        return dict(enabled=True, source='explicit_env')
    if normalized in ('false', '0', 'no', 'off'):
        return dict(enabled=False, source='explicit_env')
    return dict(enabled=False, source='invalid_env')


def resume_interrupted_enabled() -> bool:
    return resume_interrupted_policy()['enabled']


def is_cancel_message(text: str) -> bool:
    """H3: the whole message is one cancel word (trailing punctuation allowed) - the human abandons the interrupted run."""
    return bool(_CANCEL_RE.match(text or ""))


def is_continue_message(text: str) -> bool:
    """alpha.61: the whole message is one continue word - the human's answer to the unfinished-run reminder."""
    return bool(_CONTINUE_RE.match(text or ""))


def _run_input_message(cache_dir: Path) -> str | None:
    try:
        return json.loads((cache_dir / engine_core.RUN_INPUT).read_text(encoding="utf-8")).get("user_message")
    except (OSError, ValueError, AttributeError):
        return None


def _uid(user_id) -> dict:
    return {"user_id": str(user_id)} if user_id else {}


def _plain_index(cache_dir: Path) -> dict | None:
    try:
        index = json.loads((cache_dir / "_index.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return index if isinstance(index, dict) else None


def interrupted_runs(engine_aiap_dir: str | Path, *, created_before: str | None = None) -> list[dict]:
    """H3 (doc 130 §4 b): every RUNNING engine run under the cache root, read as plain JSON. After a host restart each of them is
    an interrupted run (its turn died with the previous process). Rows: cache_dir, cache_name, session_id, user_id (when the host
    recorded it), node, visit, started_at, last_turn_at, interrupted_at, stopped (alpha.104: a human Stop is open on it - the host resumer
    skips such a row, doc 255 final_plan §3.5). Heartbeat caches and caches without an engine run are skipped.
    alpha.105 (doc 259 spec §1.7): `created_before` (an ISO Z string in the now_iso() format) drops every cache whose created_at (lifecycle
    created_at, else index started_at) is not earlier - the created-at guard of doc 258 §2: this instance's own runs are not interrupted.
    Rows gain created_at, question / question_open (an open supply / restart question), supply / supply_waiting (the supply record)."""
    rows: list[dict] = []
    root = cache_root(engine_aiap_dir)
    stop_flow.heal_all(root)   # alpha.104 (doc 255 final_plan §3.6 step 5): a handover the previous process left half-made is finished or put back
    for path in _numbered_dirs(root):
        index = _plain_index(path)
        if not index or index.get("run_state") != "RUNNING":
            continue
        life = _read_lifecycle(path)
        if life.get("channel") == "heartbeat" or life.get("engine_run") is False:
            continue
        created = life.get("created_at") or index.get("started_at")
        if created_before and isinstance(created, str) and created >= created_before:
            continue
        current = index.get("current") or {}
        s = stop_state.stop_status(path)
        q = s["gate"] if s.get("question_source") else None
        sp = stop_state.supply_status(path)
        rows.append({"cache_dir": str(path), "cache_name": path.name, "session_id": index.get("session_id"), "user_id": life.get("user_id"),
                     "node": current.get("name"), "visit": current.get("visit"), "started_at": index.get("started_at"),
                     "last_turn_at": (index.get("host") or {}).get("last_turn_at") or life.get("last_turn_at"),
                     "interrupted_at": life.get("interrupted_at"), "stopped": s["open"],
                     "created_at": created,
                     "question": {"question_id": q["question_id"], "source": q["source"], "delivered": bool(q["delivered_at"]), "stop_id": s["stop_id"]} if q else None,
                     "question_open": bool(q),
                     "supply": {"state": sp["state"], "next_probe_at": sp["probe"]["next_at"], "probe_started_at": sp["probe"]["started_at"], "resume_at": sp["reset_at"],
                                "question_id": sp["question_id"], "authorized_by": sp["authorized_by"], "resume_mode": sp["resume_mode"]} if sp else None,
                     "supply_waiting": bool(sp and sp["state"] in stop_state.SUPPLY_WAITING_STATES)})
    return rows


def mark_interrupted(cache_dir: str | Path, reason: str = "host restart") -> dict:
    """H3: record in the lifecycle that the host found this run interrupted (never changes run_state)."""
    return _write_lifecycle(Path(cache_dir), interrupted_at=now_iso(), interrupted_reason=reason)


def resume_prompt_for(cache_dir: str | Path, engine_aiap_dir: str | Path, error_code: str = "HOST_RESTART") -> str | None:
    """H3: the host's own recovery re-prompt for a RUNNING run - the text recovery_reentry_dir recognises - or None when the run
    is not RUNNING. Built by checkpoint_recovery so a restart re-entry reads exactly like an in-process one."""
    import checkpoint_recovery  # noqa: PLC0415 - sibling tool on the same path; imported lazily to keep this module light
    path = Path(cache_dir)
    index = _plain_index(path)
    if not index or index.get("run_state") != "RUNNING" or not isinstance(index.get("current"), dict):
        return None
    return checkpoint_recovery.build_resume_prompt(path, Path(engine_aiap_dir).resolve(), index, error_code, 1)


def _cache_num() -> int:
    raw = os.getenv("CACHE_NUM", str(DEFAULT_CACHE_NUM))
    try:
        return max(1, int(raw))
    except ValueError:
        return DEFAULT_CACHE_NUM


def _numbered_dirs(root: Path) -> list[Path]:
    if not root.is_dir():
        return []
    return sorted((p for p in root.iterdir() if p.is_dir() and re.fullmatch(r"\d+", p.name)), key=lambda p: int(p.name))


def _read_index(cache_dir: Path) -> dict | None:
    try:
        return RunStore(cache_dir).read_index()
    except RunStoreError:
        return None


def _read_lifecycle(cache_dir: Path) -> dict:
    path = cache_dir / HOST_LIFECYCLE
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _write_lifecycle(cache_dir: Path, **fields) -> dict:
    from lib.run_store import lifecycle_lock
    with lifecycle_lock(cache_dir):
        data = _read_lifecycle(cache_dir)
        data.update(fields)
        atomic_write_bytes(cache_dir / HOST_LIFECYCLE, dumps(data).encode("utf-8"))
        return data


def cleanup_cache(root: Path, keep: int | None = None) -> list[str]:
    """Evict the oldest numbered caches beyond `keep`; never a RUNNING / WAITING_USER run (doc 423 §4.4 incident)."""
    keep = keep or _cache_num()
    dirs = _numbered_dirs(root)
    removed: list[str] = []
    excess = len(dirs) - keep
    for path in dirs:
        if excess <= 0:
            break
        index = _read_index(path)
        if index and index.get("run_state") in PROTECTED_STATES:
            continue
        shutil.rmtree(path, ignore_errors=True)
        removed.append(path.name)
        excess -= 1
    return removed


def latest_cache_for_session(root: Path, session_id: str | None) -> Path | None:
    if not session_id:
        return None
    for path in reversed(_numbered_dirs(root)):
        index = _read_index(path)
        if index and index.get("session_id") == session_id:
            return path
    return None


def previous_route_for_session(root: Path, session_id: str | None) -> dict | None:
    """alpha.21 (doc 41 §7.3): the package the session's most recent routed run used ({package, cache, run_state});
    None when the session never routed to a program (no_match and unrouted runs are skipped)."""
    if not session_id:
        return None
    for path in reversed(_numbered_dirs(root)):
        index = _read_index(path)
        if not index or index.get("session_id") != session_id:
            continue
        package = (index.get("route") or {}).get("package")
        if isinstance(package, str) and package and package != engine_core.NO_MATCH:
            return {"package": package, "cache": path.name, "run_state": index.get("run_state")}
    return None


def _same_turn_rebootstrap(cache_dir: Path, index: dict, message: str) -> bool:
    """alpha.21 (doc 41 §7.7): the host bootstrapped the same turn twice (same message, nothing committed yet, the run
    younger than REBOOTSTRAP_WINDOW_S); the second call must re-enter the same run instead of superseding it."""
    if index.get("run_state") != "RUNNING" or index.get("completed"):
        return False
    try:
        run_input = json.loads((cache_dir / engine_core.RUN_INPUT).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    if run_input.get("user_message") != message:
        return False
    age = engine_core._ms_between(index.get("started_at"), now_iso())
    return age is not None and age <= REBOOTSTRAP_WINDOW_S * 1000


def next_cache_dir(root: Path) -> Path:
    # Numbering follows this root only. A host that keeps runs of an earlier engine elsewhere tells them apart by
    # where they live (their own root, session and trace), not by the run number.
    dirs = _numbered_dirs(root)
    n = int(dirs[-1].name) + 1 if dirs else 1
    root.mkdir(parents=True, exist_ok=True)
    return root / str(n)


WORK_DIR = "_work"   # alpha.43 C1 (doc 78): the model's own working files - scripts, snapshots, drafts, saved replies, paged reads
_RESERVE_TRIES = 64   # docs/05SoulRun 90 round 5: _fresh_run's number reservation under overlapping prepares


def _ctx(cache_dir: Path, index: dict | None, entry_mode: str, requested_model, extra: dict | None = None) -> dict:
    ctx = {"turn_id": cache_dir.name, "cache_dir": str(cache_dir), "cache_name": cache_dir.name,
           "trace_id": index.get("trace_id") if index else _read_lifecycle(cache_dir).get("trace_id"),
           "session_id": index.get("session_id") if index else _read_lifecycle(cache_dir).get("session_id"),
           "entry_mode": entry_mode, "user_language": index.get("user_language") if index else None,
           "requested_model": requested_model}
    ctx.update(extra or {})
    return ctx


def _reenter_interrupted(latest: Path, *, since: str | None, reason: str, entry_mode: str, message: str, origin_channel: str,
                         requested_model, fences, tools, user_id, extras: dict | None = None, code: str = "TRANSPORT_WAIT",
                         abandon_reason: str = "host re-entry after an interrupted turn", preserve_dispatch: bool = False) -> dict:
    """H3 re-entry into the same run (alpha.60), shared since alpha.104 (doc 255 final_plan §3.4) with the continue-after-stop path: the
    dead time is recorded as `code` (TRANSPORT_WAIT / HUMAN_STOP_WAIT) and still deducted from the node's active time; the current
    dispatch ticket, if any, is abandoned; the host fields and the lifecycle record the entry. With the defaults the H3 path is byte-identical.
    docs/05SoulRun 90 round 3 (ledger decision 183): neither the wait nor the abandonment is recorded for a run whose engine stop was cut
    off before its index write (engine_core.unindexed_stop, read-only) - the run that never stopped waits at that stop, where both are
    skipped; the stop is installed by the next next-node or node-commit, never here."""
    if not engine_core.unindexed_stop(latest):
        engine_core.record_transport_wait(latest, since=since, reason=reason, code=code)
        if not preserve_dispatch:
            engine_core.abandon_dispatch(latest, reason=abandon_reason)
    engine_core.set_host_fields(latest, last_turn_at=now_iso(), origin_channel=origin_channel or None,
                                requested_model=requested_model, host_fences=fences, host_tools=tools, entry_mode=entry_mode)
    life = _read_lifecycle(latest)
    _write_lifecycle(latest, last_turn_at=now_iso(), entry_mode=entry_mode, human_note=message,
                     interrupted_reentries=int(life.get("interrupted_reentries") or 0) + 1, **_uid(user_id))
    return _ctx(latest, engine_core_index(latest), entry_mode, requested_model,
                {"recovery_reentry": True, "interrupted_reentry": True, "human_note": message, **(extras or {})})


def _plain_dir(path: Path) -> bool:
    """A real folder: not a link, junction or other reparse point (never followed)."""
    info = os.lstat(path)
    return stat.S_ISDIR(info.st_mode) and not getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT


def _unmake_run_dir(cache_dir: Path, link: dict | None) -> bool:
    """docs/05SoulRun 90 (problem 28): take back the run folder _fresh_run made for a run that found no program - only what this call
    made: the lifecycle holding the handover link it wrote (`link`, unlinked as a file, never followed), the empty _work and _proc,
    then the folder. True when that rmdir succeeded: the path is not looked at again, since another prepare may take the number at
    once and its folder is not this call's. False, with nothing more removed, when the folder holds anything this call did not make
    (another entry, a link or junction, a file in _work or _proc, a lifecycle changed since it was written) or cannot be removed: the
    caller then records init_error in it as before. rmdir never removes a folder another process has put something in meanwhile."""
    made = {WORK_DIR, RunStore.PROC} | ({HOST_LIFECYCLE} if link is not None else set())
    try:
        if not _plain_dir(cache_dir) or {entry.name for entry in os.scandir(cache_dir)} != made:
            return False
        for name in (WORK_DIR, RunStore.PROC):
            if not _plain_dir(cache_dir / name) or any(os.scandir(cache_dir / name)):
                return False
        if link is not None:
            life = cache_dir / HOST_LIFECYCLE
            if not stat.S_ISREG(os.lstat(life).st_mode) or read_bytes(life) != dumps(link).encode("utf-8"):
                return False
            life.unlink()
        for name in (WORK_DIR, RunStore.PROC):
            (cache_dir / name).rmdir()
        cache_dir.rmdir()
        return True
    except OSError:
        return False


def _fresh_run(root: Path, engine_dir: Path, agent_dir: Path, message: str, session_id, origin_channel: str, requested_model, fences, tools, user_id,
               *, lifecycle_extra: dict | None = None) -> dict:
    """A fresh run in the next numbered cache (the former tail of prepare_execution_context). `lifecycle_extra` (alpha.104, doc 255
    final_plan §3.6): fields the new run's lifecycle carries from birth, e.g. superseded_from for a new-task handover.
    docs/05SoulRun 90 (problem 28): the numbered folder reserves the run's number at once, as before (a concurrent prepare takes the
    next one). When init_run then finds no program (PROGRAM_INVALID), the folder is taken back (_unmake_run_dir) - no empty shell
    counts in the rotation of kept runs - and the context names no folder. A folder holding anything this call did not make, and
    any other init failure, keep the folder and its init_error record as before.
    docs/05SoulRun 90 round 5 (problem 23's overlapping prepares): a number a concurrent creator took is followed by the next one
    until a folder is made (alpha.104 tried once more only; with problem 28's take-back several prepares meet on the same number),
    within _RESERVE_TRIES."""
    for attempt in range(_RESERVE_TRIES):
        cache_dir = next_cache_dir(root)
        try:
            cache_dir.mkdir(parents=True, exist_ok=False)
            break
        except FileExistsError:   # alpha.104: a concurrent creator took that number - take the next one
            if attempt == _RESERVE_TRIES - 1:
                raise
    (cache_dir / WORK_DIR).mkdir()          # alpha.43 C1: working files go here, not the cache root or _proc/
    (cache_dir / RunStore.PROC).mkdir()     # alpha.43 C1: evidence captures; created up front so a redirect never fails on a missing dir
    trace_id = f"t-{cache_dir.name}-{secrets.token_hex(4)}"
    if origin_channel == "heartbeat":
        _write_lifecycle(cache_dir, channel="heartbeat", engine_run=False, trace_id=trace_id, session_id=session_id,
                         created_at=now_iso(), requested_model=requested_model, user_message=message)
        return _ctx(cache_dir, None, "heartbeat", requested_model)
    link = None
    if lifecycle_extra:   # alpha.104 (doc 256 §2.9): the link the heal looks for is on disk before init_run, so a death right after the index still heals
        link = _write_lifecycle(cache_dir, channel=origin_channel or "chat", trace_id=trace_id, session_id=session_id, **lifecycle_extra)
    try:
        engine_core.init_run(cache_dir, agent_dir=agent_dir, user_message=message, session_id=session_id,
                             trace_id=trace_id, workspace_dir=str(engine_dir),
                             previous_route=previous_route_for_session(root, session_id))
    except engine_core.EngineError as exc:
        if exc.code == "PROGRAM_INVALID" and _unmake_run_dir(cache_dir, link):   # docs/05SoulRun 90 (problem 28)
            return {"turn_id": None, "cache_dir": None, "cache_name": None, "trace_id": None, "session_id": session_id,
                    "entry_mode": "engine_unavailable", "user_language": None, "requested_model": requested_model,
                    "init_error": exc.as_dict()}
        _write_lifecycle(cache_dir, channel=origin_channel or "chat", engine_run=False, trace_id=trace_id,
                         session_id=session_id, created_at=now_iso(), init_error=exc.as_dict(), **(lifecycle_extra or {}))
        return _ctx(cache_dir, None, "engine_unavailable", requested_model, {"init_error": exc.as_dict()})
    engine_core.set_host_fields(cache_dir, turn_id=cache_dir.name, origin_channel=origin_channel or None,
                                requested_model=requested_model, host_fences=fences, host_tools=tools, entry_mode="fresh", last_turn_at=now_iso())
    _write_lifecycle(cache_dir, channel=origin_channel or "chat", engine_run=True, trace_id=trace_id,
                     session_id=session_id, created_at=now_iso(), entry_mode="fresh", **_uid(user_id), **(lifecycle_extra or {}))
    return _ctx(cache_dir, engine_core_index(cache_dir), "fresh", requested_model)


GATE_HOLD_NOTES = {   # docs/05SoulRun 90 (problem 30): the reply to a machine message at an open gate
    "zh": "这一场运行正等你回答它的问题；这条定时/agent 消息没有被当作回答，也没有执行。",
    "en": "This run is waiting for your answer to its question; this scheduled / agent message was not taken as the answer and was not executed.",
}


def _gate_hold(cache_dir: Path, index: dict, message: str, question_id: str, *, origin_channel: str, requested_model, fences, tools,
               user_id) -> dict:
    """docs/05SoulRun 90 (problem 30): a message the host marks as not the human's (human_turn False) reaches a run waiting at a
    gate. It does not answer the gate: the gate, its record and the run stay as they are; the message is kept in the lifecycle
    (pending_message, as an interrupted run keeps one), the turn is recorded (entry_mode gate_hold) and the returned context says so."""
    engine_core.set_host_fields(cache_dir, last_turn_at=now_iso(), origin_channel=origin_channel or None, requested_model=requested_model,
                                host_fences=fences, host_tools=tools, entry_mode="gate_hold")
    _write_lifecycle(cache_dir, last_turn_at=now_iso(), entry_mode="gate_hold", pending_message=message, **_uid(user_id))
    return _ctx(cache_dir, engine_core_index(cache_dir), "gate_hold", requested_model,
                {"gate_hold": True, "hold_reason": "machine_message", "question_id": question_id,
                 "public_note": GATE_HOLD_NOTES[stop_flow._lang(index)]})


_UNDECIDED = object()   # round 7 (C2): _cut_off_stop_id could not tell (prepare_execution_context's machine-turn check)


def _cut_off_stop_id(cache_dir: Path, *, undecided=None):
    """docs/05SoulRun 90 round 5 (ledger decision 185): the question id of the engine stop _cut_off_stop recognises (the record
    dispatch_budget.unindexed_stop would install, read-only, under the run lock), or None - also where the check cannot be made.
    Round 7 (line C, C2): `undecided` - returned in place of None where the check cannot be made: the run lock not obtained
    while the lock file does not prove its holder alive (run_store.lock_holder_alive: a killed process's lock is left until
    FileLock reclaims it, after stale_after), the run's records not read - the index, or a record a recogniser reads - or a
    gate record the index does not know that is not recognised (_recognised: the same recognisers as
    dispatch_budget.unindexed_stop, in its order, where such a record or a recogniser's exception means 'cannot tell', not
    'not recognised'). A turn not the human's is then refused or held as at the run waiting at a stop
    (SoulRun's _waits_at_a_cut_off_stop, prepare_execution_context's RUNNING branch), never routed by the RUNNING rules. A
    lock its live holder keeps past the wait means the run is being worked on now: None, as before. Default: as before."""
    from lib import dispatch_budget  # noqa: PLC0415
    from lib.run_store import LockTimeout, lock_holder_alive  # noqa: PLC0415
    store = None
    for attempt in (1, 2):
        try:
            store = RunStore(cache_dir)
            with store.lock():
                index = store.read_index()
                found = dispatch_budget.unindexed_stop(store, index) if undecided is None else _recognised(store, index)
        except LockTimeout:
            lock = store.cache_dir / RunStore.LOCK
            if undecided is None or lock_holder_alive(lock):
                return None
            if attempt == 1 and not lock.exists():   # its holder let go as the wait ended: the run can be read now
                continue
            return undecided
        except (engine_core.EngineError, RunStoreError, OSError, ValueError, RecursionError):
            return undecided
        except Exception:  # noqa: BLE001 - a recogniser's own (_recognised); with no `undecided`, raised as before
            if undecided is None:
                raise
            return undecided
        if undecided is None:
            return found[1]['question_id'] if found else None
        return found['question_id'] if found else None
    return undecided


def _recognised(store, index) -> dict | None:
    """Round 7 (C2): the record of the engine stop cut off before its index write, read-only - dispatch_budget.unindexed_stop's
    recognisers in its order (identity, dispatch, program-integrity), without its reading of an exception
    as 'not recognised': here it propagates, and _cut_off_stop_id takes it as 'cannot tell'. So is a gate record the index
    does not know that neither recognises (record 90 round 4, B6: malformed or unreadable data - a record, the evidence
    ledger - is 'not recognised' there, left to the orphan checks): the shape a stop cut off before its index write leaves,
    not proved to be one or not (ValueError)."""
    from lib import dispatch_budget, dispatch_identity, program_guard  # noqa: PLC0415
    for recognise in (dispatch_identity.orphan_stop, dispatch_budget.orphan_stop, program_guard.orphan_stop):
        rec = recognise(store, index)
        if rec is not None:
            return rec
    known = {row.get('question_id') for row in index['gate']['history']}
    if any(p.stem.removeprefix('_gate.') not in known for p in store.cache_dir.glob('_gate.q*.json')):
        raise ValueError('a gate record the run index does not know is not recognised')
    return None


def _cut_off_stop(cache_dir: Path) -> bool:
    """docs/05SoulRun 90 round 4 (ledger decision 184, 重启后不再问): the run looks RUNNING only because an engine stop was cut off
    before its index write, and the next next-node installs that stop and shows it (engine_core.unindexed_stop, read-only). The run
    that never stopped waits at that stop, so it is not an interrupted run to ask about: open_restart_question skips it, and the
    human's next message re-enters it so that its first serve shows the stop. Where the check cannot be made (an unreadable or
    foreign run), False: the run is handled as before."""
    try:
        return engine_core.unindexed_stop(cache_dir)
    except (engine_core.EngineError, RunStoreError, OSError, ValueError, RecursionError):
        return False


def stop_flow_supply():
    """alpha.105: lib.supply_flow, imported lazily (as resume_prompt_for imports checkpoint_recovery) - it imports this module itself."""
    from lib import supply_flow  # noqa: PLC0415
    return supply_flow


def open_restart_question(cache_dir: str | Path, *, instance_started_at: str, reason: str = "host restart", resume_mode: bool | None = None) -> dict:
    """alpha.105 (doc 259 spec §1.7): the startup scan's door for a run left RUNNING by an earlier process, mode false only - mark it interrupted
    and open a restart question (lib.supply_flow.open_restart_question_record) instead of re-entering it; a pending supply wait is suspended in
    the same write. `instance_started_at` (an ISO Z string, now_iso() format) is the created-at guard: a cache created at or after it was served
    by this instance and is not interrupted. `resume_mode` is the switch as the caller read it; None -> resume_interrupted_enabled(); in mode
    true nothing is written (not even mark_interrupted: the host marks and re-enters, spec §2.7). Idempotent: an open stop -> ALREADY_OPEN.
    docs/05SoulRun 90 round 4 (ledger decision 184): a run that looks RUNNING only because an engine stop was cut off before its index
    write (_cut_off_stop) is SKIPPED, nothing written - the run that never stopped waits at that stop and is asked nothing."""
    mode = resume_interrupted_enabled() if resume_mode is None else resume_mode is True
    if mode:
        return {"status": "SKIPPED", "reason": "resume mode: auto re-entry"}
    path = Path(cache_dir)
    index = _plain_index(path)
    if index is None:
        return {"status": "SKIPPED", "reason": "index unreadable"}
    if index.get("run_state") != "RUNNING":
        return {"status": "SKIPPED", "reason": f"run_state {index.get('run_state')}"}
    life = _read_lifecycle(path)
    if life.get("channel") == "heartbeat" or life.get("engine_run") is False:
        return {"status": "SKIPPED", "reason": "not an engine run"}
    created = life.get("created_at") or index.get("started_at")
    if isinstance(created, str) and created >= instance_started_at:
        return {"status": "SKIPPED", "reason": "created after instance start"}
    before = stop_flow._snapshot(life)   # heal_all semantics for this one cache
    life = stop_flow._merge_stop_files(path, stop_flow._heal_handover(path, life))
    if stop_flow._snapshot(life) != before:
        stop_flow._write_life(path, life)
    stop = life.get(stop_state.STOP_KEY)
    if stop_flow._is_open(stop):
        return {"status": "ALREADY_OPEN", "stop_id": stop.get("stop_id"), "question_id": (stop.get("gate") or {}).get("question_id"),
                "requested_by": stop.get("requested_by")}
    if _cut_off_stop(path):   # docs/05SoulRun 90 round 4 (ledger decision 184): nothing written, no question
        return {"status": "SKIPPED", "reason": "engine stop cut off before its index write: the next next-node shows it"}
    mark_interrupted(path, reason)
    opened = stop_flow_supply().open_restart_question_record(path, index, since=index.get("updated_at"), reason=reason)
    return dict(opened, session_id=index.get("session_id"), user_id=life.get("user_id"), cache_name=path.name)


def prepare_execution_context(user_message: str, engine_aiap_dir: str | Path, session_id: str | None = None,
                              origin_channel: str = "", requested_model: str | None = None,
                              host_fences: list | tuple | None = None, user_id: str | None = None,
                              host_tools: dict | None = None, human_turn: bool = True, host_turn_id: str | None = None,
                              origin_type: str | None = None) -> dict | None:
    """host_fences (alpha.44): the `:::<kind>` fences this host captures from the visible stream (engine_core.HOST_FENCES); recorded in
    the index host group so the served STREAM rule matches the host. None (an older host) keeps the Report-only wording.
    user_id (alpha.60 H3): the host's user id for the session, kept in the lifecycle so a restart can re-enter the run's session.
    host_tools (alpha.62, doc 135 §4 B): what the host offers beyond the stream, e.g. {"agent": False} when it has no Agent tool - the
    engine then runs declared-agent nodes inline at once (HOST_NO_AGENT_TOOL) instead of spawning; None (an older host) changes nothing.
    human_turn / host_turn_id / origin_type (alpha.104, doc 255 final_plan §2.3, doc 256 E1): whether this message comes from the human
    (False for a scheduled or agent message, which a stopped run - and since docs/05SoulRun 90 a run waiting at a gate - only records),
    the host turn's invocation id (the replay guard of a stopped run) and the host context type recorded with a held machine message.
    Runs without a stop record behave exactly as before, except that a machine message never answers an open gate."""
    fences = [str(f) for f in (host_fences or ()) if str(f) in engine_core.HOST_FENCES] or None
    tools = {str(k): bool(v) for k, v in (host_tools or {}).items()} or None
    engine_dir = Path(engine_aiap_dir).resolve()
    agent_dir = engine_dir.parent
    root = cache_root(engine_dir)
    root.mkdir(parents=True, exist_ok=True)
    cleanup_cache(root)
    message = user_message or ""
    host = {"engine_dir": engine_dir, "agent_dir": agent_dir, "root": root, "session_id": session_id, "origin_channel": origin_channel,
            "requested_model": requested_model, "fences": fences, "tools": tools, "user_id": user_id, "origin_type": origin_type}

    recovery_dir = recovery_reentry_dir(message, root)
    if recovery_dir is not None:
        rindex = _read_index(recovery_dir)
        # docs/05SoulRun 90 (problem 27): the marker re-enters only a run of this conversation; one naming another
        # conversation's run is ordinary words here (that run is neither re-entered nor changed)
        if rindex is not None and rindex.get("session_id") == session_id:
            engine_core.program_guard.assert_run_version(rindex)
            if rindex["run_state"] in PROTECTED_STATES and stop_state.stop_status(recovery_dir)["open"]:   # alpha.104 (doc 255 final_plan §2.3 step 2, doc 256 E1)
                stopped = stop_flow.recovery_into_stopped_run(recovery_dir, rindex, host=host, host_turn_id=host_turn_id)
                if stopped is not None:
                    return stopped
            supply = stop_state.supply_status(recovery_dir) or {}
            if rindex["run_state"] == "RUNNING" and supply.get("state") in stop_state.SUPPLY_WAITING_STATES \
                    and host.get("origin_type") == "supply_probe" and (supply.get("probe") or {}).get("started_at") is None:   # alpha.105 (doc 259): the host probe's first re-entry
                life = _read_lifecycle(recovery_dir)
                _write_lifecycle(recovery_dir, recovery_reentries=int(life.get("recovery_reentries") or 0) + 1, **_uid(user_id))
                return stop_flow_supply().resume_authorized(recovery_dir, rindex, host=host)
            mode = "recovery" if rindex["run_state"] in PROTECTED_STATES else "terminal"
            # doc 06 §2 1b: the dead time is not the current node's work. docs/05SoulRun 90 round 3 (ledger decision 183): not for a
            # run whose engine stop was cut off before its index write - as in _reenter_interrupted
            if rindex["run_state"] == "RUNNING" and not engine_core.unindexed_stop(recovery_dir):
                since, reason = interruption_anchor(recovery_dir)
                engine_core.record_transport_wait(recovery_dir, since=since, reason=reason)
                # Host interruption alone cannot prove a native child or its tools exited.
                engine_core.abandon_dispatch(recovery_dir, reason="host recovery re-entry")
            engine_core.set_host_fields(recovery_dir, last_turn_at=now_iso(), origin_channel=origin_channel or None,
                                        requested_model=requested_model, host_fences=fences, host_tools=tools, entry_mode=mode)
            life = _read_lifecycle(recovery_dir)
            _write_lifecycle(recovery_dir, last_turn_at=now_iso(), entry_mode=mode,
                             recovery_reentries=int(life.get("recovery_reentries") or 0) + 1, **_uid(user_id))
            return _ctx(recovery_dir, engine_core_index(recovery_dir), mode, requested_model, {"recovery_reentry": True})

    latest = latest_cache_for_session(root, session_id)
    latest_index = _read_index(latest) if latest else None
    if latest_index and origin_channel != "heartbeat" and latest_index["run_state"] in PROTECTED_STATES:   # alpha.104 (doc 255 final_plan §2.3 step 3, doc 256 E1)
        stopped = stop_flow.stopped_turn(latest, latest_index, message, host=host, human_turn=human_turn, host_turn_id=host_turn_id)
        if stopped is not None:
            return stopped
    elif latest_index and origin_channel != "heartbeat" and latest_index["run_state"] in engine_core.TERMINAL_STATES \
            and isinstance(stop_state.read_lifecycle(latest).get(stop_state.STOP_KEY), dict):
        # the run ended while a stop record was on file (open, or JUDGING with the executor's continue): close the record, then a fresh run as today
        stop_flow.resolve_terminal_stop(latest)
    if latest_index and latest_index["run_state"] == "WAITING_USER" and origin_channel != "heartbeat":
        qid = latest_index["gate"]["question_id"]
        if not human_turn:   # docs/05SoulRun 90 (problem 30): only the human answers a gate - a machine message is kept, never the answer
            # round 6 ('vc 2' defect 2): held under the question the run waits at - where the program-integrity stop was cut off
            # over this gate (problem 91's window; recognised read-only, installed by the next engine call), the stop's own, as
            # the run that never stopped, waiting at that stop, holds it
            return _gate_hold(latest, latest_index, message, _cut_off_stop_id(latest) or qid, origin_channel=origin_channel,
                              requested_model=requested_model, fences=fences, tools=tools, user_id=user_id)
        answer = engine_core.answer_gate(latest, qid, message, by=f"host:{origin_channel or 'chat'}")
        status = answer.get("status")
        entry_mode = gate_reply.entry_mode(answer)
        engine_core.set_host_fields(latest, last_turn_at=now_iso(), origin_channel=origin_channel or None,
                                    requested_model=requested_model, host_fences=fences, host_tools=tools, entry_mode=entry_mode, gate_answer_status=status)
        _write_lifecycle(latest, last_turn_at=now_iso(), entry_mode=entry_mode, gate_answer=answer, **_uid(user_id))
        return _ctx(latest, engine_core_index(latest), entry_mode, requested_model, {"gate_answer": gate_reply.context(answer, qid)})
    if latest_index and latest_index["run_state"] == "RUNNING" and origin_channel != "heartbeat":
        if _same_turn_rebootstrap(latest, latest_index, message):
            life = _read_lifecycle(latest)
            engine_core.set_host_fields(latest, last_turn_at=now_iso(), origin_channel=origin_channel or None,
                                        requested_model=requested_model, host_fences=fences, host_tools=tools, entry_mode="fresh")
            _write_lifecycle(latest, last_turn_at=now_iso(), rebootstraps=int(life.get("rebootstraps") or 0) + 1)
            return _ctx(latest, engine_core_index(latest), "fresh", requested_model, {"rebootstrap": True})
        waiting = stop_flow_supply().wait_turn(latest, latest_index, message, host=host, human_turn=human_turn, host_turn_id=host_turn_id)   # alpha.105 (doc 259): an authorized / expired wait never re-enters on a message
        if waiting is not None:
            return waiting
        held = None if human_turn or resume_interrupted_enabled() else _cut_off_stop_id(latest, undecided=_UNDECIDED)
        if held:
            # docs/05SoulRun 90 round 5 (ledger decision 185): a machine message (a schedule, another agent) to the run whose engine
            # stop was cut off before its index write is held exactly as the run waiting at that stop holds it (problem 30's
            # gate_hold: kept, nothing answered, ended or re-entered); with the switch on it is routed as before. Round 7 (C2):
            # so is one to a run the check cannot read (the lock a killed process left, a record unreadable) - held with no
            # question named, never routed by the RUNNING rules below; the hold's own write waits for that lock as any write
            return _gate_hold(latest, latest_index, message, None if held is _UNDECIDED else held, origin_channel=origin_channel,
                              requested_model=requested_model, fences=fences, tools=tools, user_id=user_id)
        if human_turn and not resume_interrupted_enabled() and _cut_off_stop(latest):
            # docs/05SoulRun 90 round 4 (ledger decision 184): with the switch off the run whose engine stop was cut off before its index
            # write gets no restart question (open_restart_question); whatever the human says next re-enters it - nothing recorded,
            # nothing answered (_reenter_interrupted) - and the next next-node installs the stop and serves it first
            since, reason = interruption_anchor(latest)
            return _reenter_interrupted(latest, since=since, reason=reason, entry_mode="recovery", message=message, origin_channel=origin_channel,
                                        requested_model=requested_model, fences=fences, tools=tools, user_id=user_id)
        if is_cancel_message(message):   # H3 (alpha.60): the human abandons the interrupted run - in both switch positions
            engine_core.terminate_run(latest, kind="human_termination", by="host",
                                      reason="cancelled by the human after an interruption")
            engine_core.set_host_fields(latest, last_turn_at=now_iso(), origin_channel=origin_channel or None,
                                        requested_model=requested_model, host_fences=fences, host_tools=tools, entry_mode="terminal")
            _write_lifecycle(latest, last_turn_at=now_iso(), entry_mode="terminal", cancelled_at=now_iso(), cancel_text=message, **_uid(user_id))
            return _ctx(latest, engine_core_index(latest), "terminal", requested_model, {"interrupted_cancel": True, "human_note": message})
        if resume_interrupted_enabled() or is_continue_message(message):   # alpha.60 / .61: resume - automatically, or on the human's continue word
            since, reason = interruption_anchor(latest)
            return _reenter_interrupted(latest, since=since, reason=reason, entry_mode="recovery", message=message, origin_channel=origin_channel,
                                        requested_model=requested_model, fences=fences, tools=tools, user_id=user_id)
        # alpha.61 (doc 132): the switch is off and this is an ordinary message - remind and wait; the run and the message are both kept
        life = _read_lifecycle(latest)
        current = latest_index.get("current") or {}
        engine_core.set_host_fields(latest, last_turn_at=now_iso(), origin_channel=origin_channel or None,
                                    requested_model=requested_model, host_fences=fences, host_tools=tools, entry_mode="interrupted_confirm")
        _write_lifecycle(latest, last_turn_at=now_iso(), entry_mode="interrupted_confirm", pending_message=message,
                         resume_prompted=int(life.get("resume_prompted") or 0) + 1, **_uid(user_id))
        return _ctx(latest, engine_core_index(latest), "interrupted_confirm", requested_model,
                    {"interrupted_confirm": True, "human_note": message, "interrupted_node": current.get("name"), "interrupted_visit": current.get("visit"),
                     "original_request": _run_input_message(latest), "resume_prompted": int(life.get("resume_prompted") or 0) + 1})

    return _fresh_run(root, engine_dir, agent_dir, message, session_id, origin_channel, requested_model, fences, tools, user_id)


def engine_core_index(cache_dir: Path) -> dict | None:
    return _read_index(Path(cache_dir))


def finalize_execution_context(cache_dir: str | Path, response_persisted: bool = True) -> dict:
    """Host says the turn's response was persisted; recorded, never used to decide completion."""
    cache_dir = Path(cache_dir)
    index = _read_index(cache_dir)
    if index is not None:
        engine_core.program_guard.assert_run_version(index)
    data = _write_lifecycle(cache_dir, response_persisted=bool(response_persisted), reconciled_at=now_iso())
    if index is not None:
        engine_core.set_host_fields(cache_dir, response_persisted=bool(response_persisted), reconciled_at=data["reconciled_at"])
        data["run_state"] = index["run_state"]
        stop_flow.note_host_index_write(cache_dir)   # alpha.104 (final_plan S5): this host write is not a commit after the human's Stop
        data["supply_resumed"] = stop_flow_supply().note_turn_end(cache_dir)   # alpha.105: the authorized probe turn delivered a final response = the supply is back
    return data


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--engine-dir", default=str(Path(__file__).resolve().parents[1]))
    ap.add_argument("--user-message", default="")
    ap.add_argument("--session-id")
    ap.add_argument("--origin-channel", default="")
    ap.add_argument("--requested-model")
    ap.add_argument("--host-fences", default="", help="alpha.44: comma-separated fences the host captures (report,message,explain,answer)")
    args = ap.parse_args(argv)
    ctx = prepare_execution_context(args.user_message, args.engine_dir, args.session_id, args.origin_channel, args.requested_model,
                                    host_fences=[f for f in args.host_fences.split(",") if f])
    print(json.dumps(ctx, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())

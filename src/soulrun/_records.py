"""SoulRun's own small records, kept beside the run data and never inside a run's folder (the engine owns those).

    <soulrun_cache_dir>/.soulrun/runs/<run>.json       which folders a run was created with, and how each was given
    <soulrun_cache_dir>/.soulrun/entries/<run>.txt     the full text of a turn, when a command line printed it (see _render)
    <soulrun_cache_dir>/.soulrun/delivered/<run>.json  which parts of the slim engine program this turn has been given
                                                       (see _slim: the program is handed out by engine node), with the
                                                       turn's facts (TURN_FACTS)
    <soulrun_cache_dir>/.soulrun/turns/<run>.json      the facts of the run's latest turn (TURN_FACTS): turn_id (the
                                                       engine's: the run's number, the same on every turn of the run),
                                                       host_turn_id (the host's), turn (1, 2, ... within the run), and
                                                       the run's trace_id. A run number the engine gives again is a new
                                                       run, counted from 1; the engine's rebootstrap of a turn is the
                                                       same turn only with the same host_turn_id (count_turn)

Rule from the design: every run records whether each location came from an argument, an environment
variable or the default - so that "where did this run look for its programs?" can be answered later.
"""
from __future__ import annotations

import contextlib
import json
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from . import _engine, _select

SOULRUN_DIR = _select.NOTES_DIRNAME             # ".soulrun"
RUNS = "runs"
ENTRIES = "entries"
DELIVERED = "delivered"
UNDELIVERED = "undelivered"                     # replies SoulRun's command line could not print (_cmd._not_printed)
TURNS = "turns"                                 # the latest turn of each run (count_turn)
REPLACE_RETRIES = (0.05, 0.2, 0.5)  # Windows refuses a replace while another program holds the file (errors 5, 32, 33)


def write_whole(target: Path, text: str) -> Path:
    """Write ``text`` to a temporary file beside ``target`` and then put it in place: a reader never sees half a file,
    and a process that dies half way never leaves one. OSError when it cannot be written; the temporary file goes."""
    temporary = target.with_name(f".{target.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary.write_text(text, encoding="utf-8", newline="\n")
        for pause in (*REPLACE_RETRIES, None):
            try:
                os.replace(temporary, target)
                return target
            except PermissionError:
                if pause is None:
                    raise
                time.sleep(pause)
    except OSError:
        with contextlib.suppress(OSError):
            temporary.unlink()
        raise
    return target


def run_record_path(soulrun_cache_dir: Path, cache_name: str) -> Path:
    return Path(soulrun_cache_dir) / SOULRUN_DIR / RUNS / f"{cache_name}.json"


def write_run_record(places, data: dict, *, candidates: str, designated: list[str], kept_from: str | None = None) -> Path | None:
    """Written once, when a run is created. Best effort: a run is never lost because its note could not be written.
    ``kept_from``: the run whose named programs this one kept (no program was named in the call that created it)."""
    from . import __version__
    try:
        target = run_record_path(places.soulrun_cache_dir, str(data["cache_name"]))
        record = {
            "soulrun_version": __version__,
            "engine_version": _engine.version(),
            "engine_digest": _engine.manifest().get("digest"),
            "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "cache_name": str(data["cache_name"]),
            "session_id": data.get("session_id"),
            "agent_dir": str(places.agent_dir), "aiap_dir": str(places.aiap_dir), "aisp_dir": str(places.aisp_dir),
            "soulrun_cache_dir": str(places.soulrun_cache_dir), "given_by": dict(places.sources),
            "candidates": candidates, "designated": designated,
        }
        if kept_from is not None:
            record["kept_from"] = kept_from
        write_whole(target, json.dumps(record, ensure_ascii=False, indent=1) + "\n")      # never half a note
        prune(places.soulrun_cache_dir)
        return target
    except OSError:
        return None


def read_run_record(soulrun_cache_dir: Path, cache_name: str) -> dict | None:
    """A run's note, or None when there is none (a run another host created) or it cannot be read."""
    try:
        record = json.loads(run_record_path(soulrun_cache_dir, cache_name).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return record if isinstance(record, dict) else None


def add_to_run_record(soulrun_cache_dir: Path, cache_name: str, **facts) -> bool:
    """Add facts SoulRun learns after a run was created (the program form it was handed out in, a problem with the slim
    form). Only a run with a note gets them; best effort, like the note itself. True when they were written."""
    record = read_run_record(soulrun_cache_dir, cache_name)
    if record is None or all(record.get(key) == value for key, value in facts.items()):
        return False
    record.update(facts)
    try:
        write_whole(run_record_path(soulrun_cache_dir, cache_name), json.dumps(record, ensure_ascii=False, indent=1) + "\n")
    except OSError:
        return False
    return True


def count_turn(soulrun_cache_dir: Path, cache_name: str, *, turn_id=None, host_turn_id=None, trace_id=None,
               entry_mode=None, rebootstrap: bool = False) -> dict:
    """A turn of this run handed back (docs/05SoulRun 87, #25): its facts (TURN_FACTS), ``turn`` its number within the
    run, kept in .soulrun/turns/<run>.json with the run's trace_id - not in the run's note, which is written once.

    The engine numbers a new run one past the highest it keeps, so a number comes back once the latest runs are gone
    (removed under CACHE_NUM, or cleared by hand): a turns file is this run's only while it holds the run's trace_id
    (the engine gives every new run its own). Another trace on file - or none, for a run the engine says it has just
    created (``entry_mode`` "fresh" without ``rebootstrap``) - and the count starts again at 1. A rebootstrap (the engine
    hands the same run back for the same message within two minutes) is the same turn, keeping its number, only when
    ``host_turn_id`` is the one on file: the same words sent again in a new host turn are the next turn, and so is a
    rebootstrap with no host_turn_id to tell. Best effort: ``turn`` is None when the record cannot be written."""
    path = Path(soulrun_cache_dir) / SOULRUN_DIR / TURNS / f"{cache_name}.json"
    try:
        kept = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        kept = {}
    kept = kept if isinstance(kept, dict) else {}
    created = entry_mode == "fresh" and not rebootstrap
    this_run = kept.get("trace_id") == trace_id if kept.get("trace_id") is not None else not created
    before = kept["turn"] if this_run and isinstance(kept.get("turn"), int) else 0
    same_turn = rebootstrap and before > 0 and host_turn_id is not None and host_turn_id == kept.get("host_turn_id")
    facts = {"turn_id": turn_id, "host_turn_id": host_turn_id, "turn": before if same_turn else before + 1}
    try:
        write_whole(path, json.dumps({**facts, "trace_id": trace_id}, ensure_ascii=False) + "\n")
    except OSError:
        facts["turn"] = None
    return facts


def delivered_path(cache_dir) -> Path:
    """The record of what this turn of a run has been given of the slim program: beside the runs, never in the run's own
    folder (cache_dir is <soulrun_cache_dir>/.execution_cache/<run>)."""
    run = Path(str(cache_dir))
    return run.parent.parent / SOULRUN_DIR / DELIVERED / f"{run.name}.json"


def read_delivered(cache_dir) -> set[str] | None:
    """The pieces this turn has been given ("system:<section>", "functions:<name>"), or None when the turn was not
    handed the slim program (no record: the entry-path form, another host, an older SoulRun)."""
    try:
        record = json.loads(delivered_path(cache_dir).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    pieces = record.get("pieces") if isinstance(record, dict) else None
    return set(pieces) if isinstance(pieces, list) else None


TURN_FACTS = ("turn_id", "host_turn_id", "turn")      # which turn a record is about (see the module's docstring)


def write_delivered(cache_dir, pieces, *, turn: dict | None = None) -> bool:
    """Replace the record. A new turn starts it again with ``turn``, the facts of TURN_FACTS; a reply or a request adds
    to it, and the turn's facts stay as the turn began (docs/05SoulRun 87, #25: they were lost). Best effort: True when
    written."""
    if turn is None:
        try:
            kept = json.loads(delivered_path(cache_dir).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            kept = {}
        turn = kept if isinstance(kept, dict) else {}
    try:
        write_whole(delivered_path(cache_dir), json.dumps({**{key: turn.get(key) for key in TURN_FACTS},
                                                            "pieces": sorted(pieces)}, ensure_ascii=False) + "\n")
    except OSError:
        return False
    return True


def clear_delivered(cache_dir) -> None:
    """A turn handed out in another form keeps nothing from an earlier slim turn of the run."""
    with contextlib.suppress(OSError):
        delivered_path(cache_dir).unlink()


def session_runs(soulrun_cache_dir: Path, session_id: str) -> list[tuple[str, dict]]:
    """The notes of one conversation's runs, oldest first: (run name, note)."""
    folder = Path(soulrun_cache_dir) / SOULRUN_DIR / RUNS
    found = []
    for note in sorted(folder.glob("*.json")) if folder.is_dir() else []:
        record = read_run_record(soulrun_cache_dir, note.stem)
        if record is not None and record.get("session_id") == session_id:
            found.append((note.stem, record))
    return sorted(found, key=lambda item: (str(item[1].get("created_at") or ""), int(item[0]) if item[0].isdigit() else 0))


def prune(soulrun_cache_dir: Path) -> int:
    """Drop SoulRun's notes for runs the engine has already removed. Returns how many files went."""
    base = Path(soulrun_cache_dir) / SOULRUN_DIR
    cache_root = Path(soulrun_cache_dir) / ".execution_cache"
    removed = 0
    for folder in (base / RUNS, base / ENTRIES, base / DELIVERED, base / UNDELIVERED, base / TURNS):
        if not folder.is_dir():
            continue
        for note in folder.iterdir():
            if note.is_file() and note.stem.isdigit() and not (cache_root / note.stem).is_dir():
                try:
                    note.unlink()
                    removed += 1
                except OSError:
                    pass
    return removed

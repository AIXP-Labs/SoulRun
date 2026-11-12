"""docs/05SoulRun 90 round 7, line C, through SoulRun itself (ledger decisions 183, 185 and 187; 'line-C-holds_1', '_2' and
'_3', 'line-P-docs-55_1'):

- C2: a real crash inside the engine's run lock leaves the lock file behind until the engine reclaims it as stale. With
  the restart switch off, a turn that is not the human's to a run whose state the check cannot read while that lock is
  there is refused (HUMAN_REPLY_REQUIRED, nothing written), as at a run waiting at a stop - never routed by the engine's
  RUNNING rules (a machine "取消" ended the run, "继续" moved it). A lock a live process keeps leaves the turn to the engine
  as before.
- C3: the interface check lists every engine function _api calls through prepare_cache - _cut_off_stop_id included, with
  the parameter SoulRun passes - so an engine without it is reported by soulrun --doctor and tools/upgrade_engine.py
  before a turn meets it.
- C5: the named-program question calls a run cut off at its engine stop what it calls the run waiting at that stop.

The engine's stop is cut off as test_round6_gate_hold cuts it off (the program-integrity stop: its record lands, the process
dies before the index write). No model is called."""
from __future__ import annotations

import ast
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from helpers import HOST, QUESTION
from test_round6_gate_hold import _at_start, _cut_off, _files

K = 1 / 15                                   # the engine's FileLock timings scaled: its 30 s wait 2 s, its 120 s stale limit 8 s
_HOLD = ('import sys, time\nsys.path.insert(0, sys.argv[1])\nfrom lib.run_store import RunStore\n'
         'lock = RunStore(sys.argv[2]).lock()\nlock.acquire()\nprint("held", flush=True)\ntime.sleep(float(sys.argv[3]))\n'
         'lock.release()\n')


@pytest.fixture
def scaled_locks(monkeypatch):
    from soulrun import host
    store_mod = host.engine("lib.run_store")
    real = store_mod.FileLock.__init__

    def init(self, path, timeout=30.0, stale_after=120.0, poll=0.05):
        real(self, path, timeout * K, stale_after * K, poll)
    monkeypatch.setattr(store_mod.FileLock, "__init__", init)


def _holder(run, seconds: float) -> subprocess.Popen:
    """Another process that takes the run's lock as every engine command does (RunStore.lock()) and keeps it."""
    from soulrun import _engine
    script = _HOLD if os.name == 'nt' else 'import time; time.sleep(1.1)\n' + _HOLD
    proc = subprocess.Popen([sys.executable, "-B", "-c", script, str(_engine.TOOLS_DIR), str(run), str(seconds)],
                            stdout=subprocess.PIPE, text=True)
    assert proc.stdout.readline().strip() == "held"
    if os.name != 'nt':
        assert int((Path(run) / '_index.lock').read_text(encoding='utf-8').split()[0]) == proc.pid
    return proc


def _killed_holder(run, age: float) -> Path:
    """A real crash inside the run lock: the process that took it is killed; its lock file stays, `age` seconds old."""
    proc = _holder(run, 600)
    proc.kill()
    proc.wait()
    lock = Path(run) / "_index.lock"
    assert lock.is_file()
    then = time.time() - age
    os.utime(lock, (then, then))
    return lock


@pytest.mark.parametrize("cut", [True, False], ids=["cut-off-stop", "genuinely-interrupted"])
def test_c2_a_machine_turn_at_a_run_locked_by_a_killed_process_is_refused(soulrun, agent, tmp_path, monkeypatch,
                                                                        scaled_locks, cut):
    """'line-C-holds_2' defect 1, through soulrun.run: while the lock a killed process left is there, the engine's check
    could not read the run and SoulRun handed the turn on - a machine "取消" ended the run, "继续" moved it and showed the
    stop from a turn not the human's. Now it is refused as at a waiting run, nothing in the agent folder changes, the lock
    stays. Whether the run was cut off at its stop or genuinely interrupted cannot be told then; once the lock is stale the
    run is read: the cut-off run is refused as before, the genuinely interrupted one routed as before (the reminder)."""
    if cut:
        ctx, twin_agent, twin, qid = _cut_off(soulrun, agent, tmp_path, monkeypatch)
    else:
        ctx = _at_start(soulrun, agent, "h1")             # RUNNING at Start, its turn died: nothing cut off
    lock = _killed_holder(ctx.cache_dir, 0.5)
    before = _files(agent)
    for message in ("取消", "继续", "scheduled report: all good"):
        then = time.time() - 0.5                  # still the dead process's lock, well below the engine's stale limit
        os.utime(lock, (then, then))
        with pytest.raises(soulrun.UsageError) as raised:
            soulrun(user_message=message, session_id="h1", agent_dir=agent, human_turn=False, origin_type="scheduled", **HOST)
        assert raised.value.code == "HUMAN_REPLY_REQUIRED", message
    assert _files(agent) == before
    time.sleep(max(0.0, 120 * K + 0.6 - (time.time() - lock.stat().st_mtime)))
    if cut:
        with pytest.raises(soulrun.UsageError) as raised:
            soulrun(user_message="取消", session_id="h1", agent_dir=agent, human_turn=False, **HOST)
        assert raised.value.code == "HUMAN_REPLY_REQUIRED"
    else:
        reminded = soulrun(user_message="scheduled report: all good", session_id="h1", agent_dir=agent, human_turn=False,
                           **HOST)
        assert reminded.entry_mode == "interrupted_confirm" and reminded.kind == "text_only"


def test_c2_a_live_holder_leaves_the_turn_to_the_engine_as_before(soulrun, agent, monkeypatch, scaled_locks):
    """A lock its live holder keeps past the check's wait: the run is being worked on now, so the turn is not refused;
    the engine routes it as before (the reminder at a run genuinely interrupted) once the holder lets go."""
    ctx = _at_start(soulrun, agent, "h1")
    live = _holder(ctx.cache_dir, 30 * K * 1.5)
    try:
        reminded = soulrun(user_message="scheduled report: all good", session_id="h1", agent_dir=agent, human_turn=False,
                           **HOST)
    finally:
        live.wait()
    assert reminded.entry_mode == "interrupted_confirm" and reminded.kind == "text_only"


def test_c3_every_engine_function_api_calls_through_prepare_cache_is_in_the_interface_check():
    """'line-C-holds_1' defect 3 / 'line-C-holds_3' defect 2 / 'line-P-docs-55_1' defect 3: _api called
    prepare_cache._cut_off_stop_id, which the interface list lacked - an engine without it passed soulrun --doctor and
    tools/upgrade_engine.py, and the first machine turn at a running run failed (ENGINE_INTERFACE_CHANGED). Every
    prepare_cache attribute _api reaches is listed, each keyword it passes with it."""
    from soulrun import _api, _engine
    tree = ast.parse(Path(_api.__file__).read_text(encoding="utf-8"))

    def is_prepare(value) -> bool:
        return (isinstance(value, ast.Name) and value.id == "prepare") or (
            isinstance(value, ast.Call) and getattr(value.func, "attr", None) == "load" and value.args
            and getattr(value.args[0], "value", None) == "prepare_cache")
    used = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute) and is_prepare(node.value)}
    listed = _engine.INTERFACE["prepare_cache"]
    assert "_cut_off_stop_id" in used and used <= set(listed), sorted(used - set(listed))
    keywords = {kw.arg for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "_cut_off_stop_id" for kw in node.keywords}
    assert keywords == {"undecided"} and set(listed["_cut_off_stop_id"]) == keywords
    assert _engine.interface_problems() == []


def test_c3_an_engine_without_it_or_its_parameter_is_reported(monkeypatch):
    from soulrun import _engine, host
    prepare = host.engine("prepare_cache")
    monkeypatch.setattr(prepare, "_cut_off_stop_id", lambda cache_dir: None)
    assert "prepare_cache._cut_off_stop_id: takes no parameter undecided" in _engine.interface_problems()
    monkeypatch.delattr(prepare, "_cut_off_stop_id")
    assert "prepare_cache._cut_off_stop_id: missing" in _engine.interface_problems()


@pytest.mark.parametrize("words, zh", [(QUESTION, True), ("Please draw a card for me", False)])
def test_c5_the_named_program_question_calls_a_run_cut_off_at_its_stop_waiting(soulrun, agent, tmp_path, monkeypatch, words,
                                                                              zh):
    """'line-C-holds_2' defect 3: a turn naming another program, at a run cut off at its engine stop, was told that run is
    "still in progress / 还在进行"; the run that never crashed, waiting at that stop, "waiting for your answer / 在等你回答".
    Now both runs get the same question, word for word; nothing is written."""
    ctx, twin_agent, twin, qid = _cut_off(soulrun, agent, tmp_path, monkeypatch)
    before = (_files(agent), _files(twin_agent))
    asked = [soulrun(user_message=words, session_id="h1", aiap="other_aiap", agent_dir=folder, **HOST)
             for folder in (agent, twin_agent)]
    assert all(a.doubt and a.doubt["code"] == "DESIGNATED_RUN_UNFINISHED" for a in asked)
    assert asked[0].text == asked[1].text and ("在等你回答" if zh else "waiting for your answer") in asked[0].text
    assert ("还在进行" if zh else "still in progress") not in asked[0].text
    assert (_files(agent), _files(twin_agent)) == before

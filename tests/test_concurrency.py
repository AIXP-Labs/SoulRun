"""Many conversations at once, as in a host like SoulBot: one process, several threads calling soulrun(...) together.
Each conversation gets its own run, its own candidates and its own notes; the engine's functions that SoulRun swaps
in memory for a designated program are back to the engine's own afterwards."""
from __future__ import annotations

import json
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from helpers import HOST, QUESTION, candidates, index

THREADS = 8


def _call(soulrun, agent, n: int, message: str = QUESTION):
    designated = n % 2 == 1
    session = f"{'d' if designated else 's'}{n}"
    kwargs = {"aiap": "demo_aiap"} if designated else {}
    return session, designated, soulrun(user_message=message, session_id=session, agent_dir=agent, **kwargs, **HOST)


def test_conversations_at_the_same_time_do_not_mix(soulrun, agent):
    from soulrun import host
    core, loader = host.engine("lib.engine_core"), host.engine("lib.program_loader")
    original = (core.init_run, loader.registry_snapshot)

    with ThreadPoolExecutor(max_workers=THREADS) as pool:
        first = list(pool.map(lambda n: _call(soulrun, agent, n), range(THREADS)))

    assert len({ctx.cache_dir for _, _, ctx in first}) == THREADS                 # one run each
    for session, designated, ctx in first:
        assert ctx.kind == "program" and ctx.entry_mode == "fresh" and ctx.session_id == session
        assert index(ctx.cache_dir)["session_id"] == session
        expected = ["demo_aiap"] if designated else ["demo_aiap", "demo_aisp", "other_aiap"]
        assert candidates(ctx) == expected, (session, candidates(ctx))
        note = json.loads((agent / ".soulrun_cache" / ".soulrun" / "runs" / f"{Path(ctx.cache_dir).name}.json").read_text(encoding="utf-8"))
        assert note["session_id"] == session and note["candidates"] == ("designated" if designated else "agent folder")
    assert (core.init_run, loader.registry_snapshot) == original                  # nothing left swapped

    with ThreadPoolExecutor(max_workers=THREADS) as pool:                         # the same conversations go on
        again = list(pool.map(lambda n: _call(soulrun, agent, n, "继续"), range(THREADS)))
    for (session, _, before), (_, _, after) in zip(first, again, strict=True):
        assert after.cache_dir == before.cache_dir and after.session_id == session and after.entry_mode != "fresh"
    assert (core.init_run, loader.registry_snapshot) == original


PROCESSES, ROUNDS = 12, 3


def test_processes_at_the_same_time_each_get_their_own_run(soulrun, agent, tmp_path, subprocess_env):
    """Each `soulrun` on a command line is its own process. Before the file lock, 12 processes started together
    lost 1 to 3 messages a round: two picked the same run number, or a read met an index being replaced.
    With the lock taken out, this test failed 5 times in 6 tries."""
    seen: set = set()
    for round_no in range(ROUNDS):
        start = threading.Barrier(PROCESSES)
        for n in range(PROCESSES):                     # each caller writes its own words (they go into its run)
            (tmp_path / f"msg-{round_no}-{n}.txt").write_text(QUESTION, encoding="utf-8")

        def one(n, round_no=round_no, start=start):
            start.wait()
            message = tmp_path / f"msg-{round_no}-{n}.txt"
            return subprocess.run([sys.executable, "-B", "-X", "utf8", "-m", "soulrun", "--user-message-file", str(message),
                                   "--session-id", f"r{round_no}p{n}", "--agent-dir", str(agent), "--json",
                                   "--host-tool", "agent=false"],
                                  capture_output=True, text=True, encoding="utf-8", env=subprocess_env, timeout=300)

        with ThreadPoolExecutor(max_workers=PROCESSES) as pool:
            done = list(pool.map(one, range(PROCESSES)))
        assert [d.returncode for d in done] == [0] * PROCESSES, [d.stderr[-400:] for d in done if d.returncode]
        contexts = [json.loads(d.stdout) for d in done]
        for n, ctx in enumerate(contexts):
            assert ctx["entry_mode"] == "fresh" and index(ctx["cache_dir"])["session_id"] == f"r{round_no}p{n}"
            assert not (tmp_path / f"msg-{round_no}-{n}.txt").exists()          # each message went into its own run
            assert (Path(ctx["cache_dir"]) / "_soulrun" / "message.1.txt").read_text(encoding="utf-8") == QUESTION
        seen |= {c["cache_dir"] for c in contexts}
    assert len(seen) == PROCESSES * ROUNDS                                  # nobody shared a run


def test_an_index_refused_for_a_moment_is_read_again_and_a_lasting_refusal_is_reported(soulrun, agent, monkeypatch):
    """Windows refuses to read a run's index while another process replaces it; the model's commands and after_turn
    write outside the prepare lock. The preparation is tried again; a refusal that lasts is the folder's own."""
    from soulrun import host
    prepare = host.engine("prepare_cache")
    real, calls = prepare.prepare_execution_context, []

    def refused_twice(*args, **kwargs):
        calls.append(1)
        if len(calls) <= 2:
            raise PermissionError(13, "Permission denied", "_index.json")
        return real(*args, **kwargs)
    monkeypatch.setattr(prepare, "prepare_execution_context", refused_twice)
    ctx = soulrun(user_message=QUESTION, session_id="busy-index", **HOST)
    assert ctx.kind == "program" and len(calls) == 3

    def always_refused(*args, **kwargs):
        calls.append(1)
        raise PermissionError(13, "Permission denied", "_index.json")
    calls.clear()
    monkeypatch.setattr(prepare, "prepare_execution_context", always_refused)
    with pytest.raises(soulrun.SoulRunError) as error:
        soulrun(user_message=QUESTION, session_id="busy-index-2", **HOST)
    assert error.value.code == "SOULRUN_CACHE_DIR_INVALID" and len(calls) == 4


def test_a_file_system_without_locks_is_reported_at_once_not_after_a_wait(soulrun, tmp_path, monkeypatch):
    """Only "another process holds it" is worth waiting for; a folder whose file system cannot lock (an NFS mount
    without locks) is reported at once, with the error the system gave, not as a busy lock two minutes later."""
    import errno
    from soulrun import _filelock

    def no_locks(handle):
        raise OSError(errno.ENOLCK, "No locks available")
    monkeypatch.setattr(_filelock, "_try_lock", no_locks)
    began = time.monotonic()
    with pytest.raises(soulrun.SoulRunError) as error:
        with _filelock.held(tmp_path / ".soulrun", wait=60):
            pass
    assert error.value.code == "PREPARE_LOCK_UNSUPPORTED" and "No locks available" in error.value.message
    assert time.monotonic() - began < 5


def test_the_file_lock_waits_for_another_process_and_is_freed_when_it_dies(soulrun, tmp_path, subprocess_env):
    from soulrun import _filelock
    folder = tmp_path / "data" / ".soulrun"
    hold = ("import sys, time, os; from pathlib import Path; from soulrun import _filelock\n"
            "with _filelock.held(Path(sys.argv[1])):\n"
            "    print('held', flush=True); time.sleep(float(sys.argv[2]))\n"
            "    os._exit(0) if sys.argv[3] == 'die' else None\n")
    holder = subprocess.Popen([sys.executable, "-B", "-c", hold, str(folder), "1.5", "keep"], stdout=subprocess.PIPE,
                              text=True, env=subprocess_env)
    assert holder.stdout.readline().strip() == "held"
    with pytest.raises(soulrun.SoulRunError) as busy:                      # a short wait gives up with a clear error
        with _filelock.held(folder, wait=0.2):
            pass
    assert busy.value.code == "PREPARE_BUSY"
    began = time.monotonic()
    with _filelock.held(folder, wait=60):                                  # a longer wait gets it when the holder is done
        waited = time.monotonic() - began
    assert holder.wait(timeout=60) == 0 and 0.3 < waited < 30

    dying = subprocess.Popen([sys.executable, "-B", "-c", hold, str(folder), "0.2", "die"], stdout=subprocess.PIPE,
                             text=True, env=subprocess_env)
    assert dying.stdout.readline().strip() == "held"
    assert dying.wait(timeout=60) == 0                                     # ended without letting go of the lock
    with _filelock.held(folder, wait=5):                                   # the system let go of it
        pass
    assert sorted(p.name for p in folder.iterdir()) == ["prepare.lock"]


def test_a_failed_call_leaves_nothing_swapped(soulrun, agent, monkeypatch):
    """SoulRun hands the engine its candidates by swapping two engine functions for the length of the preparation;
    when the preparation fails part way, both are put back."""
    from soulrun import host
    core, loader, prepare = host.engine("lib.engine_core"), host.engine("lib.program_loader"), host.engine("prepare_cache")
    original = (core.init_run, loader.registry_snapshot)

    def broken(*args, **kwargs):
        assert (core.init_run, loader.registry_snapshot) != original          # the swap is in place while preparing
        raise RuntimeError("the engine broke while preparing")
    monkeypatch.setattr(prepare, "prepare_execution_context", broken)
    with pytest.raises(RuntimeError, match="the engine broke while preparing"):
        soulrun(user_message=QUESTION, session_id="x", aiap="demo_aiap", **HOST)     # a named program: the swap is made
    assert (core.init_run, loader.registry_snapshot) == original

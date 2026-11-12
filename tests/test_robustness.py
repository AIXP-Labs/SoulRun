"""Errors and robustness: what a wrong call, a broken setup or a busy folder gets back. No model is called."""
from __future__ import annotations

import copy
import json
import pickle
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from helpers import HOST, QUESTION, candidates, commit, gate_payload, take_node


def _cli(agent: Path, env: dict, *args, data: bytes | None = None):
    return subprocess.run([sys.executable, "-B", "-X", "utf8", "-m", "soulrun", *args], cwd=str(agent), env=env,
                          input=data, capture_output=True, timeout=120)


def _json_error(done) -> dict:
    return json.loads(done.stderr.decode("utf-8"))["error"]


def _reply(done) -> dict:
    """The engine's reply to an engine command: printed first and whole (in a slim turn a part may follow it)."""
    return json.JSONDecoder().raw_decode(done.stdout.decode("utf-8"))[0]


# ---- F13: a question asked before any run exists leaves nothing behind -------------------------------------

def test_a_doubt_creates_nothing_and_carries_its_places(soulrun, agent, tmp_path):
    deep = tmp_path / "deep" / "runs"
    for call in (dict(aiap="no_such_aiap"), dict(aiap="demo_aiap", aisp="demo_aisp"),
                 dict(user_message=QUESTION, cache_dir=str(agent / "x")),
                 dict(aiap="no_such_aiap", soulrun_cache_dir=str(deep))):
        ctx = soulrun(session_id="d13", **call, **HOST)
        assert ctx.doubt, call
        assert ctx.session_id == "d13" and Path(ctx.places["agent_dir"]).resolve() == agent.resolve(), call
    assert not (agent / ".soulrun_cache").exists() and not (tmp_path / "deep").exists()


# ---- F14: every option of a doubt, carried out as written ----------------------------------------------------

def _apply(option: dict, call: dict) -> dict:
    """What a host does with a "call" option: the arguments given replace, the ones set to None are left out."""
    assert option["action"] == "call"
    again = dict(call)
    for name, value in option["arguments"].items():
        if value is None:
            again.pop(name, None)
        else:
            again[name] = value
    return again


def test_each_call_option_does_what_its_label_says(soulrun, agent):
    call = dict(user_message=QUESTION, session_id="o1", aiap="demo_aiapp")
    missing = soulrun(**call, **HOST)
    fixed = soulrun(**_apply(missing.doubt["options"][0], call), **HOST)                   # use "demo_aiap" instead
    assert fixed.kind == "program" and candidates(fixed) == ["demo_aiap"]

    call = dict(session_id="o2", aiap="demo_aiap", aisp="demo_aisp")
    which = soulrun(**call, **HOST)
    aiap_only = soulrun(**_apply(which.doubt["options"][0], call), **HOST)                # run the AIAP program
    assert aiap_only.kind == "program" and candidates(aiap_only) == ["demo_aiap"]

    other = soulrun(user_message=QUESTION, session_id="o3-other", **HOST)
    call = dict(user_message=QUESTION, session_id="o3", cache_dir=other.cache_dir)
    mismatch = soulrun(**call, **HOST)
    unnamed = soulrun(**_apply(mismatch.doubt["options"][0], call), **HOST)                # send it without naming a run
    assert unnamed.kind == "program" and unnamed.cache_dir != other.cache_dir

    first = soulrun(user_message=QUESTION, session_id="o4", **HOST)
    call = dict(user_message="继续", session_id="o4", aiap="other_aiap")
    unfinished = soulrun(**call, **HOST)
    to_that_run = soulrun(**_apply(unfinished.doubt["options"][0], call), **HOST)         # give the words to that run
    assert to_that_run.cache_dir == first.cache_dir


# ---- F15: a switch that is set must be a switch value ---------------------------------------------------------

@pytest.mark.parametrize("value", ["ture", "2", "enable", "y"])
def test_a_misspelt_switch_in_the_environment_is_an_error(soulrun, agent, monkeypatch, value):
    monkeypatch.setenv("SOULRUN_SLIM_PROGRAM", value)
    with pytest.raises(soulrun.UsageError) as error:
        soulrun(user_message=QUESTION, session_id="s15", **HOST)
    assert error.value.code == "SWITCH_INVALID" and error.value.field == "SOULRUN_SLIM_PROGRAM"
    assert not (agent / ".soulrun_cache").exists()


@pytest.mark.parametrize("value", ["0", "off", "False", " no "])
def test_a_switch_turned_off_in_the_environment_is_off(soulrun, agent, monkeypatch, value):
    monkeypatch.setenv("SOULRUN_SLIM_PROGRAM", value)
    assert soulrun(user_message=QUESTION, session_id="s15-off", **HOST).program_form == "entry_path"


@pytest.mark.parametrize("value", ["", "  "])
def test_a_switch_set_to_nothing_is_not_given(soulrun, agent, monkeypatch, value):
    """An empty variable says nothing: the default holds (the slim form)."""
    monkeypatch.setenv("SOULRUN_SLIM_PROGRAM", value)
    assert soulrun(user_message=QUESTION, session_id="s15-empty", **HOST).program_form == "slim"


@pytest.mark.parametrize("value", ["false", "no", 1, 0])
def test_a_switch_argument_must_be_true_false_or_none(soulrun, agent, value):
    with pytest.raises(soulrun.UsageError) as error:
        soulrun(user_message=QUESTION, session_id="s15-arg", slim_program=value, **HOST)
    assert error.value.code == "SWITCH_INVALID" and error.value.field == "slim_program"


def test_the_doctor_reports_the_program_form(agent, monkeypatch):
    from soulrun import _doctor
    names = lambda: {c.name: c for c in _doctor.run(agent_dir=agent)}              # noqa: E731
    assert names()["program form"].status == "OK"
    monkeypatch.setenv("SOULRUN_SLIM_PROGRAM", "1")
    monkeypatch.setenv("SOULRUN_INLINE_PROGRAM", "1")
    assert names()["program form"].status == "FAIL" and "PROGRAM_FORMS_CONFLICT" in names()["program form"].detail
    monkeypatch.setenv("SOULRUN_INLINE_PROGRAM", "ture")
    assert names()["program form"].status == "FAIL"


# ---- F16: soulrun's own arguments are not dropped in front of an engine command ---------------------------------

def test_an_engine_command_refuses_soulruns_own_arguments_and_takes_raw_ones(soulrun, agent):
    ctx = soulrun(user_message=QUESTION, session_id="c16", **HOST)
    with pytest.raises(soulrun.UsageError) as error:
        soulrun(cmd="next-node", cache_dir=ctx.cache_dir, session_id="c16", agent_dir=str(agent))
    assert error.value.code == "ARGUMENT_NOT_FOR_CMD" and error.value.field == "agent_dir"
    assert soulrun(cmd="next-node", cache_dir=ctx.cache_dir, args=["--session-id", "c16"]).returncode == 0


# ---- F18: the types of a call are checked before anything is read or written ----------------------------------

@pytest.mark.parametrize(("call", "field"), [
    (dict(user_message=b"hello"), "user_message"),
    (dict(user_message=QUESTION, session_id=7), "session_id"),
    (dict(user_message=QUESTION, session_id=""), "session_id"),
    (dict(user_message=QUESTION, session_id="a\nfake: line"), "session_id"),
    (dict(user_message=QUESTION, model=3), "model"),
    (dict(user_message=QUESTION, channel="web\r\nx"), "channel"),
    (dict(user_message=QUESTION, agent_dir="bad\x00dir"), "agent_dir"),
    (dict(user_message=QUESTION, aiap=b"demo_aiap"), "aiap"),
    (dict(user_message=QUESTION, host_tools={"agent": "false"}), "host_tools"),
    (dict(user_message=QUESTION, host_fences="message"), "host_fences"),
    (dict(user_message=QUESTION, human_turn="no"), "human_turn"),
])
def test_a_wrong_type_is_refused_and_leaves_nothing(soulrun, agent, call, field):
    with pytest.raises(soulrun.UsageError) as error:
        soulrun(**{**dict(host_fences=(), host_tools={"agent": False}), **call})
    assert error.value.code == "ARGUMENT_TYPE" and error.value.field == field
    assert not (agent / ".soulrun_cache").exists()


# ---- F19 / F33 / F17: the command line -----------------------------------------------------------------------

def test_words_in_utf16_are_read_and_words_in_another_encoding_are_refused(agent, subprocess_env):
    (agent / "utf16.txt").write_bytes("继续".encode("utf-16"))                      # what PowerShell 5.1 writes with ">"
    done = _cli(agent, subprocess_env, "--user-message-file", "utf16.txt", "--json", "--session-id", "u19")
    assert done.returncode == 0 and json.loads(done.stdout)["kind"] in ("program", "text_only")
    (agent / "gbk.txt").write_bytes("继续执行".encode("gbk"))
    for args, data in ((("--user-message-file", "gbk.txt"), None), (("--user-message-stdin",), "继续执行".encode("gbk"))):
        done = _cli(agent, subprocess_env, *args, "--json", data=data)
        assert done.returncode == 2 and _json_error(done)["code"] == "MESSAGE_NOT_UTF8"
        assert b"Traceback" not in done.stderr


def test_with_json_every_error_is_one_json_object(agent, subprocess_env):
    for args in (("--json", "--no-such"), ("--json", "--agent-dir"), ("--json", "--user-message-stdin", "--user-message-file", "x")):
        done = _cli(agent, subprocess_env, *args)
        assert done.returncode == 2 and _json_error(done)["code"] == "ARGUMENT_INVALID", args
    done = _cli(agent, subprocess_env, "--verify-engine", "--json")
    assert done.returncode == 0 and json.loads(done.stdout) == {"ok": True, "engine_version": json.loads(
        _cli(agent, subprocess_env, "--version", "--json").stdout)["engine"], "problems": []}
    done = _cli(agent, subprocess_env, "--doctor", "--version")
    assert done.returncode == 2 and b"MODES_CONFLICT" in done.stderr


def test_cmd_written_with_an_equals_sign_works_and_an_abbreviation_is_refused(soulrun, agent, subprocess_env):
    ctx = soulrun(user_message=QUESTION, session_id="c17", **HOST)
    plain = _cli(agent, subprocess_env, "--cmd", "next-node", "--cache-dir", ctx.cache_dir)
    equals = _cli(agent, subprocess_env, "--cmd=next-node", "--cache-dir", ctx.cache_dir)
    assert plain.returncode == equals.returncode == 0
    assert _reply(equals)["node"]["name"] == _reply(plain)["node"]["name"] == "Router.match"
    short = _cli(agent, subprocess_env, "--cm", "next-node", "--cache-dir", ctx.cache_dir, "--json")
    assert short.returncode == 2 and _json_error(short)["code"] == "ARGUMENT_INVALID"
    (agent / "m.txt").write_text(QUESTION, encoding="utf-8")
    both = _cli(agent, subprocess_env, "--user-message-file", "m.txt", "--cmd=next-node", "--json")
    assert both.returncode == 2 and _json_error(both)["code"] == "MESSAGE_AND_CMD"
    assert sorted(p.name for p in (agent / ".soulrun_cache" / ".execution_cache").iterdir() if p.name.isdigit()) == ["1"]


# ---- F21: the engine's errors come out as SoulRunError ----------------------------------------------------------

def test_an_engine_error_comes_out_as_a_soulrun_error_with_the_engines_code(soulrun, agent):
    from soulrun import host
    ctx = soulrun(user_message=QUESTION, session_id="e21", **HOST)
    index = Path(ctx.cache_dir) / "_index.json"
    data = json.loads(index.read_text(encoding="utf-8"))
    data["engine_version"] = "7.0.0-alpha." + "155"             # a run another engine version started (spelled apart:
    #                                                            this file must not trip the old-version rule itself)
    index.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    for attempt in (lambda: soulrun(user_message="继续", session_id="e21", **HOST),
                    lambda: host.after_turn(ctx.cache_dir, "回答")):
        with pytest.raises(soulrun.SoulRunError) as error:
            attempt()
        assert error.value.code == "RUN_ENGINE_VERSION_MISMATCH" and type(error.value.__cause__).__name__ == "EngineError"


# ---- F25 / F44: which existing folder may become the run folder ------------------------------------------------

def test_a_folder_with_other_files_beside_old_runs_is_refused_and_named(soulrun, agent, tmp_path):
    kept = tmp_path / "evidence"
    (kept / ".execution_cache" / "1").mkdir(parents=True)
    (kept / "analysis.md").write_text("notes", encoding="utf-8")
    with pytest.raises(soulrun.UsageError) as error:
        soulrun(user_message=QUESTION, soulrun_cache_dir=str(kept), **HOST)
    assert error.value.code == "SOULRUN_CACHE_DIR_NOT_EMPTY" and "analysis.md" in error.value.message
    only_runs = tmp_path / "runs_only"
    (only_runs / ".execution_cache").mkdir(parents=True)
    assert soulrun(user_message=QUESTION, soulrun_cache_dir=str(only_runs), **HOST).kind == "program"
    (only_runs / "notes.md").write_text("now SoulRun's own folder", encoding="utf-8")       # it has .soulrun now
    assert soulrun(user_message="继续", soulrun_cache_dir=str(only_runs), **HOST).cache_dir


def test_system_files_do_not_make_a_folder_non_empty(soulrun, agent, tmp_path):
    folder = tmp_path / "fresh_from_finder"
    folder.mkdir()
    for name in (".DS_Store", "desktop.ini", "Thumbs.db", ".gitkeep"):
        (folder / name).write_bytes(b"x")
    assert soulrun(user_message=QUESTION, soulrun_cache_dir=str(folder), **HOST).kind == "program"


# ---- F26: what the human reads names no absolute path and no other conversation --------------------------------

def test_a_doubt_names_no_absolute_path(soulrun, agent):
    ctx = soulrun(user_message=QUESTION, session_id="p26", aiap="dem_aiap", **HOST)
    assert str(agent.resolve()) not in ctx.text and "aiap/dem_aiap" in ctx.text
    assert Path(ctx.doubt["looked_in"]).is_absolute()                         # for the host


# ---- F27: no session_id, one run folder shared by two agents -----------------------------------------------------

def test_two_agents_sharing_a_run_folder_keep_their_own_default_conversation(soulrun, agent, tmp_path, monkeypatch):
    import shutil
    shared = tmp_path / "shared_runs"
    second = tmp_path / "agent_b"
    shutil.copytree(agent / "aiap", second / "aiap")
    monkeypatch.setenv("SOULRUN_CACHE_DIR", str(shared))
    first = soulrun(user_message=QUESTION, agent_dir=str(agent), **HOST)
    other = soulrun(user_message="继续", agent_dir=str(second), **HOST)
    assert first.session_id.startswith("default-") and other.session_id.startswith("default-")
    assert first.session_id != other.session_id and other.cache_dir != first.cache_dir
    assert soulrun(user_message="继续", agent_dir=str(agent), **HOST).cache_dir == first.cache_dir
    monkeypatch.delenv("SOULRUN_CACHE_DIR")
    assert soulrun(user_message=QUESTION, agent_dir=str(second), **HOST).session_id == "default"   # its own folder


# ---- F28: a new task after a Stop keeps the program the run was made for ----------------------------------------

def test_a_new_task_after_a_stop_keeps_the_named_program(soulrun, agent):
    from soulrun import host
    ctx = soulrun(user_message=QUESTION, session_id="k28", aiap="demo_aiap", **HOST)
    host.stop(ctx.cache_dir, "host-run-1")
    judged = soulrun(user_message="等一下，我想换个话题", session_id="k28", **HOST)
    decided = soulrun(cmd="stop-decision", cache_dir=ctx.cache_dir, stop_id=judged.data["stop_id"],
                      judge_id=judged.data["judge_id"], decision="ask", recommendation="new_task",
                      explanation="像是新任务", advice="建议新任务", reason="消息与本场无关").json()
    host.after_turn(ctx.cache_dir, decided["public_block_ref"])
    new = soulrun(user_message="2", session_id="k28", **HOST)
    assert new.data.get("stop_new_task") and new.cache_dir != ctx.cache_dir
    assert candidates(new) == ["demo_aiap"]
    record = json.loads((agent / ".soulrun_cache" / ".soulrun" / "runs" / f"{Path(new.cache_dir).name}.json").read_text(encoding="utf-8"))
    assert record["candidates"] == "designated" and record["kept_from"] == Path(ctx.cache_dir).name
    assert [Path(d).name for d in record["designated"]] == ["demo_aiap"]


# ---- F29 / F31: what the command line prints -----------------------------------------------------------------------

def test_a_long_original_request_never_pushes_the_instructions_out(soulrun, agent):
    from soulrun import _render
    long_request = "请运行 demo：" + "这是一段很长的材料。" * 6000
    soulrun(user_message=long_request, session_id="r29", **HOST)
    again = soulrun(user_message="再补充一句", session_id="r29", **HOST)
    assert _render.size(again.text) > _render.print_cap()
    printed, saved = _render.for_shell(again)
    assert _render.size(printed) <= _render.print_cap() and saved is not None and saved.read_text(encoding="utf-8") == again.text
    short_lines = [line for line in again.text.split("\n") if _render.size(line) <= _render.LONG_LINE]
    assert all(line in printed.split("\n") for line in short_lines)                  # every instruction line is whole


def test_a_full_text_that_cannot_be_saved_is_still_printed(soulrun, agent):
    from soulrun import _render
    ctx = soulrun(user_message=QUESTION, session_id="r31", **HOST)
    entries = agent / ".soulrun_cache" / ".soulrun" / "entries"
    entries.parent.mkdir(parents=True, exist_ok=True)
    entries.write_text("not a folder", encoding="utf-8")
    printed, saved = _render.for_shell(ctx)
    assert saved is None and printed == ctx.text


# ---- F30: a busy run folder holds up no other ------------------------------------------------------------------------

def test_a_run_folder_held_by_another_process_does_not_hold_up_another_folder(soulrun, agent, tmp_path, subprocess_env):
    holder = subprocess.Popen(
        [sys.executable, "-B", "-c", "import sys, time\nfrom pathlib import Path\nfrom soulrun import _filelock\n"
         "with _filelock.held(Path(sys.argv[1])):\n    print('held', flush=True)\n    time.sleep(6)\n",
         str(agent / ".soulrun_cache" / ".soulrun")], env=subprocess_env, stdout=subprocess.PIPE, text=True)
    try:
        assert holder.stdout.readline().strip() == "held"
        waiting = threading.Thread(target=lambda: soulrun(user_message=QUESTION, session_id="busy", **HOST))
        waiting.start()
        time.sleep(0.5)                                                   # it now waits on the held folder
        started = time.monotonic()
        free = soulrun(user_message=QUESTION, session_id="free", soulrun_cache_dir=str(tmp_path / "free_runs"), **HOST)
        assert free.kind == "program" and time.monotonic() - started < 4 and holder.poll() is None
    finally:
        holder.wait(timeout=30)
    waiting.join(timeout=60)


# ---- F32: a run folder that cannot be used is an error with a code --------------------------------------------------

def test_a_run_folder_that_cannot_be_used_is_reported_with_a_code(soulrun, agent):
    soulrun(user_message=QUESTION, session_id="w32", **HOST)
    notes = agent / ".soulrun_cache" / ".soulrun"
    for child in sorted(notes.rglob("*"), reverse=True):
        child.unlink() if child.is_file() else child.rmdir()
    notes.rmdir()
    notes.write_text("a file where SoulRun keeps its notes folder", encoding="utf-8")
    with pytest.raises(soulrun.UsageError) as error:
        soulrun(user_message="继续", session_id="w32", **HOST)
    assert error.value.code == "SOULRUN_CACHE_DIR_INVALID" and error.value.field == "soulrun_cache_dir"


# ---- F23 / F24 / F34 / F35: the doctor ------------------------------------------------------------------------------

def test_the_doctor_uses_the_same_folders_and_names_as_a_run(agent, tmp_path):
    import shutil

    from soulrun import _doctor
    elsewhere = tmp_path / "programs_elsewhere"
    shutil.copytree(agent / "aiap", elsewhere)
    empty = tmp_path / "no_programs_here"
    empty.mkdir()
    checks = {c.name: c for c in _doctor.run(agent_dir=empty, aiap_dir=elsewhere)}
    assert checks["programs"].status == "OK"
    checks = {c.name: c for c in _doctor.run(agent_dir=agent, aiap="nosuch")}
    assert checks["programs"].status == "FAIL" and "nosuch" in checks["programs"].detail
    (agent / "aiap" / "misplaced").mkdir()
    (agent / "aiap" / "misplaced" / "aisp.aisop.json").write_text("{}", encoding="utf-8")
    checks = {c.name: c for c in _doctor.run(agent_dir=agent)}
    assert checks["misplaced programs"].status == "WARN" and "misplaced" in checks["misplaced programs"].detail


def test_the_doctor_wants_python_not_only_python3(monkeypatch):
    from soulrun import _doctor
    monkeypatch.setattr(_doctor.shutil, "which", lambda name, *a, **k: "/usr/bin/python3" if name == "python3" else None)
    monkeypatch.setattr(_doctor.subprocess, "run", lambda *a, **k: pytest.fail("python3 was taken for the model's python"))
    slim = _doctor._python_check(None)              # a failure in every program form (test_doctor), python3 not taken
    assert slim.status == "FAIL" and "only `python3` was found" in slim.detail and "python-is-python3" in slim.detail
    monkeypatch.setenv("SOULRUN_SLIM_PROGRAM", "false")            # the entry-path form runs `python ...` commands
    check = _doctor._python_check(None)
    assert check.status == "FAIL" and "only `python3` was found" in check.detail and "python-is-python3" in check.detail


def test_the_doctor_does_not_run_a_python_in_the_current_folder(monkeypatch, tmp_path):
    from soulrun import _doctor
    planted = tmp_path / "python.bat"
    planted.write_text("echo planted", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(_doctor, "_windows", lambda: True)
    monkeypatch.setattr(_doctor.shutil, "which", lambda name, *a, **k: str(planted) if name == "python" else None)
    monkeypatch.setattr(_doctor.subprocess, "run", lambda *a, **k: pytest.fail("the planted python was run"))
    check = _doctor._python_check(None)
    assert check.status == "WARN" and "not run" in check.detail


def test_the_doctor_survives_the_broken_setups_it_describes(monkeypatch):
    from soulrun import _doctor
    monkeypatch.setattr(_doctor.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 1, stdout=None, stderr=None))
    assert _doctor._python_check(sys.executable).status == "FAIL"                     # no text at all: no crash
    broken = lambda: (_ for _ in ()).throw(PermissionError("denied"))                 # noqa: E731
    assert _doctor._safely("folders", broken) == [_doctor.Check("FAIL", "folders", "PermissionError: denied")]


def test_a_damaged_manifest_or_slim_program_is_a_fail_line(subprocess_env, tmp_path, agent):
    import shutil
    from conftest import ROOT, INSTALLED
    if INSTALLED:
        pytest.skip("the copy is made from the source tree")
    for damage in ("manifest", "slim"):
        copy = tmp_path / f"copy_{damage}"
        shutil.copytree(ROOT / "src" / "soulrun", copy / "soulrun", ignore=shutil.ignore_patterns("__pycache__"))
        if damage == "manifest":
            (copy / "soulrun" / "engine_manifest.json").write_text('{"files": ', encoding="utf-8")
        else:
            (copy / "soulrun" / "engine_node.aisop.json").unlink()
        env = dict(subprocess_env, PYTHONPATH=str(copy))
        done = subprocess.run([sys.executable, "-B", "-X", "utf8", "-m", "soulrun", "--doctor", "--agent-dir", str(agent)],
                              cwd=str(tmp_path), env=env, capture_output=True, text=True, encoding="utf-8", timeout=120)
        assert done.returncode == 1 and "Traceback" not in done.stdout + done.stderr, done.stderr
        line = "FAIL engine files" if damage == "manifest" else "FAIL slim program"
        assert line in done.stdout, done.stdout


# ---- F36: an error survives being copied or sent between processes ---------------------------------------------------

def test_a_soulrun_error_can_be_pickled_and_copied(soulrun):
    error = soulrun.UsageError("SOME_CODE", "what went wrong", field="agent_dir", expected="an existing folder")
    for again in (pickle.loads(pickle.dumps(error)), copy.copy(error)):
        assert type(again) is soulrun.UsageError and again.as_dict() == error.as_dict() and str(again) == str(error)


# ---- the gate still works under all of this -----------------------------------------------------------------------------

def test_a_gate_is_still_answered_as_before(soulrun, agent):
    ctx = soulrun(user_message=QUESTION, session_id="g", aiap="demo_aiap", aisp="demo_aisp", **HOST)
    assert commit(soulrun, ctx, gate_payload(take_node(soulrun, ctx), ["demo_aiap", "demo_aisp"], "demo_aiap"))["status"] == "WAITING_USER"
    assert soulrun(user_message="1", session_id="g", **HOST).entry_mode == "resume"


# ---- F70: SoulRun's notes are written whole or not at all ------------------------------------------------------

def test_a_note_that_cannot_be_put_in_place_leaves_the_old_one_whole_and_no_temporary_file(soulrun, agent, monkeypatch):
    from soulrun import _records
    target = agent / "note.json"
    _records.write_whole(target, '{"kept": 1}\n')
    assert target.read_text(encoding="utf-8") == '{"kept": 1}\n'

    def refused(source, destination):
        raise OSError(28, "No space left on device")
    with monkeypatch.context() as patched:              # os.replace is the engine's too: patched for this write only
        patched.setattr(_records.os, "replace", refused)
        with pytest.raises(OSError):
            _records.write_whole(target, '{"half": ')
    assert target.read_text(encoding="utf-8") == '{"kept": 1}\n'
    assert [p.name for p in agent.iterdir() if p.name.endswith(".tmp")] == []

    def no_note(target, text):
        raise OSError(28, "No space left on device")
    monkeypatch.setattr(_records, "write_whole", no_note)
    ctx = soulrun(user_message=QUESTION, session_id="r70", **HOST)     # a run is never lost because its note was not
    notes = agent / ".soulrun_cache" / ".soulrun" / "runs"
    assert ctx.kind == "program" and (not notes.exists() or list(notes.iterdir()) == [])

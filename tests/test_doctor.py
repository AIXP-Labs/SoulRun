"""soulrun --doctor: every check, and that it never creates anything."""
from __future__ import annotations

import json
import sys

import pytest

from conftest import make_agent
from helpers import HOST, QUESTION


def _statuses(checks) -> dict:
    return {c.name: c.status for c in checks}


def test_a_fresh_agent_folder_passes_and_nothing_is_created(soulrun, agent):
    from soulrun import _doctor
    before = sorted(p.relative_to(agent).as_posix() for p in agent.rglob("*"))
    checks = _doctor.run(agent_dir=agent)
    assert sorted(p.relative_to(agent).as_posix() for p in agent.rglob("*")) == before   # the write probe is gone too
    assert _doctor.exit_code(checks) == 0
    statuses = _statuses(checks)
    assert statuses.pop("time zones") in ("OK", "WARN")          # depends on this Python: see the time-zone tests
    assert statuses.pop("path length", "OK") in ("OK", "WARN")   # Windows only: see the path-length test
    assert statuses == {"versions": "OK", "engine files": "OK", "slim program": "OK", "engine interface": "OK",
                        "python for the model": "OK", "program form": "OK", "engine settings": "OK", "agent folder": "OK",
                        "programs": "OK", "soulrun_cache_dir": "OK"}
    assert "creation will be attempted at the first run" in next(c.detail for c in checks if c.name == "soulrun_cache_dir")
    assert "aiap: demo_aiap, other_aiap; aisp: demo_aisp" in next(c.detail for c in checks if c.name == "programs")
    assert not (agent / ".soulrun_cache").exists()                                 # read-only


def test_after_a_run_the_data_folder_and_the_unfinished_run_are_reported(soulrun, agent):
    from soulrun import _doctor
    soulrun(user_message=QUESTION, session_id="d1", **HOST)
    checks = _doctor.run(agent_dir=agent)
    assert "1 run(s) kept" in next(c.detail for c in checks if c.name == "soulrun_cache_dir")
    assert _statuses(checks)["unfinished runs"] == "WARN" and "version control" not in _statuses(checks)
    assert _doctor.exit_code(checks) == 0                                        # warnings do not fail


def test_a_cache_folder_without_gitignore_one_holding_an_engine_and_one_with_other_files(soulrun, agent, tmp_path):
    from soulrun import _doctor
    plain = tmp_path / "plain"
    (plain / ".execution_cache").mkdir(parents=True)                             # SoulRun's, made by hand, no .gitignore
    assert _statuses(_doctor.run(agent_dir=agent, soulrun_cache_dir=plain))["version control"] == "WARN"
    other = tmp_path / "other_engine"
    (other / "python_tools").mkdir(parents=True)
    checks = _doctor.run(agent_dir=agent, soulrun_cache_dir=other)
    assert _statuses(checks)["soulrun_cache_dir"] == "FAIL" and _doctor.exit_code(checks) == 1
    project = tmp_path / "project"
    project.mkdir()
    (project / "README.md").write_text("mine", encoding="utf-8")
    checks = _doctor.run(agent_dir=agent, soulrun_cache_dir=project)
    assert _statuses(checks)["soulrun_cache_dir"] == "FAIL" and "already holds other files" in checks[-1].detail


def test_whether_a_folder_can_be_written_is_tried_once_and_leaves_nothing(soulrun, agent, tmp_path, monkeypatch):
    from soulrun import _doctor
    folder = tmp_path / "probe"
    folder.mkdir()
    assert _doctor._writable(folder) is True and list(folder.iterdir()) == []
    assert _doctor._writable(tmp_path / "missing") is False
    attempts = []

    def refused(*args, **kwargs):                       # what a folder closed by its permissions does
        attempts.append(args[0])
        raise PermissionError(13, "Access is denied")
    monkeypatch.setattr(_doctor.os, "open", refused)
    assert _doctor._writable(folder) is False and len(attempts) == 1
    data = tmp_path / "closed"
    data.mkdir()
    checks = _doctor.run(agent_dir=agent, soulrun_cache_dir=data)
    assert _statuses(checks)["soulrun_cache_dir"] == "FAIL" and "cannot be written" in next(c.detail for c in checks if c.name == "soulrun_cache_dir")
    assert _doctor.exit_code(checks) == 1


def test_missing_cache_qualifies_the_existing_parent_probe(soulrun, agent, monkeypatch):
    from soulrun import _doctor, _select

    cache = agent / "new-parent" / "runs"
    places = _select.resolve_places(agent_dir=agent, soulrun_cache_dir=cache, create=False)
    attempts = []

    def writable(folder):
        attempts.append(folder)
        return True

    monkeypatch.setattr(_doctor, "_writable", writable)
    checks = _doctor._cache_checks(places)
    result = next(c for c in checks if c.name == "soulrun_cache_dir")
    assert result.status == "OK" and _doctor.exit_code(checks) == 0
    assert attempts == [agent]
    assert "write probe passed for" in result.detail
    assert "creation will be attempted" in result.detail
    assert "access to the new folder and its privacy are not verified" in result.detail
    assert not cache.exists() and not cache.parent.exists()


def test_time_zone_data_is_checked_in_both_pythons(soulrun, monkeypatch):
    from soulrun import _doctor
    assert _doctor._zone_data(sys.executable) == _doctor._zone_data(None)   # the probe in a child agrees with this process
    other = sys.executable + ".other"                                       # a model's python that is not this one
    monkeypatch.setattr(_doctor, "_zone_data", lambda python: True)
    assert _doctor._zone_check(other) == _doctor.Check("OK", "time zones", "named time zones can be read by both Pythons")
    assert _doctor._zone_check(sys.executable).detail == "named time zones can be read"   # the same python is probed once
    monkeypatch.setattr(_doctor, "_zone_data", lambda python: python is not None)          # only this process lacks it
    missing_here = _doctor._zone_check(other)
    assert missing_here.status == "WARN" and missing_here.detail.startswith("no time-zone data in this Python (")
    assert "the model's python" not in missing_here.detail and "pip install tzdata" in missing_here.detail
    monkeypatch.setattr(_doctor, "_zone_data", lambda python: False)
    both = _doctor._zone_check(other)
    assert "this Python (" in both.detail and f"the model's python ({other})" in both.detail
    assert _doctor.exit_code([both]) == 0                                    # a warning, not a failure


def test_the_branches_that_need_a_broken_machine(soulrun, agent, tmp_path, monkeypatch):
    from soulrun import _doctor, _engine
    missing = str(tmp_path / "no_such_python.exe")
    started = _doctor._python_check(missing)
    assert started.status == "FAIL" and "could not be started" in started.detail
    assert _doctor._zone_data(missing) is False                          # a probe that cannot start says "no data"

    def no_zone(key):
        raise _doctor.zoneinfo.ZoneInfoNotFoundError(key)
    monkeypatch.setattr(_doctor.zoneinfo, "ZoneInfo", no_zone)
    assert _doctor._zone_data(None) is False

    def unavailable():
        raise soulrun.EngineUnavailable("ENGINE_MISSING", "the bundled engine cannot be found")
    monkeypatch.setattr(_engine, "version", unavailable)
    assert _doctor.run(agent_dir=agent) == [_doctor.Check("FAIL", "engine", "the bundled engine cannot be found")]


def test_a_copy_with_a_damaged_engine_still_starts_and_says_what_is_wrong(soulrun, agent, tmp_path, subprocess_env):
    """`import soulrun` used to read the engine's version at once, so a damaged install could not even run the doctor."""
    import shutil
    import subprocess
    from pathlib import Path
    copy = tmp_path / "copy"
    shutil.copytree(Path(soulrun.__file__).parent, copy / "soulrun",
                    ignore=shutil.ignore_patterns("__pycache__", ".execution_cache", "tests"))
    (copy / "soulrun" / "soulrun_aiap" / "python_tools" / "lib" / "engine_core.py").unlink()
    env = dict(subprocess_env, PYTHONPATH=str(copy))

    def cli(*args):
        return subprocess.run([sys.executable, "-B", "-X", "utf8", "-m", "soulrun", *args], capture_output=True,
                              text=True, encoding="utf-8", env=env, cwd=str(tmp_path), timeout=120)
    imported = subprocess.run([sys.executable, "-B", "-c", "import soulrun; print(soulrun.__file__)"], capture_output=True,
                              text=True, env=env, timeout=120)
    assert imported.returncode == 0 and str(copy) in imported.stdout                     # the damaged copy is the one used
    doctor = cli("--doctor", "--agent-dir", str(agent))
    assert doctor.returncode == 1 and "Traceback" not in doctor.stdout + doctor.stderr
    assert doctor.stdout.startswith("FAIL engine: the bundled engine is not at ") and "1 check(s) failed" in doctor.stdout
    verify = cli("--verify-engine")
    assert verify.returncode == 1 and "Traceback" not in verify.stderr and "ENGINE_MISSING" in verify.stderr


def test_a_data_folder_that_is_a_file_or_cannot_be_made(soulrun, agent, tmp_path):
    from soulrun import _doctor
    a_file = tmp_path / "data.txt"
    a_file.write_text("not a folder", encoding="utf-8")
    checks = _doctor.run(agent_dir=agent, soulrun_cache_dir=a_file)
    assert _statuses(checks)["soulrun_cache_dir"] == "FAIL" and "is not a folder" in checks[-1].detail
    under_a_file = a_file / "runs"                                        # its nearest existing parent is a file
    checks = _doctor.run(agent_dir=agent, soulrun_cache_dir=under_a_file)
    assert _statuses(checks)["soulrun_cache_dir"] == "FAIL" and "cannot be written" in checks[-1].detail
    with pytest.raises(soulrun.UsageError) as raised:                     # and a run refuses it the same way
        soulrun(user_message="hi", agent_dir=agent, soulrun_cache_dir=under_a_file)
    assert raised.value.code == "SOULRUN_CACHE_DIR_INVALID" and "cannot be created" in raised.value.message
    assert a_file.read_text(encoding="utf-8") == "not a folder"


def test_the_path_length_check_on_windows(soulrun, agent, monkeypatch):
    """Measured: with long paths off, a 150-character run folder failed at the first commit (the engine's
    receipt names are 64-character digests); a 110-character one worked, its deepest file then 240 characters."""
    from pathlib import Path

    from soulrun import _doctor
    monkeypatch.setattr(_doctor, "_windows", lambda: True)
    monkeypatch.setattr(_doctor, "_long_paths_enabled", lambda: False)
    fits = _doctor._path_check(Path("C:/" + "a" * 100))
    assert fits.status == "OK" and "within Windows' 260" in fits.detail
    too_deep = _doctor._path_check(Path("C:/" + "a" * 150))
    assert too_deep.status == "WARN" and "past the 259 characters Windows allows" in too_deep.detail
    assert f"at most {259 - 1 - _doctor.DEEPEST_IN_CACHE} characters" in too_deep.detail
    monkeypatch.setattr(_doctor, "_long_paths_enabled", lambda: True)
    assert "long paths are enabled" in _doctor._path_check(Path("C:/" + "a" * 150)).detail
    assert _statuses(_doctor.run(agent_dir=agent))["path length"] == "OK"
    monkeypatch.setattr(_doctor, "_windows", lambda: False)
    assert _doctor._path_check(Path("/" + "a" * 300)) is None and "path length" not in _statuses(_doctor.run(agent_dir=agent))


@pytest.mark.parametrize(("folder", "longest", "status"), [(128, 259, "OK"), (129, 260, "WARN"), (130, 261, "WARN")])
def test_the_path_length_check_counts_the_null_that_ends_a_windows_path(soulrun, agent, monkeypatch, folder, longest,
                                                                        status):
    """Windows' 260-character limit (MAX_PATH) counts the null that ends a path, so with long paths off the longest
    path that fits is 259 characters: a deepest file of 259 is fine, one of exactly 260 is already too long. With short
    node names the deepest file is 130 characters inside the run folder, so a 129-character folder passed the check
    (docs/05SoulRun 87, section 8 item 3) although that file could not be written."""
    from pathlib import Path

    from soulrun import _doctor
    monkeypatch.setattr(_doctor, "_windows", lambda: True)
    monkeypatch.setattr(_doctor, "_long_paths_enabled", lambda: False)
    demo = [agent / "aiap" / "demo_aiap"]
    cache = Path("C:/" + "a" * (folder - 3))
    assert len(str(cache)) == folder and _doctor._deepest(demo, cache)[0] == 130
    check = _doctor._path_check(cache, demo)
    assert check.status == status and f"about {longest} characters" in check.detail, check.detail
    if status == "WARN":                                     # the folder it names is the 128-character one above: OK
        assert "past the 259 characters Windows allows" in check.detail and "at most 128 characters" in check.detail
        monkeypatch.setattr(_doctor, "_long_paths_enabled", lambda: True)
        assert _doctor._path_check(cache, demo).status == "OK"


@pytest.mark.parametrize(("tail", "longest", "status"), [("中", 259, "OK"), ("\U00020000", 260, "WARN"),
                                                         ("\U0001F600", 260, "WARN")])
def test_the_path_length_check_counts_utf16_units_as_windows_does(soulrun, agent, monkeypatch, tail, longest, status):
    """Windows measures a path in UTF-16 units: a character outside the Basic Multilingual Plane (a CJK Extension B
    character, an emoji) takes two, so a folder Python counts as 128 characters is 129 for Windows when it holds one
    (docs/05SoulRun 88, problem 84). A character inside the plane, such as 中, takes one."""
    from pathlib import Path

    from soulrun import _doctor
    monkeypatch.setattr(_doctor, "_windows", lambda: True)
    monkeypatch.setattr(_doctor, "_long_paths_enabled", lambda: False)
    demo = [agent / "aiap" / "demo_aiap"]
    cache = Path("C:/" + "a" * 124 + tail)
    assert len(str(cache)) == 128 and _doctor._deepest(demo, cache)[0] == 130
    check = _doctor._path_check(cache, demo)
    assert check.status == status and f"about {longest} characters" in check.detail, check.detail


def test_no_programs_fails(soulrun, tmp_path):
    from soulrun import _doctor
    empty = tmp_path / "empty"
    empty.mkdir()
    checks = _doctor.run(agent_dir=empty)
    assert _statuses(checks)["programs"] == "FAIL" and _doctor.exit_code(checks) == 1
    assert list(empty.iterdir()) == []


def test_a_wrong_folder_is_reported_not_raised(soulrun, tmp_path):
    from soulrun import _doctor
    checks = _doctor.run(agent_dir=tmp_path / "missing")
    assert _statuses(checks)["agent folder"] == "FAIL" and "does not exist" in checks[-1].detail


def test_the_python_a_model_will_use(soulrun, monkeypatch):
    from soulrun import _doctor
    ok = _doctor._python_check(sys.executable)
    assert ok.status == "OK" and "loads the engine's tools" in ok.detail
    monkeypatch.setattr(_doctor.shutil, "which", lambda name: None)
    missing = _doctor._python_check(None)                               # in every program form: see the test below
    assert missing.status == "FAIL" and "no `python` on PATH" in missing.detail
    monkeypatch.setattr(_doctor, "PROBE", "import no_such_module_for_the_probe")
    broken = _doctor._python_check(sys.executable)
    assert broken.status == "FAIL" and "cannot load the engine's tools" in broken.detail


def test_no_python_on_path_fails_in_every_program_form_and_says_which_runs_need_it(soulrun, agent, monkeypatch):
    """The slim form (the default) names the interpreter running SoulRun by its full path, but only in the main
    conversation's text. A sub-agent reads the engine's own agent_engine.aisop.json, whose steps run
    `python {engine_dir}/python_tools/next_node.py ...` and `... node_commit.py ...`; a program's own tools run as the
    program writes them (SoulBot's yijing program: `python tool_dirs/cast_hexagram.py`); in the entry-path form every
    engine tool runs as `python ...`. So no `python` stays a FAIL - exit 1 - in every form, and the line says which runs
    need one. It never says that every run stops at its first step: the slim form's main conversation does not."""
    from soulrun import _doctor, _slim
    monkeypatch.setattr(_doctor.shutil, "which", lambda name, *a, **k: None)
    details = set()
    for switches, form in (({}, "slim (the default"), ({"SOULRUN_SLIM_PROGRAM": "false"}, "entry_path ("),
                           ({"SOULRUN_INLINE_PROGRAM": "true"}, "full (")):
        with monkeypatch.context() as patch:
            for name, value in switches.items():
                patch.setenv(name, value)
            checks = {c.name: c for c in _doctor.run(agent_dir=agent)}
            assert checks["program form"].status == "OK" and checks["program form"].detail.startswith(form)   # in force
            found = checks["python for the model"]
            assert found.status == "FAIL" and _doctor.exit_code(list(checks.values())) == 1, (form, found)
            details.add(found.detail)
    assert len(details) == 1                                              # the same true words in every form
    said = details.pop()
    assert said.startswith("no `python` on PATH, which these need: every engine tool in the entry-path form")
    assert "a turn that falls back to it), so such a run stops at its first step" in said
    assert "a sub-agent's engine tools, in every form (`python <engine>/python_tools/...`)" in said
    assert "a program's own tools written as `python ...`, in every form" in said
    assert said.endswith("Only the slim form's main conversation runs the engine's tools without it (the interpreter "
                         "running SoulRun, by its full path)")
    assert "so the run would stop at its first step" not in said and "only `python3`" not in said
    with monkeypatch.context() as patch:                  # the slim program cannot be built: every run falls back
        def unavailable(*arguments, **options):
            raise soulrun.EngineUnavailable("SLIM_PROGRAM_STALE", "built from a different engine program")
        patch.setattr(_slim, "entry_program", unavailable)
        assert _doctor._python_check(None) == _doctor.Check("FAIL", "python for the model", said)
    monkeypatch.setenv("SOULRUN_SLIM_PROGRAM", "maybe")       # a switch value every run refuses
    assert _doctor._python_check(None) == _doctor.Check("FAIL", "python for the model", said)
    monkeypatch.delenv("SOULRUN_SLIM_PROGRAM")
    monkeypatch.setattr(_doctor.shutil, "which", lambda name, *a, **k: "/usr/bin/python3" if name == "python3" else None)
    hinted = _doctor._python_check(None)                  # the slim form, with the hint kept
    assert hinted.status == "FAIL" and hinted.detail == said + ("; only `python3` was found (/usr/bin/python3) - install "
                                                                "python-is-python3 or make `python` a link to it")


# What the same command line gives: (program-form switches, environment). Each is run once as a turn and once as
# --doctor; the doctor's program-form line must name the form that turn got, or fail where that turn stops.
FORM_SWITCHES = [
    ([], {}),
    (["--no-slim-program"], {}),
    (["--slim-program"], {}),
    (["--inline-program"], {}),
    (["--inline-program", "--no-slim-program"], {}),
    (["--inline-program", "--slim-program"], {}),
    (["--slim-program"], {"SOULRUN_SLIM_PROGRAM": "false"}),        # the argument before the variable
    (["--no-slim-program"], {"SOULRUN_SLIM_PROGRAM": "maybe"}),     # a variable the argument replaces is not read
    (["--inline-program"], {"SOULRUN_SLIM_PROGRAM": "true"}),
    (["--no-slim-program"], {"SOULRUN_INLINE_PROGRAM": "ture"}),    # the other switch's variable still is
    ([], {"SOULRUN_SLIM_PROGRAM": "off"}),
]


@pytest.mark.parametrize(("flags", "environment"), FORM_SWITCHES)
def test_the_doctor_takes_the_program_form_switches_as_a_run_takes_them(soulrun, agent, capsys, monkeypatch, tmp_path,
                                                                        flags, environment):
    """`soulrun --doctor --no-slim-program` (or --slim-program, --inline-program) used to accept the switch and drop it:
    the program-form line reported the environment's form. The doctor now resolves the switches as a run does - each
    argument before its environment variable, both forms asked for, a value that is not a switch."""
    from soulrun import cli
    for name, value in environment.items():
        monkeypatch.setenv(name, value)
    message = tmp_path / "message.txt"
    message.write_text(QUESTION, encoding="utf-8")
    ran = cli.main(["--user-message-file", str(message), "--agent-dir", str(agent), "--session-id", "forms", "--model",
                    HOST["model"], "--host-tool", "agent=false", "--json", *flags])
    turn = capsys.readouterr()
    assert cli.main(["--doctor", "--agent-dir", str(agent), "--json", *flags]) in (0, 1)
    line = next(c for c in json.loads(capsys.readouterr().out)["checks"] if c["name"] == "program form")
    if ran == 0:
        printed = json.loads(turn.out)
        assert "slim_fallback" not in printed                        # printed in the form it was given
        assert line["status"] == "OK" and line["detail"].startswith(printed["program_form"] + " ("), (printed["program_form"], line)
    else:
        error = json.loads(turn.err)["error"]
        assert error["code"] in ("PROGRAM_FORMS_CONFLICT", "SWITCH_INVALID"), error
        assert line["status"] == "FAIL" and (error["code"] in line["detail"] or line["detail"] == error["message"]), (error, line)


def test_the_doctor_names_where_a_program_form_switch_came_from(soulrun, agent, monkeypatch):
    from soulrun import _doctor
    form = lambda **switches: {c.name: c for c in _doctor.run(agent_dir=agent, **switches)}["program form"]   # noqa: E731
    assert form(slim_program=False).detail.startswith("entry_path (slim_program is off: ")
    assert form(inline_program=True).detail.startswith("full (the whole main program in the text; inline_program)")
    conflict = form(inline_program=True, slim_program=True)
    assert conflict.status == "FAIL" and conflict.detail.startswith("both inline_program and slim_program are on: ")
    monkeypatch.setenv("SOULRUN_SLIM_PROGRAM", "1")
    assert form(inline_program=True).detail.startswith("both inline_program and SOULRUN_SLIM_PROGRAM are on: ")
    assert form().detail.startswith("slim (SOULRUN_SLIM_PROGRAM is on: ")    # asked for, not the default
    with pytest.raises(soulrun.UsageError) as error:                     # a value that is not a switch, as a run says it
        soulrun(user_message=QUESTION, session_id="named", slim_program="no", **HOST)
    assert error.value.code == "SWITCH_INVALID"
    assert form(slim_program="no") == _doctor.Check("FAIL", "program form", error.value.message)


def test_the_doctor_names_the_switch_that_asked_for_the_slim_form(soulrun, agent, capsys, monkeypatch, tmp_path):
    """The slim line names the switch that asked for the slim form - the argument before its variable - and says "the
    default" only when no program-form switch was given: `--doctor --slim-program` with SOULRUN_SLIM_PROGRAM=false
    used to read "slim (the default: ...)"."""
    from soulrun import _doctor, _slim, cli
    form = lambda **switches: {c.name: c for c in _doctor.run(agent_dir=agent, **switches)}["program form"]   # noqa: E731

    def slim(check, why):
        assert check.status == "OK" and check.detail.startswith(f"slim ({why}: the engine program handed out by "), check
        assert ("the default" in check.detail) == (why == "the default"), check

    slim(form(), "the default")
    slim(form(slim_program=True), "slim_program is on")
    monkeypatch.setenv("SOULRUN_SLIM_PROGRAM", "false")
    slim(form(slim_program=True), "slim_program is on")                  # the argument before the variable
    assert cli.main(["--doctor", "--agent-dir", str(agent), "--json", "--slim-program"]) in (0, 1)
    line = next(c for c in json.loads(capsys.readouterr().out)["checks"] if c["name"] == "program form")
    slim(_doctor.Check(**line), "slim_program is on")                    # the command line, as reported
    monkeypatch.setenv("SOULRUN_SLIM_PROGRAM", "true")
    slim(form(), "SOULRUN_SLIM_PROGRAM is on")
    monkeypatch.setenv("SOULRUN_INLINE_PROGRAM", "off")
    slim(form(), "SOULRUN_SLIM_PROGRAM is on")                           # the slim switch decided it
    monkeypatch.delenv("SOULRUN_SLIM_PROGRAM")
    slim(form(), "SOULRUN_INLINE_PROGRAM is off and no slim switch is given")   # a switch was given: not "the default"
    monkeypatch.delenv("SOULRUN_INLINE_PROGRAM")
    slim(form(inline_program=False), "inline_program is off and no slim switch is given")
    monkeypatch.setenv("SOULRUN_SLIM_PROGRAM", "  ")                     # set to nothing: not given
    slim(form(), "the default")
    try:                                                                 # the warning names the same
        with monkeypatch.context() as patch:
            patch.setattr(_slim, "FILE", tmp_path / "missing.json")
            _slim.document.cache_clear()
            for switches, why in (({}, "the default"), ({"slim_program": True}, "slim_program is on")):
                warned = form(**switches)
                assert warned.status == "WARN" and warned.detail.startswith(f"slim ({why}), but the slim program "
                                                                            "cannot be built ("), warned
                assert warned.detail.endswith("): every run falls back to entry_path"), warned
    finally:
        _slim.document.cache_clear()


def test_a_tampered_engine_and_a_stale_slim_program_fail(soulrun, agent, monkeypatch):
    from soulrun import _doctor, _engine, _slim
    monkeypatch.setattr(_engine, "verify", lambda: ["changed: AIAP.md"])

    def stale():
        raise soulrun.EngineUnavailable("SLIM_PROGRAM_STALE", "engine_node.aisop.json was built from a different engine program")
    monkeypatch.setattr(_slim, "document", stale)
    checks = _doctor.run(agent_dir=agent)
    assert _statuses(checks)["engine files"] == "FAIL" and _statuses(checks)["slim program"] == "FAIL"
    assert _doctor.exit_code(checks) == 1


def test_an_engine_that_no_longer_takes_soulruns_calls_fails(soulrun, agent, monkeypatch):
    """The interface check reads the bundled engine itself: a parameter or a name SoulRun relies on that the engine
    lacks is a failure the doctor names, before a run reaches that path."""
    from soulrun import _doctor, _engine
    interface = {module: dict(names) for module, names in _engine.INTERFACE.items()}
    interface["lib.engine_core"]["init_run"] = ("agent_dir", "registry_roots", "no_such_parameter")
    interface["lib.reply_io"]["NO_SUCH_CONSTANT"] = None
    interface["no_such_module"] = {"x": ()}
    monkeypatch.setattr(_engine, "INTERFACE", interface)
    checks = _doctor.run(agent_dir=agent)
    detail = next(c.detail for c in checks if c.name == "engine interface")
    assert _statuses(checks)["engine interface"] == "FAIL" and _doctor.exit_code(checks) == 1
    assert "lib.engine_core.init_run: takes no parameter no_such_parameter" in detail
    assert "lib.reply_io.NO_SUCH_CONSTANT: missing" in detail and "no_such_module: cannot be loaded" in detail


@pytest.mark.parametrize(("settings", "status", "said"), [
    ({}, "OK", "none set: the engine keeps 100 runs, asks the human after a restart, and waits up to 6 h"),
    ({"CACHE_NUM": "5", "SOULBOT_RESUME_INTERRUPTED_RUNS": "yes", "SOULBOT_SUPPLY_WAIT_MAX_SECONDS": "600"}, "OK",
     "CACHE_NUM=5: keeps the newest 5 runs; a new run deletes the oldest finished ones beyond that; "
     "SOULBOT_RESUME_INTERRUPTED_RUNS is on: after a restart an unfinished run re-enters by itself; "
     "SOULBOT_SUPPLY_WAIT_MAX_SECONDS=600: the engine waits up to 600 s"),
    ({"CACHE_NUM": "all"}, "WARN", "CACHE_NUM='all' is not a number: the engine keeps 100 runs"),
    ({"SOULBOT_RESUME_INTERRUPTED_RUNS": "ture"}, "WARN", "is not a switch value: the engine treats it as off"),
    ({"SOULBOT_SUPPLY_WAIT_MAX_SECONDS": "30"}, "WARN", "the engine waits up to 21600 s"),
    ({"SOULBOT_HOST_REPORT_WAIT_S": "soon"}, "FAIL", "the engine cannot be loaded with it, so no run starts"),
])
def test_the_engines_own_settings_are_read_as_the_engine_reads_them(soulrun, agent, monkeypatch, settings, status, said):
    """SoulRun reads none of these; the engine does in every run, and falls back without a word on a value it cannot
    use. CACHE_NUM decides how many finished runs are kept, so it deletes runs: the doctor says what each one does."""
    from soulrun import _doctor
    for name, value in settings.items():
        monkeypatch.setenv(name, value)
    check = next(c for c in _doctor.run(agent_dir=agent) if c.name == "engine settings")
    assert check.status == status and said in check.detail, check.detail


def test_the_command_line_doctor(soulrun, agent, capsys, tmp_path):
    from soulrun import cli
    assert cli.main(["--doctor", "--agent-dir", str(agent)]) == 0
    out = capsys.readouterr().out
    assert out.strip().endswith("all checks passed") and "OK   programs:" in out
    empty = make_agent(tmp_path / "second")
    assert cli.main(["--doctor", "--agent-dir", str(empty), "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["ok"] is True and {c["name"] for c in data["checks"]} >= {"engine files", "python for the model", "programs"}
    nothing = tmp_path / "nothing"
    nothing.mkdir()
    assert cli.main(["--doctor", "--agent-dir", str(nothing)]) == 1
    assert capsys.readouterr().out.strip().endswith("1 check(s) failed")


@pytest.mark.parametrize("flag", ["--doctor"])
def test_the_doctor_is_listed_in_the_help(soulrun, capsys, flag):
    from soulrun import cli
    with pytest.raises(SystemExit):
        cli.main(["--help"])
    assert flag in capsys.readouterr().out


def test_a_wrong_run_folder_does_not_hide_the_programs_check(soulrun, tmp_path):
    """Both are said at once: the run folder holds other files, and the agent folder has no program."""
    from soulrun import _doctor
    empty = tmp_path / "empty_agent"
    empty.mkdir()
    taken = tmp_path / "project"
    taken.mkdir()
    (taken / "README.md").write_text("a project", encoding="utf-8")
    statuses = _statuses(_doctor.run(agent_dir=empty, soulrun_cache_dir=taken))
    assert statuses["soulrun_cache_dir"] == "FAIL" and statuses["programs"] == "FAIL" and statuses["agent folder"] == "OK"


# ---- how deep a run's files go (docs/05SoulRun 87, #24) -------------------------------------------------------------
# An AIAP program whose node GenerateStep runs a module: the engine names that module's node
# generate_scaffold.GenerateAgentCard - the node of the deepest file of the Creator's run 7.
SCAFFOLD_MAIN = [
    {"role": "system", "content": {"protocol": "AIAP V1.0.0", "axiom_0": "Human_Sovereignty_and_Wellbeing", "id": "scaffold.main",
                                   "name": "Scaffold", "version": "1.0.0", "summary": "Builds a scaffold",
                                   "flow_format": "mermaid", "loading_mode": "normal", "trust_level": 3}},
    {"role": "user", "content": {"instruction": "ASSERT RUN aisop.main", "user_input": "{user_input}",
                                 "aisop": {"main": "graph TD\n    Start[入口] --> GenerateStep[生成] --> endNode((End))"},
                                 "functions": {"Start": {"step1": "做"}, "GenerateStep": {"step1": "RUN aisop.generate_scaffold"}}}},
]
SCAFFOLD_MODULE = [
    {"role": "system", "content": {"protocol": "AIAP V1.0.0", "id": "scaffold.generate_scaffold", "name": "Generate scaffold",
                                   "version": "1.0.0", "summary": "The module", "flow_format": "mermaid"}},
    {"role": "user", "content": {"instruction": "RUN aisop.main",
                                 "aisop": {"main": "graph TD\n    GenerateAgentCard[卡片] --> endNode((End))"},
                                 "functions": {"GenerateAgentCard": {"step1": "写"}}}},
]


def _scaffold(agent):
    from conftest import write_json
    write_json(agent / "aiap" / "scaffold_aiap" / "main.aisop.json", SCAFFOLD_MAIN)
    write_json(agent / "aiap" / "scaffold_aiap" / "generate_scaffold.aisop.json", SCAFFOLD_MODULE)
    return agent / "aiap" / "scaffold_aiap"


def test_the_deepest_file_follows_the_longest_node_name_of_the_programs(soulrun, agent):
    """The deepest file is a node's public block written again with other content:
    .execution_cache/<run>/_public/plan.<n>.<node>.v<visit>.<sha256>.txt - 146 characters in the Creator's run 7
    (plan.29.sub.generate_scaffold.GenerateAgentCard.v1...), 148 once run numbers have three digits. The doctor works
    it out from the node names, as the engine names them, of the programs it finds."""
    from soulrun import _doctor
    program = _scaffold(agent)
    deepest = _doctor._deepest([program], agent / ".soulrun_cache")
    assert deepest == (148, "a block of node generate_scaffold.GenerateAgentCard (scaffold_aiap)")
    # Programs with short node names: every run also writes the engine's own nodes' blocks, and the longest of them,
    # plan.<n>.Engine.execute-report.v<visit>.<sha256>.txt, is the deepest file - deeper than an accepted reply's receipt
    # (.execution_cache/<run>/_work/_receipts/<sha256>.<operation>.json, 123; 87 #19 moved it out of _work/replies/).
    demo = [agent / "aiap" / "demo_aiap"]
    assert _doctor._deepest(demo, agent / ".soulrun_cache") == (130, "a block of engine node Engine.execute-report")
    root = agent / ".soulrun_cache" / ".execution_cache"
    (root / "1234").mkdir(parents=True)                                       # a four-digit run number goes one deeper
    assert _doctor._deepest([program], agent / ".soulrun_cache")[0] == 149
    assert _doctor._deepest(demo, agent / ".soulrun_cache") == (131, "a block of engine node Engine.execute-report")


def test_the_engines_own_blocks_count_for_a_program_with_short_node_names(soulrun, agent, monkeypatch):
    """A 133-character run folder and a program whose node names are all short: its own blocks and an accepted reply's
    receipt stay within 260, but the engine's execution-report block written again goes to 264 characters."""
    from pathlib import Path

    from soulrun import _doctor, _engine
    blocks = [name for _size, name in _doctor._engine_block_stems()]                    # the names follow the engine
    assert "Engine.execute-report" in blocks and not set(blocks) & set(_engine.load("lib.engine_core").ANSWER_NODES)
    assert set(blocks) < set(_engine.load("lib.program_loader").ENGINE_NODES)           # the answer nodes write none
    assert "ENGINE_NODES" in _engine.INTERFACE["lib.program_loader"] and "ANSWER_NODES" in _engine.INTERFACE["lib.engine_core"]
    monkeypatch.setattr(_doctor, "_windows", lambda: True)
    monkeypatch.setattr(_doctor, "_long_paths_enabled", lambda: False)
    folder = Path("C:/" + "a" * 130)
    assert len(str(folder)) == 133
    check = _doctor._path_check(folder, [agent / "aiap" / "demo_aiap"])
    assert check.status == "WARN" and "about 264 characters" in check.detail, check.detail
    assert "a block of engine node Engine.execute-report" in check.detail and "at most 128 characters" in check.detail


def test_a_folder_that_passed_with_the_old_depth_is_now_warned_about(soulrun, agent, monkeypatch, tmp_path):
    """A run folder of 115 characters: 115 + 1 + 140 passed the old check, but the scaffold program's deepest file
    goes to 264 characters - past Windows' 260."""
    from soulrun import _doctor
    _scaffold(agent)
    monkeypatch.setattr(_doctor, "_windows", lambda: True)
    monkeypatch.setattr(_doctor, "_long_paths_enabled", lambda: False)
    base = str(tmp_path / "d")
    if len(base) > 110:
        pytest.skip(f"the temporary folder is too long for this case ({len(base)} characters)")
    data = base + "x" * (115 - len(base))
    assert len(data) == 115
    check = next(c for c in _doctor.run(agent_dir=agent, soulrun_cache_dir=data) if c.name == "path length")
    assert check.status == "WARN" and "about 264 characters" in check.detail and "at most 110 characters" in check.detail
    assert "generate_scaffold.GenerateAgentCard" in check.detail and "scaffold_aiap" in check.detail


def test_without_a_node_name_to_go_by_the_depth_is_at_least_150(soulrun, agent, monkeypatch):
    from pathlib import Path

    from soulrun import _doctor
    assert _doctor.DEEPEST_IN_CACHE >= 150
    assert _doctor._deepest([], agent / ".soulrun_cache") == (_doctor.DEEPEST_IN_CACHE, None)
    broken = agent / "aiap" / "broken_aiap"
    broken.mkdir(parents=True)
    (broken / "main.aisop.json").write_text("not json", encoding="utf-8")
    assert _doctor._deepest([broken], agent / ".soulrun_cache") == (_doctor.DEEPEST_IN_CACHE, None)
    monkeypatch.setattr(_doctor, "_windows", lambda: True)
    monkeypatch.setattr(_doctor, "_long_paths_enabled", lambda: False)
    check = _doctor._path_check(Path("C:/" + "a" * 150))
    assert check.status == "WARN" and "no node name to go by" in check.detail

"""Where things are: the program in the package, the runs in soulrun_cache_dir, the programs in an agent folder."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from conftest import AIAP_DOC, AISP_DOC, make_agent, write_json
from helpers import HOST, QUESTION, candidates, run_input, runs, take_node


def test_the_program_is_in_the_package_and_only_data_is_written_to_the_agent_folder(soulrun, agent):
    ctx = soulrun(user_message=QUESTION, session_id="p1", **HOST)
    engine_dir = Path(soulrun.engine_info()["engine_dir"]).resolve()
    assert f"engine_dir: {engine_dir}" in ctx.text
    entry = soulrun(user_message=QUESTION, session_id="p1b", slim_program=False, **HOST)
    assert f"entry_path: {engine_dir / 'main.aisop.json'}" in entry.text
    assert agent.resolve() not in engine_dir.parents
    data = agent / ".soulrun_cache"
    # run data, SoulRun's own notes, and the file that keeps the folder out of version control
    assert sorted(p.name for p in data.iterdir()) == [".execution_cache", ".gitignore", ".soulrun"]
    assert not any(p.suffix == ".py" for p in data.rglob("*"))
    assert not (engine_dir / ".execution_cache").exists()
    assert ctx.places["sources"] == {"agent_dir": "default", "aiap_dir": "default", "aisp_dir": "default", "soulrun_cache_dir": "default"}


def test_agent_dir_argument_beats_the_current_folder(soulrun, agent, tmp_path, monkeypatch):
    other = make_agent(tmp_path / "other_agent")
    monkeypatch.chdir(tmp_path)
    ctx = soulrun(user_message=QUESTION, session_id="p2", agent_dir=other, **HOST)
    assert Path(ctx.cache_dir).resolve().is_relative_to(other.resolve())
    assert Path(run_input(ctx)["agent_dir"]).resolve() == other.resolve()
    assert ctx.places["sources"]["agent_dir"] == "argument"


def test_agent_dir_from_the_environment(soulrun, agent, tmp_path, monkeypatch):
    other = make_agent(tmp_path / "env_agent")
    monkeypatch.setenv("SOULRUN_AGENT_DIR", str(other))
    ctx = soulrun(user_message=QUESTION, session_id="p3", **HOST)
    assert Path(ctx.cache_dir).resolve().is_relative_to(other.resolve()) and ctx.places["sources"]["agent_dir"] == "environment"


def test_soulrun_cache_dir_precedence_argument_then_environment_then_default(soulrun, agent, tmp_path, monkeypatch):
    by_env, by_arg = tmp_path / "data_env", tmp_path / "data_arg"
    monkeypatch.setenv("SOULRUN_CACHE_DIR", str(by_env))
    a = soulrun(user_message=QUESTION, session_id="p4", **HOST)
    assert Path(a.cache_dir).resolve().is_relative_to(by_env.resolve()) and a.places["sources"]["soulrun_cache_dir"] == "environment"
    b = soulrun(user_message=QUESTION, session_id="p5", soulrun_cache_dir=by_arg, **HOST)
    assert Path(b.cache_dir).resolve().is_relative_to(by_arg.resolve()) and b.places["sources"]["soulrun_cache_dir"] == "argument"
    assert runs(agent / ".soulrun_cache") == []


def test_runs_elsewhere_still_find_the_agents_programs(soulrun, agent, tmp_path):
    """The engine derives the agent folder from the folder above the runs; SoulRun tells it the real one."""
    ctx = soulrun(user_message=QUESTION, session_id="p6", soulrun_cache_dir=tmp_path / "far" / "data", **HOST)
    assert candidates(ctx) == ["demo_aiap", "demo_aisp", "other_aiap"]
    assert Path(run_input(ctx)["agent_dir"]).resolve() == agent.resolve()
    assert take_node(soulrun, ctx)["node"]["name"] == "Router.match"


def test_a_folder_that_is_set_but_wrong_is_an_error_not_a_silent_fallback(soulrun, agent, tmp_path, monkeypatch):
    with pytest.raises(soulrun.UsageError) as error:
        soulrun(user_message=QUESTION, agent_dir=tmp_path / "missing", **HOST)
    assert error.value.code == "DIR_NOT_FOUND" and error.value.field == "agent_dir"
    with pytest.raises(soulrun.UsageError) as error:
        soulrun(user_message=QUESTION, aiap_dir=tmp_path / "missing", **HOST)
    assert error.value.field == "aiap_dir"
    a_file = tmp_path / "a_file"
    a_file.write_text("x", encoding="utf-8")
    with pytest.raises(soulrun.UsageError) as error:
        soulrun(user_message=QUESTION, soulrun_cache_dir=a_file, **HOST)
    assert error.value.code == "SOULRUN_CACHE_DIR_INVALID"
    monkeypatch.setenv("SOULRUN_AGENT_DIR", str(tmp_path / "missing"))
    with pytest.raises(soulrun.UsageError) as error:
        soulrun(user_message=QUESTION, **HOST)
    assert "environment" in str(error.value)
    assert runs(agent / ".soulrun_cache") == []


def test_a_cache_folder_that_holds_an_engine_program_is_refused(soulrun, agent, tmp_path):
    """A SoulBot agent's own engine folder is another engine's home: SoulRun must not put its runs there
    (nor rotate that engine's oldest runs out)."""
    other_engine = tmp_path / "Soul_Agent" / "soulbot_execute_engine_aiap"
    (other_engine / "python_tools").mkdir(parents=True)
    (other_engine / ".execution_cache" / "7").mkdir(parents=True)
    with pytest.raises(soulrun.UsageError) as error:
        soulrun(user_message=QUESTION, soulrun_cache_dir=other_engine, **HOST)
    assert error.value.code == "SOULRUN_CACHE_DIR_HOLDS_AN_ENGINE" and error.value.field == "soulrun_cache_dir"
    assert sorted(p.name for p in (other_engine / ".execution_cache").iterdir()) == ["7"]


def test_a_named_cache_folder_with_other_files_is_refused(soulrun, agent, tmp_path):
    """A project folder named by mistake: run data - the user's words - would sit among its files, without a
    .gitignore of its own. A new, empty or already-SoulRun folder is fine; so is the old default folder."""
    project = tmp_path / "project"
    project.mkdir()
    (project / "README.md").write_text("mine\n", encoding="utf-8")
    with pytest.raises(soulrun.UsageError) as error:
        soulrun(user_message=QUESTION, soulrun_cache_dir=project, **HOST)
    assert error.value.code == "SOULRUN_CACHE_DIR_NOT_EMPTY" and error.value.field == "soulrun_cache_dir"
    assert sorted(p.name for p in project.iterdir()) == ["README.md"]                      # nothing written
    empty = tmp_path / "empty"
    empty.mkdir()
    assert soulrun(user_message=QUESTION, session_id="p13", soulrun_cache_dir=empty, **HOST).kind == "program"
    again = soulrun(user_message=QUESTION, session_id="p14", soulrun_cache_dir=empty, **HOST)  # now SoulRun's: fine
    assert again.kind == "program" and runs(empty) == [1, 2]
    old = tmp_path / "Soul_Agent" / "soulrun_aiap"                  # the earlier default name, holding earlier runs
    (old / ".execution_cache" / "1").mkdir(parents=True)
    (old / ".gitignore").write_text("*\n", encoding="utf-8")
    assert soulrun(user_message=QUESTION, session_id="p15", soulrun_cache_dir=old, **HOST).kind == "program"


def test_where_the_runs_go(soulrun, agent, tmp_path, monkeypatch):
    """Not named: <agent folder>/.soulrun_cache, the agent folder being the current folder unless one is named.
    Named: that folder itself, the way pip, pytest and ruff take their cache-dir."""
    monkeypatch.chdir(agent)
    ctx = soulrun(user_message=QUESTION, session_id="w1", **HOST)
    assert Path(ctx.places["soulrun_cache_dir"]) == agent.resolve() / ".soulrun_cache"
    assert Path(ctx.cache_dir).parent == agent.resolve() / ".soulrun_cache" / ".execution_cache"
    given = tmp_path / "keep_runs_here"
    ctx = soulrun(user_message=QUESTION, session_id="w2", soulrun_cache_dir=given, **HOST)
    assert Path(ctx.places["soulrun_cache_dir"]) == given.resolve()
    assert Path(ctx.cache_dir).parent == given.resolve() / ".execution_cache"
    other = make_agent(tmp_path / "named_agent")                                         # a named agent folder keeps
    ctx = soulrun(user_message=QUESTION, session_id="w4", agent_dir=other, **HOST)       # its runs beside its programs
    assert Path(ctx.places["soulrun_cache_dir"]) == other.resolve() / ".soulrun_cache"


def test_a_cache_folder_soulrun_creates_keeps_itself_out_of_version_control(soulrun, agent, tmp_path):
    """Run data holds the user's own words and by default sits inside a project folder."""
    soulrun(user_message=QUESTION, session_id="p11", **HOST)
    ignore = agent / ".soulrun_cache" / ".gitignore"
    lines = ignore.read_text(encoding="utf-8").splitlines()
    assert lines[-1] == "*" and all(line.startswith("#") for line in lines[:-1])
    assert b"\r" not in ignore.read_bytes()
    ignore.write_text("mine\n", encoding="utf-8")                           # the owner's edit is kept
    soulrun(user_message="继续", session_id="p11", **HOST)
    assert ignore.read_text(encoding="utf-8") == "mine\n"
    new = tmp_path / "new_cache"                                             # a named folder SoulRun makes: ignored too
    soulrun(user_message=QUESTION, session_id="p12", soulrun_cache_dir=new, **HOST)
    assert (new / ".gitignore").read_text(encoding="utf-8").splitlines()[-1] == "*"
    existing = tmp_path / "already_there"                    # an empty folder made by hand: taken, and ignored too
    existing.mkdir()
    ctx = soulrun(user_message=QUESTION, session_id="p13", soulrun_cache_dir=existing, **HOST)
    assert ctx.kind == "program" and (existing / ".gitignore").read_text(encoding="utf-8").splitlines()[-1] == "*"
    (existing / ".gitignore").unlink()                       # once SoulRun keeps runs there, the owner decides
    soulrun(user_message="继续", session_id="p13", soulrun_cache_dir=existing, **HOST)
    assert not (existing / ".gitignore").exists()


def test_a_run_folder_left_without_its_gitignore_by_a_first_call_that_was_cut_off_gets_one(soulrun, agent):
    """The first call made the folder and stopped before writing the .gitignore (killed, power cut): the next one,
    still taking the folder for the first time, writes it."""
    (agent / ".soulrun_cache").mkdir()
    soulrun(user_message=QUESTION, session_id="p14", **HOST)
    assert (agent / ".soulrun_cache" / ".gitignore").is_file()


def test_a_question_before_any_run_writes_nothing_into_an_existing_folder(soulrun, agent, tmp_path):
    existing = tmp_path / "kept_empty"
    existing.mkdir()
    ctx = soulrun(user_message=QUESTION, session_id="p15", soulrun_cache_dir=existing, aiap="no_such_program", **HOST)
    assert ctx.doubt and not (existing / ".gitignore").exists()


# The ways the first call in an existing folder can end once SoulRun has taken its prepare lock there (which makes
# .soulrun), before any run is prepared: (runs brought over first?, the call's arguments). The name is the code of the
# question - or of the error, for a machine turn.
ENDINGS_UNDER_THE_LOCK = {
    "NAMED_RUN_MISMATCH": (False, dict(user_message=QUESTION, cache_dir="7")),
    "DESIGNATED_RUN_UNFINISHED": (True, dict(user_message=QUESTION, aiap="other_aiap")),
    "ENGINE_BUILD_MISMATCH": (True, dict(user_message="另外一件事")),
    "ENGINE_BUILD_MISMATCH error": (True, dict(user_message="另外一件事", human_turn=False)),
    "ENGINE_BUILD_RUN_ENDED": (True, dict(user_message="取消")),
}


def _first_call_under_the_lock(soulrun, folder: Path, ending: str, *, owners_ignore: str | None = None):
    """The first call SoulRun gets for ``folder``, an existing folder it has not taken yet: empty, or holding only an
    engine's runs - an unfinished one of this conversation, begun with no SoulRun note - as when runs are brought
    over from another host. (code, text) of what it ended in; text is None for an error."""
    import shutil
    brought_over, arguments = ENDINGS_UNDER_THE_LOCK[ending]
    folder.mkdir()
    if brought_over:
        soulrun(user_message=QUESTION, session_id="first", soulrun_cache_dir=folder, **HOST)
        shutil.rmtree(folder / ".soulrun")
        (folder / ".gitignore").unlink()
    assert sorted(p.name for p in folder.iterdir()) == ([".execution_cache"] if brought_over else [])
    if owners_ignore is not None:
        (folder / ".gitignore").write_text(owners_ignore, encoding="utf-8")
    arguments = dict(arguments)
    if "cache_dir" in arguments:
        arguments["cache_dir"] = folder / ".execution_cache" / arguments["cache_dir"]
    try:
        ctx = soulrun(session_id="first", soulrun_cache_dir=folder, **arguments, **HOST)
    except soulrun.UsageError as error:
        return error.code, None
    return ctx.doubt["code"], ctx.text


@pytest.mark.parametrize("ending", sorted(ENDINGS_UNDER_THE_LOCK))
def test_a_folder_taken_for_the_first_time_keeps_out_of_version_control_however_the_first_call_ends(soulrun, agent,
                                                                                                    tmp_path, ending):
    """A question asked under the prepare lock, or a machine turn refused there, used to end the first call after the
    lock had made .soulrun and before the .gitignore was written - and from then on the folder counted as taken, so it
    never got one (problem 87). The question itself is the same with or without the .gitignore, and an owner's own
    .gitignore stays as it is."""
    from soulrun import _select
    taken = tmp_path / "taken"
    code, text = _first_call_under_the_lock(soulrun, taken, ending)
    assert code == ending.split()[0]
    assert (taken / ".soulrun" / "prepare.lock").is_file()                       # SoulRun has taken the folder ...
    assert (taken / ".gitignore").read_text(encoding="utf-8") == _select.IGNORE_TEXT     # ... and it ignores itself
    owned = tmp_path / "owned"
    assert _first_call_under_the_lock(soulrun, owned, ending, owners_ignore="mine\n") == (code, text)
    assert (owned / ".gitignore").read_text(encoding="utf-8") == "mine\n"
    later = soulrun(user_message=QUESTION, session_id="later", soulrun_cache_dir=taken, **HOST)
    assert later.kind == "program" and (taken / ".gitignore").read_text(encoding="utf-8") == _select.IGNORE_TEXT


@pytest.mark.parametrize("name, code", [("README.md", "SOULRUN_CACHE_DIR_NOT_EMPTY"),
                                        ("main.aisop.json", "SOULRUN_CACHE_DIR_HOLDS_AN_ENGINE")])
def test_a_folder_soulrun_must_refuse_gets_nothing_written_into_it(soulrun, agent, tmp_path, name, code):
    folder = tmp_path / "refused"
    folder.mkdir()
    (folder / name).write_text("mine\n", encoding="utf-8")
    with pytest.raises(soulrun.UsageError) as error:
        soulrun(user_message=QUESTION, session_id="r1", soulrun_cache_dir=folder,
                cache_dir=folder / ".execution_cache" / "7", **HOST)
    assert error.value.code == code and sorted(p.name for p in folder.iterdir()) == [name]


@pytest.mark.skipif(os.name == "nt", reason="POSIX permissions")
def test_a_run_folder_soulrun_makes_is_its_owners_only(soulrun, agent):
    soulrun(user_message=QUESTION, session_id="p16", **HOST)
    assert (agent / ".soulrun_cache").stat().st_mode & 0o077 == 0


def test_folders_with_chinese_and_spaces(soulrun, tmp_path, subprocess_env):
    """Chinese users' folders often carry Chinese and spaces: the call, the engine's own steps and the command line."""
    import json
    import subprocess
    import sys

    from helpers import commit, route_payload
    agent = make_agent(tmp_path / "我的 代理 目录" / "易经 助手")
    ctx = soulrun(user_message=QUESTION, session_id="zh-1", agent_dir=agent, **HOST)
    assert Path(ctx.cache_dir).is_relative_to(agent / ".soulrun_cache") and candidates(ctx) == ["demo_aiap", "demo_aisp", "other_aiap"]
    reply = commit(soulrun, ctx, route_payload(take_node(soulrun, ctx), "demo_aiap"))
    assert reply["status"] == "COMMITTED", reply
    elsewhere = tmp_path / "运行 记录"
    done = subprocess.run([sys.executable, "-B", "-X", "utf8", "-m", "soulrun", "--user-message-stdin", "--session-id", "zh-2",
                           "--agent-dir", str(agent), "--soulrun-cache-dir", str(elsewhere), "--json", "--host-tool", "agent=false"],
                          input=QUESTION.encode("utf-8"), capture_output=True, env=subprocess_env, timeout=120)
    assert done.returncode == 0, done.stderr.decode("utf-8", "replace")
    data = json.loads(done.stdout.decode("utf-8"))
    assert Path(data["cache_dir"]).parent == elsewhere.resolve() / ".execution_cache" and data["entry_mode"] == "fresh"


def test_an_agent_folder_without_any_program_is_reported_before_anything_is_created(soulrun, tmp_path, monkeypatch):
    """Not the engine's PROGRAM_INVALID (which names options SoulRun has not got) and no half-made run: SoulRun looks
    first, through the whole folder (a registry may list programs deeper than one level)."""
    empty = tmp_path / "empty_agent"
    (empty / "aiap" / "group" / "deep_aiap").mkdir(parents=True)
    monkeypatch.chdir(empty)
    for _ in range(2):
        with pytest.raises(soulrun.UsageError) as error:
            soulrun(user_message=QUESTION, **HOST)
        assert error.value.code == "NO_PROGRAM_FOLDER" and error.value.field == "agent_dir"
    assert not (empty / ".soulrun_cache").exists()
    (empty / "aiap" / "group" / "deep_aiap" / "main.aisop.json").write_text("{}", encoding="utf-8")
    from soulrun import _api, _select
    _api._require_programs(_select.resolve_places(create=False))         # now a program two levels down counts


def test_each_run_records_which_folders_it_used(soulrun, agent):
    ctx = soulrun(user_message=QUESTION, session_id="p7", **HOST)
    assert Path(ctx.places["agent_dir"]).resolve() == agent.resolve()
    assert Path(ctx.places["soulrun_cache_dir"]).resolve() == (agent / ".soulrun_cache").resolve()


def test_the_record_is_kept_on_disk_beside_the_run_data_not_inside_the_run(soulrun, agent, tmp_path, monkeypatch):
    import json
    monkeypatch.setenv("SOULRUN_CACHE_DIR", str(tmp_path / "data_env"))
    ctx = soulrun(user_message=QUESTION, session_id="p8", aiap="demo_aiap", **HOST)
    record_path = tmp_path / "data_env" / ".soulrun" / "runs" / "1.json"
    record = json.loads(record_path.read_text(encoding="utf-8"))
    assert record["soulrun_version"] == soulrun.__version__ and record["engine_version"] == soulrun.ENGINE_VERSION
    assert record["session_id"] == "p8" and record["cache_name"] == "1" and record["candidates"] == "designated"
    assert record["given_by"] == {"agent_dir": "default", "aiap_dir": "default", "aisp_dir": "default", "soulrun_cache_dir": "environment"}
    assert record["designated"][0].replace("\\", "/").endswith("agent/aiap/demo_aiap")
    assert not any(".soulrun" in p.parts for p in Path(ctx.cache_dir).rglob("*"))
    soulrun(user_message="继续", session_id="p8", **HOST)                    # a continued run does not rewrite its record
    assert json.loads(record_path.read_text(encoding="utf-8")) == record


def test_notes_of_runs_the_engine_has_removed_are_dropped(soulrun, agent):
    import shutil

    from soulrun import _records
    first = soulrun(user_message=QUESTION, session_id="p9", **HOST)
    data = agent / ".soulrun_cache"
    notes = (data / ".soulrun" / "runs" / "1.json", _records.delivered_path(first.cache_dir),   # a slim turn has all three
             data / ".soulrun" / "turns" / "1.json")                     # docs/05SoulRun 87 (#25): which turn it was
    assert all(note.is_file() for note in notes)
    shutil.rmtree(first.cache_dir)                                           # what the engine does to its oldest finished runs
    assert _records.prune(data) == 3 and not any(note.exists() for note in notes)


def _link_folder(link: Path, target: Path) -> None:
    """A folder link, as a user makes one to keep runs on another disk: a junction on Windows, else a symbolic link."""
    if os.name == "nt":
        import _winapi
        _winapi.CreateJunction(str(target), str(link))
    else:
        os.symlink(target, link, target_is_directory=True)


def test_a_run_folder_that_is_a_link_still_takes_the_agent_folders_programs(soulrun, agent, tmp_path):
    """The engine takes the agent folder to be the parent of the run folder's real location. A default run folder
    linked to another disk would make it look for programs beside the link's target: SoulRun names the agent folder."""
    elsewhere = tmp_path / "elsewhere"
    write_json(elsewhere / "aiap" / "stranger_aiap" / "main.aisop.json", AIAP_DOC)
    (elsewhere / "runs_store").mkdir()
    _link_folder(agent / ".soulrun_cache", elsewhere / "runs_store")
    ctx = soulrun(user_message=QUESTION, session_id="linked", **HOST)
    assert ctx.kind == "program" and candidates(ctx) == ["demo_aiap", "demo_aisp", "other_aiap"]
    assert Path(ctx.cache_dir).resolve().is_relative_to((elsewhere / "runs_store").resolve())   # the runs went there


def test_one_folder_given_for_both_kinds_is_scanned_once(soulrun, agent, tmp_path):
    both = tmp_path / "programs"
    write_json(both / "demo_aiap" / "main.aisop.json", AIAP_DOC)
    write_json(both / "demo_aisp" / "aisp.aisop.json", AISP_DOC)
    ctx = soulrun(user_message=QUESTION, session_id="both", aiap_dir=both, aisp_dir=both, **HOST)
    assert candidates(ctx) == ["demo_aiap", "demo_aisp"]                      # each once, not twice


def _registered(agent: Path) -> None:
    """aiap/ with its registry script, which enables demo_aiap only: other_aiap sits there but is not a candidate."""
    (agent / "aiap" / "aiap_list.py").write_text("import sys\nsys.exit(0)\n", encoding="utf-8")   # --check: the list is current
    write_json(agent / "aiap" / "aiap_list.json", {"aiap_list_version": "1.0", "packages": [{"id": "demo_aiap", "path": "aiap/demo_aiap/main.aisop.json"}]})


def test_a_program_folder_with_its_registry_script_gives_the_same_candidates_however_it_is_named(soulrun, agent, tmp_path):
    _registered(agent)
    default = soulrun(user_message=QUESTION, session_id="reg1", **HOST)
    assert candidates(default) == ["demo_aiap", "demo_aisp"]                       # the script left other_aiap out
    named = soulrun(user_message=QUESTION, session_id="reg2", aiap_dir=agent / "aiap", aisp_dir=agent / "aisp", **HOST)
    assert candidates(named) == ["demo_aiap", "demo_aisp"]
    other = tmp_path / "other_agent"
    other.mkdir()
    with pytest.raises(soulrun.UsageError) as error:                               # alone, it would be scanned instead
        soulrun(user_message=QUESTION, session_id="reg3", agent_dir=other, aiap_dir=agent / "aiap", **HOST)
    assert error.value.code == "REGISTRY_FOLDER_ALONE" and f"agent_dir={agent}" in error.value.message
    assert list(other.iterdir()) == []                                             # refused before anything is made
    chosen = soulrun(user_message=QUESTION, session_id="reg4", agent_dir=other, aiap=str(agent / "aiap" / "other_aiap"), **HOST)
    assert candidates(chosen) == ["other_aiap"]                                    # naming one program is the person's choice


def test_the_doctor_names_the_registry_scripts_a_run_will_execute(soulrun, agent, tmp_path):
    from soulrun import _doctor
    _registered(agent)
    check = next(c for c in _doctor.run(agent_dir=agent) if c.name == "registry scripts")
    assert check.status == "WARN" and "aiap_list.py" in check.detail and "at every run" in check.detail
    other = tmp_path / "other_agent"
    other.mkdir()
    check = next(c for c in _doctor.run(agent_dir=other, aiap_dir=agent / "aiap") if c.name == "registry scripts")
    assert check.status == "FAIL" and "registry script aiap_list.py" in check.detail

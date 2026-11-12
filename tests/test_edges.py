"""The less travelled paths: a tampered engine, a turn that must stay text-only, a named run that is not the latest,
engine-command arguments, errors as data, the slim program's guard, and the command line's failures."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from helpers import HOST, QUESTION


# ---- the bundled engine is checked file by file ----------------------------------------------------------------

@pytest.fixture
def engine_copy(tmp_path, monkeypatch):
    """A copy of the installed part of the engine, standing in for the bundled one."""
    from soulrun import _engine
    copy = tmp_path / "soulrun_aiap"
    shutil.copytree(_engine.ENGINE_DIR, copy, ignore=shutil.ignore_patterns("tests", "RELEASE*", "pytest.ini", "__pycache__",
                                                                             ".pytest_cache", ".execution_cache"))
    monkeypatch.setattr(_engine, "ENGINE_DIR", copy)
    return copy


def test_an_untouched_engine_passes_the_check(engine_copy):
    from soulrun import _engine
    assert _engine.verify() == []


def test_a_changed_a_missing_and_an_extra_engine_file_are_each_reported(engine_copy):
    from soulrun import _engine
    (engine_copy / "AIAP.md").write_bytes((engine_copy / "AIAP.md").read_bytes() + b"\n")
    (engine_copy / "python_tools" / "gate_answer.py").unlink()
    (engine_copy / "python_tools" / "lib" / "added_later.py").write_text("x = 1\n", encoding="utf-8")
    assert sorted(_engine.verify()) == ["changed: AIAP.md", "missing: python_tools/gate_answer.py",
                                        "not in manifest: python_tools/lib/added_later.py"]


def test_without_a_manifest_the_engine_cannot_be_verified(engine_copy, monkeypatch):
    from soulrun import _engine
    monkeypatch.setattr(_engine, "manifest", lambda: {})                   # what manifest() gives when the file is absent
    problems = _engine.verify()
    assert problems == ["no manifest: the bundled engine cannot be verified"]


# ---- a turn the engine says must stay text-only ----------------------------------------------------------------

def _prepare():
    from soulrun import host
    return host.engine("prepare_cache")


def _fake_prepare(monkeypatch, soulrun, **data):
    prepare = _prepare()
    base = {"turn_id": "t-1", "cache_dir": "runs/9", "cache_name": "9", "trace_id": "tr-9", "session_id": "x",
            "entry_mode": "stopped", "user_language": "zh", "public_block_ref": "⟦engine:9/menu.q001.txt⟧",
            "question_id": "q001", "stop_id": "s-1"}
    monkeypatch.setattr(prepare, "prepare_execution_context", lambda *a, **k: {**base, **data})


def test_a_text_only_turn_never_carries_a_program_whatever_form_was_asked(soulrun, agent, monkeypatch):
    _fake_prepare(monkeypatch, soulrun, stop_question=True, question_source=None)
    for form in ({}, {"slim_program": True}, {"inline_program": True}):
        ctx = soulrun(user_message="先停", session_id="x", **form, **HOST)
        assert ctx.kind == "text_only" and ctx.program is None and ctx.program_form is None
        heads = [block.split("\n", 1)[0] for block in ctx.blocks]
        assert heads[0] == "[EXECUTION CONTEXT]" and heads[-1] == "[TURN EXECUTION ASSERTION]"
        assert "ENGINE_TOOLS=FORBIDDEN" in ctx.blocks[-1] and "[EXECUTE ENGINE ENTRY]" not in ctx.text
        assert "program_form" not in ctx.as_dict()


def test_a_run_the_engine_could_not_create_is_an_error_not_an_empty_answer(soulrun, agent, monkeypatch):
    prepare = _prepare()
    monkeypatch.setattr(prepare, "prepare_execution_context", lambda *a, **k: None)
    with pytest.raises(soulrun.SoulRunError) as error:
        soulrun(user_message=QUESTION, session_id="x", **HOST)
    assert error.value.code == "ENGINE_NO_ANSWER"


# ---- a named run that is not the conversation's latest -----------------------------------------------------------

def test_naming_an_older_run_of_the_conversation_is_asked_about(soulrun, agent, monkeypatch, tmp_path):
    ctx = soulrun(user_message=QUESTION, session_id="n1", **HOST)
    prepare = _prepare()
    later = Path(ctx.cache_dir).parent / "99"
    monkeypatch.setattr(prepare, "latest_cache_for_session", lambda root, session: later)
    doubt = soulrun(user_message="继续", session_id="n1", cache_dir=ctx.cache_dir, **HOST)
    assert doubt.kind == "text_only" and doubt.doubt["code"] == "NAMED_RUN_MISMATCH"
    assert "latest run of this conversation" in " ".join(doubt.doubt["problems"])


# ---- engine commands -----------------------------------------------------------------------------------------------

def test_engine_command_lines_and_results(soulrun):
    from soulrun import _cmd
    line = _cmd.argv("next-node", cache_dir="runs/1", agent_ticket="T", json=True, no_deref=False, offset=None,
                     input_field=["a", "b"], args=["--extra"])
    assert line[1:4] == ["-B", "-X", "utf8"] and line[4].endswith("next_node.py")
    assert line[5:] == ["--cache-dir", "runs/1", "--agent-ticket", "T", "--json", "--input-field", "a", "--input-field", "b",
                        "--extra"]                                          # False and None options are left out
    result = _cmd.CmdResult("next-node", 0, '{"a": 1}', "")
    assert result.ok and str(result) == '{"a": 1}' and result.json() == {"a": 1}
    assert not _cmd.CmdResult("node-commit", 3, "", "bad").ok
    with pytest.raises(soulrun.UsageError) as error:
        _cmd.run("node-commit", cache_dir="runs/1", payload={"x": 1}, stdin="{}")
    assert error.value.code == "PAYLOAD_AND_STDIN"
    with pytest.raises(soulrun.UsageError) as error:
        _cmd.argv("no-such-command")
    assert error.value.code == "UNKNOWN_CMD"


# ---- errors as data, the slim program's guard, small helpers ---------------------------------------------------

def test_errors_carry_a_stable_code_the_field_and_what_was_expected(soulrun):
    error = soulrun.UsageError("SOULRUN_CACHE_DIR_INVALID", "not a folder", field="soulrun_cache_dir", expected="a folder")
    assert error.as_dict() == {"code": "SOULRUN_CACHE_DIR_INVALID", "message": "not a folder", "field": "soulrun_cache_dir", "expected": "a folder"}
    assert soulrun.SoulRunError("X", "plain").as_dict() == {"code": "X", "message": "plain"}


def test_the_slim_program_refuses_engine_params_it_does_not_know(soulrun, monkeypatch):
    from soulrun import _slim
    doc = json.loads(_slim.FILE.read_text(encoding="utf-8"))
    doc[0]["content"]["params"]["ticket"] = "a new parameter of a later engine"
    monkeypatch.setattr(_slim, "document", lambda: doc)
    with pytest.raises(soulrun.EngineUnavailable) as error:
        _slim.entry_program("x", cache_dir="C", entry_mode="recovery")     # params comes with a turn that re-enters
    assert error.value.code == "SLIM_PROGRAM_PARAMS"


def test_small_helpers(tmp_path):
    from soulrun import _select
    assert _select.programs_in(tmp_path / "missing") == []
    item = _select.Designated(protocol="aisp", given="demo", directory=tmp_path / "demo", found=False)
    assert item.entry == tmp_path / "demo" / "aisp.aisop.json"


# ---- the command line, in this process ---------------------------------------------------------------------------

def _cli(capsys, *args):
    from soulrun import cli
    code = cli.main(list(args))
    out = capsys.readouterr()
    return code, out.out, out.err


def test_command_line_information_commands(soulrun, capsys):
    code, out, _ = _cli(capsys, "--version")
    assert code == 0 and out.strip() == f"soulrun {soulrun.__version__} (engine {soulrun.ENGINE_VERSION})"
    code, out, _ = _cli(capsys, "--engine-info")
    assert code == 0 and json.loads(out)["engine_version"] == soulrun.ENGINE_VERSION
    code, out, _ = _cli(capsys, "--verify-engine")
    assert code == 0 and out.strip().endswith("unchanged")
    code, out, _ = _cli(capsys)
    assert code == 0 and out.startswith(f"SoulRun {soulrun.__version__}")


def test_command_line_failures_have_codes_and_exit_statuses(soulrun, capsys):
    code, _, err = _cli(capsys, "--cmd")
    assert code == 2 and "--cmd needs a name" in err
    code, _, err = _cli(capsys, "--cmd", "next-node", "--user-message-stdin", "--json")
    assert code == 2 and json.loads(err)["error"]["code"] == "MESSAGE_AND_CMD"
    code, _, err = _cli(capsys, "--cmd", "no-such-command", "--json")
    assert code == 2 and json.loads(err)["error"]["code"] == "UNKNOWN_CMD"


def test_command_line_turn_and_the_print_cap(soulrun, agent, capsys, monkeypatch, tmp_path):
    from soulrun import _render
    message = tmp_path / "message.txt"
    message.write_text(QUESTION, encoding="utf-8")
    code, out, _ = _cli(capsys, "--user-message-file", str(message), "--session-id", "c1", "--json",
                        "--model", HOST["model"], "--host-tool", "agent=false")
    data = json.loads(out)
    from soulrun import _blocks
    assert code == 0 and data["kind"] == "program" and data["program_form"] == "slim"      # the default form
    assert data["system_prompt"] == _blocks.SLIM_SYSTEM_PROMPT and "slim_fallback" not in data
    assert Path(data["full_text_file"]).read_text(encoding="utf-8") == data["text"]
    monkeypatch.setattr(_render, "print_cap", lambda: 500)                 # pretend the cap is tiny
    full = soulrun(user_message=QUESTION, session_id="c2", inline_program=True, **HOST)
    printed, saved = _render.for_shell(full)                              # the full form: a marker names the file
    marker = json.loads(printed.split("\n\n")[-1])
    assert marker["program"]["omitted"] is True and marker["program"]["read"] == str(saved)
    assert full.program not in printed and saved.read_text(encoding="utf-8") == full.text
    slim = soulrun(user_message=QUESTION, session_id="c3", slim_program=True, **HOST)
    printed, saved = _render.for_shell(slim)                              # the slim form: printed in the entry-path form
    assert slim.program not in printed and "already loaded" not in printed and "[LOADED AISOP" not in printed
    assert "entry_path: " in printed and printed.startswith("[EXECUTION CONTEXT]") and _render.form_shown(slim, printed) == "entry_path"
    assert saved.read_text(encoding="utf-8") == slim.text
    from soulrun import host                                              # a slim turn with a note: the note stays
    host.stop(slim.cache_dir, "host-run-1")
    judged = soulrun(user_message="等一下", session_id="c3", **HOST)
    assert judged.program_form == "slim" and judged.blocks[1].startswith("[RUN STOPPED - JUDGE]")
    printed, _saved = _render.for_shell(judged)
    assert "[RUN STOPPED - JUDGE]" in printed and "entry_path: " in printed and judged.program not in printed
    assert printed.split("\n\n")[1].startswith("[RUN STOPPED - JUDGE]") and _render.form_shown(judged, printed) == "entry_path"
    # the command line says so, and hands over the opening instruction of the form it printed (SoulBot's)
    message.write_text(QUESTION, encoding="utf-8")                       # the first call moved the file into its run
    code, out, _ = _cli(capsys, "--user-message-file", str(message), "--session-id", "c4", "--json",
                        "--model", HOST["model"], "--host-tool", "agent=false")
    data = json.loads(out)
    assert code == 0 and data["program_form"] == "entry_path" and data["slim_fallback"] == "TOO_LONG_FOR_COMMAND_LINE"
    assert data["system_prompt"] == _blocks.system_prompt("entry_path") != _blocks.SLIM_SYSTEM_PROMPT

"""The one call: the guide, the argument rules, the callable package."""
from __future__ import annotations

import types

import pytest

from helpers import HOST, QUESTION, runs


def test_the_package_itself_is_callable_and_still_an_ordinary_module(soulrun):
    assert isinstance(soulrun, types.ModuleType)
    assert callable(soulrun)
    assert soulrun.run is not None and soulrun.__version__


def test_no_message_and_no_cmd_gives_the_guide_and_creates_nothing(soulrun, agent):
    ctx = soulrun()
    assert ctx.kind == "guide" and ctx.cache_dir is None
    assert soulrun.__version__ in ctx.text and soulrun.ENGINE_VERSION in ctx.text
    for name in soulrun.COMMANDS:
        assert name in ctx.text
    assert not (agent / ".soulrun_cache").exists()
    assert str(ctx) == ctx.text == soulrun.guide()


@pytest.mark.parametrize("blank", ["", "   ", " \n\t "])
def test_a_blank_message_also_gives_the_guide(soulrun, agent, blank):
    assert soulrun(user_message=blank).kind == "guide"
    assert not (agent / ".soulrun_cache").exists()


def test_message_and_cmd_together_is_an_error(soulrun, agent):
    with pytest.raises(soulrun.UsageError) as error:
        soulrun(user_message="你好", cmd="next-node")
    assert error.value.code == "MESSAGE_AND_CMD" and isinstance(error.value, ValueError)


def test_an_unknown_cmd_is_an_error_that_lists_the_known_ones(soulrun):
    with pytest.raises(soulrun.UsageError) as error:
        soulrun(cmd="no-such")
    assert error.value.code == "UNKNOWN_CMD" and error.value.expected == sorted(soulrun.COMMANDS)


def test_an_unknown_argument_is_an_error_not_silently_ignored(soulrun, agent):
    with pytest.raises(soulrun.UsageError) as error:
        soulrun(user_message=QUESTION, sesion_id="typo")
    assert error.value.code == "UNKNOWN_ARGUMENT" and error.value.field == "sesion_id"
    assert runs(agent / ".soulrun_cache") == []


def test_a_heartbeat_turn_is_refused(soulrun, agent):
    with pytest.raises(soulrun.UsageError) as error:
        soulrun(user_message="tick", channel="heartbeat")
    assert error.value.code == "HEARTBEAT_NOT_ENGINE"


def test_a_message_starts_a_run_and_hands_back_a_program_turn(soulrun, agent):
    ctx = soulrun(user_message=QUESTION, session_id="s1", **HOST)
    assert ctx.kind == "program" and ctx.entry_mode == "fresh" and ctx.turn_id == "1" and ctx.session_id == "s1"
    assert ctx.cache_dir.replace("\\", "/").endswith("agent/.soulrun_cache/.execution_cache/1")
    assert ctx.text == "\n\n".join(ctx.blocks)
    assert ctx.as_dict()["kind"] == "program" and ctx.doubt is None
    assert ctx.program_form == "slim" and ctx.program is not None and ctx.slim_fallback is None   # the slim form by default
    assert ctx.data["requested_model"] == HOST["model"]


def test_every_cmd_name_starts_a_real_engine_tool(soulrun):
    """Each name maps to an engine tool that exists and answers --help."""
    for name in soulrun.COMMANDS:
        result = soulrun(cmd=name, args=["--help"])
        assert result.returncode == 0 and "usage:" in result.stdout.lower(), (name, result.stderr)
        assert result.cmd == name


def test_the_kinds_and_commands_are_the_documented_ones(soulrun):
    assert soulrun.KINDS == ("guide", "program", "text_only")
    assert list(soulrun.COMMANDS) == ["next-node", "node-commit", "stop-decision", "gate-answer"]
    assert soulrun.DEFAULT_SESSION == "default"


# ---- engine commands: their failures are SoulRun errors, and a human's answer stays off the command line ------

def test_a_command_that_prints_no_json_or_does_not_finish_is_a_soulrun_error(soulrun, agent, tmp_path):
    refused = soulrun(cmd="node-commit", cache_dir=tmp_path / "nowhere", payload={"a": 1})
    assert refused.returncode != 0 and refused.stdout.strip() == ""
    with pytest.raises(soulrun.SoulRunError) as error:
        refused.json()
    assert error.value.code == "CMD_OUTPUT_NOT_JSON" and f"exit code {refused.returncode}" in error.value.message
    ctx = soulrun(user_message=QUESTION, session_id="cmd-timeout", **HOST)
    with pytest.raises(soulrun.SoulRunError) as error:
        soulrun(cmd="next-node", cache_dir=ctx.cache_dir, timeout=0.001)
    assert error.value.code == "CMD_TIMEOUT" and error.value.field == "timeout"


def test_a_humans_answer_to_a_gate_never_goes_on_the_command_line(soulrun, agent, monkeypatch):
    """SECURITY: the human's words reach the engine through a file or standard input, never the process list."""
    from soulrun import _cmd
    from helpers import commit, gate_payload, take_node
    ctx = soulrun(user_message=QUESTION, session_id="answer", aiap="demo_aiap", aisp="demo_aisp", **HOST)
    reply = commit(soulrun, ctx, gate_payload(take_node(soulrun, ctx), ["demo_aiap", "demo_aisp"], "demo_aiap"))
    seen, real = {}, _cmd.subprocess.run

    def watch(line, **kwargs):
        seen["line"] = list(line)
        handed = line[line.index("--answer-file") + 1]
        seen["file"], seen["text"] = handed, open(handed, encoding="utf-8").read()
        return real(line, **kwargs)
    monkeypatch.setattr(_cmd.subprocess, "run", watch)
    soulrun(cmd="gate-answer", cache_dir=ctx.cache_dir, question_id=reply["gate"]["question_id"], answer="1 - 我的私人回答")
    assert "--answer" not in seen["line"] and not [part for part in seen["line"] if "私人回答" in part]
    assert seen["text"] == "1 - 我的私人回答"
    import os
    assert not os.path.exists(seen["file"])                                # removed once the command was done

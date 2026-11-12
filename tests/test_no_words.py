"""No user words.

- nothing named, or only big folders named        -> the guide; nothing is created
- one program named (aiap= or aisp=)              -> that program is run; a program that needs words asks the
                                                     human for them (the engine's HSAW law), SoulRun never invents any
- both an AIAP program and an AISP skill named     -> the human is asked which one, before any run exists
"""
from __future__ import annotations

import json
import subprocess
import sys

import pytest

from helpers import HOST, QUESTION, candidates, run_input, runs, take_node


@pytest.mark.parametrize("nothing", [None, "", "   ", "﻿"])
def test_no_words_and_no_program_named_gives_the_guide(soulrun, agent, nothing):
    assert soulrun(user_message=nothing).kind == "guide"
    assert soulrun(user_message=nothing, aiap_dir=agent / "aiap", aisp_dir=agent / "aisp").kind == "guide"
    assert not (agent / ".soulrun_cache").exists()


@pytest.mark.parametrize("protocol, name", [("aiap", "demo_aiap"), ("aisp", "demo_aisp")])
def test_no_words_and_one_program_named_runs_that_program(soulrun, agent, protocol, name):
    ctx = soulrun(session_id=f"nw-{protocol}", **{protocol: name}, **HOST)
    assert ctx.kind == "program" and ctx.entry_mode == "fresh" and ctx.program_form == "slim"
    assert candidates(ctx) == [name]                                         # the named program and nothing else
    assert run_input(ctx)["user_message"] == ""                              # no words were made up for the user
    assert take_node(soulrun, ctx)["node"]["name"] == "Router.match"         # the engine takes it from here
    assert "[EXECUTE ENGINE ENTRY]" in ctx.text


def test_blank_words_count_as_no_words(soulrun, agent):
    ctx = soulrun(user_message=" \n\t ", session_id="nw-blank", aiap="demo_aiap", **HOST)
    assert ctx.kind == "program" and run_input(ctx)["user_message"] == ""


def test_no_words_and_both_named_asks_which_one_first(soulrun, agent):
    ctx = soulrun(session_id="nw-both", aiap="demo_aiap", aisp="demo_aisp", **HOST)
    assert ctx.kind == "text_only" and ctx.cache_dir is None and ctx.doubt["code"] == "WHICH_DESIGNATED_PROGRAM"
    assert runs(agent / ".soulrun_cache") == []                              # nothing was run
    # no words to tell the language by: the question is written in both, with the same numbers
    assert "你同时指定了 AIAP 程序「demo_aiap」和 AISP 技能「demo_aisp」" in ctx.text
    assert "Both the AIAP program \"demo_aiap\" and the AISP skill \"demo_aisp\" were named" in ctx.text
    assert ctx.text.count("1. ") == 2 and ctx.text.count("3. ") == 2
    options = ctx.doubt["options"]
    assert [o["action"] for o in options] == ["call", "call", "cancel"]
    assert options[0]["label"] == "运行 AIAP 程序「demo_aiap」 / Run the AIAP program \"demo_aiap\""
    assert options[0]["arguments"] == {"aisp": None} and options[1]["arguments"] == {"aiap": None}
    # following an option: call again with the same (absent) words and those arguments changed
    picked = soulrun(session_id="nw-both", aiap="demo_aiap", aisp=None, **HOST)
    assert picked.kind == "program" and candidates(picked) == ["demo_aiap"]


def test_with_words_both_named_are_candidates_as_before(soulrun, agent):
    ctx = soulrun(user_message=QUESTION, session_id="nw-words", aiap="demo_aiap", aisp="demo_aisp", **HOST)
    assert ctx.kind == "program" and candidates(ctx) == ["demo_aiap", "demo_aisp"]  # the engine judges from the words


def test_no_words_and_a_named_program_that_is_missing_asks_in_both_languages(soulrun, agent):
    ctx = soulrun(aiap="demo_aiapp", session_id="nw-missing", **HOST)
    assert ctx.kind == "text_only" and ctx.doubt["code"] == "DESIGNATED_NOT_FOUND"
    assert "找不到" in ctx.text and "was not found" in ctx.text
    assert ctx.doubt["options"][0]["arguments"] == {"aiap": "demo_aiap"}


def test_a_named_program_in_a_conversation_with_an_unfinished_run_asks_first(soulrun, agent):
    """The engine continues a conversation's latest unfinished run; handed the call, it would ask about that run and
    never mention the named program. SoulRun asks first, naming both: the named program did not start."""
    first = soulrun(user_message=QUESTION, session_id="nw-unfinished", **HOST)
    again = soulrun(session_id="nw-unfinished", aiap="other_aiap", **HOST)
    assert again.kind == "text_only" and again.doubt["code"] == "DESIGNATED_RUN_UNFINISHED"
    assert again.doubt["cache_dir"] == first.cache_dir and again.doubt["run_state"] == "RUNNING"
    assert "other_aiap" in again.text and "没有开始" in again.text and "was not started" in again.text
    assert [o["action"] for o in again.doubt["options"]] == ["ask", "cancel"]     # no words: nothing to give that run
    assert again.doubt["options"][0]["arguments"] == {"session_id": None}         # another conversation must be named
    assert runs(agent / ".soulrun_cache") == [1] and run_input(first)["user_message"] == QUESTION   # nothing created or changed


def test_the_command_line_runs_a_named_program_without_words(agent, subprocess_env):
    def cli(*args):
        return subprocess.run([sys.executable, "-B", "-X", "utf8", "-m", "soulrun", *args, "--json"], cwd=str(agent),
                              env=subprocess_env, capture_output=True, text=True, encoding="utf-8", timeout=120)
    one = cli("--aiap", "demo_aiap", "--session-id", "nw-cli", "--host-tool", "agent=false")
    assert one.returncode == 0, one.stderr
    assert json.loads(one.stdout)["kind"] == "program" and json.loads(one.stdout)["entry_mode"] == "fresh"
    both = cli("--aiap", "demo_aiap", "--aisp", "demo_aisp", "--session-id", "nw-cli2")
    assert both.returncode == 0 and json.loads(both.stdout)["doubt"]["code"] == "WHICH_DESIGNATED_PROGRAM"
    guide = subprocess.run([sys.executable, "-B", "-X", "utf8", "-m", "soulrun"], cwd=str(agent), env=subprocess_env,
                           capture_output=True, text=True, encoding="utf-8", timeout=120)
    assert guide.returncode == 0 and guide.stdout.startswith("SoulRun ")

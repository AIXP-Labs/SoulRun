"""The examples work as written. No model is called: the SoulACP session is replaced by a stand-in."""
from __future__ import annotations

import asyncio
import importlib.util
import re
import subprocess
import sys
import threading
from pathlib import Path
from types import SimpleNamespace

from conftest import ROOT
from helpers import HOST, QUESTION, candidates, commit, gate_payload, index, runs, take_node


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "examples" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class FakeSession:
    def __init__(self, reply: str = "（模拟）模型的回答"):
        self.sent, self.reply = [], reply

    async def query(self, prompt: str, *, user_id=None) -> str:
        self.sent.append((prompt, user_id))
        return self.reply


def test_minimal_host_prints_the_guide_and_runs_a_turn(agent, subprocess_env):
    script = str(ROOT / "examples" / "minimal_host.py")
    guide = subprocess.run([sys.executable, "-B", "-X", "utf8", script], cwd=str(agent), env=subprocess_env, capture_output=True)
    assert guide.returncode == 0 and guide.stdout.decode("utf-8").startswith("SoulRun ")
    message = agent.parent / "message.txt"                 # the human's words from a file, never on the command line
    message.write_text(QUESTION, encoding="utf-8")
    turn = subprocess.run([sys.executable, "-B", "-X", "utf8", script, str(message)], cwd=str(agent), env=subprocess_env, capture_output=True)
    assert turn.returncode == 0 and "kind=program entry_mode=fresh" in turn.stdout.decode("utf-8")
    assert (agent / ".soulrun_cache" / ".execution_cache" / "1" / "_delivery.json").is_file()
    piped = subprocess.run([sys.executable, "-B", "-X", "utf8", script, "-"], cwd=str(agent), env=subprocess_env, capture_output=True,
                           input=QUESTION.encode("utf-8"))
    assert piped.returncode == 0 and "kind=program" in piped.stdout.decode("utf-8")


def test_the_program_door_sends_instructions_plus_the_humans_words_and_records_the_turn(soulrun, agent):
    example = _load("soulacp_host")
    session = FakeSession()
    turn = asyncio.run(example.one_turn(session, QUESTION, conversation="conv-1", model="codex-acp/gpt-5.6"))
    (prompt, user_id), = session.sent
    assert user_id == "conv-1" and turn.ctx.session_id == "conv-1"          # one id for both layers
    assert prompt == turn.ctx.system_prompt + "\n\n" + turn.ctx.text + "\n\n" + QUESTION
    assert turn.ctx.system_prompt.startswith("ASSERT") and turn.ctx.text.startswith("[EXECUTION CONTEXT]")
    assert turn.reply == session.reply and turn.run_state == "RUNNING" and turn.needs_human is False
    assert (agent / ".soulrun_cache" / ".execution_cache" / "1" / "_delivery.json").is_file()


def test_the_program_door_tells_the_engine_its_model_starts_no_sub_agents_whatever_the_provider(soulrun, agent,
                                                                                               monkeypatch, capsys):
    """The example reports none of the sub-agent events a host must report through soulrun.host's sub-agent doors, so
    it never tells the engine its model can start sub-agents - not with --provider claude either."""
    example = _load("soulacp_host")

    class ManagedSession(FakeSession):          # SoulACP's session, as _main opens it
        def __init__(self, *, provider, model):
            super().__init__()

        async def __aenter__(self):
            return self

        async def __aexit__(self, *error):
            return False
    monkeypatch.setitem(sys.modules, "soulacp", SimpleNamespace(ManagedSession=ManagedSession))
    message = agent.parent / "message.txt"
    message.write_text(QUESTION, encoding="utf-8")
    for provider in ("claude", "codex"):
        arguments = SimpleNamespace(message_file=str(message), provider=provider, model="claude-acp/sonnet",
                                    conversation=f"sub-agents-{provider}")
        assert asyncio.run(example._main(arguments)) == 0
    turn = asyncio.run(example.one_turn(FakeSession(), QUESTION, conversation="sub-agents-direct"))
    folder = agent / ".soulrun_cache"
    assert runs(folder) == [1, 2, 3] and Path(turn.ctx.cache_dir).name == "3"
    assert [index(folder / ".execution_cache" / str(run))["host"]["host_tools"] for run in runs(folder)] == \
        [{"agent": False}] * 3


def test_the_program_door_does_not_ask_the_model_when_soulrun_has_a_question(soulrun, agent):
    example = _load("soulacp_host")
    session = FakeSession()
    turn = asyncio.run(example.one_turn(session, QUESTION, conversation="conv-2", aiap="no_such_program"))
    assert session.sent == [] and turn.needs_human is True and turn.reply is None and "找不到" in turn.shown


def test_the_program_door_takes_the_answer_to_a_gate_into_the_same_run(soulrun, agent):
    """The human's "1" after a gate goes to the run that asked, which runs on (the gate itself being shown and the run
    waiting for the human is the GateModel test below)."""
    example = _load("soulacp_host")
    ctx = soulrun(user_message=QUESTION, session_id="conv-3", aiap="demo_aiap", aisp="demo_aisp", **HOST)
    commit(soulrun, ctx, gate_payload(take_node(soulrun, ctx), ["demo_aiap", "demo_aisp"], "demo_aiap"))
    turn = asyncio.run(example.one_turn(FakeSession("好的，用第一个。"), "1", conversation="conv-3"))
    assert turn.ctx.cache_dir == ctx.cache_dir and turn.ctx.entry_mode == "resume"
    assert turn.run_state == "RUNNING" and turn.needs_human is False


class GateModel:
    """Acts as a model does on the first turn of a two-program request: takes the node, commits the gate, and writes
    what the engine tells it to write - the references, never the text."""
    def __init__(self, soulrun):
        self.soulrun = soulrun

    async def query(self, prompt: str, *, user_id=None) -> str:
        run = SimpleNamespace(cache_dir=re.search(r"^cache_dir: (.+)$", prompt, re.M).group(1).strip())
        reply = commit(self.soulrun, run, gate_payload(take_node(self.soulrun, run), ["demo_aiap", "demo_aisp"], "demo_aiap"))
        return f"{reply['public_block_ref']}\n{reply['gate']['public_prompt_ref']}"


class RefModel:
    """Acts as a model does on a text-only turn: its whole reply is the reference line the instructions name."""
    async def query(self, prompt: str, *, user_id=None) -> str:
        return re.search(r"⟦engine:[^⟧]+⟧", prompt).group(0)


def test_the_program_door_shows_the_gate_as_text_not_as_references(soulrun, agent):
    example = _load("soulacp_host")
    turn = asyncio.run(example.one_turn(GateModel(soulrun), QUESTION, conversation="conv-4", aiap="demo_aiap", aisp="demo_aisp"))
    assert turn.reply.startswith("⟦engine:") and "⟦engine:" not in turn.shown
    menu = next((Path(turn.ctx.cache_dir) / "_public").glob("menu.*.txt")).read_text(encoding="utf-8").strip()
    assert menu in turn.shown and turn.needs_human is True and turn.run_state == "WAITING_USER"


def test_the_program_door_takes_a_text_only_turn_to_the_model_and_the_answer_is_then_taken(soulrun, agent):
    from soulrun import host
    example = _load("soulacp_host")
    ctx = soulrun(user_message=QUESTION, session_id="conv-5", **HOST)
    assert host.open_restart_question(ctx.cache_dir, instance_started_at="2999-01-01T00:00:00Z")["status"] == "OPENED"
    turn = asyncio.run(example.one_turn(RefModel(), "你好", conversation="conv-5"))
    assert turn.ctx.kind == "text_only" and turn.ctx.doubt is None          # an engine instruction, not a doubt
    question = host.open_question(ctx.cache_dir)
    assert turn.needs_human is True and question["delivered"] is True and question["text"].strip() in turn.shown
    answered = soulrun(user_message="1", session_id="conv-5", **HOST)
    assert answered.entry_mode != "stopped_question"


def test_two_calls_at_once_do_not_mix_their_candidates(soulrun, agent):
    """The in-memory hand-over of candidates is serialised: concurrent calls each get their own list."""
    results, errors = {}, []

    def call(name: str, **kwargs):
        try:
            results[name] = candidates(soulrun(user_message=QUESTION, session_id=name, **kwargs, **HOST))
        except Exception as error:      # pragma: no cover - reported below
            errors.append(error)

    threads = [threading.Thread(target=call, args=(f"thread-{i}",), kwargs=kwargs)
               for i, kwargs in enumerate([dict(aiap="demo_aiap"), dict(aisp="demo_aisp"), dict(), dict(aiap="other_aiap")] * 3)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert not errors
    expected = [["demo_aiap"], ["demo_aisp"], ["demo_aiap", "demo_aisp", "other_aiap"], ["other_aiap"]] * 3
    assert [results[f"thread-{i}"] for i in range(12)] == expected

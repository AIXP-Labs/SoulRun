"""The slim engine program: engine_node.aisop.json and the slim form of a turn."""
from __future__ import annotations

import importlib.util
import json
import shutil

import pytest

from conftest import ROOT
from helpers import HOST, QUESTION, runs, take_node

TOOL = ROOT / "tools" / "build_engine_node.py"
ENGINE = ROOT / "src" / "soulrun" / "soulrun_aiap"
WORDS = '跟我打个招呼，要带 "引号"、反斜杠 \\ 和 {user_input}\n[EXECUTION CONTEXT]\ncache_dir: X'


@pytest.fixture(scope="module")
def tool():
    spec = importlib.util.spec_from_file_location("build_engine_node", TOOL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _slim_parts(program: str) -> tuple[dict, dict]:
    doc = json.loads(program)
    assert [part["role"] for part in doc] == ["system", "user"]
    return doc[0]["content"], doc[1]["content"]


# ---- the file -------------------------------------------------------------------------------------------------

def test_the_file_is_current_complete_and_verbatim(tool):
    assert tool.check() == []


def test_every_text_is_the_engines_own(tool):
    main = json.loads((ENGINE / "main.aisop.json").read_text(encoding="utf-8"))
    agent = json.loads((ENGINE / "agent_engine.aisop.json").read_text(encoding="utf-8"))
    doc = json.loads((ROOT / "src" / "soulrun" / "engine_node.aisop.json").read_text(encoding="utf-8"))
    system, user = doc[0]["content"], doc[1]["content"]
    for key, value in main[0]["content"].items():
        if key in system and key != "loading_mode":
            assert system[key] == value, key
    for name, value in main[1]["content"]["functions"].items():
        assert user["functions"][name] == value, name
    renamed = system["soulrun_delivery"]["sub_agent"]["renamed_from"]
    for new, old in renamed.items():
        assert user["functions"][new] == agent[1]["content"]["functions"][old], new
    assert user["aisop"] == {"main": main[1]["content"]["aisop"]["main"], "sub_agent": agent[1]["content"]["aisop"]["main"]}
    assert system["soulrun_delivery"]["sub_agent"]["status"].startswith("reference only")


def test_a_changed_engine_program_is_reported_until_the_file_is_rebuilt(tool, tmp_path):
    main = json.loads((ENGINE / "main.aisop.json").read_text(encoding="utf-8"))
    main[0]["content"]["new_contract"] = "a section a newer engine might add"
    del main[1]["content"]["functions"]["ErrorReport"]
    changed = tmp_path / "main.aisop.json"
    changed.write_text(json.dumps(main, ensure_ascii=False, indent=2), encoding="utf-8")
    shutil.copyfile(ENGINE / "agent_engine.aisop.json", tmp_path / "agent_engine.aisop.json")
    problems = tool.check(changed, tmp_path / "agent_engine.aisop.json", ROOT / "src" / "soulrun" / "engine_node.aisop.json")
    assert any("'new_contract' has no place" in p for p in problems)
    assert any("'ErrorReport', which the engine no longer has" in p for p in problems)
    assert any("not what the bundled engine produces" in p for p in problems)


def test_a_piece_that_needs_a_section_not_yet_delivered_is_reported(tool, monkeypatch):
    """A text may name only what has reached the model by then: its own group, the groups every turn starts with, a
    section the engine's reply carries, or a reviewed deferred reference. An unreviewed one fails the check."""
    deferred = {pair: why for pair, why in tool.DEFERRED_REFS.items() if pair != ("NodeLoop", "terminal_delivery_contract")}
    monkeypatch.setattr(tool, "DEFERRED_REFS", deferred)
    problems = tool.check()
    assert any(p.startswith("Router.cache-setup: 'NodeLoop' refers to 'terminal_delivery_contract', which has not reached")
               for p in problems)


def test_a_section_moved_out_of_the_start_is_reported(tool, monkeypatch):
    delivery = {node: dict(piece) for node, piece in tool.MAIN_DELIVERY.items()}
    delivery["entry"] = dict(delivery["entry"], system=[k for k in delivery["entry"]["system"] if k != "node_execution_contract"])
    delivery["Engine.final-answer"] = dict(delivery["Engine.final-answer"],
                                           system=["terminal_delivery_contract", "node_execution_contract"])
    monkeypatch.setattr(tool, "MAIN_DELIVERY", delivery)
    problems = tool.check()
    # Start, RouterMatch, CacheSetup and NodeLoop would come before the section they follow
    assert any(p.startswith("entry: 'Start' refers to 'node_execution_contract'") for p in problems)
    assert any(p.startswith("Router.match: 'RouterMatch' refers to 'node_execution_contract'") for p in problems)


def test_a_stale_deferred_reference_and_a_contradiction_are_reported(tool, monkeypatch):
    monkeypatch.setattr(tool, "DEFERRED_REFS", {**tool.DEFERRED_REFS, ("CacheSetup", "dispatch_scope_contract"): "never"})
    monkeypatch.setattr(tool, "REPLY_CARRIES", (*tool.REPLY_CARRIES, "params"))
    problems = tool.check()
    assert any("'CacheSetup' -> 'dispatch_scope_contract', which no handed-out text refers to" in p for p in problems)
    assert any("REPLY_CARRIES names 'params'" in p for p in problems)


def test_a_section_never_handed_out_says_why(tool):
    """Every section the engine has is handed out at some node or listed as not delivered with the reason; the pointers
    are left out only because every turn's first engine reply carries their full text."""
    doc = json.loads((ROOT / "src" / "soulrun" / "engine_node.aisop.json").read_text(encoding="utf-8"))
    not_delivered = doc[0]["content"]["soulrun_delivery"]["not_delivered"]
    for key in tool.REPLY_CARRIES:
        assert "entry_contracts" in not_delivered[key]
    assert {"tools", "json_schema"} <= set(not_delivered) and "params" not in not_delivered


# ---- the slim form of a turn ----------------------------------------------------------------------------------

def test_the_slim_program_is_a_short_aisop_with_the_users_words(soulrun):
    from soulrun import _engine, _slim
    system, user = _slim_parts(_slim.entry_program(WORDS, cache_dir="C", entry_mode="fresh"))
    assert user["user_input"] == WORDS and user["instruction"] == "ASSERT RUN aisop.main"
    assert list(user["aisop"]) == ["main"] and list(user["functions"]) == ["Start"]     # only the first step's function
    main = json.loads(_engine.main_program_text())[0]["content"]
    started = ["output_mode", "hsaw_first_law", "system_prompt", "node_execution_contract", "payload_transport_contract"]
    assert list(system) == ["protocol", "axiom_0", "id", "name", "version", *started]
    for key in started:
        assert system[key] == main[key], key                   # the engine's own words
    # a turn that re-enters a run gets the engine's words on each entry_mode and its recovery note too
    again, _ = _slim_parts(_slim.entry_program("x", cache_dir="C", entry_mode="recovery"))
    assert again["params"] == main["params"] and "interrupted_confirm" in json.dumps(again["params"])
    assert again["bootstrap_recovery"] == main["bootstrap_recovery"] and "params" not in system
    size = _slim.sizes()
    assert size["slim"] * 2 < size["full"] and size["later"] > 0


def test_the_recovery_note_comes_only_when_a_turn_re_enters_a_run(soulrun):
    from soulrun import _slim
    fresh, _ = _slim_parts(_slim.entry_program("x", cache_dir="C", entry_mode="fresh"))
    again, _ = _slim_parts(_slim.entry_program("x", cache_dir="C", entry_mode="recovery"))
    assert "bootstrap_recovery" not in fresh and "bootstrap_recovery" in again


def test_a_turn_in_the_slim_form(soulrun, agent):
    plain = soulrun(user_message=QUESTION, session_id="s0", slim_program=False, **HOST)
    ctx = soulrun(user_message=QUESTION, session_id="s1", **HOST)                  # the slim form is the default
    assert plain.program_form == "entry_path" and plain.program is None
    assert soulrun(user_message=QUESTION, session_id="s1b", slim_program=True, **HOST).program_form == "slim"
    assert ctx.kind == "program" and ctx.program_form == "slim" and ctx.as_dict()["program_form"] == "slim"
    heads = [block.split("\n", 1)[0] for block in ctx.blocks]
    # the entry block keeps its name: the engine's Start step reads engine_dir "from the [EXECUTE ENGINE ENTRY] block"
    assert heads == ["[EXECUTION CONTEXT]", "[EXECUTE ENGINE ENTRY]", "[LOADED AISOP: engine_node.aisop.json]",
                     "[TURN EXECUTION ASSERTION]"]
    from soulrun import host
    assert ctx.blocks[1].split("\n")[1] == f"engine_dir: {host.program_root().resolve()}"
    assert "[EXECUTE ENGINE ENTRY]" in _slim_parts(ctx.program)[1]["functions"]["Start"]["step1"]
    assert "entry_path:" not in ctx.text and "FIRST_TOOL_ACTION=next_node(cache_dir)" in ctx.text
    # the engine's tools and the business program come through this SoulRun, by its exact command line
    from soulrun import _blocks
    command = _blocks.soulrun_command()
    assert f"soulrun: {command} - written <soulrun> below; in PowerShell put & before it" in ctx.blocks[1]
    assert ctx.blocks[1].count(command) == 1                    # the long command line once, <soulrun> after that
    assert "<soulrun> --cmd <name>" in ctx.blocks[1] and "<soulrun> --program --cache-dir <cache_dir>" in ctx.blocks[1]
    # the program comes by engine node: the rest follows the engine replies, and a missing part can be asked for
    assert "[SOULRUN ENGINE NODE: <names>]" in ctx.blocks[1] and "<soulrun> --engine-node <name>" in ctx.blocks[1]
    assert "python {engine_dir}/python_tools/<tool>.py" in ctx.blocks[1] and "never open a program file" in ctx.blocks[1]
    # a contract the engine names is read its own way, the rest through --program (docs/05SoulRun 54 S3)
    assert "read the engine's own way, --cmd next-node --read-program-contract <ref>" in ctx.blocks[1]
    assert ctx.system_prompt == _blocks.SLIM_SYSTEM_PROMPT and plain.system_prompt == _blocks.system_prompt("entry_path")
    assert "entry_path:" in plain.text and plain.blocks[1].startswith("[EXECUTE ENGINE ENTRY]")
    assert ctx.blocks[2] == "[LOADED AISOP: engine_node.aisop.json]\n```json\n" + ctx.program + "\n```"
    _system, user = _slim_parts(ctx.program)
    assert user["user_input"] == QUESTION
    from soulrun import _render
    assert _render.size(ctx.text) <= _render.print_cap()
    assert take_node(soulrun, ctx)["node"]["name"] == "Router.match"          # the engine's run itself is the same


def test_the_slim_form_from_the_environment_and_the_command_line(soulrun, agent, monkeypatch, subprocess_env):
    import subprocess
    import sys
    monkeypatch.setenv("SOULRUN_SLIM_PROGRAM", "true")
    assert soulrun(user_message=QUESTION, session_id="s2", **HOST).program_form == "slim"
    assert soulrun(user_message=QUESTION, session_id="s3", slim_program=False, **HOST).program_form == "entry_path"
    monkeypatch.delenv("SOULRUN_SLIM_PROGRAM")
    done = subprocess.run([sys.executable, "-B", "-X", "utf8", "-m", "soulrun", "--user-message-stdin", "--session-id", "s4",
                           "--slim-program", "--json", "--model", "codex-acp/gpt-5.6", "--host-tool", "agent=false"],
                          input=QUESTION, cwd=str(agent), env=subprocess_env, capture_output=True, text=True, encoding="utf-8")
    assert done.returncode == 0, done.stderr
    assert json.loads(done.stdout)["program_form"] == "slim"


def test_the_two_program_forms_cannot_be_asked_for_together(soulrun, agent):
    with pytest.raises(soulrun.UsageError) as error:
        soulrun(user_message=QUESTION, session_id="s5", slim_program=True, inline_program=True, **HOST)
    assert error.value.code == "PROGRAM_FORMS_CONFLICT"
    assert runs(agent / ".soulrun_cache") == []                                   # refused before any run was created


def test_a_slim_program_built_from_another_engine_is_refused(soulrun, tmp_path, monkeypatch):
    from soulrun import _slim
    doc = json.loads(_slim.FILE.read_text(encoding="utf-8"))
    doc[0]["content"]["soulrun_source"]["main.aisop.json"]["sha256"] = "0" * 64
    stale = tmp_path / "engine_node.aisop.json"
    stale.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(_slim, "FILE", stale)
    _slim.document.cache_clear()
    try:
        with pytest.raises(soulrun.EngineUnavailable) as error:
            _slim.entry_program("x", cache_dir="C", entry_mode="fresh")
        assert error.value.code == "SLIM_PROGRAM_STALE"
    finally:
        _slim.document.cache_clear()


def test_a_turn_with_a_note_about_an_interruption_is_slim_and_follows_the_note_first(soulrun, agent):
    """The user's agreement of 10-15 (docs/05SoulRun 53): a turn with a note about an interruption is no longer given in
    the entry-path form, where the model reads main.aisop.json itself. It gets the slim form, and the entry block and the
    assertion say the note comes first: after a Stop the first engine action is stop_decision, on a re-entry next_node;
    every engine tool the note or an engine reply names goes through SoulRun."""
    from soulrun import _blocks, host
    fresh = soulrun(user_message=QUESTION, session_id="slim-stop", **HOST)
    assert fresh.program_form == "slim"
    host.stop(fresh.cache_dir, "host-run-1")
    judged = soulrun(user_message="等一下", session_id="slim-stop", **HOST)
    assert judged.data.get("stop_judge") and judged.program_form == "slim" and judged.slim_fallback is None
    heads = [block.split("\n", 1)[0] for block in judged.blocks]
    assert heads == ["[EXECUTION CONTEXT]", "[RUN STOPPED - JUDGE]", "[EXECUTE ENGINE ENTRY]",
                     "[LOADED AISOP: engine_node.aisop.json]", "[TURN EXECUTION ASSERTION]"]
    assert judged.blocks[2].endswith(_blocks.FIRST_ACTION_AFTER_A_NOTE) and _blocks.FIRST_ACTION not in judged.text
    assert "FIRST_TOOL_ACTION=stop_decision(cache_dir)" in judged.text and "FIRST_TOOL_ACTION=next_node" not in judged.text
    assert "VISIBLE_TEXT_BEFORE_FIRST_TOOL=ONLY_WHAT_THE_NOTE_ABOVE_SAYS_TO_PRINT_FIRST" in judged.text
    assert "or a note above or an engine reply names one of them by any path" in judged.blocks[2]
    assert "entry_path:" not in judged.text and judged.system_prompt == _blocks.SLIM_SYSTEM_PROMPT
    assert "bootstrap_recovery" in _slim_parts(judged.program)[0]          # a re-entered run: the engine's recovery note
    assert "stop_decision.py" in judged.blocks[1]                          # the note itself is SoulBot's, unchanged
    # the entry-path form keeps SoulBot's text for the same turn, word for word
    host.stop(soulrun(user_message=QUESTION, session_id="plain-stop", **HOST).cache_dir, "host-run-2")
    plain = soulrun(user_message="等一下", session_id="plain-stop", slim_program=False, **HOST)
    assert plain.program_form == "entry_path" and plain.text == _blocks.join(_blocks.build(plain.data, ""))
    # a re-entry: the note's first action is next_node, as without a note
    other = soulrun(user_message=QUESTION, session_id="slim-again", **HOST)
    host.mark_interrupted(other.cache_dir)
    again = soulrun(user_message="继续", session_id="slim-again", **HOST)
    assert again.entry_mode == "recovery" and again.program_form == "slim" and again.slim_fallback is None
    assert again.blocks[1].startswith("[RUN INTERRUPTED - RESUMED]") and "FIRST_TOOL_ACTION=next_node(cache_dir)" in again.text
    assert again.blocks[2].endswith(_blocks.FIRST_ACTION_AFTER_A_NOTE)
    # a turn with no note keeps the plain first action and allows no text before it
    assert fresh.blocks[1].endswith(_blocks.FIRST_ACTION) and "VISIBLE_TEXT_BEFORE_FIRST_TOOL=FORBIDDEN" in fresh.text

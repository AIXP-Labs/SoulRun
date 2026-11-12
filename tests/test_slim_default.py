"""The slim form is the default (docs/05SoulRun 49 §5): with SoulRun the model reads nothing itself - the engine program
is in the text, the engine's tools and the business program come through soulrun. The entry-path form (SoulBot's text)
is one switch away, and a turn falls back to it when the slim form cannot be used."""
import copy
import json
import subprocess
from pathlib import Path

import pytest
from conftest import write_json
from helpers import HOST, QUESTION, commit, gate_payload, route_payload, take_node


def _cli(capsys, *arguments) -> tuple[int, str, str]:
    from soulrun import cli
    code = cli.main(list(arguments))
    out, err = capsys.readouterr()
    return code, out, err


def _note(agent: Path, run: str) -> dict:
    from soulrun import _records
    return _records.read_run_record(agent / ".soulrun_cache", run) or {}


# ---- the default and the switch ------------------------------------------------------------------------------------

def test_the_slim_form_is_the_default_and_the_entry_path_form_is_one_switch_away(soulrun, agent, monkeypatch, capsys):
    from soulrun import _agent_text, _blocks
    ctx = soulrun(user_message=QUESTION, session_id="d1", **HOST)
    assert ctx.program_form == "slim" and ctx.system_prompt == _blocks.SLIM_SYSTEM_PROMPT and ctx.slim_fallback is None
    assert _note(agent, "1")["slim_used"] is True                               # the run's note says how it went out
    off = soulrun(user_message=QUESTION, session_id="d2", slim_program=False, **HOST)
    assert off.program_form == "entry_path" and off.system_prompt == _agent_text.SYSTEM_PROMPT and off.slim_fallback is None
    assert "slim_used" not in _note(agent, "2")
    monkeypatch.setenv("SOULRUN_SLIM_PROGRAM", "false")
    assert soulrun(user_message=QUESTION, session_id="d3", **HOST).program_form == "entry_path"
    monkeypatch.delenv("SOULRUN_SLIM_PROGRAM")
    message = agent / "message.txt"
    message.write_text(QUESTION, encoding="utf-8")
    code, out, _ = _cli(capsys, "--user-message-file", str(message), "--session-id", "d4", "--json", "--no-slim-program",
                        "--model", HOST["model"], "--host-tool", "agent=false")
    data = json.loads(out)
    assert code == 0 and data["program_form"] == "entry_path" and data["system_prompt"] == _agent_text.SYSTEM_PROMPT


def test_the_opening_instruction_goes_with_the_form(soulrun, agent):
    from soulrun import _agent_text, _blocks, host
    assert host.system_prompt() == host.system_prompt("slim") == _blocks.SLIM_SYSTEM_PROMPT
    assert host.system_prompt("entry_path") == host.system_prompt("full") == _agent_text.SYSTEM_PROMPT
    with pytest.raises(soulrun.UsageError) as error:
        host.system_prompt("thin")
    assert error.value.code == "PROGRAM_FORM_UNKNOWN"
    assert soulrun().system_prompt is None                                       # the guide is not a model turn
    missing = soulrun(user_message=QUESTION, aiap="no_such_program", **HOST)
    assert missing.doubt and missing.system_prompt is None                        # a question for the human: neither
    # the slim instruction never sends the model to read a file, and SoulBot's names exactly that
    assert "never read an engine or program file" in _blocks.SLIM_SYSTEM_PROMPT
    assert "physically read the Execute Engine entry" in _agent_text.SYSTEM_PROMPT


def test_an_output_the_command_line_saved_to_a_file_is_read_whole_by_its_path(soulrun, agent):
    """docs/05SoulRun 87 (record 86 #26): run 7's main session found 21 outputs saved to a file and read one whole; the others it
    searched for fields. The entry says the saved file is that output: read whole by its path, page by page, never searched."""
    ctx = soulrun(user_message=QUESTION, session_id="r26", **HOST)
    entry = next(block for block in ctx.blocks if block.startswith("[EXECUTE ENGINE ENTRY]"))
    tools = entry.split("engine_tools: ", 1)[1].split("\nbusiness_program: ", 1)[0]
    assert "Read that output whole every time" in tools
    assert "saves a long output to a file" in tools and "by its path" in tools and "page by page" in tools
    assert "never search it" in tools


# ---- falling back --------------------------------------------------------------------------------------------------

def test_a_slim_program_that_cannot_be_built_gives_the_entry_path_form_for_that_turn(soulrun, agent, tmp_path, monkeypatch):
    from soulrun import _agent_text, _slim
    doc = json.loads(_slim.FILE.read_text(encoding="utf-8"))
    doc[0]["content"]["soulrun_source"]["main.aisop.json"]["sha256"] = "0" * 64
    stale = tmp_path / "engine_node.aisop.json"
    stale.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    try:
        with monkeypatch.context() as patch:
            patch.setattr(_slim, "FILE", stale)
            _slim.document.cache_clear()
            ctx = soulrun(user_message=QUESTION, session_id="f1", **HOST)
            assert ctx.program_form == "entry_path" and ctx.slim_fallback == "SLIM_PROGRAM_UNAVAILABLE: SLIM_PROGRAM_STALE"
            assert ctx.system_prompt == _agent_text.SYSTEM_PROMPT and "[LOADED AISOP" not in ctx.text
            patch.setattr(_slim, "FILE", tmp_path / "missing.json")
            _slim.document.cache_clear()
            gone = soulrun(user_message=QUESTION, session_id="f2", **HOST)
            assert gone.program_form == "entry_path" and gone.slim_fallback == "SLIM_PROGRAM_UNAVAILABLE: FileNotFoundError"
    finally:
        _slim.document.cache_clear()
    assert soulrun(user_message=QUESTION, session_id="f3", **HOST).program_form == "slim"      # only those turns


def test_a_run_left_at_router_match_after_the_model_took_it_keeps_the_entry_path_form(soulrun, agent):
    from soulrun import _agent_text, _blocks
    ctx = soulrun(user_message=QUESTION, session_id="st1", **HOST)
    assert take_node(soulrun, ctx)["node"]["name"] == "Router.match"             # the model took the node ...
    asked = soulrun(user_message="另外一件事", session_id="st1", **HOST)            # ... and the next turn came first
    assert asked.entry_mode == "interrupted_confirm" and asked.kind == "text_only"
    assert asked.slim_fallback == "EARLIER_SLIM_PROBLEM: STALLED_AT_ROUTER_MATCH"
    assert asked.system_prompt == _agent_text.SYSTEM_PROMPT and _note(agent, "1")["slim_problem"] == "STALLED_AT_ROUTER_MATCH"
    resumed = soulrun(user_message="继续", session_id="st1", **HOST)
    assert resumed.kind == "program" and resumed.program_form == "entry_path"
    assert resumed.slim_fallback == "EARLIER_SLIM_PROBLEM: STALLED_AT_ROUTER_MATCH"
    other = soulrun(user_message=QUESTION, session_id="st2", **HOST)              # another conversation: still slim
    assert other.program_form == "slim" and other.system_prompt == _blocks.SLIM_SYSTEM_PROMPT


def test_a_question_put_to_the_human_at_router_match_is_not_a_stall(soulrun, agent):
    """Two programs fit and the model asks which one (docs/05SoulRun 82, production runs 2 and 3 of 10-27): the run
    waits at Router.match with nothing committed, but the model did its part. A turn that does not answer, and the
    answer, keep the slim form; a model that then leaves Router.match unanswered is still caught."""
    from soulrun import _blocks
    ctx = soulrun(user_message=QUESTION, session_id="g1", aiap="demo_aiap", aisp="demo_aisp", **HOST)
    reply = commit(soulrun, ctx, gate_payload(take_node(soulrun, ctx), ["demo_aiap", "demo_aisp"], "demo_aiap"))
    assert reply["status"] == "WAITING_USER"
    aside = soulrun(user_message="这两个有什么区别？", session_id="g1", **HOST)       # not an answer: still waiting
    assert aside.slim_fallback is None and "slim_problem" not in _note(agent, "1")
    answered = soulrun(user_message="1", session_id="g1", **HOST)
    assert answered.cache_dir == ctx.cache_dir and answered.data["gate_answer"]["status"]
    assert answered.program_form == "slim" and answered.slim_fallback is None
    assert answered.system_prompt == _blocks.SLIM_SYSTEM_PROMPT and "slim_problem" not in _note(agent, "1")
    take_node(soulrun, answered)                                                  # took Router.match again, no commit
    later = soulrun(user_message="另外一件事", session_id="g1", **HOST)
    assert later.slim_fallback == "EARLIER_SLIM_PROBLEM: STALLED_AT_ROUTER_MATCH"


def test_a_turn_the_host_closed_with_no_engine_call_counts_and_an_interrupted_one_does_not(soulrun, agent):
    from soulrun import host
    ctx = soulrun(user_message=QUESTION, session_id="h1", **HOST)
    host.after_turn(ctx.cache_dir, "我不知道该怎么做。")                          # the model answered without the engine
    asked = soulrun(user_message="另外一件事", session_id="h1", **HOST)
    assert asked.slim_fallback == "EARLIER_SLIM_PROBLEM: STALLED_AT_ROUTER_MATCH"
    quiet = soulrun(user_message=QUESTION, session_id="h2", **HOST)
    host.mark_interrupted(quiet.cache_dir)                                       # the host went down before the model acted
    again = soulrun(user_message="另外一件事", session_id="h2", **HOST)
    assert again.entry_mode == "interrupted_confirm" and again.slim_fallback is None
    assert "slim_problem" not in _note(agent, Path(quiet.cache_dir).name)


def test_a_run_that_failed_at_an_engine_node_passes_the_entry_path_form_on_to_the_conversation(soulrun, agent, monkeypatch):
    from soulrun import _api, host
    first = soulrun(user_message=QUESTION, session_id="e1", **HOST)
    host.mark_interrupted(first.cache_dir)
    soulrun(user_message="另外一件事", session_id="e1", **HOST)
    cancelled = soulrun(user_message="取消", session_id="e1", **HOST)              # the first run ends
    assert cancelled.data.get("interrupted_cancel")
    real = _api._index
    failed = {"run_state": "FAILED", "current": {"name": "Router.cache-setup", "visit": 1}, "completed": []}
    with monkeypatch.context() as patch:
        patch.setattr(_api, "_index", lambda cache_dir: failed if Path(cache_dir).name == "1" else real(cache_dir))
        second = soulrun(user_message=QUESTION, session_id="e1", **HOST)          # as if the first had failed there
    assert second.entry_mode == "fresh" and second.program_form == "entry_path"
    assert second.slim_fallback == "EARLIER_SLIM_PROBLEM: ENGINE_NODE_FAILED in run 1"
    host.mark_interrupted(second.cache_dir)
    soulrun(user_message="另外一件事", session_id="e1", **HOST)
    soulrun(user_message="取消", session_id="e1", **HOST)
    third = soulrun(user_message=QUESTION, session_id="e1", **HOST)               # the conversation keeps it
    assert third.program_form == "entry_path" and third.slim_fallback == f"EARLIER_SLIM_PROBLEM: INHERITED from run {Path(second.cache_dir).name}"
    assert soulrun(user_message=QUESTION, session_id="e2", **HOST).program_form == "slim"


# ---- the business program through soulrun -------------------------------------------------------------------------

LONG = "规则正文。" * 3000                     # a shared constraint long enough to need paging (15,000 characters)
RICH = [
    {"role": "system", "content": {
        "protocol": "AIAP V1.0.0", "axiom_0": "Human_Sovereignty_and_Wellbeing", "id": "rich.main", "name": "Rich AIAP",
        "version": "2.0.0", "summary": "Rich AIAP package: tells a story", "flow_format": "mermaid", "loading_mode": "normal",
        "trust_level": 3, "system_prompt": "你是讲故事的助手。每次回答末尾附 [AI生成内容]。",
        "output_mode": {"output": "L1"},
        "tools": [{"name": "file_system"}, {"name": "story_tool", "description": "writes the story"}],
        "params": {"style": {"type": "string", "default": "short"}},
        "shared_constraints": {"program_dir": "the folder of this file", "long_rule": LONG},
        "tool_dirs": [{"path": "tool_dirs/", "files": [{"file": "tell.py", "entry_point": "python tool_dirs/tell.py"}]}]}},
    {"role": "user", "content": {
        "instruction": "ASSERT RUN aisop.main", "user_input": "{user_input}",
        "aisop": {"main": "graph TD\n    Start[入口] --> Tell[讲故事]\n    Tell --> endNode((End))"},
        "functions": {"Start": {"step1": "接收请求"},
                      "Tell": {"step1": "run story_tool: python tool_dirs/tell.py, under shared_constraints.program_dir"}}}},
]


@pytest.fixture
def routed(soulrun, agent):
    """A run routed to the rich program (Router.match committed), ready for Router.cache-setup."""
    write_json(agent / "aiap" / "rich_aiap" / "main.aisop.json", RICH)
    ctx = soulrun(user_message="请运行 rich：讲个故事", session_id="pv", aiap="rich_aiap", **HOST)
    node = take_node(soulrun, ctx)
    assert commit(soulrun, ctx, route_payload(node, "rich_aiap"))["status"] == "COMMITTED"
    return ctx


def _files(folder: Path) -> dict:
    return {p.relative_to(folder).as_posix(): (p.stat().st_size, p.stat().st_mtime_ns) for p in folder.rglob("*") if p.is_file()}


def test_the_program_overview_node_and_field_come_from_the_run(soulrun, agent, routed):
    from soulrun import host
    before = _files(Path(routed.cache_dir)) | {f"agent:{k}": v for k, v in _files(agent / "aiap").items()}
    overview = host.program_view(routed.cache_dir)
    assert overview["program"]["entry_file"] == "main.aisop.json" and overview["main_graph"] == RICH[1]["content"]["aisop"]["main"]
    assert overview["main_nodes"] == ["Start", "Tell", "endNode"] and overview["entry_node"] == "Start" and overview["end_nodes"] == ["endNode"]
    system = RICH[0]["content"]
    assert overview["system"] == {key: system[key] for key in ("system_prompt", "output_mode", "tools", "params")}
    sizes = {item["field"]: item["chars"] for item in overview["fields"]}
    assert sizes["shared_constraints"] == len(json.dumps(system["shared_constraints"], ensure_ascii=False, separators=(",", ":")))
    from soulrun import _program                          # only a field worth fetching is listed by size (54 S1)
    assert set(sizes) == {"shared_constraints"} and all(item["chars"] >= _program.LISTED_FROM for item in overview["fields"])
    assert "tool_dirs" in overview["other_fields"] and "protocol" in overview["other_fields"]
    assert "system_prompt" not in overview["other_fields"] and "shared_constraints" not in overview["other_fields"]
    tell = host.program_view(routed.cache_dir, node="Tell")
    assert tell["function"] == RICH[1]["content"]["functions"]["Tell"] and tell["file"] == "main.aisop.json"
    assert [t["name"] for t in tell["tools_named"]] == ["story_tool"]                 # named in the step, file_system not
    assert [e["file"] for e in tell["tool_entries_named"]] == ["tell.py"]
    assert tell["shared_constraints_cited"] == {"program_dir": "the folder of this file"}
    text, offset = "", 0
    while offset is not None:                                                         # a long field, page by page
        page = host.program_view(routed.cache_dir, field="shared_constraints", offset=offset, limit=4000)
        assert page["total_chars"] == sizes["shared_constraints"] and not page["complete"]
        assert len(page["text"]) <= 4000                                              # the page asked for, no more
        text, offset = text + page["text"], page["next_offset"]
    assert json.loads(text) == system["shared_constraints"]
    from soulrun import _program, _render
    text, offset, pages = "", 0, 0                       # the default page: CJK text is paged by bytes as well, under the cap
    while offset is not None:
        page = host.program_view(routed.cache_dir, field="shared_constraints", offset=offset)
        assert len(json.dumps(page, ensure_ascii=False).encode("utf-8")) < _render.print_cap()
        assert len(json.dumps(page["text"], ensure_ascii=False).encode("utf-8")) <= _program.PAGE_BYTES
        text, offset, pages = text + page["text"], page["next_offset"], pages + 1
    assert json.loads(text) == system["shared_constraints"] and pages == 2
    small = host.program_view(routed.cache_dir, field="version")
    assert small["complete"] is True and small["value"] == "2.0.0"
    assert host.program_view(routed.cache_dir, field="user.aisop")["value"] == RICH[1]["content"]["aisop"]
    after = _files(Path(routed.cache_dir)) | {f"agent:{k}": v for k, v in _files(agent / "aiap").items()}
    assert after == before                                                            # nothing was written anywhere


def test_a_field_is_written_the_way_the_engine_writes_it(soulrun, routed):
    """The size and fingerprint SoulRun gives for a field that is not a string are the ones the engine reports in a
    node's program_contracts, and SoulRun's pages of it hold the engine's own --read-program-contract text: a model can
    tell that both are the same rule (docs/05SoulRun 56 S5)."""
    from soulrun import host
    served = take_node(soulrun, routed)
    assert served["node"]["name"] == "Router.cache-setup"
    payload = copy.deepcopy(served["payload_skeleton"])
    payload.update(output="Start > Tell", user_summary="讲故事的请求走 Start → Tell。", outer_nodes_in_path=["Start", "Tell"])
    reply = commit(soulrun, routed, payload, node="Router.cache-setup")
    assert reply["status"] == "COMMITTED" and reply["next"]["node"] == "Start", reply
    contracts = ((reply.get("next_plan") or {}).get("input_authority") or {}).get("program_contracts") \
        or take_node(soulrun, routed)["input_authority"]["program_contracts"]
    shared = {row["field"]: row for row in contracts["items"]}["shared_constraints"]
    assert shared["complete"] is False                                               # long: the engine gives only its ref
    listed = {item["field"]: item for item in host.program_view(routed.cache_dir)["fields"]}["shared_constraints"]
    assert (listed["chars"], listed["sha256"]) == (shared["total_chars"], shared["value_sha256"])
    offset, pages = 0, 0
    while offset is not None:                                                        # the same text, page by page
        ours = host.program_view(routed.cache_dir, field="shared_constraints", offset=offset, limit=4000)
        assert (ours["total_chars"], ours["sha256"]) == (shared["total_chars"], shared["value_sha256"])
        read = soulrun(cmd="next-node", cache_dir=routed.cache_dir,
                       args=["--read-program-contract", shared["ref"], "--offset", str(offset), "--limit", "4000"])
        assert read.returncode == 0, read.stdout + read.stderr
        theirs = read.json()
        assert theirs["value_sha256"] == shared["value_sha256"]
        assert (ours["text"], ours["next_offset"]) == (theirs["text"], theirs["next_offset"])
        offset, pages = ours["next_offset"], pages + 1
    assert pages == 4                                                                # 15,000-odd characters in 4,000s


@pytest.mark.parametrize(("arguments", "code"), [
    (dict(node="NoSuch"), "NODE_UNKNOWN"), (dict(field="no_field"), "FIELD_UNKNOWN"),
    (dict(field="version", offset=-1), "PAGE_INVALID"), (dict(field="version", limit=0), "PAGE_INVALID"),
    (dict(node="Tell", field="version"), "PROGRAM_VIEW_CONFLICT"), (dict(field="version", doc="other.json"), "DOC_UNKNOWN"),
])
def test_a_wrong_program_question_is_refused_by_name(soulrun, routed, arguments, code):
    from soulrun import host
    with pytest.raises(soulrun.SoulRunError) as error:
        host.program_view(routed.cache_dir, **arguments)
    assert error.value.code == code


def test_the_program_command_line(soulrun, agent, routed, capsys):
    code, out, _ = _cli(capsys, "--program", "--cache-dir", routed.cache_dir, "--node", "Start")
    assert code == 0 and json.loads(out)["function"] == {"step1": "接收请求"}
    code, out, err = _cli(capsys, "--program", "--json")
    assert code == 2 and json.loads(err)["error"]["code"] == "CACHE_DIR_REQUIRED"
    code, _, err = _cli(capsys, "--program", "--cache-dir", str(agent), "--json")
    assert code == 2 and json.loads(err)["error"]["code"] == "NOT_A_RUN"
    code, _, err = _cli(capsys, "--node", "Start", "--json")
    assert code == 2 and json.loads(err)["error"]["code"] == "PROGRAM_OPTION_ALONE"
    message = agent / "m.txt"
    message.write_text(QUESTION, encoding="utf-8")
    code, _, err = _cli(capsys, "--program", "--cache-dir", routed.cache_dir, "--user-message-file", str(message), "--json")
    assert code == 2 and json.loads(err)["error"]["code"] == "MODES_CONFLICT"


def test_the_command_the_text_names_runs_this_soulrun_without_its_search_path(soulrun, agent, routed, subprocess_env, tmp_path):
    """The model's shell may hold another python, and not this package on its search path: the command line SoulRun
    writes into the slim text (this interpreter, this package's launcher) still reaches this SoulRun and its engine."""
    from soulrun import _blocks
    command = _blocks.soulrun_command()
    python, launcher = (part.strip('"') for part in command.split('" "'))
    env = {k: v for k, v in subprocess_env.items() if k != "PYTHONPATH"}
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    version = subprocess.run([python, launcher, "--version"], cwd=elsewhere, env=env, capture_output=True, text=True, encoding="utf-8")
    assert version.returncode == 0 and version.stdout.startswith(f"soulrun {soulrun.__version__}")
    served = subprocess.run([python, launcher, "--cmd", "next-node", "--cache-dir", routed.cache_dir], cwd=elsewhere, env=env,
                            capture_output=True, text=True, encoding="utf-8")
    reply, end = json.JSONDecoder().raw_decode(served.stdout)          # the engine's reply first, whole
    assert served.returncode == 0 and reply["node"]["name"] == "Router.cache-setup"
    assert served.stdout[end:].lstrip().startswith("[SOULRUN ENGINE NODE: ")   # then the part this step needs
    shown = subprocess.run([python, launcher, "--program", "--cache-dir", routed.cache_dir], cwd=elsewhere, env=env,
                           capture_output=True, text=True, encoding="utf-8")
    assert shown.returncode == 0 and json.loads(shown.stdout)["main_nodes"] == ["Start", "Tell", "endNode"]


def test_the_doctor_says_which_form_and_warns_when_the_slim_program_cannot_be_built(agent, monkeypatch, tmp_path):
    from soulrun import _doctor, _slim
    form = lambda: {c.name: c for c in _doctor.run(agent_dir=agent)}["program form"]   # noqa: E731
    assert form().status == "OK" and form().detail.startswith("slim (the default")
    monkeypatch.setenv("SOULRUN_SLIM_PROGRAM", "off")
    assert form().status == "OK" and form().detail.startswith("entry_path (SOULRUN_SLIM_PROGRAM is off")
    monkeypatch.delenv("SOULRUN_SLIM_PROGRAM")
    try:
        with monkeypatch.context() as patch:
            patch.setattr(_slim, "FILE", tmp_path / "missing.json")
            _slim.document.cache_clear()
            assert form().status == "WARN" and "every run falls back to entry_path" in form().detail
    finally:
        _slim.document.cache_clear()

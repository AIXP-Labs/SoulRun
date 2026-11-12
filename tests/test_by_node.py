"""The slim engine program handed out by engine node (docs/05SoulRun 65, 66): a turn starts with what its first step
needs; every other part follows the engine reply that first needs it, once per turn; any part can be asked for."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from helpers import HOST, QUESTION, commit, route_payload, take_node

STARTED = {"system:output_mode", "system:hsaw_first_law", "system:system_prompt", "system:node_execution_contract",
           "system:payload_transport_contract", "functions:Start"}


def _part(text: str) -> tuple[str, list]:
    head, _, rest = text.partition("\n```json\n")
    return head, json.loads(rest[:rest.rindex("\n```")])


def _given(part: list) -> set[str]:
    names = set()
    for message in part:
        content = message["content"]
        names |= {f"functions:{fn}" for fn in content.get("functions", {})} if message["role"] == "user" else \
            {f"system:{key}" for key in content}
    return names


def test_a_turn_starts_with_a_record_of_what_it_was_given(soulrun, agent):
    from soulrun import _records
    slim = soulrun(user_message=QUESTION, session_id="n1", **HOST)
    assert slim.program_form == "slim" and _records.read_delivered(slim.cache_dir) == STARTED
    plain = soulrun(user_message=QUESTION, session_id="n2", slim_program=False, **HOST)
    assert plain.program_form == "entry_path" and _records.read_delivered(plain.cache_dir) is None


def test_each_part_comes_once_with_the_reply_that_needs_it(soulrun, agent):
    from soulrun import _records, _slim
    ctx = soulrun(user_message=QUESTION, session_id="n3", **HOST)
    served = take_node(soulrun, ctx)
    head, part = _part(_slim.node_part(ctx.cache_dir, served))
    assert head.startswith("[SOULRUN ENGINE NODE: Router.match] ")
    assert _given(part) == {"functions:RouterMatch"}
    assert _slim.node_part(ctx.cache_dir, served) is None                     # once per turn
    committed = commit(soulrun, ctx, route_payload(served, "demo_aiap"))
    assert committed["status"] == "COMMITTED", committed.get("errors")
    head, part = _part(_slim.node_part(ctx.cache_dir, committed))
    assert head.startswith("[SOULRUN ENGINE NODE: Router.cache-setup] ")
    assert _given(part) == {"functions:CacheSetup", "functions:NodeLoop"}
    assert _records.read_delivered(ctx.cache_dir) == STARTED | {"functions:RouterMatch", "functions:CacheSetup",
                                                                 "functions:NodeLoop"}
    # every text keeps the engine's own words
    main = json.loads((_slim.FILE.parent / "soulrun_aiap" / "main.aisop.json").read_text(encoding="utf-8"))
    assert part[0]["content"]["functions"]["NodeLoop"] == main[1]["content"]["functions"]["NodeLoop"]


def test_a_new_turn_starts_again_and_another_form_keeps_nothing(soulrun, agent):
    from soulrun import _records, _slim
    ctx = soulrun(user_message=QUESTION, session_id="n4", **HOST)
    served = take_node(soulrun, ctx)
    assert _slim.node_part(ctx.cache_dir, served) is not None
    _slim.start_turn(ctx.cache_dir, "resume")                     # the next turn, maybe a new model session
    assert _records.read_delivered(ctx.cache_dir) == STARTED | {"system:params", "system:bootstrap_recovery"}
    assert _slim.node_part(ctx.cache_dir, served) is not None
    _records.clear_delivered(ctx.cache_dir)                       # a turn handed out in another form
    assert _slim.node_part(ctx.cache_dir, served) is None


@pytest.mark.parametrize("reply, groups", [
    ({"reply_file": "r", "node": {"name": "Router.match", "kind": "engine"}}, ["Router.match"]),
    ({"reply_file": "r", "node": "Router.match", "next_plan": {"node": {"name": "Router.cache-setup", "kind": "engine"}}},
     ["Router.cache-setup"]),
    ({"reply_file": "r", "node": {"name": "cast", "kind": "business"}, "dispatch": {"required": True}},
     ["business", "dispatch"]),
    ({"reply_file": "r", "node": "interpret", "next_plan": {"node": {"name": "Engine.execute-report", "kind": "engine"}}},
     ["Engine.execute-report"]),
    ({"reply_file": "r", "node": "Engine.execute-report", "next_plan": {"node": {"name": "Engine.final-answer"}}},
     ["Engine.final-answer"]),
    ({"reply_file": "r", "run": {"state": "FAILED"}}, ["run_failed"]),
    ({"reply_file": "r", "run_state": "COMPLETED", "terminal_delivery_refs": ["x"]}, ["terminal"]),
    ({"reply_file": "r", "node": "NLU", "status": "REJECTED"}, []),      # a refusal: the same node, nothing new
    ({"ref": "an input read by reference"}, []),                     # a read-only query serves no node
    ("not a reply", []),
])
def test_which_groups_a_reply_calls_for(reply, groups):
    from soulrun import _slim
    assert _slim.groups_for(reply) == groups


def test_every_group_a_reply_can_call_for_is_in_the_file():
    from soulrun import _slim
    assert set(_slim.groups()) == {"entry", "recovery_entry", "business", "dispatch", "run_failed",
                                   "terminal", *_slim.NODE_GROUPS}


def test_the_command_line_prints_the_reply_whole_then_the_part(soulrun, agent, subprocess_env):
    ctx = soulrun(user_message=QUESTION, session_id="n5", **HOST)
    line = [sys.executable, "-B", "-X", "utf8", "-m", "soulrun", "--cmd", "next-node", "--cache-dir", ctx.cache_dir]
    done = subprocess.run(line, cwd=str(agent), env=subprocess_env, capture_output=True, text=True, encoding="utf-8")
    reply, end = json.JSONDecoder().raw_decode(done.stdout)
    assert done.returncode == 0 and reply["node"]["name"] == "Router.match"
    assert done.stdout[end:].lstrip().startswith("[SOULRUN ENGINE NODE: Router.match]")
    # a refused command: the tool's own output and exit code, nothing added
    bad = subprocess.run([*line, "--no-such-option"], cwd=str(agent), env=subprocess_env, capture_output=True, text=True,
                         encoding="utf-8")
    assert bad.returncode != 0 and "[SOULRUN ENGINE NODE" not in bad.stdout
    # the run folder written with an equals sign is the same run folder
    other = soulrun(user_message=QUESTION, session_id="n5b", **HOST)
    equals = subprocess.run([*line[:7], "next-node", f"--cache-dir={other.cache_dir}"], cwd=str(agent), env=subprocess_env,
                            capture_output=True, text=True, encoding="utf-8")
    _reply, end = json.JSONDecoder().raw_decode(equals.stdout)
    assert equals.stdout[end:].lstrip().startswith("[SOULRUN ENGINE NODE: Router.match]")


def test_a_sub_agents_command_gets_nothing_added(soulrun, monkeypatch, capsysbinary):
    """What the main conversation was given must not be marked as given by a sub-agent's call."""
    from soulrun import _cmd, _slim
    reply = b'{"reply_file": "r", "node": {"name": "cast", "kind": "business"}}'
    monkeypatch.setattr(_cmd.subprocess, "run", lambda line, **kw: subprocess.CompletedProcess(line, 0, reply))
    asked = []
    monkeypatch.setattr(_slim, "node_part", lambda cache_dir, _reply, room=None: asked.append(cache_dir) or "PART\n")
    assert _cmd.passthrough("next-node", ["--cache-dir", "runs/1", "--agent-ticket", "T"]) == 0
    assert _cmd.passthrough("next-node", ["--agent-ticket=T", "--cache-dir", "runs/1"]) == 0
    assert asked == [] and capsysbinary.readouterr().out == b""             # the tool printed for itself
    assert _cmd.passthrough("next-node", ["--cache-dir", "runs/1"]) == 0
    assert asked == ["runs/1"] and capsysbinary.readouterr().out == reply + b"\nPART\n"


def test_a_part_that_would_pass_the_cap_is_named_not_printed(soulrun, agent):
    """The engine keeps what it prints under its cap (a model CLI keeps a longer output in a file, which a model then
    has to read and parse): the part after a reply stays under the same cap, else one line names it."""
    from soulrun import _records, _slim
    ctx = soulrun(user_message=QUESTION, session_id="n9", **HOST)
    served = take_node(soulrun, ctx)
    line = _slim.node_part(ctx.cache_dir, served, room=100)
    assert line.startswith("[SOULRUN ENGINE NODE: Router.match] ") and line.count("\n") == 1 and "```" not in line
    assert f'Before you do this step, run: <soulrun> --engine-node Router.match --cache-dir "{ctx.cache_dir}"' in line
    assert _records.read_delivered(ctx.cache_dir) == STARTED                  # not given: it comes when asked for
    size = len(_slim._render(["Router.match"], *_slim._parts(["Router.match"])).encode("utf-8"))
    assert "```" not in _slim.node_part(ctx.cache_dir, served, room=size - 1)        # one byte short: still named only
    whole = _slim.node_part(ctx.cache_dir, served, room=size)
    assert whole.startswith("[SOULRUN ENGINE NODE: Router.match] ") and "```json" in whole
    assert "functions:RouterMatch" in _records.read_delivered(ctx.cache_dir)


def test_the_command_line_counts_the_reply_against_the_cap(soulrun, monkeypatch, capsysbinary):
    from soulrun import _cmd, _render, _slim
    reply = b'{"reply_file": "r", "node": {"name": "cast", "kind": "business"}}'
    monkeypatch.setattr(_cmd.subprocess, "run", lambda line, **kw: subprocess.CompletedProcess(line, 0, reply))
    rooms = []
    monkeypatch.setattr(_slim, "node_part", lambda cache_dir, _reply, room=None: rooms.append(room) or "PART\n")
    monkeypatch.setattr(_render, "print_cap", lambda: 1000)
    assert _cmd.passthrough("next-node", ["--cache-dir", "runs/1"]) == 0
    assert rooms == [1000 - len(reply) - 1] and capsysbinary.readouterr().out == reply + b"\nPART\n"


class _ClosedPipe:
    """Standard output whose reader went away after ``room`` writes (on Windows a closed pipe is OSError 22)."""

    def __init__(self, room: int = 0):
        self.room, self.written = room, []
        self.buffer = self

    def write(self, data):
        if self.room <= 0:
            raise OSError(22, "Invalid argument")
        self.room -= 1
        self.written.append(data)

    def flush(self):
        pass


def test_a_reply_that_cannot_be_printed_is_noted_not_a_traceback(soulrun, agent, monkeypatch, capsys):
    """docs/05SoulRun 80 B3: the engine has done its work and kept its reply; only SoulRun's copy did not arrive."""
    from soulrun import _cmd, _records, _slim
    ctx = soulrun(user_message=QUESTION, session_id="n-pipe", **HOST)
    reply = b'{"status": "COMMITTED", "node": {"name": "cast", "kind": "business"}}'
    monkeypatch.setattr(_cmd.subprocess, "run", lambda line, **kw: subprocess.CompletedProcess(line, 0, reply))
    monkeypatch.setattr(_slim, "node_part", lambda cache_dir, _reply, room=None: "PART\n")
    monkeypatch.setattr(sys, "stdout", _ClosedPipe())
    assert _cmd.passthrough("node-commit", ["--cache-dir", ctx.cache_dir]) == _cmd.REPLY_NOT_PRINTED
    err = capsys.readouterr().err
    assert err.count("\n") == 1 and "SOULRUN_REPLY_NOT_PRINTED" in err and "Traceback" not in err
    monkeypatch.setattr(sys, "stdout", _ClosedPipe(room=1))              # the reply went out, the part after it did not
    assert _cmd.passthrough("node-commit", ["--cache-dir", ctx.cache_dir]) == _cmd.REPLY_NOT_PRINTED
    path = Path(ctx.places["soulrun_cache_dir"]) / _records.SOULRUN_DIR / _records.UNDELIVERED / f"{Path(ctx.cache_dir).name}.jsonl"
    lines = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert [line["printed"] for line in lines] == ["nothing", "the reply"]
    assert all(line["reply_bytes"] == len(reply) and line["reply_status"] == "COMMITTED" and line["delivered"] is False
               and line["cmd"] == "node-commit" and line["exit_code"] == 0 for line in lines)


def test_a_closed_pipe_on_the_real_command_line(soulrun, agent, subprocess_env):
    """The reader closes its end before the engine has replied (docs/05SoulRun 79 T9): exit code 74, one line on standard
    error, no traceback; the engine's own reply is still kept in the run."""
    from soulrun import _cmd, _records
    ctx = soulrun(user_message=QUESTION, session_id="n-pipe-real", **HOST)
    line = [sys.executable, "-B", "-X", "utf8", "-m", "soulrun", "--cmd", "next-node", "--cache-dir", ctx.cache_dir]
    child = subprocess.Popen(line, cwd=str(agent), env=subprocess_env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    child.stdout.close()                                                # long before the engine has started
    err = child.stderr.read().decode("utf-8")
    assert child.wait(timeout=300) == _cmd.REPLY_NOT_PRINTED, err
    assert "SOULRUN_REPLY_NOT_PRINTED" in err and "Traceback" not in err
    note = Path(ctx.places["soulrun_cache_dir"]) / _records.SOULRUN_DIR / _records.UNDELIVERED / f"{Path(ctx.cache_dir).name}.jsonl"
    assert json.loads(note.read_text(encoding="utf-8").splitlines()[-1])["printed"] == "nothing"
    assert list((Path(ctx.cache_dir) / "_work" / "replies").glob("*.json"))     # the engine kept its reply


def test_a_reply_that_cannot_be_printed_outside_soulruns_folders_leaves_no_note(soulrun, tmp_path, monkeypatch, capsys):
    from soulrun import _cmd
    reply = b'{"status": "REJECTED"}'
    monkeypatch.setattr(_cmd.subprocess, "run", lambda line, **kw: subprocess.CompletedProcess(line, 2, reply))
    monkeypatch.setattr(sys, "stdout", _ClosedPipe())
    before = sorted(tmp_path.rglob("*"))
    assert _cmd.passthrough("node-commit", ["--cache-dir", str(tmp_path / "runs" / "1")]) == _cmd.REPLY_NOT_PRINTED
    assert "SOULRUN_REPLY_NOT_PRINTED" in capsys.readouterr().err and sorted(tmp_path.rglob("*")) == before


def test_where_an_engine_command_names_its_run_folder():
    from soulrun import _cmd
    assert _cmd._cache_dir_in(["--cache-dir", "runs/1", "--json"]) == "runs/1"
    assert _cmd._cache_dir_in(["--json", "--cache-dir=runs/2"]) == "runs/2"
    assert _cmd._cache_dir_in(["--cache-dir"]) is None and _cmd._cache_dir_in(["--cache-dir="]) is None
    assert _cmd._cache_dir_in(["--node", "x"]) is None


def test_a_part_on_request(soulrun, agent, subprocess_env):
    from soulrun import _records, _slim
    head, part = _part(_slim.part_for(["NodeLoop"]))
    assert head.startswith("[SOULRUN ENGINE NODE: NodeLoop] ") and _given(part) == {"functions:NodeLoop"}
    _, part = _part(_slim.part_for(["dispatch", "node_execution_contract"]))
    assert _given(part) == {"system:dispatch_scope_contract", "system:node_execution_contract"}
    for never in ("tools", "json_schema", "sub_agent_init", "nothing"):
        with pytest.raises(soulrun.UsageError) as error:
            _slim.part_for([never])
        assert error.value.code == "ENGINE_NODE_UNKNOWN"
    ctx = soulrun(user_message=QUESTION, session_id="n6", **HOST)
    done = subprocess.run([sys.executable, "-B", "-X", "utf8", "-m", "soulrun", "--engine-node", "Engine.final-answer",
                           "--cache-dir", ctx.cache_dir], cwd=str(agent), env=subprocess_env, capture_output=True,
                          text=True, encoding="utf-8")
    assert done.returncode == 0 and done.stdout.startswith("[SOULRUN ENGINE NODE: Engine.final-answer] ")
    assert {"functions:Final", "system:terminal_delivery_contract"} <= _records.read_delivered(ctx.cache_dir)


def test_the_record_goes_with_its_run(soulrun, agent):
    from soulrun import _records
    ctx = soulrun(user_message=QUESTION, session_id="n7", **HOST)
    gone = _records.delivered_path(ctx.cache_dir).with_name("999.json")
    gone.write_text(json.dumps({"pieces": []}), encoding="utf-8")
    _records.prune(agent / ".soulrun_cache")
    assert not gone.exists() and _records.delivered_path(ctx.cache_dir).exists()


def test_a_turn_printed_in_the_entry_path_form_keeps_no_record(soulrun, agent, monkeypatch):
    from soulrun import _records, _render
    ctx = soulrun(user_message=QUESTION, session_id="n8", **HOST)
    monkeypatch.setattr(_render, "print_cap", lambda: 100)          # too long to print: the entry-path form is printed
    text, _saved = _render.for_shell(ctx)
    assert "[LOADED AISOP" not in text and _records.read_delivered(ctx.cache_dir) is None


def _turn_facts(cache_dir) -> dict:
    from soulrun import _records
    record = json.loads(_records.delivered_path(cache_dir).read_text(encoding="utf-8"))
    return {key: record.get(key) for key in ("turn_id", "host_turn_id", "turn")}


def test_the_record_says_which_turn_of_the_run_it_is_and_keeps_it_as_parts_are_added(soulrun, agent):
    """docs/05SoulRun 87 (#25): the engine's turn_id is the run's number, the same on every turn of a run (ctx.turn_id
    too); the record of what a turn was given also keeps the host's own id for the turn and which turn of the run it
    is - and keeps them when a reply or a request adds a part."""
    from pathlib import Path

    from soulrun import _records, _slim
    ctx = soulrun(user_message=QUESTION, session_id="n9", host_turn_id="inv-1", **HOST)
    run = Path(ctx.cache_dir).name
    assert ctx.turn_id == run
    assert _turn_facts(ctx.cache_dir) == {"turn_id": run, "host_turn_id": "inv-1", "turn": 1}
    served = take_node(soulrun, ctx)
    assert _slim.node_part(ctx.cache_dir, served) is not None                  # a reply adds a part
    _slim.part_for(["Engine.final-answer"], ctx.cache_dir)                     # and so does a request
    assert "functions:Final" in _records.read_delivered(ctx.cache_dir)
    assert _turn_facts(ctx.cache_dir) == {"turn_id": run, "host_turn_id": "inv-1", "turn": 1}
    assert commit(soulrun, ctx, route_payload(served, "demo_aiap"))["status"] == "COMMITTED"
    again = soulrun(user_message="继续", session_id="n9", host_turn_id="inv-2", **HOST)
    assert again.cache_dir == ctx.cache_dir and again.turn_id == run and again.program_form == "slim"
    assert _turn_facts(again.cache_dir) == {"turn_id": run, "host_turn_id": "inv-2", "turn": 2}
    plain = soulrun(user_message="继续", session_id="n9", host_turn_id="inv-3", slim_program=False, **HOST)
    assert plain.program_form == "entry_path" and _records.read_delivered(plain.cache_dir) is None
    latest = agent / ".soulrun_cache" / ".soulrun" / "turns" / f"{run}.json"         # every turn, in any form
    assert json.loads(latest.read_text(encoding="utf-8")) == {"turn_id": run, "host_turn_id": "inv-3", "turn": 3,
                                                              "trace_id": ctx.data["trace_id"]}   # the run's own
    last = soulrun(user_message="继续", session_id="n9", **HOST)
    assert _turn_facts(last.cache_dir) == {"turn_id": run, "host_turn_id": None, "turn": 4}
    assert "turns" not in _records.read_run_record(agent / ".soulrun_cache", run)    # the run's note is written once


def _kept_turn(agent, run) -> dict:
    path = agent / ".soulrun_cache" / ".soulrun" / "turns" / f"{run}.json"
    return {key: value for key, value in json.loads(path.read_text(encoding="utf-8")).items() if key != "trace_id"}


def test_a_run_number_used_again_starts_its_turns_at_one(soulrun, agent):
    """The engine numbers a new run one past the highest it keeps, so a number comes back once the latest runs are gone
    (here the user clears the runs and keeps SoulRun's notes). The new run's first turn is turn 1, in the turns file
    and in the record of what the turn was given - not the old run's count carried on."""
    import shutil
    first = soulrun(user_message=QUESTION, session_id="u1", host_turn_id="old-1", **HOST)
    soulrun(user_message="继续", session_id="u1", host_turn_id="old-2", **HOST)
    run = Path(first.cache_dir).name
    assert _kept_turn(agent, run)["turn"] == 2
    shutil.rmtree(agent / ".soulrun_cache" / ".execution_cache")
    new = soulrun(user_message=QUESTION, session_id="u2", host_turn_id="new-1", **HOST)
    assert Path(new.cache_dir).name == run and new.entry_mode == "fresh" and not new.data.get("rebootstrap")
    assert _kept_turn(agent, run) == {"turn_id": run, "host_turn_id": "new-1", "turn": 1}
    assert _turn_facts(new.cache_dir) == {"turn_id": run, "host_turn_id": "new-1", "turn": 1}
    soulrun(user_message="继续", session_id="u2", host_turn_id="new-2", **HOST)
    assert _kept_turn(agent, run)["turn"] == 2                                  # and counts on from there


def test_a_run_number_the_engine_gave_again_after_removing_the_run_starts_at_one(soulrun, agent, monkeypatch):
    """No one removes anything by hand: with CACHE_NUM 2 and two older runs still going, the engine removes the newest
    run once it has ended, and the next run takes its number in the same call."""
    monkeypatch.setenv("CACHE_NUM", "2")
    soulrun(user_message=QUESTION, session_id="e1", **HOST)                    # still going: never removed
    soulrun(user_message=QUESTION, session_id="e2", **HOST)
    third = soulrun(user_message=QUESTION, session_id="e3", host_turn_id="e3-1", **HOST)
    run = Path(third.cache_dir).name
    ended = soulrun(user_message="取消", session_id="e3", host_turn_id="e3-2", **HOST)
    assert ended.cache_dir == third.cache_dir and ended.entry_mode == "terminal"
    assert _kept_turn(agent, run)["turn"] == 2
    new = soulrun(user_message=QUESTION, session_id="e4", host_turn_id="e4-1", **HOST)
    assert Path(new.cache_dir).name == run and new.data.get("trace_id") != third.data.get("trace_id")
    assert _kept_turn(agent, run) == {"turn_id": run, "host_turn_id": "e4-1", "turn": 1}
    assert _turn_facts(new.cache_dir) == {"turn_id": run, "host_turn_id": "e4-1", "turn": 1}


def test_the_same_turn_bootstrapped_again_keeps_its_number_and_a_new_host_turn_does_not(soulrun, agent):
    """The engine hands the same run back for the same message within two minutes (rebootstrap). With the same
    host_turn_id it is the host bootstrapping one turn twice: the same turn. A human sending the same words again is a
    new host turn (a new host_turn_id): the next turn - and so is a rebootstrap with no host_turn_id to tell them apart."""
    first = soulrun(user_message=QUESTION, session_id="b1", host_turn_id="h1", **HOST)
    run = Path(first.cache_dir).name
    twice = soulrun(user_message=QUESTION, session_id="b1", host_turn_id="h1", **HOST)
    assert twice.cache_dir == first.cache_dir and twice.data.get("rebootstrap") is True
    assert _kept_turn(agent, run) == {"turn_id": run, "host_turn_id": "h1", "turn": 1}
    assert _turn_facts(twice.cache_dir) == {"turn_id": run, "host_turn_id": "h1", "turn": 1}
    again = soulrun(user_message=QUESTION, session_id="b1", host_turn_id="h2", **HOST)
    assert again.cache_dir == first.cache_dir and again.data.get("rebootstrap") is True
    assert _kept_turn(agent, run) == {"turn_id": run, "host_turn_id": "h2", "turn": 2}
    unnamed = soulrun(user_message=QUESTION, session_id="b1", **HOST)
    assert unnamed.data.get("rebootstrap") is True and _kept_turn(agent, run)["turn"] == 3
    unnamed = soulrun(user_message=QUESTION, session_id="b1", **HOST)       # no host turn on file either: nothing to tell
    assert unnamed.data.get("rebootstrap") is True and _kept_turn(agent, run) == {"turn_id": run, "host_turn_id": None,
                                                                                    "turn": 4}


def test_a_turns_file_without_the_runs_trace_is_kept_counting_unless_the_run_is_new(soulrun, tmp_path):
    """A turns file written before the run's trace was kept in it: a turn of a run already going counts on from it, the
    first turn of a run the engine says it has just created starts at 1."""
    from soulrun import _records
    path = tmp_path / ".soulrun" / "turns" / "7.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"turn_id": "7", "host_turn_id": "a", "turn": 4}), encoding="utf-8")
    on = _records.count_turn(tmp_path, "7", turn_id="7", host_turn_id="b", trace_id="t-7-1", entry_mode="resume")
    assert on["turn"] == 5
    path.write_text(json.dumps({"turn_id": "7", "host_turn_id": "a", "turn": 4}), encoding="utf-8")
    new = _records.count_turn(tmp_path, "7", turn_id="7", host_turn_id="b", trace_id="t-7-2", entry_mode="fresh")
    assert new["turn"] == 1
    other = _records.count_turn(tmp_path, "7", turn_id="7", host_turn_id="c", trace_id="t-7-3", entry_mode="recovery")
    assert other["turn"] == 1                         # another run's trace on file: not this run's count

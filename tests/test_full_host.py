"""A full host on SoulRun alone - no SoulBot code: what the human sees, a Stop, a restart, a broken connection, and the
calls that name a program or a run. No model is called; where a model would act, the test sends what a model sends."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from helpers import HOST, QUESTION, commit, gate_payload, runs, take_node

FAR_FUTURE = "2999-01-01T00:00:00Z"          # "this host process started later than every run"


def _record(agent: Path, run: int) -> bytes:
    return (agent / ".soulrun_cache" / ".soulrun" / "runs" / f"{run}.json").read_bytes()


def _index(ctx) -> dict:
    return json.loads((Path(ctx.cache_dir) / "_index.json").read_text(encoding="utf-8"))


def _lifecycle(ctx) -> dict:
    path = Path(ctx.cache_dir) / "_host_lifecycle.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def _gate(soulrun, session_id: str):
    ctx = soulrun(user_message=QUESTION, session_id=session_id, aiap="demo_aiap", aisp="demo_aisp", **HOST)
    reply = commit(soulrun, ctx, gate_payload(take_node(soulrun, ctx), ["demo_aiap", "demo_aisp"], "demo_aiap"))
    assert reply["status"] == "WAITING_USER"
    return ctx, reply


# ---- what the human sees: references expanded --------------------------------------------------------------

def test_the_model_writes_references_and_the_host_shows_the_blocks(soulrun, agent):
    from soulrun import host
    ctx, reply = _gate(soulrun, "refs")
    refs = [ref for ref in (reply.get("public_block_ref"), (reply.get("gate") or {}).get("public_prompt_ref")) if ref]
    assert refs and all(ref.startswith("⟦engine:") for ref in refs)
    assert reply.get("public_block") is None and (reply.get("gate") or {}).get("public_prompt") is None   # the model has no text
    model_reply = "\n".join(refs)                                   # what the engine tells the model to write
    shown = host.expand_refs(model_reply, cache_dir=ctx.cache_dir)
    assert "⟦engine:" not in shown
    menu = next((Path(ctx.cache_dir) / "_public").glob("menu.*.txt")).read_text(encoding="utf-8").strip()
    assert menu and menu in shown
    assert host.expand_refs(model_reply) == shown                   # the same, found from the agent folder


@pytest.mark.parametrize("ref", ["⟦engine:1/../_index.json⟧", "⟦engine:1/_index.json⟧", "⟦engine:9/menu.q001.txt⟧",
                                 "⟦engine:1/menu.nope.txt⟧", "⟦engine:x/menu.q001.txt⟧"])
def test_a_reference_to_anything_but_a_public_block_stays_as_it_is(soulrun, agent, ref):
    from soulrun import host
    ctx, _ = _gate(soulrun, "refs-unsafe")
    text = f"before {ref} after"
    assert host.expand_refs(text, cache_dir=ctx.cache_dir) == text


def test_a_note_inside_the_brackets_is_ignored_and_nothing_is_created(soulrun, agent, tmp_path):
    from soulrun import host
    ctx, reply = _gate(soulrun, "refs-note")
    name = Path(reply["public_block_ref"][len("⟦engine:"):-1]).name
    noted = f"⟦engine:{Path(ctx.cache_dir).name}/{name}（菜单）⟧"
    assert "⟦engine:" not in host.expand_refs(noted, cache_dir=ctx.cache_dir)
    empty = tmp_path / "never-ran"
    empty.mkdir()
    assert host.expand_refs(noted, agent_dir=empty) == noted and list(empty.iterdir()) == []


# ---- a Stop: the human's answer to the stop question is taken once its menu was shown -----------------------

def test_a_stop_question_is_answered_after_the_reply_that_showed_it(soulrun, agent):
    from soulrun import host
    ctx = soulrun(user_message=QUESTION, session_id="stop", **HOST)
    assert host.stop(ctx.cache_dir, "host-run-1")["action"] == "STOPPED"
    judged = soulrun(user_message="等一下，我想换个话题", session_id="stop", **HOST)
    assert judged.data.get("stop_judge")
    decided = soulrun(cmd="stop-decision", cache_dir=ctx.cache_dir, stop_id=judged.data["stop_id"],
                      judge_id=judged.data["judge_id"], decision="ask", recommendation="new_task",
                      explanation="像是新任务", advice="建议新任务", reason="消息与本场无关").json()
    assert decided["status"] == "GATE" and decided["public_block_ref"].startswith("⟦engine:")
    question = host.open_question(ctx.cache_dir)
    assert question["question_id"] == decided["question_id"] and question["delivered"] is False and question["text"]

    refused = soulrun(user_message="2", session_id="stop", **HOST)       # not shown yet: the engine takes no answer
    assert refused.data.get("stop_question") and refused.entry_mode == "stopped_question"

    after = host.after_turn(ctx.cache_dir, decided["public_block_ref"])  # the model's whole reply: the reference line
    assert after["question_delivered"]["status"] == "DELIVERED" and host.open_question(ctx.cache_dir)["delivered"]
    taken = soulrun(user_message="2", session_id="stop", **HOST)
    assert taken.data.get("stop_new_task") and taken.entry_mode == "fresh" and taken.cache_dir != ctx.cache_dir
    # the new task's note says to print its public_note first, then run from Router.match: the slim form allows that text
    assert taken.program_form == "slim" and taken.blocks[1].startswith("[RUN STOPPED - NEW TASK]")
    assert "FIRST_TOOL_ACTION=next_node(cache_dir)" in taken.text
    assert "VISIBLE_TEXT_BEFORE_FIRST_TOOL=ONLY_WHAT_THE_NOTE_ABOVE_SAYS_TO_PRINT_FIRST" in taken.text


def test_continuing_after_a_stop_points_the_model_at_the_bundled_engines_tool(soulrun, agent):
    """When the model judges that a message after a Stop continues the run (stop-decision continue), the next step
    names the bundled engine's own next_node.py, never a path inferred from the run folder (engine problem 31,
    doc 35 F11; fixed in docs/05SoulRun 90)."""
    from soulrun import host
    ctx = soulrun(user_message=QUESTION, session_id="stop-continue", **HOST)
    host.stop(ctx.cache_dir, "host-run-1")
    judged = soulrun(user_message="继续吧", session_id="stop-continue", **HOST)
    decided = soulrun(cmd="stop-decision", cache_dir=ctx.cache_dir, stop_id=judged.data["stop_id"],
                      judge_id=judged.data["judge_id"], decision="continue", reason="消息是让这一场接着做").json()
    assert decided["status"] == "CONTINUE"
    named = Path(decided["next_action"].split(" --cache-dir ")[0].removeprefix("python "))
    engine_tool = Path(soulrun.engine_info()["engine_dir"]).resolve() / "python_tools" / "next_node.py"
    assert engine_tool.is_file() and named.resolve() == engine_tool


# ---- a restart: with the switch off (the default) the human is asked, never re-entered quietly --------------

def _restart_question(soulrun, session_id: str):
    from soulrun import host
    assert host.resume_interrupted_enabled() is False                    # the default: stop and ask
    ctx = soulrun(user_message=QUESTION, session_id=session_id, **HOST)
    rows = host.interrupted_runs(created_before=FAR_FUTURE)
    assert Path(ctx.cache_dir).resolve() in [Path(row["cache_dir"]).resolve() for row in rows]
    opened = host.open_restart_question(ctx.cache_dir, instance_started_at=FAR_FUTURE)
    assert opened["status"] == "OPENED"
    return ctx, opened


def test_after_a_restart_the_host_shows_the_question_and_the_human_answers_it(soulrun, agent):
    from soulrun import host
    ctx, opened = _restart_question(soulrun, "restart")
    question = host.open_question(ctx.cache_dir)
    assert question["question_id"] == opened["question_id"] and question["source"] == "restart_doubt"
    assert question["text"] and question["delivered"] is False
    assert host.expand_refs(question["reference"], cache_dir=ctx.cache_dir).strip() == question["text"].strip()
    assert host.mark_question_delivered(ctx.cache_dir)["status"] == "DELIVERED"       # the host showed it itself
    assert host.mark_question_delivered(ctx.cache_dir, "restart-99")["status"] != "DELIVERED"
    answered = soulrun(user_message="1", session_id="restart", **HOST)
    assert not answered.data.get("stop_question") and answered.entry_mode != "stopped_question"


def test_with_the_question_open_the_re_entry_text_does_not_re_enter(soulrun, agent):
    from soulrun import host
    ctx, _ = _restart_question(soulrun, "restart-guard")
    again = soulrun(user_message=host.resume_prompt(ctx.cache_dir), session_id="restart-guard",
                    origin_type="engine_recovery", human_turn=False, **HOST)
    assert again.entry_mode != "recovery" and not again.data.get("recovery_reentry")


def test_the_expanded_menu_in_a_reply_marks_it_delivered_too(soulrun, agent):
    from soulrun import host
    ctx, _ = _restart_question(soulrun, "restart-text")
    question = host.open_question(ctx.cache_dir)
    shown = "人看到的：\n" + host.expand_refs(question["reference"], cache_dir=ctx.cache_dir)
    assert host.after_turn(ctx.cache_dir, shown)["question_delivered"]["status"] == "DELIVERED"
    assert host.after_turn(ctx.cache_dir, shown)["question_delivered"] is None            # once is enough


# ---- re-entry text names a run: only that run's own conversation may use it --------------------------------

def test_re_entry_text_for_another_conversations_run_is_refused(soulrun, agent):
    from soulrun import host
    alice = soulrun(user_message="ALICE 的原话：" + QUESTION, session_id="alice", **HOST)
    bob = soulrun(user_message=host.resume_prompt(alice.cache_dir), session_id="bob",
                  origin_type="engine_recovery", human_turn=False, **HOST)
    assert bob.kind == "text_only" and bob.doubt["code"] == "NAMED_RUN_MISMATCH"
    assert bob.doubt["named_by"] == "recovery_marker" and [o["action"] for o in bob.doubt["options"]] == ["cancel"]
    assert "ALICE" not in bob.text and bob.cache_dir is None
    assert _index(alice)["session_id"] == "alice" and not _lifecycle(alice).get("recovery_reentries")
    own = soulrun(user_message=host.resume_prompt(alice.cache_dir), session_id="alice",
                  origin_type="engine_recovery", human_turn=False, **HOST)
    assert own.entry_mode == "recovery" and own.cache_dir == alice.cache_dir


# ---- a named program is never quietly replaced by an unfinished run -----------------------------------------

def test_naming_another_program_right_after_the_first_asks_and_keeps_the_record(soulrun, agent):
    first = soulrun(session_id="pick", aiap="demo_aiap", **HOST)
    record = _record(agent, 1)
    second = soulrun(session_id="pick", aiap="other_aiap", **HOST)      # within the engine's two-minute window
    assert second.doubt and second.doubt["code"] == "DESIGNATED_RUN_UNFINISHED"
    assert second.doubt["cache_dir"] == first.cache_dir and "demo_aiap" in second.text and "other_aiap" in second.text
    assert runs(agent / ".soulrun_cache") == [1] and _record(agent, 1) == record


def test_the_same_program_again_gets_the_same_run_and_its_record_stays(soulrun, agent):
    first = soulrun(session_id="again", aiap="demo_aiap", **HOST)
    record = _record(agent, 1)
    # The same folder and program, the folder now given as an argument: a rewritten record would say so.
    second = soulrun(session_id="again", aiap="demo_aiap", agent_dir=str(agent), **HOST)
    assert second.cache_dir == first.cache_dir and second.data.get("rebootstrap") is True
    assert _record(agent, 1) == record                                   # written once, when the run was created


def test_naming_a_program_after_words_without_one_asks(soulrun, agent):
    soulrun(user_message=QUESTION, session_id="words", **HOST)          # all programs were candidates
    named = soulrun(user_message=QUESTION, session_id="words", aiap="other_aiap", **HOST)
    assert named.doubt and named.doubt["code"] == "DESIGNATED_RUN_UNFINISHED"
    assert named.doubt["options"][0] == {"number": 1, "label": named.doubt["options"][0]["label"],
                                         "action": "call", "arguments": {"aiap": None, "aisp": None}}


def test_a_run_waiting_at_a_gate_is_not_answered_by_a_named_program(soulrun, agent):
    ctx, _ = _gate(soulrun, "gate-named")
    gate_before = _index(ctx)["gate"]
    named = soulrun(user_message="请用 other_aiap 给我抽一张牌", session_id="gate-named", aiap="other_aiap", **HOST)
    assert named.doubt["code"] == "DESIGNATED_RUN_UNFINISHED" and named.doubt["run_state"] == "WAITING_USER"
    assert _index(ctx)["gate"] == gate_before                            # no answer recorded at the open gate
    answered = soulrun(user_message="1", session_id="gate-named", **HOST)
    assert answered.cache_dir == ctx.cache_dir and answered.entry_mode == "resume"


# ---- a broken connection: the request is checked before the engine reads it --------------------------------

def test_a_recovery_request_can_be_a_mapping_and_a_bad_one_is_refused(soulrun, agent):
    from soulrun import host
    soulrun(user_message=QUESTION, session_id="rec", **HOST)
    planned = host.runner_recovery({"phase": "plan", "session_id": "rec", "error_code": "ACP_PROCESS_EXIT"})
    assert planned["action"] == "resume" and planned["recovery_token"]
    typed = host.RecoveryRequest(phase="start", session_id="rec", error_code="ACP_PROCESS_EXIT",
                                 recovery_token=planned["recovery_token"])
    assert host.runner_recovery(typed)["action"] == "resume"
    for bad in ({"session_id": "rec", "error_code": "X"}, {"phase": "go", "session_id": "rec", "error_code": "X"},
                {"phase": "plan", "session_id": "", "error_code": "X"}):
        with pytest.raises(soulrun.UsageError) as caught:
            host.runner_recovery(bad)
        assert caught.value.code == "RECOVERY_REQUEST_INVALID"


def _text_only_turn(ctx, note: str, language: str = "中文") -> None:
    """A turn that runs nothing: the context, the note (SoulBot's fixed wording, unchanged) and SoulBot's text-only
    assertion - never the entry block and "first, read the entry" assertion, which would send the model to read
    main.aisop.json although the note says to run nothing."""
    from soulrun import _agent_text, _blocks, _engine
    assert ctx.kind == "text_only" and ctx.doubt is None and ctx.program_form is None and ctx.program is None
    assert [block.split("\n", 1)[0] for block in ctx.blocks] == ["[EXECUTION CONTEXT]", note, "[TURN EXECUTION ASSERTION]"]
    assert ctx.blocks[1] == _agent_text.interruption_block(ctx.data, _engine.ENGINE_DIR)
    assert ctx.blocks[2] == _agent_text.ASSERTION_TEXT_ONLY_TEMPLATE.format(language_name=language)
    assert "[EXECUTE ENGINE ENTRY]" not in ctx.text and "FIRST_TOOL_ACTION" not in ctx.text
    assert ctx.text == _blocks.join(_blocks.build(ctx.data, ""))


def test_a_confirmation_and_a_cancel_are_text_only_turns(soulrun, agent):
    """After an interruption the engine asks the human to confirm, and a cancel ends the run: on both it wants only a
    text reply. ctx.kind says so, and in every program form the text is the context, the note and the text-only
    assertion - not the entry block and "first, read the entry" assertion SoulBot's rule gave them (problem 32), which
    would send the model to read main.aisop.json (docs/05SoulRun 53). The opening instruction goes with the form."""
    from soulrun import _agent_text, _blocks, host
    ctx = soulrun(user_message=QUESTION, session_id="confirm", **HOST)
    host.mark_interrupted(ctx.cache_dir)
    asked = soulrun(user_message="另外一件事", session_id="confirm", **HOST)
    assert asked.entry_mode == "interrupted_confirm" and asked.slim_fallback is None
    _text_only_turn(asked, "[RUN INTERRUPTED - CONFIRM]")
    assert asked.system_prompt == _blocks.SLIM_SYSTEM_PROMPT
    cancelled = soulrun(user_message="取消", session_id="confirm", **HOST)
    assert cancelled.data.get("interrupted_cancel")
    _text_only_turn(cancelled, "[RUN CANCELLED]")
    plain = soulrun(user_message=QUESTION, session_id="plain-run", **HOST)
    assert plain.kind == "program" and plain.program_form == "slim"
    # the entry-path form and the full form: the same blocks, with SoulBot's opening instruction
    for session, form in (("confirm-old", dict(slim_program=False)), ("confirm-full", dict(inline_program=True))):
        old = soulrun(user_message=QUESTION, session_id=session, **form, **HOST)
        assert old.program_form == ("entry_path" if "slim_program" in form else "full")
        host.mark_interrupted(old.cache_dir)
        asked_old = soulrun(user_message="另外一件事", session_id=session, **form, **HOST)
        assert asked_old.entry_mode == "interrupted_confirm"
        _text_only_turn(asked_old, "[RUN INTERRUPTED - CONFIRM]")
        assert asked_old.system_prompt == _agent_text.SYSTEM_PROMPT
        cancelled_old = soulrun(user_message="取消", session_id=session, **form, **HOST)
        assert cancelled_old.data.get("interrupted_cancel")
        _text_only_turn(cancelled_old, "[RUN CANCELLED]")
        assert cancelled_old.system_prompt == _agent_text.SYSTEM_PROMPT


def test_a_turn_with_any_text_only_key_gets_no_entry_block_in_the_entry_path_form():
    """The rule itself, key by key: every key that makes ctx.kind "text_only" also decides the entry-path blocks."""
    from soulrun import _blocks
    base = {"turn_id": "7", "cache_dir": "runs/7", "cache_name": "7", "trace_id": "t", "user_language": "en"}
    for key in ("stop_question", "stop_hold", "stop_ended", "supply_authorized", "supply_hold",
                "interrupted_confirm", "interrupted_cancel"):
        blocks = _blocks.build({**base, key: True})
        assert _blocks.runs_nothing({**base, key: True}) and "[EXECUTE ENGINE ENTRY]" not in _blocks.join(blocks), key
        assert blocks[-1].startswith("[TURN EXECUTION ASSERTION]") and "FIRST_RESPONSE_MUST_BE=text" in blocks[-1], key
    plain = _blocks.build(base)
    assert not _blocks.runs_nothing(base) and plain[1].startswith("[EXECUTE ENGINE ENTRY]")

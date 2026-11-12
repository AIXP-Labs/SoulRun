"""The "pick a program" step, driven the way a model would drive it (no model is called)."""
from __future__ import annotations

import pytest

from helpers import HOST, QUESTION, commit, gate_payload, index, route_payload, take_node


def test_next_node_serves_the_pick_a_program_step(soulrun, agent):
    ctx = soulrun(user_message=QUESTION, session_id="r1", aiap="demo_aiap", **HOST)
    node = take_node(soulrun, ctx)
    assert node["node"]["name"] == "Router.match" and len(node["steps"]) == 3
    assert node["payload_skeleton"]["node"] == "Router.match"


def test_one_designated_program_that_fits_is_used(soulrun, agent):
    ctx = soulrun(user_message=QUESTION, session_id="r2", aiap="demo_aiap", **HOST)
    reply = commit(soulrun, ctx, route_payload(take_node(soulrun, ctx), "demo_aiap"))
    assert reply["status"] == "COMMITTED" and reply["next"]["node"] == "Router.cache-setup"
    assert index(ctx.cache_dir)["route"]["package"] == "demo_aiap"


def test_a_program_outside_the_candidates_is_refused_by_the_engine(soulrun, agent):
    ctx = soulrun(user_message=QUESTION, session_id="r3", aiap="demo_aiap", **HOST)
    reply = commit(soulrun, ctx, route_payload(take_node(soulrun, ctx), "other_aiap"))
    assert reply["status"] == "REJECTED"
    error = reply["errors"][0]
    assert error["code"] == "ROUTE_INVALID" and error["expected"] == ["demo_aiap", "no_match"]
    assert index(ctx.cache_dir)["route"]["package"] is None


def test_two_fitting_programs_open_a_gate_and_the_answer_comes_back_through_the_same_call(soulrun, agent):
    ctx = soulrun(user_message=QUESTION, session_id="r4", aiap="demo_aiap", aisp="demo_aisp", **HOST)
    reply = commit(soulrun, ctx, gate_payload(take_node(soulrun, ctx), ["demo_aiap", "demo_aisp"], "demo_aiap"))
    assert reply["status"] == "WAITING_USER" and index(ctx.cache_dir)["run_state"] == "WAITING_USER"

    answered = soulrun(user_message="1", session_id="r4", **HOST)
    assert answered.cache_dir == ctx.cache_dir and answered.entry_mode == "resume" and answered.kind == "program"
    assert answered.data["gate_answer"]["status"]

    again = take_node(soulrun, answered)
    assert again["node"]["name"] == "Router.match"
    assert again["input_authority"]["gate_answer"]["chosen_intent"] == "demo_aiap"

    done = commit(soulrun, answered, route_payload(again, "demo_aiap", "按你的选择，用 demo_aiap。"))
    assert done["status"] == "COMMITTED" and index(ctx.cache_dir)["route"]["package"] == "demo_aiap"


def test_the_answer_can_also_name_the_run_by_cache_dir(soulrun, agent):
    ctx = soulrun(user_message=QUESTION, session_id="r5", aiap="demo_aiap", aisp="demo_aisp", **HOST)
    commit(soulrun, ctx, gate_payload(take_node(soulrun, ctx), ["demo_aiap", "demo_aisp"], "demo_aiap"))
    answered = soulrun(user_message="2", session_id="r5", cache_dir=ctx.cache_dir, **HOST)
    assert answered.cache_dir == ctx.cache_dir and answered.entry_mode == "resume"
    assert take_node(soulrun, answered)["input_authority"]["gate_answer"]["chosen_intent"] == "demo_aisp"


def test_a_designated_program_that_does_not_fit_becomes_a_direct_reply(soulrun, agent):
    """The design: whether a program fits is the engine's Router.match to decide; SoulRun adds no judgement and opens
    no gate. A designated program that does not fit is never swapped for another: "no_match" is accepted and the run
    goes on to a direct reply."""
    ctx = soulrun(user_message="帮我写一首关于秋天的诗", session_id="r6", aiap="demo_aiap", **HOST)
    reply = commit(soulrun, ctx, route_payload(take_node(soulrun, ctx), "no_match", "指定的程序做不了这件事。"))
    assert reply["status"] == "COMMITTED" and reply["next"]["node"] == "DirectReply"


def test_a_message_not_from_the_human_cannot_answer_an_open_gate(soulrun, agent):
    """While a run waits at a gate, SoulRun refuses a turn marked as not the human's (HUMAN_REPLY_REQUIRED) before
    the engine sees it: the gate and the run's index stay as they were."""
    ctx = soulrun(user_message=QUESTION, session_id="r9", aiap="demo_aiap", aisp="demo_aisp", **HOST)
    commit(soulrun, ctx, gate_payload(take_node(soulrun, ctx), ["demo_aiap", "demo_aisp"], "demo_aiap"))
    before = index(ctx.cache_dir)
    with pytest.raises(soulrun.UsageError) as error:
        soulrun(user_message="1", session_id="r9", human_turn=False, **HOST)
    assert error.value.code == "HUMAN_REPLY_REQUIRED" and index(ctx.cache_dir) == before


@pytest.mark.parametrize('wrong_route', ['demo_aisp', 'no_match'])
def test_human_program_choice_binds_the_route(soulrun, agent, wrong_route):
    """Keep the former engine-today regression as a rejection, not an accepted authorization gap."""
    ctx = soulrun(user_message=QUESTION, session_id="r7", aiap="demo_aiap", aisp="demo_aisp", **HOST)
    commit(soulrun, ctx, gate_payload(take_node(soulrun, ctx), ["demo_aiap", "demo_aisp"], "demo_aiap"))
    answered = soulrun(user_message="1", session_id="r7", **HOST)
    again = take_node(soulrun, answered)
    assert again["input_authority"]["gate_answer"]["chosen_intent"] == "demo_aiap"
    before = index(ctx.cache_dir)
    reply = commit(soulrun, answered, route_payload(again, wrong_route, "改用另一个。"))
    assert reply['status'] == 'REJECTED' and reply['errors'][0]['code'] == 'ROUTE_CHOICE_CONFLICT'
    assert reply['errors'][0]['expected'] == 'demo_aiap'
    assert index(ctx.cache_dir) == before
    correct = commit(soulrun, answered, route_payload(again, 'demo_aiap'))
    assert correct['status'] == 'COMMITTED' and index(ctx.cache_dir)['route']['package'] == 'demo_aiap'

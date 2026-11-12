"""Which programs are candidates: the arguments only decide the list; the engine's main program picks from it."""
from __future__ import annotations

from conftest import AIAP_DOC, write_json
from helpers import HOST, QUESTION, candidates, runs, take_node


def test_nothing_designated_uses_everything_under_the_agent_folder(soulrun, agent):
    ctx = soulrun(user_message=QUESTION, session_id="c1", **HOST)
    assert candidates(ctx) == ["demo_aiap", "demo_aisp", "other_aiap"]


def test_one_designated_aiap_by_path(soulrun, agent):
    ctx = soulrun(user_message=QUESTION, session_id="c2", aiap=agent / "aiap" / "demo_aiap", **HOST)
    assert candidates(ctx) == ["demo_aiap"]


def test_one_designated_aisp_by_name_is_looked_up_in_the_big_folder(soulrun, agent):
    ctx = soulrun(user_message=QUESTION, session_id="c3", aisp="demo_aisp", **HOST)
    assert candidates(ctx) == ["demo_aisp"]


def test_both_designated_gives_exactly_those_two(soulrun, agent):
    ctx = soulrun(user_message=QUESTION, session_id="c4", aiap="demo_aiap", aisp="demo_aisp", **HOST)
    assert candidates(ctx) == ["demo_aiap", "demo_aisp"]


def test_designated_plus_big_folders_uses_the_designated_only(soulrun, agent):
    ctx = soulrun(user_message=QUESTION, session_id="c5", aiap="demo_aiap",
                  aiap_dir=agent / "aiap", aisp_dir=agent / "aisp", **HOST)
    assert candidates(ctx) == ["demo_aiap"]


def test_big_folders_elsewhere(soulrun, agent, tmp_path):
    elsewhere = tmp_path / "elsewhere"
    write_json(elsewhere / "programs" / "far_aiap" / "main.aisop.json", AIAP_DOC)
    (elsewhere / "skills").mkdir()
    ctx = soulrun(user_message=QUESTION, session_id="c6", aiap_dir=elsewhere / "programs", aisp_dir=elsewhere / "skills", **HOST)
    assert candidates(ctx) == ["far_aiap"]
    assert ctx.places["sources"]["aiap_dir"] == "argument"


def test_a_designated_program_keeps_its_real_location(soulrun, agent):
    """The engine must read the designated program where it is, not from a copy."""
    ctx = soulrun(user_message=QUESTION, session_id="c7", aiap="demo_aiap", aisp="demo_aisp", **HOST)
    node = take_node(soulrun, ctx)
    assert node["node"]["name"] == "Router.match"
    assert sorted(item["package"] for item in node["input_authority"]["registry_snapshot"]) == ["demo_aiap", "demo_aisp"]
    from helpers import run_input
    dirs = sorted(item["dir"].replace("\\", "/") for item in run_input(ctx)["snapshot"])
    assert dirs[0].endswith("agent/aiap/demo_aiap") and dirs[1].endswith("agent/aisp/demo_aisp")


def test_a_designated_program_is_enough_without_any_big_folder(soulrun, agent, tmp_path, monkeypatch):
    """A caller may have just one program somewhere and an otherwise empty working folder."""
    work = tmp_path / "empty_work"
    work.mkdir()
    monkeypatch.chdir(work)
    ctx = soulrun(user_message=QUESTION, session_id="c10", aiap=agent / "aiap" / "demo_aiap", **HOST)
    assert candidates(ctx) == ["demo_aiap"] and take_node(soulrun, ctx)["node"]["name"] == "Router.match"
    assert sorted(p.name for p in work.iterdir()) == [".soulrun_cache"]


def test_a_designated_program_may_be_given_as_a_relative_path_or_as_its_entry_file(soulrun, agent):
    relative = soulrun(user_message=QUESTION, session_id="c11", aiap="./aiap/demo_aiap", **HOST)
    by_file = soulrun(user_message=QUESTION, session_id="c12", aisp=agent / "aisp" / "demo_aisp" / "aisp.aisop.json", **HOST)
    assert candidates(relative) == ["demo_aiap"] and candidates(by_file) == ["demo_aisp"]


def test_a_designated_name_that_is_not_found_opens_a_doubt_and_creates_nothing(soulrun, agent):
    ctx = soulrun(user_message=QUESTION, session_id="c8", aiap="demo_aiapp", **HOST)
    assert ctx.kind == "text_only" and ctx.entry_mode == "soulrun_doubt" and ctx.cache_dir is None
    assert ctx.doubt["code"] == "DESIGNATED_NOT_FOUND" and ctx.doubt["recommendation"] == "demo_aiap"
    assert ctx.doubt["present"] == ["demo_aiap", "other_aiap"]
    assert "找不到" in ctx.text and "demo_aiap" in ctx.text and "建议" in ctx.text and "取消" in ctx.text
    assert runs(agent / ".soulrun_cache") == []
    use_close, name_another, cancel = ctx.doubt["options"]
    assert [o["number"] for o in ctx.doubt["options"]] == [1, 2, 3]
    assert use_close["action"] == "call" and use_close["arguments"] == {"aiap": "demo_aiap"}
    assert name_another["action"] == "ask" and cancel["action"] == "cancel"
    # SoulRun keeps no memory of the question; the caller carries the human's choice back with the same message.
    chosen = soulrun(user_message=QUESTION, session_id="c8", **use_close["arguments"], **HOST)
    assert chosen.kind == "program" and candidates(chosen) == ["demo_aiap"]


def test_the_doubt_is_written_in_the_language_of_the_message(soulrun, agent):
    ctx = soulrun(user_message="Please run the demo and say hello", session_id="c9", aisp="nope", **HOST)
    assert ctx.kind == "text_only" and "was not found" in ctx.text and "Cancel" in ctx.text
    assert ctx.doubt["recommendation"] is None

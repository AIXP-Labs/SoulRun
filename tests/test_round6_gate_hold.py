"""docs/05SoulRun 90 round 6 (ledger decisions 183 and 185; 'vc 2' and 'vc 3' defect 1): a turn that is not the human's
(human_turn False - a schedule, another agent) to a run whose engine stop was cut off before its index write is refused
by soulrun.run exactly as at the run that never crashed, waiting at that stop: HUMAN_REPLY_REQUIRED, nothing written.

The engine's own stop is cut off here the way the engine's tests cut it off (its record lands, the process dies before the
index write), in SoulRun's bundled engine: the program-integrity stop, which needs no sub-agent - the program's files
change while the run is at a node. The run that never crashed is the same run, copied before the cut, whose next step
showed the stop. No model is called."""
from __future__ import annotations

import copy
import json
import shutil
import sys
from pathlib import Path

import pytest

from helpers import HOST, QUESTION, commit, route_payload, take_node


class Died(BaseException):
    """The process dies (simulated): no engine handler sees it."""


def _files(root: Path) -> dict:
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}


def _at_start(soulrun, agent, session: str):
    """A run of demo_aiap at its Start node (RUNNING): Router.match and Router.cache-setup committed, Start served."""
    ctx = soulrun(user_message=QUESTION, session_id=session, aiap="demo_aiap", **HOST)
    assert commit(soulrun, ctx, route_payload(take_node(soulrun, ctx), "demo_aiap"))["status"] == "COMMITTED"
    served = take_node(soulrun, ctx)
    payload = copy.deepcopy(served["payload_skeleton"])
    payload.update(output="Start", user_summary="打招呼的请求走 Start。", outer_nodes_in_path=["Start"])
    reply = commit(soulrun, ctx, payload, node="Router.cache-setup")
    assert reply["status"] == "COMMITTED" and reply["next"]["node"] == "Start", reply
    assert take_node(soulrun, ctx)["node"]["name"] == "Start"
    return ctx


def _cut_off(soulrun, agent, tmp_path, monkeypatch, session: str = "h1"):
    """The run at Start; the program's files change; on a copy of the agent folder the next step opens the integrity stop
    and shows it (the run that never crashed); on the run itself the stop's record lands and the process dies before its
    index write. Returns (the run, the copy's agent folder and run, the cut-off stop's id)."""
    from soulrun import host
    core, guard, store_mod = host.engine("lib.engine_core"), host.engine("lib.program_guard"), host.engine("lib.run_store")
    ctx = _at_start(soulrun, agent, session)
    program = agent / "aiap" / "demo_aiap" / "main.aisop.json"
    doc = json.loads(program.read_text(encoding="utf-8"))
    doc[1]["content"]["functions"]["Start"]["step1"] = "做（改过）"
    program.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    twin_agent = tmp_path / "twin"
    shutil.copytree(agent, twin_agent)
    twin = twin_agent / Path(ctx.cache_dir).relative_to(agent)
    shown = core.serve(twin)
    assert shown["status"] == "WAITING_USER" and (shown.get("gate") or {}).get("public_prompt_ref"), shown
    real, fired = store_mod.RunStore.write_json_once, []

    def once(self, path, obj):
        out = real(self, path, obj)
        if not fired and sys._getframe(1).f_code is guard.pause.__code__:
            fired.append(path.name)
            raise Died(f"the process died right after {path.name} landed")
        return out
    with monkeypatch.context() as m:
        m.setattr(store_mod.RunStore, "write_json_once", once)
        with pytest.raises(Died):
            core.serve(ctx.cache_dir)
    store = store_mod.RunStore(ctx.cache_dir)
    index = store.read_index()
    known = {row["question_id"] for row in index["gate"]["history"]}
    orphans = [p.stem.removeprefix("_gate.") for p in Path(ctx.cache_dir).glob("_gate.q*.json")
               if p.stem.removeprefix("_gate.") not in known]
    assert index["run_state"] == "RUNNING" and len(orphans) == 1 and fired == [f"_gate.{orphans[0]}.json"]
    assert store_mod.RunStore(twin).read_index()["run_state"] == "WAITING_USER"
    return ctx, twin_agent, twin, orphans[0]


@pytest.mark.parametrize("message", ["取消", "继续", "2", "scheduled report: all good"])
def test_a_machine_turn_to_a_run_cut_off_at_its_stop_is_refused_as_at_the_stop(soulrun, agent, tmp_path, monkeypatch, message):
    """Until round 6 the engine held such a turn (gate_hold) and SoulRun handed it to the model as a program turn, whose
    next-node installed the stop and showed it from a turn that was not the human's. Now both runs refuse it alike, before
    the engine is called: the same error, and not a byte changes in either agent folder. The human's next message re-enters
    the run and its next step shows the stop first."""
    from soulrun import host
    ctx, twin_agent, twin, qid = _cut_off(soulrun, agent, tmp_path, monkeypatch)
    before = (_files(agent), _files(twin_agent))
    errors = []
    for folder in (agent, twin_agent):
        with pytest.raises(soulrun.UsageError) as raised:
            soulrun(user_message=message, session_id="h1", agent_dir=folder, human_turn=False, origin_type="scheduled", **HOST)
        errors.append(raised.value)
    assert errors[0].code == "HUMAN_REPLY_REQUIRED" and errors[0].as_dict() == errors[1].as_dict()
    assert str(errors[0]) == str(errors[1]) and (_files(agent), _files(twin_agent)) == before
    human = soulrun(user_message=message, session_id="h1", agent_dir=agent, **HOST)
    assert human.cache_dir == ctx.cache_dir and human.entry_mode == "recovery" and human.kind == "program"
    shown = host.engine("lib.engine_core").serve(ctx.cache_dir)
    assert shown["gate"]["question_id"] == qid and shown["gate"]["public_prompt_ref"]


def test_with_the_switch_on_a_machine_turn_goes_to_the_engine_as_before(soulrun, agent, tmp_path, monkeypatch):
    """Problem 89 (open): with SOULBOT_RESUME_INTERRUPTED_RUNS on nothing changes - the machine's cancel word ends the run."""
    ctx, twin_agent, twin, qid = _cut_off(soulrun, agent, tmp_path, monkeypatch)
    monkeypatch.setenv("SOULBOT_RESUME_INTERRUPTED_RUNS", "true")
    ended = soulrun(user_message="取消", session_id="h1", agent_dir=agent, human_turn=False, **HOST)
    assert ended.entry_mode == "terminal" and ended.kind == "text_only"


def test_a_hold_the_engine_still_returns_is_refused_never_a_program_turn(soulrun, agent, tmp_path, monkeypatch):
    """Should SoulRun's own check miss the cut-off stop (or the run reach a gate between its check and the engine's), the
    engine holds the turn (gate_hold): SoulRun refuses it all the same."""
    from soulrun import _api
    ctx, twin_agent, twin, qid = _cut_off(soulrun, agent, tmp_path, monkeypatch)
    monkeypatch.setattr(_api, "_waits_at_a_cut_off_stop", lambda *args, **kwargs: False, raising=False)
    with pytest.raises(soulrun.UsageError) as raised:
        soulrun(user_message="scheduled report: all good", session_id="h1", agent_dir=agent, human_turn=False, **HOST)
    assert raised.value.code == "HUMAN_REPLY_REQUIRED"
    life = json.loads((Path(ctx.cache_dir) / "_host_lifecycle.json").read_text(encoding="utf-8"))
    assert life["entry_mode"] == "gate_hold" and not list((Path(ctx.cache_dir) / "_public").glob(f"menu.{qid}.*"))

"""What a host does around a model turn: the named doors pass straight through to the engine."""
from __future__ import annotations

import json
import os
from pathlib import Path

from helpers import HOST, QUESTION, commit, gate_payload, take_node

# The engine modules SoulBot's host loads by name today (importlib.import_module after a sys.path insert).
# With SoulRun each of them is soulrun.host.engine("<name>").
HOST_MODULES = ("lib.render", "lib.dispatch_resource_context", "lib.menu_history", "lib.partial_commit",
                "prepare_cache", "checkpoint_recovery", "public_delivery_observer", "user_gate_audit",
                "lib.engine_core", "lib.run_store", "lib.stop_state", "lib.stop_flow", "lib.supply_flow")


def test_after_turn_records_what_was_said_and_that_it_was_stored(soulrun, agent):
    from soulrun import host
    ctx = soulrun(user_message=QUESTION, session_id="h1", **HOST)
    result = host.after_turn(ctx.cache_dir, "（模拟）模型的回答")
    assert result["run_state"] == "RUNNING"
    assert result["observed"]["public_chars"] == len("（模拟）模型的回答") and len(result["observed"]["public_sha256"]) == 64
    files = {p.name for p in Path(ctx.cache_dir).iterdir()}
    assert {"_delivery.json", "_host_lifecycle.json"} <= files


def _gate(soulrun, session_id: str) -> tuple:
    ctx = soulrun(user_message=QUESTION, session_id=session_id, aiap="demo_aiap", aisp="demo_aisp", **HOST)
    reply = commit(soulrun, ctx, gate_payload(take_node(soulrun, ctx), ["demo_aiap", "demo_aisp"], "demo_aiap"))
    assert reply["status"] == "WAITING_USER" and reply["gate"]["public_prompt_ref"]
    return ctx, reply["gate"]


def test_observe_notices_that_a_gates_menu_was_shown_and_only_then(soulrun, agent):
    """The engine records a gate's menu as delivered only when the reply carries it - the menu as the human reads it,
    or the engine's reference to it - never for a reply without it, nor for its question alone."""
    from soulrun import host
    ctx, gate = _gate(soulrun, "h2")
    for reply in ("我先想一想。", "有两个程序都能做这件事，用哪一个？"):               # no menu; the question without its options
        seen = host.observe(ctx.cache_dir, reply)["gate_delivery"]
        assert seen["question_id"] == gate["question_id"] and seen["observed"] is False and not seen["delivered_at"]
    menu = host.expand_refs(gate["public_prompt_ref"], cache_dir=ctx.cache_dir)
    assert menu != gate["public_prompt_ref"] and "demo_aisp" in menu
    seen = host.observe(ctx.cache_dir, "请选择：\n" + menu)["gate_delivery"]
    assert seen["observed"] is True and seen["basis"] == "menu_verbatim" and seen["delivered_at"]

    other, gate = _gate(soulrun, "h2b")
    seen = host.observe(other.cache_dir, "请选择：\n" + gate["public_prompt_ref"])["gate_delivery"]
    assert seen["observed"] is True and seen["basis"] == "menu_ref" and seen["delivered_at"]


def test_interrupted_runs_and_the_text_that_re_enters_one(soulrun, agent):
    from soulrun import host
    ctx = soulrun(user_message=QUESTION, session_id="h3", **HOST)
    rows = host.interrupted_runs()
    assert [Path(row["cache_dir"]).resolve() for row in rows] == [Path(ctx.cache_dir).resolve()]
    assert rows[0]["session_id"] == "h3"
    host.mark_interrupted(ctx.cache_dir)
    prompt = host.resume_prompt(ctx.cache_dir)
    engine_dir = Path(soulrun.engine_info()["engine_dir"]).resolve()
    assert prompt.startswith("[EXECUTE ENGINE RECOVERY]\n")
    assert f"engine_dir: {engine_dir}" in prompt and f"cache_dir: {Path(ctx.cache_dir)}" in prompt
    assert str(engine_dir / "python_tools" / "next_node.py") in prompt


def test_the_recovery_text_re_enters_the_same_run_through_the_one_call(soulrun, agent, monkeypatch):
    """The path for SOULBOT_RESUME_INTERRUPTED_RUNS=true. With the switch off (the default) a host opens a restart
    question instead (tests/test_full_host.py): the re-entry text itself does not look at the switch."""
    from soulrun import host
    monkeypatch.setenv("SOULBOT_RESUME_INTERRUPTED_RUNS", "true")
    assert host.resume_interrupted_enabled() is True
    ctx = soulrun(user_message=QUESTION, session_id="h4", **HOST)
    again = soulrun(user_message=host.resume_prompt(ctx.cache_dir), session_id="h4", origin_type="engine_recovery",
                    human_turn=False, **HOST)
    assert again.cache_dir == ctx.cache_dir and again.entry_mode == "recovery" and again.data.get("recovery_reentry") is True


def test_latest_run_and_cache_root(soulrun, agent):
    from soulrun import host
    ctx = soulrun(user_message=QUESTION, session_id="h5", **HOST)
    assert host.cache_root().resolve() == (agent / ".soulrun_cache" / ".execution_cache").resolve()
    assert host.latest_run("h5").resolve() == Path(ctx.cache_dir).resolve() and host.latest_run("nobody") is None


def test_runner_recovery_finds_the_run_in_the_data_folder_and_points_the_text_at_the_program(soulrun, agent):
    from types import SimpleNamespace

    from soulrun import host
    ctx = soulrun(user_message=QUESTION, session_id="h6", **HOST)
    request = SimpleNamespace(phase="plan", session_id="h6", error_code="ACP_PROCESS_EXIT", recovery_token=None,
                              invocation_id="inv-1", error_details={})
    planned = host.runner_recovery(request)
    assert planned["action"] == "resume" and planned["recovery_token"] and planned["prompt"] == "", planned
    request.phase, request.recovery_token = "start", planned["recovery_token"]
    decision = host.runner_recovery(request)
    prompt = decision.get("prompt") or ""
    assert decision["action"] == "resume" and prompt.startswith("[EXECUTE ENGINE RECOVERY]\n"), decision
    engine_dir = Path(soulrun.engine_info()["engine_dir"]).resolve()
    lines = prompt.split("\n")
    assert lines[1] == f"engine_dir: {engine_dir}"
    assert lines[2] == f"cache_dir: {Path(ctx.cache_dir).resolve()}"
    assert str(engine_dir / "python_tools" / "next_node.py") in prompt
    assert str(agent.resolve() / ".soulrun_cache" / "python_tools") not in prompt


def test_the_resume_switch_defaults_to_stop_and_ask(soulrun, monkeypatch):
    from soulrun import host
    assert host.resume_interrupted_enabled() is False
    monkeypatch.setenv("SOULBOT_RESUME_INTERRUPTED_RUNS", "true")
    assert host.resume_interrupted_enabled() is True


def test_a_host_asks_where_the_data_and_the_program_are_instead_of_knowing_folder_names(soulrun, agent, tmp_path):
    from soulrun import host
    ctx = soulrun(user_message=QUESTION, session_id="h9", **HOST)
    data = host.soulrun_cache_dir(agent_dir=agent)
    assert data == Path(ctx.places["soulrun_cache_dir"]) and Path(ctx.cache_dir).parent == host.cache_root(agent_dir=agent) == data / ".execution_cache"
    assert host.soulrun_cache_dir(soulrun_cache_dir=tmp_path / "elsewhere") == (tmp_path / "elsewhere").resolve()
    assert host.soulrun_cache_dir(soulrun_cache_dir=data) == data                    # handing its answer back gives it back
    program = host.program_root()
    assert (program / "python_tools" / "next_node.py").is_file() and (program / "main.aisop.json").is_file()
    assert f"engine_dir: {program.resolve()}" in ctx.text
    assert agent.resolve() not in program.resolve().parents                  # the program is not inside the agent folder


def test_asking_about_an_agent_that_never_ran_leaves_no_folder_behind(soulrun, tmp_path):
    """A host asks every agent at start-up which runs were cut off; an agent that never ran gets no run folder."""
    from conftest import make_agent
    from soulrun import host
    fresh = make_agent(tmp_path / "never_ran")
    before = sorted(p.relative_to(fresh).as_posix() for p in fresh.rglob("*"))
    assert host.interrupted_runs(agent_dir=fresh) == [] and host.latest_run("default", agent_dir=fresh) is None
    assert host.soulrun_cache_dir(agent_dir=fresh) == fresh.resolve() / ".soulrun_cache"
    assert host.cache_root(agent_dir=fresh) == fresh.resolve() / ".soulrun_cache" / ".execution_cache"
    assert sorted(p.relative_to(fresh).as_posix() for p in fresh.rglob("*")) == before
    soulrun(user_message=QUESTION, agent_dir=fresh, **HOST)                  # the first run makes it, with its .gitignore
    assert (fresh / ".soulrun_cache" / ".gitignore").is_file()


def test_every_engine_module_a_soulbot_host_loads_by_name_comes_through_the_host_door(soulrun):
    from soulrun import _engine, host
    for name in HOST_MODULES:
        module = host.engine(name)
        assert _engine.ENGINE_DIR.resolve() in Path(module.__file__).resolve().parents, name
        assert host.engine(name) is module                                   # loaded once, the same module every time


def test_the_list_of_host_modules_covers_what_soulbot_loads_today():
    """SoulBot's host source when it is beside this repository, else the list recorded from it in the samples."""
    import soulbot_side
    loaded = set(soulbot_side.host_modules())
    assert loaded, "found no engine import in SoulBot: has the host changed how it loads the engine?"
    assert loaded <= set(HOST_MODULES), sorted(loaded - set(HOST_MODULES))


def test_soulrun_host_can_be_reached_after_a_plain_import(subprocess_env):
    """`import soulrun` and then `soulrun.host....`, as the SoulBot integration guide writes it: the host doors are
    loaded the first time they are asked for, not at import."""
    import subprocess
    import sys
    code = ("import sys, soulrun; assert 'soulrun.host' not in sys.modules; "
            "print(soulrun.host.program_root().name, soulrun.host is sys.modules['soulrun.host'])")
    done = subprocess.run([sys.executable, "-B", "-c", code], env=subprocess_env, capture_output=True, text=True, encoding="utf-8")
    assert done.returncode == 0 and done.stdout.split() == ["soulrun_aiap", "True"], done.stdout + done.stderr


def _fresh(subprocess_env, code: str, *paths) -> str:
    import subprocess
    import sys
    env = dict(subprocess_env)
    if paths:
        env["PYTHONPATH"] = os.pathsep.join([*map(str, paths), env.get("PYTHONPATH", "")])
    done = subprocess.run([sys.executable, "-B", "-c", code], env=env, capture_output=True, text=True, encoding="utf-8")
    assert done.returncode == 0, done.stdout + done.stderr
    return done.stdout.strip()


def test_a_name_the_engine_uses_already_taken_by_the_host_is_named_not_used(soulrun, agent, tmp_path, subprocess_env):
    """The engine's tools import each other by top-level names (lib, prepare_cache, checkpoint_recovery ...). A host's
    own module of one of those names - even one the engine only imports indirectly - is reported, never used."""
    (tmp_path / "hosts" / "lib").mkdir(parents=True)
    (tmp_path / "hosts" / "lib" / "__init__.py").write_text("HOSTS_OWN = True\n", encoding="utf-8")
    (tmp_path / "hosts" / "checkpoint_recovery.py").write_text("HOSTS_OWN = True\n", encoding="utf-8")
    call = ("import os, soulrun\nos.chdir({agent!r})\ntry:\n    soulrun(user_message='hi', session_id='x', host_tools={{'agent': False}})\n"
            "except soulrun.SoulRunError as error:\n    print(error.code, error.field)\n")
    first_lib = "import lib\n" + call.format(agent=str(agent))
    assert _fresh(subprocess_env, first_lib, tmp_path / "hosts") == "ENGINE_NAME_CLASH lib"
    first_other = "import checkpoint_recovery\n" + call.format(agent=str(agent))
    assert _fresh(subprocess_env, first_other, tmp_path / "hosts") == "ENGINE_NAME_CLASH checkpoint_recovery"


def test_host_engine_refuses_a_name_that_is_not_an_engine_module_before_importing_it(subprocess_env):
    code = ("import sys, soulrun\nfrom soulrun import host\ntry:\n    host.engine('this')\nexcept soulrun.SoulRunError as error:\n"
            "    print(error.code, 'this' in sys.modules)\n")
    assert _fresh(subprocess_env, code) == "ENGINE_MODULE_UNKNOWN False"     # the Zen of Python was never printed


# ---- sub-agents: what a qualified host observes and reports (docs/05SoulRun 87, #12) ----------------------------------
# Each door, the engine function it passes straight through to, and one call as a host makes it: the arguments the door
# is given and those the engine function must receive (positional, keyword).
_AT = "2026-10-28T00:00:00Z"
_CHILD = "child-01234567"
DISPATCH_DOORS = {
    "dispatches_nodes": ("lib.dispatch_scope", "enabled", (
        (({"program": {"loading_mode": "node"}},), {}), (({"program": {"loading_mode": "node"}},), {}))),
    "observe_agent_start": ("lib.engine_core", "observe_dispatch_start", (
        (("RUN", "a" * 64), dict(session_id="s", tool_call_id="c", event_id="e", at=_AT, resume_agent_id=_CHILD,
                                 policy_ref="b" * 64)),
        (("RUN", "a" * 64), dict(session_id="s", tool_call_id="c", event_id="e", at=_AT, resume_agent_id=_CHILD,
                                 policy_ref="b" * 64)))),
    "observe_agent_return": ("lib.engine_core", "record_dispatch_return", (
        (("RUN", "d001"), dict(session_id="s", tool_call_id="c", event_id="e", at=_AT, status="completed",
                               agent_id=_CHILD, completion_tool_call_id="poll", observation={"x": 1})),
        (("RUN", "d001"), dict(session_id="s", tool_call_id="c", event_id="e", at=_AT, status="completed",
                               agent_id=_CHILD, completion_tool_call_id="poll", observation={"x": 1})))),
    "observe_agent_task_event": ("lib.engine_core", "record_dispatch_task_event", (
        (("RUN",), dict(session_id="s", agent_id=_CHILD, tool_call_id="c", event_id="e", at=_AT,
                        event_type="task_notification", status="failed")),
        (("RUN",), dict(session_id="s", agent_id=_CHILD, tool_call_id="c", event_id="e", at=_AT,
                        event_type="task_notification", status="failed")))),
    "observe_resume_failure": ("lib.engine_core", "record_dispatch_resume_failure", (
        (("RUN", "d001"), dict(session_id="s", agent_id=_CHILD, tool_call_id="c", event_id="e", at=_AT)),
        (("RUN", "d001"), dict(session_id="s", agent_id=_CHILD, tool_call_id="c", event_id="e", at=_AT)))),
    "resumed_agent_start": ("lib.engine_core", "native_resume_start", (
        (("RUN",), dict(session_id="s", agent_id=_CHILD, bootstrap_sha256="a" * 64)),
        (("RUN",), dict(session_id="s", agent_id=_CHILD, bootstrap_sha="a" * 64)))),
    "parent_policy_ref": ("lib.engine_core", "native_parent_policy", ((("RUN", "s"), {}), (("RUN", "s"), {}))),
    "observe_tool_request": ("lib.dispatch_resource_context", "record_request", (
        (("RUN", "d001"), dict(parent_session_id="s", parent_tool_call_id="p", tool_call_id="c", tool_name="Read",
                               raw_input={"file_path": "x"}, event_id="e", at=_AT, native_parent_tool_call_id="n")),
        (("RUN", "d001"), dict(parent_session_id="s", parent_tool_call_id="p", tool_call_id="c", tool_name="Read",
                               raw_input={"file_path": "x"}, event_id="e", at=_AT, native_parent_tool_call_id="n")))),
    "observe_tool_result": ("lib.dispatch_resource_context", "record_result", (
        (("RUN", "d001"), dict(parent_session_id="s", parent_tool_call_id="p", tool_call_id="c", tool_name="Read",
                               status="completed", event_id="e", at=_AT, native_parent_tool_call_id=None)),
        (("RUN", "d001"), dict(parent_session_id="s", parent_tool_call_id="p", tool_call_id="c", tool_name="Read",
                               status="completed", event_id="e", at=_AT, native_parent_tool_call_id=None)))),
    "resolve_tool_parent": ("lib.dispatch_resource_context", "resolve_parent", (
        (("RUN", "d001"), dict(parent_session_id="s", parent_tool_call_id="p", native_parent_tool_call_id="n")),
        (("RUN", "d001"), dict(parent_session_id="s", parent_tool_call_id="p", native_parent_tool_call_id="n")))),
}


def test_every_dispatch_door_passes_straight_through_to_the_engine_function_it_names(soulrun, monkeypatch):
    """A host reports what it saw of sub-agents through named doors (docs/05SoulRun 87, #12): no door decides anything,
    each hands its arguments to the engine function and its answer back."""
    from soulrun import host
    for door, (module_name, function, (given, expected)) in DISPATCH_DOORS.items():
        assert door in host.__all__, door
        seen = []
        module = host.engine(module_name)
        monkeypatch.setattr(module, function, lambda *args, _door=door, _seen=seen, **kwargs: _seen.append((args, kwargs))
                            or {"answer": _door})
        assert getattr(host, door)(*given[0], **given[1]) == {"answer": door}, door
        assert seen == [expected], (door, seen)


def test_an_engine_error_comes_out_of_a_dispatch_door_as_soulruns(soulrun, monkeypatch):
    from soulrun import host
    core = host.engine("lib.engine_core")

    def refuse(*args, **kwargs):
        raise core.EngineError("DISPATCH_CONCURRENT_EXECUTOR", "A different Agent already owns this segment.")
    monkeypatch.setattr(core, "observe_dispatch_start", refuse)
    try:
        host.observe_agent_start("RUN", "a" * 64, session_id="s", tool_call_id="c", event_id="e", at=_AT)
    except soulrun.SoulRunError as error:
        assert error.code == "DISPATCH_CONCURRENT_EXECUTOR" and isinstance(error.__cause__, core.EngineError)
    else:
        raise AssertionError("the engine's refusal did not come out")


def test_the_dispatch_doors_reach_the_real_engine_on_a_run(soulrun, agent):
    """On a run that hands no node to a sub-agent, the engine binds nothing a host reports - and says so."""
    from soulrun import host
    ctx = soulrun(user_message=QUESTION, session_id="h10", **HOST)
    run = ctx.cache_dir
    index = json.loads((Path(run) / "_index.json").read_text(encoding="utf-8"))
    assert host.dispatches_nodes(index) is False
    assert host.observe_agent_start(run, "a" * 64, session_id="s", tool_call_id="c", event_id="e", at=_AT) == {"status": "NOT_APPLICABLE"}
    assert host.observe_agent_return(run, "d001-00000000", session_id="s", tool_call_id="c", event_id="e", at=_AT,
                                     status="completed")["status"] == "RETURN_UNVERIFIED"
    assert host.observe_agent_task_event(run, session_id="s", agent_id=_CHILD, tool_call_id="c", event_id="e", at=_AT,
                                         event_type="task_started")["status"] == "RETURN_UNVERIFIED"
    assert host.observe_resume_failure(run, "d001-00000000", session_id="s", agent_id=_CHILD, tool_call_id="c",
                                       event_id="e", at=_AT)["status"] == "DELIVERY_FAILURE_UNBOUND"
    assert host.resumed_agent_start(run, session_id="s", agent_id=_CHILD, bootstrap_sha256="a" * 64) is None
    assert host.parent_policy_ref(run, "s") is None
    tool = dict(parent_session_id="s", parent_tool_call_id="p", tool_call_id="c", tool_name="Read", event_id="e", at=_AT)
    assert host.observe_tool_request(run, "d001-00000000", raw_input={"file_path": "x"}, **tool) ==         {"status": "NOT_APPLICABLE", "tool_permission_granted": False}
    assert host.observe_tool_result(run, "d001-00000000", status="completed", **tool) ==         {"status": "REQUEST_UNBOUND", "tool_permission_granted": False}


def test_every_dispatch_door_is_in_the_interface_check(soulrun, monkeypatch):
    """A newer engine that renames one of these functions, or drops a parameter a door passes, is found by
    soulrun --doctor and tools/upgrade_engine.py before a host meets it in a run."""
    import inspect

    from soulrun import _engine, host
    for door, (module_name, function, (_, (_, keywords))) in DISPATCH_DOORS.items():
        listed = _engine.INTERFACE.get(module_name, {})
        assert function in listed, (door, module_name, function)
        assert set(keywords) <= set(listed[function] or ()), (door, sorted(set(keywords) - set(listed[function] or ())))
        door_keywords = [name for name, p in inspect.signature(getattr(host, door)).parameters.items()
                         if p.kind is p.KEYWORD_ONLY]
        assert len(door_keywords) == len(keywords), (door, door_keywords, keywords)
    assert _engine.interface_problems() == []
    monkeypatch.delattr(host.engine("lib.engine_core"), "record_dispatch_task_event")
    monkeypatch.delattr(host.engine("lib.dispatch_resource_context"), "resolve_parent")
    problems = _engine.interface_problems()
    assert "lib.engine_core.record_dispatch_task_event: missing" in problems
    assert "lib.dispatch_resource_context.resolve_parent: missing" in problems

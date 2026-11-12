"""docs/05SoulRun 90, the step after round 7 (line F; ledger decision 189), through SoulRun itself: a business gate a
sub-agent pauses at is shown by SoulRun in any host. Its node-commit writes no menu; the main conversation calls next-node
once before it presents anything of that gate, and that next-node shows the gate (writes its menu) and serves it.

Three host set-ups run the same program - node loading mode, its node run by a sub-agent that pauses at a user_gate or at
an engine-composed hsaw_doubt gate, at the node itself or deeper in its sub-graph (scope dispatch):

- SoulRun's own command line with ``--host-tool agent=true``, as the SoulSkill bridge runs it: every step is the real
  ``soulrun`` command (a subprocess) - the turn, ``--cmd next-node`` and ``--cmd node-commit`` for the main conversation and
  the sub-agent (``--agent-ticket``). This host sees no tool call, so it reports neither the sub-agent's start nor its
  return. The main conversation's next-node prints the gate under [SOULRUN FOR THE HUMAN].
- a host that reports the return: ``soulrun.host.observe_agent_start`` when the Agent call appears and
  ``observe_agent_return`` when it ends. Decision 193: recording that return writes no menu; the main conversation's
  next-node shows the gate, just as in the other two set-ups.
- an SDK host: its task events (``observe_agent_task_event``) bind only a resumed sub-agent, so for this first segment they
  are refused and write nothing: SoulRun decides at the main next-node, as on the command line.

In all three the human answers once and it is taken, and the gate and the references the main conversation presents are
the same. A turn that dies before the main next-node holds the human's message until that next-node shows the gate.
No model is called."""
from __future__ import annotations

import copy
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

GATE = {"question": "要继续这一步吗？", "options": [{"kind": "execute", "label": "继续", "intent": "go_on"},
                                                {"kind": "cancel", "label": "取消", "intent": "cancel"}],
        "closing": "请回复编号。", "recommendation": "go_on", "advice": "建议继续：没有发现风险（建议不是选择）。",
        "explanation": "这道门决定是否继续；继续与取消的差别是是否往下做。"}
DOUBT = {"category": "doubt", "severity": "critical", "classification_uncertain": False, "escalated_from": None,
         "impact_classes": ["authorization"], "disposition": "FREEZE_NOW", "title": "目标文件已存在且内容不同",
         "description": "程序要求写入 a.txt，但它已存在且内容不同；程序没写怎么办。", "evidence_refs": ["evidence:sources"],
         "reversible": True, "classification_rationale": "继续就是替人选。", "recommendation": "none"}
HEADER = "[SOULRUN FOR THE HUMAN]"
FREE = "请帮我把这个任务接着做完"


def _program(kind: str) -> dict:
    """The program's files: node mode; its node (Start) or its sub-graph's second node run by a sub-agent."""
    system = {"protocol": "AIAP V1.0.0", "axiom_0": "Human_Sovereignty_and_Wellbeing", "id": "subdemo.main",
              "name": "Sub Demo", "version": "1.0.0", "summary": "Sub demo: a sub-agent asks the human",
              "flow_format": "mermaid", "loading_mode": "node", "trust_level": 3}
    gate = kind.endswith("user_gate")
    if kind.startswith("node"):
        start = {"step1": "问用户要不要继续", "execute_mode": "agent", "Error": "e"}
        if gate:
            start["user_gate"] = True
        return {"main.aisop.json": [{"role": "system", "content": system}, {"role": "user", "content": {
            "instruction": "ASSERT RUN aisop.main", "user_input": "{user_input}",
            "aisop": {"main": "graph TD\n    Start[入口] --> endNode((End))"}, "functions": {"Start": start}}}]}
    h2 = {"step1": "准备", "step2": 'sys.io.confirm("要继续这一步吗？") -> answer', "step3": "用答复", "Error": "e"} if gate \
        else {"step1": "汇总", "Error": "e"}
    helper = [{"role": "system", "content": dict(system, id="subdemo.helper", summary="Sub demo helper")},
              {"role": "user", "content": {"instruction": "ASSERT RUN aisop.main", "user_input": "{user_input}",
                                           "aisop": {"main": "graph TD\n    H1[收集] --> H2[汇总]\n    H2 --> endNode((End))"},
                                           "functions": {"H1": {"step1": "收集三项待办", "Error": "e"}, "H2": h2}}}]
    main = [{"role": "system", "content": system}, {"role": "user", "content": {
        "instruction": "ASSERT RUN aisop.main", "user_input": "{user_input}",
        "aisop": {"main": "graph TD\n    Start[读取] --> Plan[helper.aisop.json]\n    Plan --> endNode((End))"},
        "functions": {"Start": {"step1": "读取请求", "Error": "e"},
                      "Plan": {"step1": "委托 helper 收集与汇总", "execute_mode": "agent", "Error": "e"}}}}]
    return {"main.aisop.json": main, "helper.aisop.json": helper}


class Run:
    """One agent folder and its run, every step through the real soulrun command line (a subprocess)."""

    def __init__(self, root: Path, kind: str, env: dict):
        self.root, self.kind, self.env = root, kind, env
        self.agent = root / "agent"
        folder = self.agent / "aiap" / "subdemo"
        folder.mkdir(parents=True)
        for name, doc in _program(kind).items():
            (folder / name).write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
        self.turn("请运行 subdemo")
        self.cache = self.agent / ".soulrun_cache" / ".execution_cache" / "1"

    def soulrun(self, *args, stdin: str | None = None) -> subprocess.CompletedProcess:
        done = subprocess.run([sys.executable, "-B", "-m", "soulrun", *args], cwd=self.agent, env=self.env, input=stdin,
                              capture_output=True, text=True, encoding="utf-8")
        return done

    def turn(self, words: str) -> subprocess.CompletedProcess:
        message = self.root / "message.txt"
        message.write_text(words, encoding="utf-8")
        done = self.soulrun("--user-message-file", str(message), "--keep-message-file", "--session-id", "s1",
                            "--host-tool", "agent=true", "--channel", "cli")
        assert done.returncode == 0, done.stderr[-2000:]
        return done

    def cmd(self, name: str, *args, payload=None) -> tuple[dict, str]:
        """An engine command: (its reply, what SoulRun printed after it)."""
        stdin = None if payload is None else json.dumps(payload, ensure_ascii=False)
        done = self.soulrun("--cmd", name, "--cache-dir", str(self.cache), *args,
                            *(("--payload-stdin",) if payload is not None else ()), stdin=stdin)
        reply, end = json.JSONDecoder().raw_decode(done.stdout)
        return reply, done.stdout[end:]

    def index(self) -> dict:
        return json.loads((self.cache / "_index.json").read_text(encoding="utf-8"))

    def menus(self, qid: str) -> list[str]:
        return sorted(p.name for p in (self.cache / "_public").glob(f"menu.{qid}.*"))

    def text_of(self, ref: str) -> str | None:
        name = ref[len("⟦engine:"):-1].split("/", 1)[1]
        path = self.cache / "_public" / name
        return path.read_text(encoding="utf-8") if path.is_file() else None


def _commit(run: Run, node: str, served: dict, *, ticket: str | None = None, **fields) -> dict:
    payload = copy.deepcopy(served["payload_skeleton"])
    payload.update(fields)
    args = ("--node", node) + (("--agent-ticket", ticket) if ticket else ())
    reply, after = run.cmd("node-commit", *args, payload=payload)
    assert reply.get("status") in ("COMMITTED", "WAITING_USER"), (node, reply.get("errors"))
    run.last_after = after
    return reply


def _route(run: Run) -> dict:
    """Router.match and Router.cache-setup by the main conversation (and Start, inline, in the scope form): the last commit's
    next_plan issues the sub-agent's ticket (kept as run.dispatch_plan, with what SoulRun printed after that reply); then
    the main conversation's next-node, which names the ticket. Returns that reply."""
    served, _ = run.cmd("next-node")
    _commit(run, "Router.match", served, output="subdemo", user_summary="选定程序。",
            route={"package": "subdemo", "rationale": "The request names this program."})
    served, _ = run.cmd("next-node")
    path = ["Start"] if run.kind.startswith("node") else ["Start", "Plan"]
    last = _commit(run, "Router.cache-setup", served, output="Start", user_summary="按请求走主路径。", outer_nodes_in_path=path)
    if run.kind.startswith("scope"):
        served, _ = run.cmd("next-node")
        assert served["node"]["name"] == "Start", served["node"]
        last = _commit(run, "Start", served, output="ok", user_summary="读取了请求。", steps={"done": ["step1"], "remaining": [],
                                                                                    "not_applicable": []},
                user_message={"has": False, "items": [], "not_applicable": [], "none_reason": "这一步没有要告诉你的话。"})
    run.dispatch_plan, run.dispatch_after = last.get("next_plan") or {}, run.last_after
    issued, _ = run.cmd("next-node")
    assert (issued.get("dispatch") or {}).get("ticket"), issued
    return issued


NO_MESSAGE = {"has": False, "items": [], "not_applicable": [], "none_reason": "这一步只问一个问题，没有别的话要说。"}


def _pause(run: Run, ticket: str) -> dict:
    """The sub-agent: claims the ticket (--agent-ticket) and pauses at the business gate of the run's kind."""
    served, _ = run.cmd("next-node", "--agent-ticket", ticket)
    hsaw = run.kind.endswith("hsaw_doubt")
    if run.kind.startswith("scope"):
        assert served["node"]["name"] == "Plan/helper.H1", served["node"]
        done = _commit(run, "Plan/helper.H1", served, ticket=ticket, output={"items": 3}, user_summary="收集了三项。",
                       steps={"done": ["step1"], "remaining": [], "not_applicable": []}, user_message=NO_MESSAGE)
        served = done["next_plan"]
        assert served["node"]["name"] == "Plan/helper.H2", served["node"]
    node = served["node"]["name"]
    fields = dict(status="PARTIAL", output={}, user_summary="需要你决定。", explain="这一步要由你决定。", user_message=NO_MESSAGE)
    if hsaw:
        fields.update(steps={"done": [], "remaining": ["step1"], "not_applicable": []}, hsaw_items=[DOUBT])
        fields.pop("gate", None)
    elif run.kind.startswith("scope"):
        fields.update(steps={"done": ["step1"], "remaining": ["step2", "step3"], "not_applicable": []}, gate=GATE)
    else:
        fields.update(steps={"done": [], "remaining": ["step1"], "not_applicable": []}, gate=GATE)
    payload = copy.deepcopy(served["payload_skeleton"])
    payload.update(fields)
    if hsaw:
        payload.pop("gate", None)
    reply, after = run.cmd("node-commit", "--node", node, "--agent-ticket", ticket, payload=payload)
    assert reply.get("status") == "WAITING_USER" and reply["dispatch"]["closed"], reply.get("errors")
    assert after.strip() == "", after[:300]                    # a sub-agent's command gets nothing added
    return reply


@pytest.fixture
def soulrun_env(subprocess_env) -> dict:
    env = dict(subprocess_env)
    env.pop("SOULBOT_RESUME_INTERRUPTED_RUNS", None)
    return env


KINDS = ["node_user_gate", "node_hsaw_doubt", "scope_user_gate", "scope_hsaw_doubt"]


def _norm(text: str, run: Run) -> str:
    """What two runs of the same program never share: the gate's and the ticket's random ids, digests, times."""
    text = text.replace(str(run.cache), "<run>").replace(str(run.cache).replace("\\", "/"), "<run>")
    text = re.sub(r"\bq\d{3}-[0-9a-f]{8}\b", "<qid>", text)
    text = re.sub(r"\bd\d{3}-[0-9a-f]{8}\b", "<ticket>", text)
    text = re.sub(r"\bH-[0-9a-f]{8}\b", "<hsaw item>", text)
    text = re.sub(r"\b[0-9a-f]{64}\b|\bsha256 [0-9a-f]{16}\b|\bsha=[0-9a-f]{8}\b", "<sha>", text)
    text = re.sub(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}[:][0-9]{2}[:][0-9]{2}(?:[.][0-9]+)?Z?|elapsed [0-9]+ ms", "<time>", text)
    return text


def assert_joint_presentation(run, paused, before, main):
    """Decision197: presentation adds only the bound fence/question, never execution."""
    source = paused['gate']['question_id']
    qid = main['gate']['question_id']
    assert qid != source and main['resume']['source'] == qid
    assert run.menus(qid) and not run.menus(source)
    rec = json.loads((run.cache / f'_gate.{qid}.json').read_text(encoding='utf-8'))
    assert rec['identity_handoff']['business_question_id'] == source and rec['answered_at'] is None
    assert rec['previous_gate'] == before['gate']
    fence_ref = rec['identity_handoff']['fence_ref']
    raw = (run.cache / fence_ref['path']).read_bytes()
    import hashlib
    assert hashlib.sha256(raw).hexdigest() == fence_ref['sha256']
    fence = json.loads(raw)
    assert fence['question_id'] == qid and fence['trace_id'] == before['trace_id']
    assert fence['ticket'] == paused['dispatch']['ticket'] and fence['business_question_id'] == source
    assert fence['node'] == before['current']['name'] and fence['visit'] == before['current']['visit']
    assert fence['checkpoint']['external_execution'] == 'UNKNOWN'
    expected = copy.deepcopy(before)
    owner = next(row for row in expected['nodes'].values()
                 if (row.get('dispatch') or {}).get('ticket') == fence['ticket'])
    assert owner['dispatch']['state'] == 'CLAIMED'
    assert owner['dispatch']['scope_root'] == fence['scope_root']
    owner['dispatch'].update(state='ABANDONED', closed_reason='identity_unverified', closed_at=fence['at'])
    expected['gate'].update(state='WAITING_USER', question_id=qid, node=rec['node'], source='hsaw_doubt', kind='choice',
                            presented_at=rec['presented_at'], delivered_at=None, answered_at=None)
    expected['gate']['history'].append(dict(question_id=qid, node=rec['node'], source='hsaw_doubt', prompt_text=None,
        presented_at=rec['presented_at'], answered_at=None, resolution_kind=None, answer_ref=f'_gate.{qid}.json'))
    expected['tickets'].append(dict(question_id=qid, state='READY', minted_at=rec['presented_at']))
    after = run.index()
    expected['updated_at'] = after['updated_at']
    assert after == expected, 'No change outside the explicit fence and new current human question is permitted'
    assert main['dispatch']['required'] is False
    refs = [main['gate']['public_prompt_ref'] if ref == paused['gate']['public_prompt_ref'] else ref
            for ref in paused['dispatch']['public_refs']]
    assert main['dispatch']['public_refs'] == refs
    assert paused['gate']['public_prompt_ref'] not in refs
    return qid, refs


def _setup(tmp_path: Path, kind: str, setup: str, env: dict) -> dict:
    """The program in one host set-up, up to the human's single answer. Returns what to compare across set-ups."""
    from soulrun import host
    run = Run(tmp_path / setup, kind, env)
    issued = _route(run)
    ticket = issued["dispatch"]["ticket"]
    record = json.loads((run.cache / f"_dispatch.{ticket}.json").read_text(encoding="utf-8"))
    import hashlib
    bootstrap_sha = hashlib.sha256(record["bootstrap"].encode("utf-8")).hexdigest()
    if setup == "reports_return":                                # the Agent call appears
        started = host.observe_agent_start(run.cache, bootstrap_sha, session_id="parent", tool_call_id="call-1",
                                           event_id="start-1", at="2030-01-01T00:00:00Z")
        assert started["status"] == "START_BOUND", started
    paused = _pause(run, ticket)
    qid = paused["gate"]["question_id"]
    assert run.menus(qid) == []                                  # the sub-agent's pause shows nothing
    if setup == "reports_return":                                # the Agent call ends
        got = host.observe_agent_return(run.cache, ticket, session_id="parent", tool_call_id="call-1", event_id="end-1",
                                        at="2030-01-01T00:01:00Z", status="completed", agent_id="child-agent-1")
        assert got["status"] == "RETURN_OBSERVED" and run.menus(qid) == [], got
    elif setup == "sdk":                                         # the SDK's task events: refused for a first segment
        for event, status in (("task_started", None), ("task_notification", "completed")):
            got = host.observe_agent_task_event(run.cache, session_id="parent", agent_id="child-task-1",
                                                tool_call_id="call-1", event_id=f"sdk-{event}", at="2030-01-01T00:01:00Z",
                                                event_type=event, status=status)
            assert got["status"] == "RETURN_UNVERIFIED", got
        assert run.menus(qid) == []
    else:
        assert run.menus(qid) == []
    files_before = {p.relative_to(run.cache).as_posix(): p.read_bytes() for p in run.cache.rglob("*")
                    if p.is_file() and "_work" not in p.relative_to(run.cache).parts}
    before_index = run.index()
    main, printed = run.cmd("next-node")                         # the main conversation, before presenting anything
    current_qid, shown = assert_joint_presentation(run, paused, before_index, main)
    after = {p.relative_to(run.cache).as_posix(): p.read_bytes() for p in run.cache.rglob("*")
             if p.is_file() and "_work" not in p.relative_to(run.cache).parts}
    added = set(after) - set(files_before)
    assert added and all(name.startswith(f"_public/menu.{current_qid}.")
        or name in (f'_gate.{current_qid}.json', f'_dispatch_fence.{current_qid}.json') for name in added)
    assert all(after[name] == body for name, body in files_before.items() if name != '_index.json')
    second, _ = run.cmd("next-node")
    assert second["gate"]["public_prompt_ref"] == main["gate"]["public_prompt_ref"]
    assert {p.relative_to(run.cache).as_posix(): p.read_bytes() for p in run.cache.rglob("*")
            if p.is_file() and "_work" not in p.relative_to(run.cache).parts} == after
    shown += [r for r in (main.get("public_block_ref"), main["gate"]["public_prompt_ref"]) if r and r not in shown]
    texts = [run.text_of(ref) for ref in shown]
    assert all(t is not None for t in texts), shown
    menu = run.text_of(main["gate"]["public_prompt_ref"])        # the command line prints references, not block text
    assert menu and main["gate"]["public_prompt_ref"] != paused["gate"]["public_prompt_ref"]
    if HEADER in printed:                                        # SoulRun's command line printed the turn: the gate's text
        assert menu.strip() in printed
    human = run.turn("1")                                        # the human answers once
    index = run.index()
    row = [h for h in index["gate"]["history"] if h["question_id"] == qid]
    assert row and row[0].get("resolution_kind") == "chosen" and "entry_mode: resume" in human.stdout, human.stdout[:600]
    assert [h for h in index['gate']['history'] if h['question_id'] == current_qid][0]['resolution_kind'] == 'chosen'
    assert index['dispatch']['tickets_issued'] == before_index['dispatch']['tickets_issued']
    return dict(menu=_norm(menu, run), refs=[_norm(r, run) for r in shown], texts=[_norm(t, run) for t in texts],
                printed=HEADER in printed)


@pytest.mark.parametrize("kind", KINDS)
def test_f1_three_host_setups_one_answer_taken_the_same_gate_and_references(tmp_path, kind, soulrun_env):
    """Decision 189 through SoulRun: SoulRun's own command line (a host that never reports the return), a host that
    reports it, an SDK host whose task events do not bind this segment. In each the sub-agent's pause writes no menu, the
    main conversation's next-node serves the gate and every reference it presents resolves, the human's single '1' is
    taken; the gate and the references are the same in all three. On the command line the next-node prints the gate's
    text for the human."""
    views = {setup: _setup(tmp_path, kind, setup, soulrun_env) for setup in ("command_line", "reports_return", "sdk")}
    assert views["command_line"].pop("printed") is True
    for setup in ("reports_return", "sdk"):
        views[setup].pop("printed")
    assert views["command_line"] == views["reports_return"] == views["sdk"]


RULE = ("WAITING_USER returns ordered public_refs and stops; before presenting any of it main calls next-node once (no "
        "ticket), which shows and serves the gate;")
SCOPE = ("A child's returned WAITING_USER is presented only after main calls next-node once (no ticket), which shows and "
         "serves that gate;")


def test_f1_the_command_lines_main_conversation_is_told_to_call_next_node_before_presenting(tmp_path, soulrun_env):
    """Decision 189's contract reaches the model on SoulRun's own command line: the main conversation's next-node that issues
    the sub-agent's ticket carries the rule (payload_rules: resume.dispatch_segments) and a note saying the same, and the
    part of the slim program SoulRun prints after it (the dispatch group) says it too."""
    run = Run(tmp_path / "cli", "node_user_gate", soulrun_env)
    _route(run)
    plan = run.dispatch_plan
    assert plan["dispatch"]["bootstrap"] and plan["dispatch"]["required"], plan.get("dispatch")
    assert any(RULE in str(rule) for rule in plan["payload_rules"]), plan["payload_rules"]
    assert "after a returned WAITING_USER main calls next-node once before presenting them" in plan["dispatch"]["note"]
    assert SCOPE in run.dispatch_after, run.dispatch_after[:2000]


@pytest.mark.parametrize("message", ["1", "继续", FREE])
@pytest.mark.parametrize("kind", ["node_user_gate", "scope_hsaw_doubt"])
def test_f1_on_the_command_line_a_message_before_the_main_next_node_is_held_then_shown_then_taken(tmp_path, kind, message,
                                                                                                 soulrun_env):
    """The turn died after the sub-agent returned and before the main conversation's next-node: the human's '1', '继续' or
    free text through the real soulrun command line is not taken - the run's index, gate records and menus are as they
    were, the gate still not shown. The next turn's next-node shows the gate; the human's '1' is then taken."""
    run = Run(tmp_path / "cli", kind, soulrun_env)
    ticket = _route(run)["dispatch"]["ticket"]
    paused = _pause(run, ticket)
    qid = paused["gate"]["question_id"]
    keep = lambda: (run.index()["gate"], sorted(p.name for p in run.cache.glob("_gate.q*.json")), run.menus(qid))  # noqa: E731
    before = keep()
    held = run.turn(message)
    assert "entry_mode: resume_invalid_answer" in held.stdout, held.stdout[:600]
    assert keep() == before and run.menus(qid) == []
    before_index = run.index()
    main, printed = run.cmd("next-node")
    current_qid, _ = assert_joint_presentation(run, paused, before_index, main)
    assert HEADER in printed and run.text_of(main["gate"]["public_prompt_ref"]).strip() in printed
    taken = run.turn("1")
    assert "entry_mode: resume" in taken.stdout and [h for h in run.index()["gate"]["history"]
                                                     if h["question_id"] == qid][0].get("resolution_kind") == "chosen"
    assert [h for h in run.index()['gate']['history'] if h['question_id'] == current_qid][0]['resolution_kind'] == 'chosen'

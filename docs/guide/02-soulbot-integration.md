# SoulBot on SoulRun: How It Is Wired

SoulBot runs its agents' turns through SoulRun: an agent that opts in hands every turn to `soulrun(...)`, and the
engine it runs is the one bundled in this package (`soulrun_aiap`, version 1.0.0). SoulBot keeps no engine copy of its
own for such an agent. This page describes that wiring as SoulBot has it, and what a host has to get right around
it. Nothing in this repository changes SoulBot.

This is a reference integration for opted-in agents, based on recorded host wiring, not an assertion that
every SoulBot release or live installation has these exact internals. The code below is a skeleton with
host-provided names and omitted plumbing, not a standalone runnable agent. Verify that framework version's
own interfaces and imported SoulRun package before adapting it; a document edit does not update the framework.

## The agent (`agent.py`)

An agent opts in on its `LlmAgent`: `engine_backend='soulrun'`. Its `agent.py` is a thin entry - it builds SoulBot's
own blocks (time, tools, schedule, messaging, MCP, the program folders) and asks SoulRun for the rest:

```python
from soulrun import run as _soulrun
from soulbot.engine_hooks import HOST_FENCES as _HOST_FENCES, _last_user_text

def _router_instruction(_ctx) -> str:
    parts = [_TEXT_ONLY_SYSTEM_PROMPT, ...]        # SoulBot's own blocks
    user_message = _last_user_text(session, ...)   # the human's words, from the session's events
    if not heartbeat:                               # a heartbeat never goes through the engine
        data_root = getattr(_ctx.agent, "_engine_data_root", None) or root_agent._engine_data_root
        if data_root is None:
            raise RuntimeError("SoulRun Agent must be bound to its Host before preparing a turn")
        run = _soulrun(
            user_message=user_message,
            agent_dir=_AGENT_DIR,
            soulrun_cache_dir=data_root,            # bound by the host: <agent>/.soulrun_cache
            session_id=session_id,                  # SoulBot's own conversation id
            user_id=host_user_id or None,
            channel=origin_channel,
            model=getattr(_ctx.agent, "model", root_agent.model),
            host_fences=_HOST_FENCES,
            host_tools=_host_tools(getattr(_ctx.agent, "model", root_agent.model)),
            human_turn=human_turn,                  # False for scheduled turns, agent messages and the host's own
                                                    # probe and recovery turns
            host_turn_id=getattr(_ctx, "invocation_id", None),
            origin_type=origin_type or None,
        )
        parts.extend(run.blocks)
        parts[0] = run.system_prompt or _TEXT_ONLY_SYSTEM_PROMPT
    else:
        ...                                         # the heartbeat program, run directly
    return "\n\n".join(parts)

root_agent = LlmAgent(name=_AGENT_DIR.name, engine_backend='soulrun', instruction=_router_instruction)   # and the rest
```

- `run.blocks` are the engine blocks the template used to build itself; `run.system_prompt` is the opening
  instruction that goes with the turn's program form (SoulRun's own for the slim form, the default). A question
  SoulRun asks before any run is handed to the engine (`run.doubt`: a named program not found, a run left by another
  engine build, ...) carries no system prompt: the text-only instruction stays, and the model shows the question as
  written and waits.
- A heartbeat turn never reaches SoulRun: `soulrun(..., channel="heartbeat")` is refused (`HEARTBEAT_NOT_ENGINE`).
- In the slim form the model runs the engine's tools and reads the business program through SoulRun's own command
  line (the interpreter running SoulRun, by full path); the agent's model CLI must be allowed to run it.
- `host_tools` truthfully describes the managed tools available in that host session. Set `{"agent": True}` only
  when real dispatch is available and qualified; a provider label or model claim is not that evidence.
  With `False` the engine runs a node meant for a sub-agent inline. Reporting events alone proves no original-child identity.
- Besides `agent.py` and its heartbeat program, the agent folder holds its programs (`aiap/`, `aisp/`) and its run
  data (`.soulrun_cache/`). It carries no engine folder - no `soulrun_aiap/` and no `soulbot_execute_engine_aiap/`.

## The host

| Where in SoulBot | What it does with SoulRun |
| --- | --- |
| `agents/base_agent.py` | the field `engine_backend` (`'soulrun'` or None) - the agent's own opt-in; nothing is guessed from folders |
| `engine_hooks.engine_dir_of(agent_dir, backend='soulrun')` | `soulrun.host.soulrun_cache_dir(agent_dir=...)`, which must be `<agent>/.soulrun_cache` (another layout is refused) |
| `engine_hooks.attach_engine_hooks` | loads `soulrun.host.engine('prepare_cache')` first (the engine's modules must be SoulRun's), refuses an installed SoulRun that lacks one of the sub-agent doors (`SOULRUN_DISPATCH_DOORS_MISSING`), then binds `agent._engine_data_root` and the recovery, question, after-turn and cancel callbacks |
| `engine_hooks.engine_scope(agent)` | a context variable: during a turn, run lookups use the very agent instance that runs it, never another app's agent of the same name |
| `engine_hooks.expand_engine_refs` and the after-turn callback | SoulBot's own code for what `host.expand_refs` and `host.after_turn` do (SoulRun's doors follow SoulBot's rules): references expanded from the bound data root's runs; after the turn, a shown question's menu marked delivered, then what the model said, then that the reply was stored |
| the sub-agent bridge (`engine_hooks.AgentToolReturnBridge`) | reports what it sees of the model's sub-agents through `soulrun.host`'s doors: `observe_agent_start`, `observe_agent_return`, `observe_agent_task_event`, `observe_resume_failure`, `observe_tool_request` and `observe_tool_result`, with `dispatches_nodes`, `resumed_agent_start`, `parent_policy_ref` and `resolve_tool_parent` |
| `engine_paths.program_directory(data_root)` | `soulrun.host.program_root()` for the package layout - where the engine's tools are |
| recovery after a broken model connection | `soulrun.host.runner_recovery(request, soulrun_cache_dir=root, resume_mode=...)` |
| the send layer (`models/acp_llm.py`) | `soulrun.host.project_slim_policy(...)` reads the slim form's turn policy, so two turns of one run compare as the same instructions; the turn's own fragment is forwarded unchanged |
| `server/agent_loader.py`, `server/api_server.py` | bind every opted-in agent the same way at load time, including agents handed in already loaded. SoulRun agents are loaded first; an agent that cannot be bound (`ENGINE_NAME_CLASH`, a SoulRun error) is left out with its reason kept (`GET /agents/load-errors`), and the host starts with the others |
| `server/routes/engine_view.py` (the web page's engine view) | lists a conversation's runs from the agent's run folders - `.soulrun_cache/`, and for history the older engine folders `soulrun_aiap/` and `soulbot_execute_engine_aiap/` - and marks every run outside the agent's bound data root read-only |
| `server/routes/engine_actions.py` | ending a stopped run, the one change the web page may make, uses the agent's bound data root and never another app's |

## Rules a host must keep

- **One engine per process.** The engine's tools use plain top-level module names (`lib`, `prepare_cache`, ...). An
  agent that still carries its own engine folder (directory mode) loads those names from there; SoulRun then refuses
  to load beside it (`ENGINE_NAME_CLASH`) instead of mixing two engines. A host should treat that as the failure of
  that one agent - skip it and say why - not of the whole host, and should not create new directory-mode agents next
  to SoulRun agents.
- **Find runs only through SoulRun.** `soulrun.host.soulrun_cache_dir(...)` / `cache_root(...)` for runs,
  `program_root()` for the engine's tools, `soulrun.host.engine("<name>")` for engine modules. None of these creates
  a folder.
- **Runs of an older engine are read-only.** Runs left in an agent's old engine folder (`soulbot_execute_engine_aiap/`
  or `soulrun_aiap/`) were made by another engine. SoulBot shows them read-only and never continues them or answers
  their open questions with SoulRun's engine; new work starts in a new conversation.
  Framework display support does not promise SoulRun can interpret every historical format, including v6 records.
- **Runs of another SoulRun build are asked about.** A run records the exact engine digest it began with. When the
  installed SoulRun carries a different build - even under the same version number - or the run has no record of its
  build, the conversation's unfinished run is not continued: a human turn gets a question
  (`run.doubt["code"] == "ENGINE_BUILD_MISMATCH"`) offering to end that run, to work in another conversation, or to
  leave it. A reply of one cancel word (`取消`, `cancel`, `stop` ...)
  ends it through the engine's own `terminate_run` (marked as ended by the human; none of its steps is run) - only a
  run of the same engine version can be ended so. A machine turn (`human_turn=False`) is refused with the
  `ENGINE_BUILD_MISMATCH` error. So upgrade SoulRun when no run is waiting, or expect that question.
- **A gate is answered by a human.** While a run waits at a gate for the human's answer (`WAITING_USER`), SoulRun
  refuses a machine turn (`human_turn=False`) with `HUMAN_REPLY_REQUIRED`, and so it does, with
  `SOULBOT_RESUME_INTERRUPTED_RUNS` off, at a run whose engine stop was cut off before its index write and at a run
  marked running that cannot be read then (the run lock a killed process left). And only once it has been shown: the
  engine writes an engine stop's menu only when the main conversation's step is served it, not when a sub-agent's
  step meets it or the engine opens it while taking an answer, and the menu of a business gate a sub-agent paused at
  when the main conversation's step is served it - the main conversation calls that next-node before it presents the
  gate, as in any host. SoulBot's report of that return (`observe_agent_return`, when the Agent call ends) records
  lifecycle facts only: it neither writes the menu nor marks it shown. The engine takes no message as the answer before
  that menu or a recorded delivery - the main conversation's next step shows the gate, and the human answers then.
- **Install SoulRun where SoulBot runs.** Consult that SoulBot version's own dependency declaration; this document
  does not impose a different constraint on the framework. Verify the actual imported package and engine digest,
  not just an installation in another interpreter. An opted-in agent imports `soulrun` when it is loaded, and binding it fails
  (`SOULRUN_DISPATCH_DOORS_MISSING`) when the installed SoulRun lacks one of the sub-agent doors.
- **Report without granting identity.** All reports are diagnostic by default. An unproved original child requires
  explicit new-agent authorization at the presented gate. Only `execute` choices grant it; cancel and terminate
  preserve their kind/label and issue no new ticket. Fencing a ticket does not prove its process exited.
- **Declare text capture truthfully.** `@host` requires the text to have reached the host before submission.
  A non-streaming endpoint cannot claim live capture merely because the web path streams. A recorded SoulBot
  `/run` observation includes one rejected final submission and possible degradation of other `@host` text;
  this belongs to framework capture, not a SoulRun endpoint-specific branch. See [Verification Scope](../verification-1.0.0.md).
- **Check the place.** `soulrun --doctor --agent-dir <agent>` reports the program form and the command line the slim
  form gives the model, missing time-zone data, and on Windows a run folder deep enough to reach the 260-character
  limit. An agent folder may carry Chinese characters and spaces: SoulRun's call, the engine's steps and SoulRun's
  command line are tested with both. The commands the model is given name the run folder unquoted, though (see the
  README's [Known Limits](../../README.md#known-limits)): the model must quote such a path, or keep agent folders
  without spaces.
- **One process, many conversations.** Preparing a run takes a lock in the process and a file lock in
  `<soulrun_cache_dir>/.soulrun/prepare.lock`, so even several processes never share a run number.
- **When a reply cannot be printed.** In the slim form SoulRun's command line prints each engine reply. If the reader
  has gone (a closed pipe), it exits with code 74 and one line on standard error, and notes the reply in
  `<soulrun_cache_dir>/.soulrun/undelivered/<run>.jsonl`; the engine itself has kept the reply in the run's
  `_work/replies/`. A sub-agent's commands are not captured: there the engine prints to the pipe itself, and when it
  cannot print the reply to a node submission it rejected, the run goes on unchanged (the engine notes it as
  `REJECTED_REPLY_NOT_DELIVERED`) and the sub-agent submits again. A reply to an accepted submission that could not
  be printed still stops the run for a human.

## Running a named program with no user words

For a schedule entry or a "run this program" button: `_soulrun(user_message="", aiap="<program>", ...)` (or `aisp=`).
SoulRun starts a run with that program as the only candidate; a program that needs words asks the human through an
HSAW doubt gate, and the answer comes back as an ordinary message (`user_message=answer`, no `aiap=`). A scheduler
passes `human_turn=False`.

## What changed from SoulBot's own engine folder

Before, each agent carried `soulbot_execute_engine_aiap/` (engine program and runs together) and `agent.py` built the
engine blocks itself, about 200 lines. Now the program is SoulRun's, the runs are in `<agent>/.soulrun_cache` (the
engine's runs in `.execution_cache/`, SoulRun's own small records beside them in `.soulrun/`), and `agent.py` calls
`soulrun(...)`. The shape of a run and, with `slim_program=False`, every block the model reads are the same as
before; the default program form is the slim one. The engine's version is 1.0.0, and every 1.x engine keeps the
feature set the engine inherited (see the README's [The Engine](../../README.md#the-engine)).

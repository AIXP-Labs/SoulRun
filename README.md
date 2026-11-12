# SoulRun

**The AISOP Execution Engine as One Call — Run AIAP Programs and AISP Skills from Any Host**

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-Apache%202.0-green.svg)](LICENSE)
[![CI](https://github.com/AIXP-Labs/SoulRun/actions/workflows/ci.yml/badge.svg)](https://github.com/AIXP-Labs/SoulRun/actions/workflows/ci.yml)

[中文文档](README_CN.md) | English

[Quick Start](#quick-start) · [Python API](#usage) · [CLI](#command-line) · [Hosts](#for-hosts) ·
[Privacy](#privacy-and-local-files) · [Verification](docs/verification-1.0.0.md) · [Documentation Map](docs/README.md)

## What is SoulRun?

SoulRun is the execution runtime of the AIXP ecosystem as a Python package. AISOP programs — **AIAP
packages** (`*_aiap`) and **AISP skills** (`*_aisp`) — are run by **SoulRun's engine**: it serves the
program one node at a time, takes each node's result back as evidence, keeps the run on disk so it can be
stopped, resumed and re-entered, and stops at every gate where a human must decide. The engine travels inside
one dependency-free package, with a single call in front of it:

```python
import soulrun

message = "Read the hexagram for this month"
ctx = soulrun(user_message=message)          # start a run, or continue the one this message belongs to
if ctx.doubt:                              # a question for the human, not a request to the model
    show_to_the_human(ctx.text)
else:
    reply = send_to_your_model(ctx.system_prompt, ctx.text + "\n\n" + message)
```

`send_to_your_model` and `show_to_the_human` are host-provided placeholders, not SoulRun APIs.
For reference expansion and turn recording, use the loop in [First Call](#first-call).

SoulRun does not talk to a model. It prepares the run on the local disk and hands back what the model needs for
this turn: `ctx.text`, and `ctx.system_prompt`, the opening instruction that goes with it. The host sends them with
whatever model access it has (SoulBot uses [SoulACP](https://soulacp.dev)), and the model then drives the engine
with the engine's commands. By default the text is in the slim form: it carries the part of the engine program the
turn starts with - each later part comes with the engine reply whose step needs it - and the model runs the
engine's tools and gets the business program through `soulrun` commands, never opening a file itself. On a command
line, where the model itself shows the human what the engine has for them, SoulRun hands it that text as well.
Switched over, the text is in the entry-path form, word for word the text SoulBot's agent template gave the model
before SoulBot ran on SoulRun, except that a turn that runs nothing never carries its entry block (see
[Program Forms](#program-forms)). So SoulBot, [SoulAgent](https://soulagent.dev), a small script or a command-line
session can all run the same programs with the same engine.

### Key Features

- **One Call** — `soulrun(user_message=...)` starts a run or continues the one the message belongs to; with no arguments it returns the guide and creates nothing
- **Any Host** — SoulRun never calls a model; the host sends `ctx.text` through its own model access, so the same engine serves a framework, an agent, a script or a terminal
- **The Model Reads Nothing Itself** — in the default slim form the engine program comes inside `ctx.text`; the main conversation's model runs the engine's tools and gets the business program through `soulrun` commands, never by opening a file (see [Program Forms](#program-forms), and [Known Limits](#known-limits) for sub-agents and fallback turns)
- **Engine Inside, Verified** — the engine ships inside the package with a SHA-256 manifest of every file; `soulrun --verify-engine` checks an installed copy against the manifest it came with, and in a checkout of this repository one tool brings a newer engine in (and back out)
- **Program and Data Separate** — the engine is read-only inside the installed package; runs live in `soulrun_cache_dir` (by default `.soulrun_cache` beside your programs), which ignores itself in version control
- **Zero Dependencies** — SoulRun and the engine use the Python standard library only, on Python 3.11+
- **Human Sovereignty by Construction** — whenever SoulRun cannot tell what the human wants, it asks; it never invents the user's words, never picks a program for the human and never answers a gate (see [Axiom 0 in SoulRun](#axiom-0-in-soulrun))
- **Host Doors** — `soulrun.host` gives a full host what it calls around a model turn: after every turn, on a Stop, after a restart, after a broken model connection, and when sub-agents start and return
- **Self-Checking** — `soulrun --verify-engine` checks every engine file; `soulrun --doctor` checks a machine before a run and leaves nothing behind
- **Many Conversations at Once** — preparing a run is locked across threads and processes, so two calls never take the same run

### Historical Run Records

SoulRun 1.0.0 does not guarantee compatibility with v6-era execution records. Retained historical
fixtures check only their explicitly stated properties, not general v6 record compatibility. This does
not change current AISOP/AIAP/AISP program execution, human authorization checks, or the rule that
accepted work is not executed again during recovery.

### Axiom 0 in SoulRun

SoulRun follows Axiom 0 — [Human Sovereignty and Wellbeing](https://hsaw.dev) — on its own, not only
through the engine it carries. These rules hold in SoulRun's code and are covered by its tests:

| Rule | What SoulRun does |
|---|---|
| **The human decides; SoulRun asks** | A designated program that cannot be found, a `cache_dir` that is not the conversation's latest unfinished run, an AIAP program and an AISP skill both named with no words, a named program while the conversation still has an unfinished run not created for it, or an unfinished run left by another engine build: nothing is run and no run is created. The human gets a question that says what was looked for, what exists and a non-binding suggestion (`ctx.doubt`). |
| **Never invent the user's words** | With no words and one program named, the program is run with an empty message; a program that needs words asks the human through the engine's HSAW doubt gate. SoulRun never writes a request on the human's behalf. |
| **Never choose for the human** | A designated program is used as designated and never silently replaced; which candidate fits the words is judged by the engine, and an unclear case goes to the human. |
| **Never answer for the human** | A gate or a doubt is shown to the human as written; the human's reply comes back as an ordinary message. Nothing in SoulRun answers a question, and while a run waits at a gate for the human's answer, a turn marked as not the human's (`human_turn=False`) is refused (`HUMAN_REPLY_REQUIRED`). |
| **No silent fallback** | A value that is set but unusable is an error with a stable code, never quietly replaced by a default. |
| **The human's words stay the human's** | SoulRun opens no network connection. Runs, which hold the user's words, stay in `soulrun_cache_dir`, and so does the file a command-line turn read them from (moved into its run). A folder SoulRun creates, or takes for the first time, gets a `.gitignore` of `*` unless it already has one (on Linux and macOS a folder it creates is its owner's only), and a folder that already holds other files is refused. |
| **Say what was done** | Each run records which folders it used and whether each came from an argument, an environment variable or a default; `soulrun --doctor` reports what would quietly degrade a run. |

The engine applies the same axiom inside a run: its user gates and HSAW doubt gates stop the run
until the human answers, and a human Stop ends the turn.

---

## Quick Start

### Prerequisites

| Requirement | Notes |
|---|---|
| Python 3.11+ | `requires-python` declares a minimum, not an upper bound. CI configures 3.11–3.15; measured runtime-head results and untested versions are separate (see [Verified Test Baseline](#verified-test-baseline)) |
| A `python` the model's shell can find | The model runs these with it: every engine tool in the entry-path form, a sub-agent's engine tools in every form (the engine's sub-agent program runs `python <engine>/python_tools/...`), and a program's own tools written as `python ...`, in every form. Only the main conversation of the slim form (the default) runs the engine's tools without it, naming the interpreter running SoulRun by its full path. `soulrun --doctor` reports both; no `python` is a `FAIL` in every form |
| A host with model access | Anything that can send `ctx.text` to a model and its reply back: SoulBot, a SoulACP session, an API client |
| Time-zone data on Windows | `python -m pip install tzdata` for a python.org Python (see [Known Limits](#known-limits)) |

### Install

```bash
python -m pip install soulrun                                          # from PyPI
python -m pip install "git+https://github.com/AIXP-Labs/SoulRun.git"   # or straight from GitHub
```

These are release-installation commands, not proof that a release is currently available on either platform.
V1.0.0 remains fixed during release preparation; for a local candidate, use its verified artifact or approved
checkout and check the manifest, not the version number alone. See [Verification Scope](docs/verification-1.0.0.md).

Then check it:

```bash
soulrun --version                # SoulRun's version and the bundled engine's
soulrun --verify-engine          # the installed engine is the recorded one
```

To work on SoulRun itself and run its tests, install a checkout of this repository in editable mode:
`python -m pip install -e ".[dev]"`; building and publishing are in [INSTALL.md](INSTALL.md).

### First Call

Put your programs in an agent folder — AIAP packages under `aiap/`, AISP skills under `aisp/` — and call
SoulRun from there (or pass `agent_dir=`):

```bash
soulrun                                      # the guide
soulrun --doctor                             # is everything in place for a run?
soulrun --user-message-file msg.txt          # prints the text for the model (msg.txt then goes into the run)
```

```python
import soulrun

from soulrun import host

ctx = soulrun(user_message=message, session_id="conversation-1",
              host_tools={"agent": False})   # say what the host can do: not given, the engine assumes sub-agents
if ctx.doubt:                                # SoulRun asks the human first: show it as written and wait
    show_to_the_human(ctx.text)
else:                                        # program or text_only: the model's turn
    reply = send_to_your_model(ctx.system_prompt, ctx.text + "\n\n" + message)   # opening instruction, then the turn
    show_to_the_human(host.expand_refs(reply, cache_dir=ctx.cache_dir))   # blocks, not their references
    host.after_turn(ctx.cache_dir, reply)    # after every turn
```

The package is typed (`py.typed`), but a type checker cannot see that a module is callable: a host that
type-checks writes `from soulrun import run` and calls `run(...)` - the same function, giving `Ctx` (or `CmdResult`
with `cmd=`).

A complete host loop without a model is in [`examples/minimal_host.py`](examples/minimal_host.py); the same
loop with a real command-line model through SoulACP is in [`examples/soulacp_host.py`](examples/soulacp_host.py).

---

## Architecture

### Where SoulRun Sits

```text
host (SoulBot, SoulAgent, a script, a terminal session)
  │  soulrun(user_message=..., session_id=...)
  ▼
SoulRun ── finds the conversation's run or prepares a new one, sets the candidates,
  │        asks the human when it cannot tell what is wanted
  │  ctx.text: the text for the model this turn (by default carrying the slim engine program)
  ▼
the host sends ctx.text to its model (SoulACP, an API, ...)
  │
  ▼
the model drives the bundled engine with the engine's own commands:
  next-node → do the node → node-commit → ... ; a gate stops the run until the human answers
```

### Program and Data Are Separate

| What | Where |
|---|---|
| the engine (program) | inside the installed `soulrun` package, read-only |
| the runs | `soulrun_cache_dir` — by default `.soulrun_cache` in the agent folder (the current folder unless one is named), or the folder you name. It holds run data only. A folder that holds an engine program (such as a SoulBot agent's own engine folder) is refused, so two engines never share one set of runs; so is one that already holds other files. Deleting it deletes the runs, unfinished ones included |
| your programs | `aiap_dir`, `aisp_dir` (by default `aiap/` and `aisp/` in the agent folder) |

Inside `soulrun_cache_dir`:

| Path | Whose | What |
|---|---|---|
| `.gitignore` | SoulRun's | `*`, to reduce accidental inclusion of run data: written when SoulRun creates the folder, or takes one for the first time that has none. After that the owner decides. It does not untrack files, prevent forced inclusion, encrypt data or restrict access |
| `.execution_cache/<N>/` | the engine's | one folder per run. The engine keeps the latest 100 runs (`CACHE_NUM`) and removes older ones that are finished; a run that is still going or waiting for the human is never removed. Every call reads each kept run: measured on an earlier build (not re-measured for this one), a call took about 50 ms with a few runs and about 0.2 s with 100. It also takes longer as the index of the conversation's latest run grows, which SoulRun and the engine read and check on every call (on that earlier build, 77 ms a read for a 1.9 MB index, a long node program's; SoulRun reads it twice before the engine prepares the turn - once while finding the conversation's latest run, once more for its checks - and once after) |
| `.soulrun/runs/<N>.json` | SoulRun's | which folders the run was created with, and whether each came from an argument, an environment variable or the default; the SoulRun version, engine version and engine digest that created it, and its candidates. Later, whether the run was given the slim form and any problem the slim form had, and, when a human ends a run of another engine build here, that it was ended that way |
| `.soulrun/turns/<N>.json` | SoulRun's | the run's latest turn: `turn_id` (the engine's, which is the run's number - `ctx.turn_id` too - the same on every turn of the run), `host_turn_id` (the host's), `turn` (1, 2, ... within the run), and the run's `trace_id`. The engine numbers a new run one past the highest it keeps, so a number comes back once the latest runs are removed or cleared: a run whose `trace_id` is not the one kept here counts from 1 again. When the engine hands the same run back for the same message within two minutes (a rebootstrap), it is the same turn, keeping its number, only with the same `host_turn_id`; otherwise - another `host_turn_id`, or none to tell by - it is the next turn |
| `.soulrun/delivered/<N>.json` | SoulRun's | in a slim turn, which parts of the engine program the turn has been given, with the turn's `turn_id`, `host_turn_id` and `turn`; a new turn starts it again ([Program Forms](#program-forms)) |
| `.soulrun/entries/<N>.txt` | SoulRun's | the full text of a turn, when a command line printed it |
| `.soulrun/undelivered/<N>.jsonl` | SoulRun's | one line for each engine reply SoulRun's command line could not print (the reader closed the pipe); the engine kept the reply in the run |
| `.soulrun/prepare.lock` | SoulRun's | empty; while a run is being prepared, the operating system's lock on it makes other processes wait, so two never take the same run number. Released when the process ends, however it ends |

Apart from the message file a command-line turn moves into its run (`<run>/_soulrun/message.<n>.txt`), SoulRun
writes nothing inside a run's own folder; it drops its notes once the engine has removed the run.

---

## Usage

### From Python

```python
import soulrun

ctx = soulrun(user_message="...")            # the package itself is callable; soulrun.run is the same function
ctx.kind          # "program" | "text_only" | "guide"
ctx.text          # give this to the model (for a doubt: show it to the human)
ctx.system_prompt # the opening instruction that goes with this turn: put it where your own was
ctx.cache_dir     # the run this turn belongs to
ctx.session_id    # the conversation, as given or as SoulRun chose it
ctx.turn_id       # the engine's turn_id: the run's number, the same on every turn of the run
ctx.entry_mode    # how the engine classified the message: fresh, resume, recovery, terminal, ...
ctx.program_form  # "slim" (the default), "entry_path" or "full"; None when the turn runs nothing
ctx.slim_fallback # why this turn has the entry-path form instead of the slim one, else None
ctx.doubt         # set when SoulRun asks the human before any run can be created: its code and options
ctx.data          # the engine's own answer, unchanged

soulrun()                                    # the guide; nothing is created
soulrun(aiap="daily_report")                 # no words, one program named: that program is run
soulrun(cmd="next-node", cache_dir=ctx.cache_dir)   # run one engine command
```

`ctx` also carries `blocks` (the same text as separate blocks), `places` (the folders used and where each came
from), `program` (the program text when the turn hands one over) and `as_dict()`. The package gives
`soulrun.__version__`, `soulrun.ENGINE_VERSION`, `soulrun.engine_info()` and `soulrun.guide()`.

### What Comes Back

| `ctx.kind` | When | What to do |
|---|---|---|
| `program` | a run is ready | give `ctx.text` and the human's words to the model, with `ctx.system_prompt` as the opening instruction |
| `text_only` without `ctx.doubt` | the engine decided this turn must not enter the program (for example after a human Stop, when it asks to confirm after an interruption, or on a cancel) | give `ctx.text` to the model; it answers in text only and runs no command |
| `text_only` with `ctx.doubt` | SoulRun has a question before any run exists | show `ctx.text` to the human and wait; the model is not asked |
| `guide` | no message, no program named and no `cmd` | read it |

### What the Human Sees

The engine has the model write every public block - a gate's menu, a node's block, the final answer - as one
reference line, `⟦engine:<run>/<file>⟧`, never as text. Before a reply is shown, the host puts the blocks in:
`host.expand_refs(reply, cache_dir=ctx.cache_dir)`. After every turn, a `text_only` one too, it calls
`host.after_turn(ctx.cache_dir, reply)`: besides recording what was said, it marks a question's menu as delivered
when the reply carries it - the engine takes no answer to a question asked after a Stop, a restart, a broken
connection or an execution fault before that. Inside a run, a gate takes no answer before it has been shown either:
before its menu is written - for an engine stop only when the main conversation is served it, not when a sub-agent
meets it or the engine asks it while taking an answer; for a business gate a sub-agent pauses at, when the main
conversation's next step serves it - which, in any host, the main conversation calls before it presents that gate -
or its delivery is recorded. Recording that sub-agent's return (`host.observe_agent_return`) does not write its menu
or mark it shown. A message that comes earlier is not taken; the main conversation's next step shows the
gate, and the human answers then.

### Continuing a Run

When the model's reply ends at a question, wait for the human and call again with the answer:

```python
ctx = soulrun(user_message=answer, session_id="the same conversation")
```

The engine recognises the answer and continues the same run. Nothing ever answers on the human's behalf.
`cache_dir=` only makes sure the message goes to that run: it must be this conversation's latest unfinished run,
or the human is asked. One conversation takes one turn at a time: call again only when the last turn has ended (the
model answered, `after_turn` done) and queue what arrives meanwhile - a message sent while the model still works is
taken as "the last turn was cut off".

### No Words

With no program named (or only the big folders), the call hands back the guide. With one program named
(`aiap=` or `aisp=`), that program is run: some programs need no words, and one that does asks the human for
them — the engine's rule; SoulRun never makes words up. With both an AIAP program and an AISP skill named,
nothing says which one to run, so the human is asked first, in both Chinese and English, since there are no
words to tell the language by.

A named program does not start while the conversation still has an unfinished run that was not created for it
(the engine continues one run per conversation): the human is asked first (`DESIGNATED_RUN_UNFINISHED`) - continue
that run, run the program in another conversation, or cancel. The same holds with words.

### Arguments

All are optional.

| Argument | Not given | Meaning |
|---|---|---|
| `session_id` | one conversation per agent folder (`ctx.session_id` says which) | which conversation the message belongs to; a host with conversations should always pass it |
| `cache_dir` | the engine finds the conversation's run | which run the message is for; it must be that conversation's unfinished run |
| `aiap_dir`, `aisp_dir` | `aiap` and `aisp` under `agent_dir` | folders holding many programs |
| `aiap`, `aisp` | none designated | one designated program: a folder path, its entry file, or a name looked up in the folder above |
| `agent_dir` | `SOULRUN_AGENT_DIR`, else the current folder | the agent folder: the folder that holds your programs in its `aiap/` and `aisp/` (SoulBot's word: each of its agents has one) |
| `soulrun_cache_dir` | `SOULRUN_CACHE_DIR`, else `<agent_dir>/.soulrun_cache` | the folder the runs are kept in. A named one is that folder itself (as with pip's, pytest's or ruff's cache-dir); it must be new, empty or already SoulRun's. Not to be confused with `cache_dir`, one run inside it. A relative path is read from the current folder, not the agent folder. |
| `user_id`, `channel`, `model`, `host_fences`, `host_tools`, `human_turn`, `host_turn_id`, `origin_type` | the engine's defaults | what a host knows about the turn. `host_tools` not given means the host *can* start sub-agents: a host that cannot says `{"agent": False}` |
| `slim_program` | on | the slim form, see [Program Forms](#program-forms); `False` (`SOULRUN_SLIM_PROGRAM=false`, `--no-slim-program`) gives the entry-path form, SoulBot's text |
| `inline_program` | off | experimental second-stage form, see [Program Forms](#program-forms); it turns the slim form off, and cannot be combined with `slim_program=True`. Both switches take `True`, `False` or nothing; their environment variables 1/true/yes/on or 0/false/no/off (an empty one counts as not set) - anything else is `SWITCH_INVALID` |
| `cmd` | — | run one engine command instead; cannot be combined with `user_message`. The command's own options go as keyword arguments (`node=`, `payload=`, ...), with `args=[...]`, `stdin=` and `timeout=`; SoulRun's own arguments are refused with it (`ARGUMENT_NOT_FOR_CMD`) |

A value that is set but unusable is an error; SoulRun never falls back to a default silently. Every error is a
`soulrun.SoulRunError` with a stable `code`, the `field` concerned and what was `expected`: `UsageError` when the
call is wrong, `EngineUnavailable` when the bundled engine cannot be loaded; an error the engine raises keeps the
engine's own code. [GUIDE.md](GUIDE.md) lists the codes.

### Which Program Runs

The arguments only decide **what the candidates are**. Which one runs is judged by the engine's main
program from the user's words; when that is unclear, the human is asked.

| Given | Candidates |
|---|---|
| nothing | everything under `aiap_dir` and `aisp_dir` |
| `aiap=` or `aisp=` | just that one |
| both | just those two |
| a designated program **and** the big folders | the designated one only |
| a designated program that cannot be found | nothing runs: SoulRun asks, says where it looked, what the big folder holds, and what it would suggest |

### Engine Commands

```python
soulrun(cmd="next-node", cache_dir=...)                       # the node to do now
soulrun(cmd="node-commit", cache_dir=..., node="...", payload={...})
```

`next-node`, `node-commit`, `stop-decision` and `gate-answer` are the engine's own command-line tools. The model
uses the first two on every step. In the slim form (the default) the text names them as commands run through
SoulRun; in the entry-path form it names the engine's scripts by path. Every spelling runs the same code. On the
command line, in a slim turn, an engine reply is printed whole and first, followed by the part of the engine program
its step needs when the turn has not had it yet ([Program Forms](#program-forms)); `soulrun(cmd=...)` returns the
reply alone.

---

## Command Line

```bash
soulrun                                              # the guide
soulrun --user-message-file msg.txt                  # prints what the model should be given; msg.txt goes into the run
soulrun --user-message-file msg.txt --keep-message-file   # the same, msg.txt staying where it is
soulrun --user-message-stdin --json < msg.txt        # one JSON object instead
soulrun --aiap <name>                                # no words, one program named: that program is run
soulrun --cmd next-node --cache-dir <dir>            # every argument but "--cmd NAME" goes to the engine tool
soulrun --program --cache-dir <dir> [--node N | --field F]   # the business program the run is bound to, as JSON
soulrun --report <link> --cache-dir <dir>            # the complete execution report behind an engine-report: link
soulrun --engine-node <name> [--cache-dir <dir>]     # a part of the slim engine program, on request
soulrun --expand <reference> --cache-dir <dir>       # the text of a public block, as a host shows it
soulrun --user-message-file msg.txt --no-slim-program   # the entry-path form (SoulBot's text)
soulrun --version                                    # SoulRun's version and the bundled engine's
soulrun --engine-info                                # which engine is bundled, as JSON
soulrun --verify-engine                              # every bundled engine file against its recorded SHA-256
soulrun --doctor                                     # is everything in place for a run? leaves nothing behind
```

`soulrun --doctor` (add `--agent-dir`, `--soulrun-cache-dir`, `--aiap-dir`, `--aisp-dir`, `--aiap`, `--aisp` and the
program-form switches `--slim-program`, `--no-slim-program`, `--inline-program` as a run would get them, and
`--json`) prints one line per check — `OK`, `WARN` or `FAIL`: the versions, the engine files against the
manifest, whether the slim program was built from this engine, the engine's interface as SoulRun calls it, the
`python` a model's shell will find, time-zone data, the program form a run with those switches gets, the engine's
own environment settings (`CACHE_NUM` decides how many runs are kept), the agent folder and its programs (programs in the
wrong folder, and registry scripts the engine would run, too), the run folder (written to with one file that is
removed at once — on Windows the usual check only looks at the read-only attribute), a run folder without
`.gitignore` or, on Linux and macOS, one other users can open, runs that never finished, and on Windows a run folder
deep enough for the engine's files to reach the 260-character limit. It runs no program. It exits `1` when a check
fails; warnings do not fail.

The user's words are read from a file or from standard input, never from the command line itself. A
byte-order mark at the very start (Notepad and PowerShell often write one) is dropped, here and in the Python
call alike: it is not part of the words, and the engine does not recognise "继续" behind one. A file in UTF-16 with
its byte-order mark (what Windows PowerShell 5.1 writes with `>`) is read too; anything else that is not UTF-8 is
refused (`MESSAGE_NOT_UTF8`), never guessed. Once the turn has its run, the file is moved into that run's folder
(`<run>/_soulrun/message.<n>.txt`), so the human's words do not stay in the project and go when the engine removes
the run; `--keep-message-file` leaves it, and a turn without a run (a question before any run) leaves it for the call
that answers. Words written into a new run folder before its first run do not keep the folder from being used.

A turn printed on the command line has no host program between SoulRun and the model to show the human the
blocks the engine names by reference lines (plans, nodes' blocks with their messages, gates, the final answer,
the evidence): the model is the host. The text says so (`[SOULRUN SCREEN]`), and after each engine reply the
command line prints the text of the blocks it names under `[SOULRUN FOR THE HUMAN]`, once per turn, for the model
to print on the screen. Blocks that would pass the print cap follow a later reply with room (a gate's and the final
answer's replies are short); `soulrun --expand` prints one on request. `--json` and the Python call are for host
programs, which show the blocks themselves (SoulBot does), and get none of this.

Exit codes: `0` success (a guide, a run and a question for the human are all successes), `2` wrong usage, `1` any
other error (a failed `--verify-engine` or `--doctor` check, an unusable engine, an engine error); with `--json` an
error SoulRun raises is one JSON object on standard error, and `--verify-engine` and `--doctor` print their report,
failed checks included, as JSON on standard output. With `--cmd`, once the engine tool runs, the exit code is the tool's
own, or `74` when its reply could not be printed ([The Engine](#the-engine)); what SoulRun refuses before that (a
missing or unknown command name, a user message given with `--cmd`) is wrong usage, `2`.

---

## For Hosts

`soulrun.host` gives a host the engine functions it calls around a model turn — without knowing where the
engine lives:

```python
from soulrun import host

# every turn
host.expand_refs(reply, cache_dir=ctx.cache_dir)      # the reply as the human reads it: blocks, not references
host.after_turn(ctx.cache_dir, reply)                 # after every turn: a shown question's delivery, what was said
host.observe(cache_dir, reply)                        # after_turn's second step alone: what the model said
host.finalize(cache_dir)                              # after_turn's last step alone: the reply was stored
# a Stop, a restart, a broken connection
host.stop(ctx.cache_dir, host_run_id)                 # the human pressed Stop
host.open_question(cache_dir)                         # the question a run waits on outside the model, or None
host.mark_question_delivered(cache_dir)               # the host showed that question itself
host.interrupted_runs(created_before=started_at)      # runs cut off by a restart
host.resume_interrupted_enabled()                     # the human's setting: re-enter after a restart, or ask (default)
host.open_restart_question(cache_dir, instance_started_at=started_at)   # switch off: ask the human (or SKIPPED)
host.mark_interrupted(cache_dir)                      # switch on: note that the run was cut off ...
host.resume_prompt(cache_dir)                         # ... and the text that re-enters it
host.runner_recovery(host.RecoveryRequest(...))       # the decision after a broken model connection
# where things are, and what the model is given
host.soulrun_cache_dir(agent_dir=...)                 # the agent's runs
host.cache_root(agent_dir=...)                        # the folder of numbered runs inside it
host.latest_run(session_id, agent_dir=...)            # a conversation's latest run, or None
host.program_root()                                   # the engine's program folder inside the package (its tools)
host.engine("lib.stop_flow")                          # any engine module, for hosts that already call it by name
host.system_prompt("slim")                            # the opening instruction for a form, before any call
host.project_slim_policy(text, cache_dir=..., entry_mode=...)     # a slim turn's fixed instructions, to compare turns
host.program_view(ctx.cache_dir)                      # what soulrun --program prints (node=, field= as there)
host.execution_report(link, cache_dir=ctx.cache_dir)  # the complete execution report behind its engine-report: link
# sub-agents (below)
host.dispatches_nodes(index)                          # does this run hand its nodes to sub-agents?
host.observe_agent_start(cache_dir, sha256, ...)      # what the host saw: a sub-agent started
```

A host that used to keep the engine inside each agent folder replaces "the agent's engine folder" with
`soulrun_cache_dir(...)` wherever it means runs, and with `program_root()` wherever it means the engine's
tools. None of these doors creates the run folder: asking about an agent that never ran leaves nothing
behind; the first `soulrun(...)` run makes it. How SoulBot is wired to SoulRun, and the rules a host must keep (one
engine per process, runs found only through SoulRun, what happens to runs of an older engine or of another SoulRun
build), are in [docs/guide/02-soulbot-integration.md](docs/guide/02-soulbot-integration.md). The execution report block ends
with an `engine-report:<run>/<node>@<visit>/<sha256>` link to the complete report; SoulBot's web page opens
it, and every other host opens it with `host.execution_report(link, …)` or `soulrun --report <link>` - checked
as SoulBot checks it (bound to the run, hashing to its digest), paged when long. A host with an opening instruction
of its own puts `ctx.system_prompt` in its place, so the instruction always matches the program form of the turn
(SoulBot's agent template does; for the guide or a question SoulRun asks before any run exists, `ctx.system_prompt`
is `None` and the template keeps its own text-only instruction).

**After a restart** the human's setting decides (`host.resume_interrupted_enabled()`, from
`SOULBOT_RESUME_INTERRUPTED_RUNS`; unset means stop and ask). For each run of `interrupted_runs(created_before=…)`
that is not already stopped (`row["stopped"]`): with the switch off, `open_restart_question(...)`; when it is
OPENED, show `open_question(cache_dir)["text"]` in the run's conversation and call `mark_question_delivered(cache_dir)`;
the human's answer then comes as an ordinary message. For a run whose engine stop was cut off before its index write
it returns SKIPPED, with nothing to show: the human's next message re-enters that run and its stop is shown first
(a turn not from the human is refused there, `HUMAN_REPLY_REQUIRED`, as at a waiting gate). With the switch on,
`mark_interrupted(cache_dir)` and send
`resume_prompt(cache_dir)` through `soulrun(..., session_id=<the run's>, origin_type="engine_recovery",
human_turn=False)`. A stopped run is left to the human; show its question again when `row["question"]` was never
delivered. Re-entry text works only in its run's own conversation.

**A Stop**: `host.stop(ctx.cache_dir, host_run_id)`, and end the model's turn under way. The human's next message
goes through `soulrun(...)` as usual; the engine and the model work out what to ask, and the reply that shows the
question is handled like any other turn.

**A broken connection**: `host.runner_recovery(request)` with `phase="plan"` gives the engine's decision (the phases
are `host.RECOVERY_PHASES`). `resume`: wait `delay_seconds`, send `phase="start"` and give the model the decision's
`prompt`, then `phase="complete"` when that turn ends (`phase="cancel"` when it is cancelled). `ask`: show
`public_text` (expanded) and send `phase="delivered"`. `wait` / `hold`: show `public_text` when there is one and try
again after `next_probe_seconds`. `stop`: give up, showing `public_text` when there is one. `completed`: the run had
already finished.

**One model session across turns.** A host that keeps one model session for a run's turns (SoulBot's send layer
does) compares a slim turn's fixed instructions with `host.project_slim_policy(text, cache_dir=..., entry_mode=...)`,
where `text` is the whole text the host gives the model, `ctx.text` included (`ctx.system_prompt` alone carries no
program part and gives `None`; pass it positionally: the parameter is named `system_prompt`): it rebuilds and checks the program part this package generated, and returns
`policy_text` (the instructions with that part replaced by a marker), `source_digest` and the part itself, unchanged
(`runtime_fragment`) - or `None` for anything it cannot verify. `policy_text` is for comparing only, never a prompt
to send in place of the original. It authorizes nothing: whether the host may keep the model session still rests on
its own protected checks. In the default-untrusted build, `host.parent_policy_ref` returns `None`: an ordinary
host report is not authenticated parent or child identity.

**Sub-agents** (diagnostic host reports). A run in node mode (`host.dispatches_nodes(index)`) hands its nodes to
sub-agents. Hosts can report the tool events they observe, but this build qualifies no report source as proof of
the original child's identity. When a synchronous Agent/Task call, or a SendMessage that resumes a sub-agent, appears:
`observe_agent_start` (with the SHA-256 of its prompt; the answer names the ticket). When that call ends:
`observe_agent_return` (completed or failed); the engine records the return, not presentation of the business gate.
Its menu remains unpublished until the main conversation's next step, which it calls before presenting the returned
references, in every host. The return's separate accepted-block proof does not publish or acknowledge a menu. The
SDK's own task events for a resumed sub-agent:
`observe_agent_task_event`; a failed SendMessage: `observe_resume_failure`. The tool calls a sub-agent makes, as
the SDK reports them under their parent: `observe_tool_request` when pending, `observe_tool_result` when they end
(`resolve_tool_parent` maps a resumed sub-agent's original parent). Two lookups: `resumed_agent_start`,
`parent_policy_ref`. Each door passes straight through to the engine function its docstring names, and
`soulrun --doctor` and `tools/upgrade_engine.py` check those functions. A host that sees no tool calls (a plain
command line) reports none. In every host, an unverified identity requires explicit human authorization for one
new agent, not a claim that the original child resumed. The first unshown business menu combines the business
choice with that authorization. Pause/inspect consumes neither; business refusal follows its original route.
Only an `execute` choice carries new-agent authorization. `cancel` and `terminate` keep their own kind and label,
authorize no replacement, and issue no new ticket. A choice such as “do not export, but finish the report” can still
be an execution choice; the exact presented question and accepted answer determine its scope, not a keyword alone.
An already answered plain menu, later loss, missing replacement wording or unclear authorization requires a
separate question. The old execution right is fenced before asking; a new ticket is issued only after acceptance.
Fencing does not prove process exit: uncertain external effects must be checked, not repeated. Distinct accepted
checkpoints' handovers are counted separately; repeated failures at the same progress retain the existing two
replacement limit. Reports alone grant no replacement or continuation authority. Qualification of a protected
host event and state-writing boundary is a separate review, not enabled by an option in this build.

---

## The Engine

The engine lives in `src/soulrun/soulrun_aiap`: its runtime files, each recorded with its SHA-256 in a manifest.

```bash
python tools/sync_engine.py --check                                                     # prove nothing drifted
python tools/upgrade_engine.py --from <engine tree> --engine-version <X.Y.Z> --dry-run   # what a newer engine would change
python tools/upgrade_engine.py --from <engine tree> --engine-version <X.Y.Z>             # bring it in
python tools/upgrade_engine.py --restore .engine_backups/<kept>                          # go back
```

`upgrade_engine.py` copies the new engine's runtime files byte for byte and checks its identity, version, license
and contract fingerprints; nothing in the engine is rewritten. Before anything is replaced it checks that the slim
program can be built from the new engine, that the engine takes SoulRun's calls as SoulRun makes them, that a run
with a named program can be made (without a model) and, when SoulBot's agent template is found and still carries
the wording, the fixed wording;
when one of these fails, nothing is changed. It then keeps the engine it replaces under `.engine_backups/`, copies
the new one in whole, writes its manifest and rebuilds the slim program. New contents under the version already
bundled need `--same-version`. `--restore` checks the kept archive and that SoulRun can use it before putting it
back; an older engine the current SoulRun cannot call is restored together with the SoulRun it came with.
`--legacy-clean` selects the older cleaner, which rewrites texts and writes the version into the engine, for older
development trees of the engine; it refuses SoulRun's own engine and is not used for it. SoulRun's own version is not touched, and no command here publishes a package.

- `src/soulrun/engine_manifest.json` records the engine version and the SHA-256 of every file;
  `soulrun --verify-engine` checks an installed copy against it.
- SoulRun's version number promises SoulRun's own surface ([GOVERNANCE.md](GOVERNANCE.md#versioning)). What the
  engine makes changes with the engine version and is outside that promise: `ctx.data`, the modules
  `host.engine()` reaches, what the engine puts inside the dicts the host doors return, the engine's own error
  codes, and the files inside a run. The second-stage form is outside it too, and so is the wording of the slim
  form's own texts, which follows the engine as the two are improved together. A new engine is always recorded
  in the CHANGELOG.
- Every 1.x engine keeps the feature set it inherited: its version-dependent behaviours stay on under the version
  number 1.0.0. The engine's files are kept exactly as published, its feature selectors included.
- Unfinished runs require the exact engine digest recorded at creation, not merely the same version.
  With a missing or different build record the run is never continued: a human turn gets a question
  (`ctx.doubt["code"] == "ENGINE_BUILD_MISMATCH"`: end that run, work in another conversation, or leave it), and a
  reply of one cancel word ends it through the engine's `terminate_run` without running any of its steps (only a run
  of the same engine version); a machine turn (`human_turn=False`) is refused with the `ENGINE_BUILD_MISMATCH` error.
  To continue such a run, use its original complete environment. The check is SoulRun's, made when it prepares a
  turn; it is no reason to drive another build's run with the engine's tools directly.
- When SoulRun's command line cannot print an engine reply (the reader closed the pipe) it exits with code 74, writes
  one line to standard error and notes the reply in `<soulrun_cache_dir>/.soulrun/undelivered/<run>.jsonl`; the
  engine has kept the reply in the run.
- The fixed wording the model reads before every turn, and SoulBot's opening instruction, were lifted from
  SoulBot's agent template by `tools/port_agent_text.py` into `src/soulrun/_agent_text.py`, which records that
  template's SHA-256; the `[EXECUTION CONTEXT]` block is rebuilt line for line by SoulRun's own code (`_blocks.py`).
  In the entry-path form SoulRun hands out the text that template gave the model, except on a confirmation after an
  interruption and a cancel: they run nothing, and get the template's text-only assertion instead of its entry block
  and assertion. The slim form keeps the context and interruption blocks and puts its own entry block, assertion
  and opening instruction in place of the rest. SoulBot's agent template now hands every turn to SoulRun and
  carries none of this wording, so it is kept in SoulRun as last generated.
- `src/soulrun/engine_node.aisop.json` is the engine program arranged by engine node: still AISOP, every text
  copied verbatim from the engine's `main.aisop.json`, and its `soulrun_delivery` says which part goes with which
  engine node and why the rest is never handed out. It is generated by `tools/build_engine_node.py` and never
  edited by hand (`--check` proves it current, complete and verbatim, and that no part refers to a text the model
  has not been given by then).

The engine is not edited by hand in this repository: changes reach it through `tools/upgrade_engine.py`.

---

## Program Forms

How the engine program reaches the model. `ctx.program_form` says which form a turn used; a `text_only` turn has
none (`None`). `ctx.system_prompt` is the opening instruction that goes with it: a host puts it where its own was.

- **Slim form (the default).** The design rule: with SoulRun the model reads no file itself, and is given only what
  the step in front of it needs. `ctx.text` carries the start of the slim engine program, composed from
  `engine_node.aisop.json` - the engine's own texts, the user's words in `user_input` - and an entry block that tells
  the model how to do the rest through SoulRun: every engine tool as `"<python>" "<soulrun>/_launch.py" --cmd next-node|node-commit|...` (the
  interpreter running SoulRun and this package's launcher, by absolute path, so the model's shell reaches this
  SoulRun whatever its own `python` is), and the business program as `... --program --cache-dir <run>` (the main
  graph, the node list, the program's system_prompt, output_mode, tools and params, with the size and fingerprint
  of every other sizeable field; `--node` one node's function; `--field` any field in full). A program contract an
  engine reply names in `program_contracts` (the shared constraints, say) is read the engine's own way,
  `... --cmd next-node --read-program-contract <ref>`; SoulRun counts a field the way the engine writes it, so both
  give the same size and fingerprint for the same rule. The model never opens a program file. The entry block, the
  assertion, the opening instruction, the lines SoulRun adds after engine replies and, on a command line, the screen
  block are SoulRun's own wording.
- **Handed out by engine node.** A turn starts with the group `entry`: the engine's identity, `output_mode`,
  `hsaw_first_law`, `system_prompt`, the node execution and payload transport contracts (needed from the first engine
  reply on) and the `Start` function - about two fifths of the main program; a turn that re-enters a run adds `params`
  and `bootstrap_recovery`. Every other group follows the engine reply that first needs it, once per turn: SoulRun's
  command line prints the reply whole and first, then `[SOULRUN ENGINE NODE: <groups>]` and the part as a short
  AISOP. Router.match brings `RouterMatch`; Router.cache-setup `CacheSetup` and `NodeLoop`; a business node
  `NodeLoop`; a dispatch the dispatch scope contract; Engine.execute-report `Report`; Engine.final-answer `Final` and
  the terminal delivery contract; a failed run `ErrorReport`. The output stays under the engine's own print cap
  (29,000 bytes; a model CLI keeps a longer output in a file): a part that would pass it is not printed, and one line
  names it and asks the model to run the `soulrun --engine-node` command that prints it before the step. Never
  handed out: the engine's `tools` and `json_schema` (each engine tool's own reply says what it takes), the pointers to the four
  contracts whose full text every turn's first engine reply carries, and the descriptive fields. What a turn has been
  given is recorded in `<soulrun_cache_dir>/.soulrun/delivered/<run>.json`, with which turn it is: `turn_id` (the
  engine's, which is the run's number, as `ctx.turn_id`: the same on every turn of the run), `host_turn_id` (the
  host's) and `turn` (1, 2, ... within the run, counted as the `.soulrun/turns/<N>.json` row above says); a new turn starts again, since it may be a new model session. `soulrun --engine-node <group, section or function> [--cache-dir <run>]` prints any part on
  request.
- **Real runs.** The recorded R115 runtime head has limited Claude and Codex CLI/SDK and isolated SoulBot evidence;
  the reporting-host restriction, inherited cases and untested paths remain explicit. A documentation edit does not
  repeat those runs or qualify every host (see [Verified Test Baseline](#verified-test-baseline)).
- **A note about an interruption** (the judgement after a Stop, a re-entry, a new task after a Stop) keeps the slim
  form: the note comes first, and the entry block and the assertion say so - a Stop's judgement begins with
  `stop_decision`, the others with `next_node`, and any text the note says to print comes before it - while every
  engine tool the note or an engine reply names goes through SoulRun too. A turn that runs nothing (a confirmation
  after an interruption, a cancel, a question) gets the context, the note and a text-only assertion, never an
  entry block that would send the model to read `main.aisop.json`.
- **Falling back.** A turn gets the entry-path form instead, and says why in `ctx.slim_fallback`, when:
  the slim program cannot be built (`engine_node.aisop.json` missing or built from
  another engine) - `SLIM_PROGRAM_UNAVAILABLE`; or the run, or the conversation's previous run, went wrong in the slim
  form - `EARLIER_SLIM_PROBLEM`: still at Router.match with nothing committed when the next turn came although the
  model had its turn, or failed at an engine node. Such a problem is written in the run's note and the rest of that
  conversation keeps the entry-path form; other conversations keep the slim form. A turn too long for a command line
  is printed in the entry-path form (`--json` says `TOO_LONG_FOR_COMMAND_LINE`).
- **Entry-path form.** `slim_program=False`, `SOULRUN_SLIM_PROGRAM=false` or `--no-slim-program`: the text
  SoulBot's agent template gave before SoulBot ran on SoulRun (see [The Engine](#the-engine)) - the model reads
  `main.aisop.json` itself - and the opening instruction that went with it as `ctx.system_prompt`. A turn that runs
  nothing gets the context, the note and the text-only assertion here too: the template also gave a confirmation
  after an interruption and a cancel its entry block and "read the entry first" assertion, although their notes
  say to run nothing.
- **Second-stage form (experimental).** `inline_program=True` (or `SOULRUN_INLINE_PROGRAM=true`) also hands back the
  main program with the user's words placed in its `user_input` slot, as data, last, into the engine's untouched
  text; it turns the slim form off. On a command line the output stays under the engine's own cap (29,000 bytes):
  when the whole does not fit, the program is left out and a marker names the file that holds the full text. It has
  not been accepted with real runs.

---

## Project Structure

```text
SoulRun/
├── src/soulrun/
│   ├── __init__.py              # the callable package and its version
│   ├── __main__.py              # python -m soulrun
│   ├── _api.py                  # the one call
│   ├── _select.py               # agent_dir, aiap_dir, aisp_dir, soulrun_cache_dir, candidates
│   ├── _adapter.py              # hands the candidates to the engine for one call
│   ├── _blocks.py               # the text the model is given before an engine turn
│   ├── _agent_text.py           # generated from SoulBot's agent template (never edited by hand)
│   ├── _slim.py                 # the slim engine program, handed out by engine node
│   ├── _policy.py               # host.project_slim_policy: a slim turn's fixed instructions, checked
│   ├── _program.py              # soulrun --program: a run's business program, handed to the model
│   ├── _report.py               # soulrun --report: the complete execution report behind its link
│   ├── _launch.py               # the command line the slim text names (this interpreter, this package)
│   ├── _records.py              # SoulRun's notes beside the run data
│   ├── _filelock.py             # one run prepared at a time, across processes
│   ├── _cmd.py                  # engine commands
│   ├── _screen.py               # no host program on a command line: the blocks for the human
│   ├── _message_file.py         # the message file goes into its run's folder
│   ├── _render.py               # what the command line prints, under the cap
│   ├── _engine.py               # the bundled engine: where it is, its version, its check
│   ├── _doctor.py               # soulrun --doctor
│   ├── errors.py                # SoulRunError, UsageError, EngineUnavailable
│   ├── host.py                  # doors for hosts
│   ├── cli.py                   # the soulrun command
│   ├── guide.txt                # the guide (also read by model sessions)
│   ├── py.typed                 # the package is typed
│   ├── engine_manifest.json     # engine version, source, SHA-256 of every file
│   ├── engine_node.aisop.json   # generated: the engine program arranged by node
│   └── soulrun_aiap/            # SoulRun's engine: the runtime files only
├── tests/                       # SoulRun's own tests (no model is called)
├── tools/                       # engine cleaning, sync and upgrade, generators, package and docs checks
├── examples/                    # a minimal host and the SoulACP "program door"
├── docs/                        # documentation map and developer guides
└── pyproject.toml
```

---

## Testing

```bash
python -m pip install -e ".[dev]"                             # test tools
python tools/sync_engine.py --check                           # the engine matches its manifest
python tools/sync_engine.py --check-release                  # the engine's recorded source form and payload, read only
python src/soulrun/soulrun_aiap/tools/aiap_conformance_check.py src/soulrun/soulrun_aiap   # the engine's own AIAP check
python tools/build_engine_node.py --check                     # the slim program matches the engine
python -m ruff check src tests tools examples                 # lint
python tools/check_docs.py                                    # docs: links, anchors, fences, local paths, footers
python -m pytest -rs                                          # SoulRun's own tests (-rs: why any test was skipped)
SOULRUN_TEST_INSTALLED=1 <clean env>/bin/python -m pytest     # the same tests, against a wheel installed alone (INSTALL.md)
```

No test calls a model. Where a model would act, the test sends the engine what a model would send.

### Verified Test Baseline

The current 97-resource source manifest, after history trimming and host-neutral usage clarification, is
`9e618ba59d3238058305a41778af6b1b03000107b0343633eb044cee0ad15d3b`.
Executable sources and governance fields are unchanged; the standalone caller guide was corrected too.

**November 11 local qualification of that digest, before the release-check refresh:**

| Scope | Environment | Result |
|---|---|---|
| Shared Engine full selection | Windows 3.12.9 | 8613 passed, 9 skipped; 8622 total, 0 failed/errors |
| Shared Engine full selection | Ubuntu 3.12.3 | 8606 passed, 16 skipped; 8622 total, 0 failed/errors |
| SoulRun source package suite | Windows 3.12.9 | 912 passed, 3 skipped; 915 total, 0 failed/errors |
| SoulRun source package suite | Ubuntu 3.11.18, 3.12.3, 3.13.18, 3.14.10 and 3.15.2, each separately | 911 passed, 4 skipped; 915 total in each run, 0 failed/errors |
| Fresh installed wheel | Ubuntu 3.12.3 | 911 passed, 4 skipped; 915 total, 0 failed/errors |

A subsequent QA-only process-race repair was checked with 17 guard tests on each platform. The current
8626-ID Engine qualification composes 8609 unchanged IDs from the full runs with those 17 tests; **no
single full run of 8626 is claimed**. Each of the 25 platform skips passed on the other platform, without
turning either run into zero skips or qualifying native Windows symlinks that lacked privileges.
Those Python 3.15 results are local compatibility evidence, not a hosted-CI result or support-policy change. Windows SDK
3.11–3.15 and cold-install results are inherited from the exact earlier payload, not rerun measurements.

One local user-site CLI/SDK installation was updated and its 124 payload files verified; that does not
update a production host. Current release-check changes and their artifacts need their own maintainer
receipts. See [Verification Scope](docs/verification-1.0.0.md) for dated artifact hashes, inheritance,
remaining observations and the distinction between local checks and hosted CI.

The [CI matrix](.github/workflows/ci.yml) covers Windows and Ubuntu with Python 3.11–3.15 (10 source-test jobs and 2 package jobs).
The newly added Python 3.15 jobs await hosted execution; earlier CI results do not qualify them.
Historical build tables are retained in the [verification archive](docs/verification-1.0.0.md#readme-history-archive).

---

## Installation Options

These are for people working on SoulRun itself; everyone else installs from PyPI or GitHub
([Install](#install)).

```bash
# Development (editable), with test tools
pip install -e ".[dev]"

# Build and release tools
pip install -e ".[release]"

# A built wheel: the installed package carries the engine and no longer needs this folder
python -m build
pip install dist/soulrun-<version>-py3-none-any.whl
```

See [INSTALL.md](INSTALL.md) for the detailed installation, packaging and publishing guide.

---

## Privacy and Local Files

- Runtime records can contain user messages, human answers, tool output and business results. They are not encrypted
  by SoulRun; a checksum detects content changes but does not hide content or authenticate its author.
- Keep run data, host logs, provider profiles and credentials outside source and release folders. The repository's
  ignore rules cover common local material and keep `.env.example` templates visible. They do not remove already
  tracked files, erase history, change ACLs or prove that a folder is private. Review the exact files to be shared.
- Supply sensitive user text through standard input or a private message file, not a command argument or literal shell
  history entry. Message-file consumption is not secure erasure: run records and the host/provider may retain copies.
- SoulRun itself does not contact a model or upload records. Hosts, providers, business programs and their tools have
  separate network, logging and retention policies. `human_turn` and host capabilities must be supplied truthfully by
  the host; a flag or an ordinary report is not an authenticated identity proof.
- Do not paste credentials or raw private runs into an issue. Use a synthetic reproduction and the disclosure process
  in [SECURITY.md](SECURITY.md). No ignore pattern or passing sample scan makes arbitrary future input safe to publish.

## Known Limits

- **Enforcement boundary.** With a qualified host, a gate refuses a managed operation that lacks the accepted human
  answer, authority, ticket or evidence it needs. This is not an operating-system sandbox, and it does not stop an
  arbitrary command line or an untrusted host from calling unrelated tools. File hashes check recorded content; they
  are not an independently trusted signature. An `ASSERT` the engine does not check is not machine-proved.
- **Reports are not original-child identity.** All report sources are unqualified in this build, including hosts
  that report the whole path through `soulrun.host` ([For Hosts](#for-hosts)). Explicit human authorization, not a
  report, permits a new agent to continue recorded unfinished work. The original execution right is fenced first;
  this does not attest process exit. Restoring original-child continuation requires a separate review of protected
  event provenance and machine-state writes. Recorded or synthetic events test rules, not real-host qualification.
- **A business gate a sub-agent pauses at is shown by SoulRun at the main conversation's next step.** The contract
  has the main conversation call next-node once before it presents such a gate; that step writes the gate's menu and
  serves it, in any host - SoulRun's own command line with `--host-tool agent=true` (as the SoulSkill bridge runs it),
  SoulBot, an SDK host - so one answer to the presented business gate is accepted. A host's return report never writes
  that menu or marks it shown; if the turn ends after the report but before the main next step, an answer is still held. A
  model that presents the sub-agent's references without that next step shows a gate SoulRun has not counted as
  shown: the human's first reply is not taken, the next step shows the gate, and the human answers once more.
  This presentation rule does not authenticate original-child identity. The first menu explicitly combines business
  choice and new-agent authorization; old wording or later loss requires another question, not implied consent.
- **A designated program that does not fit the request** is not forced to run: at Router.match the request can go
  to `no_match` and is answered directly, without a gate that asks the human first; the answer begins with a line
  saying no designated or scanned program matched. **After the human has chosen
  between candidates** at Router.match, the run is bound to the chosen program: another candidate or `no_match` is
  refused (`ROUTE_CHOICE_CONFLICT`), and missing or conflicting evidence of the choice is not taken as a choice. This
  binds the choice; it does not make a model-written label or the program's conclusions correct.
- **While a run waits at a gate for the human's answer**, a turn marked as not the human's (`human_turn=False`,
  `--machine-turn`) is refused (`HUMAN_REPLY_REQUIRED`), and so it is, with `SOULBOT_RESUME_INTERRUPTED_RUNS` off, at
  a run whose engine stop was cut off before its index write (it reads as running; nothing in it is written) and at a
  run marked running that cannot be read then (the run lock a killed process left, until the engine reclaims it after
  two minutes; a gate record its index does not know that the engine cannot classify). The engine's own entry, called
  directly, does not raise this error but does not take such a turn as the answer either: it keeps the message and
  leaves the gate open (`entry_mode` `gate_hold`). Either way a host says truthfully whether a message comes from a
  human. With the switch on, a machine message to such a run is routed as to any interrupted run (a cancel word ends
  it); a message that starts with the host's recovery marker and names such a run of that conversation (its
  `cache_dir:` in the same run folder) goes to the engine with the switch in either position.
- **A Creator program that still recognises the run format by an engine version starting with "7."** cannot find
  its target on engine 1.0.0 until the Creator itself changes.
- **Candidate lists other than "everything under the agent folder"** are passed to the engine in memory for
  the duration of one call, because its `prepare` entry does not take them yet.
- **A question raised before any run exists** (program not found, wrong `cache_dir`, an unfinished run not
  created for the named program, a run left by another engine build) is handed back as text.
  Every option in `ctx.doubt["options"]` carries what to do when the human picks it — `call` with the
  arguments to change, `ask`, or `cancel` — but SoulRun keeps no memory of the question: whoever shows it
  carries the answer back.
- **Reconnect handling inside the engine** assumes program and data share a folder. `host.resume_prompt` and
  `host.runner_recovery` give it the run folder and point the re-entry text at the program; a host that calls
  the engine's handler directly would send the model to a tool that is not there. (After a Stop,
  when the model judges that the run goes on - `stop-decision` with `continue` - the engine's next step names its
  own `next_node.py`.) In the slim form the entry block has the model run any engine tool a reply names through
  SoulRun, whatever its path; the entry-path form still meets the reconnect case when a host calls the handler
  directly.
- **The model's command line must be able to read the installed package.** The engine's tools (and, in the
  entry-path form, the engine program) are read from where SoulRun is installed (`soulrun --engine-info`); a model CLI that may only read its working
  folder, or runs in a sandbox, cannot follow the first instruction. Limited Claude and Codex paths were tested;
  they do not qualify every CLI, sandbox or reporting-host configuration.
- **Folders with spaces.** The commands the model is given name the engine's folder and the run folder as they
  are, unquoted (the fixed wording is SoulBot's, word for word): with a space in either, as under Windows'
  Program Files, a shell that runs the command literally fails. Install SoulRun and keep runs in folders
  without spaces. In the slim form the command that runs SoulRun itself is quoted; the run folder is not.
- **The slim form reaches the main conversation only.** The engine hands a sub-agent the path of its own engine
  program (`agent_engine.aisop.json`), and the sub-agent reads it. The engine's own texts also still speak of
  reading the program entry, and its node packets do not carry the business program's tools, params or
  system_prompt: the slim entry block says that reading is done and sends the model to `soulrun --program`. The
  engine itself hands out neither.
- **What reaches the screen is up to the model.** On a command line SoulRun hands the model the text of every block
  for the human, and the model has to print it. In independent sessions on an earlier build, Claude Code put every
  gate in full, every final answer and evidence, and most node blocks on the screen, but not the blocks of the first
  few steps (routing, setup, the first node), whatever the wording. Later CLI/SDK functional runs do not prove that
  every model forwards every block. A host needing deterministic display must render accepted text/references itself.
- **The parts handed out by node come through SoulRun's command line.** An engine tool run another way (the
  engine's script by path, or `soulrun(cmd=...)` in Python) returns the reply alone; the entry block tells the
  model to ask for a part it lacks with `soulrun --engine-node`. A part that would take an engine reply past the
  print cap costs the model that one extra command; a reply the engine itself prints past the cap (it folds what it
  can) is still kept in a file by a model CLI that does so, with the line naming the part after it.
- **A turn that falls back reads files again.** A turn given in the entry-path form - the slim program cannot be
  built, or the conversation went wrong in the slim form - carries SoulBot's opening instruction, so the model
  reads `main.aisop.json` itself and runs the engine's tools with its shell's `python`. Turns with a note about
  an interruption do not fall back.
- **Tested platforms.** The recorded runtime head has Windows Python 3.12.9 and Ubuntu Python 3.12.3 evidence.
  The dated local Python 3.11–3.15 SDK and Ubuntu Engine results have the exact scope above; macOS was not tested.
  Local QA and a documentation revision do not establish hosted-CI or every-platform qualification
  (see [Verified Test Baseline](#verified-test-baseline)).
- **Time zones on Windows.** When the model's provider names a zone for its usage-limit reset ("resets 2pm
  (America/New_York)"), the engine reads it with `zoneinfo`; when it cannot read that zone (no time-zone data, or a
  zone name it does not know) it uses local time and records that in the run (`SUPPLY_RESET_ZONE_UNREADABLE`, shown
  in the run's report). Windows has no time-zone data of its own: a Python from python.org needs
  `python -m pip install tzdata`. SoulRun itself keeps no run-time dependency; `soulrun --doctor` warns when the data
  is missing.
- **Path length on Windows.** A run nests its files about 130 to 150 characters deep inside `soulrun_cache_dir`:
  the deepest is a node's block, named with the node's name and a 64-character digest: a program's node (146 in an
  AIAP Creator run, 148 once run numbers have three digits) or, when the programs' node names are short, the engine's
  own `Engine.execute-report`, whose block every run writes (130 at a three-digit run number). With Windows' long
  paths off, a run folder too long for that makes the engine fail; its tools now say so ("Path too long: N
  characters … 260 …"), where earlier builds reported a misleading "No such file or directory" (on an earlier
  build, a 150-character folder failed at the first commit). Keep the folder short or enable long paths; `soulrun --doctor` works the depth out from the node names of the programs it finds and of the engine's own
  nodes, names the node, and warns.

---

## Documentation

| Document | Description |
|----------|-------------|
| [docs/README.md](docs/README.md) | Documentation map: reader map, sources of truth, generated records, and the documentation gate |
| [docs/verification-1.0.0.md](docs/verification-1.0.0.md) | Dated runtime/artifact evidence, skip scope, inherited cases and untested boundaries (EN + CN) |
| [GUIDE.md](GUIDE.md) | Comprehensive usage guide (Chinese) |
| [INSTALL.md](INSTALL.md) | Installation, packaging, and publishing (Chinese) |
| [DEPENDENCIES.md](DEPENDENCIES.md) / [DEPENDENCIES_CN.md](DEPENDENCIES_CN.md) | Verified dependency baseline, Python matrix, engine bundle, and upgrade policy |
| [SECURITY.md](SECURITY.md) | Security policy and vulnerability reporting (EN + CN) |
| [CONTRIBUTING.md](CONTRIBUTING.md) / [CONTRIBUTING_CN.md](CONTRIBUTING_CN.md) | Contribution process, including the bundled-engine rule |
| [GOVERNANCE.md](GOVERNANCE.md) | Project governance and decision-making |
| [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) | Community code of conduct (Axiom 0 alignment) |
| [CHANGELOG.md](CHANGELOG.md) | Release history |
| [docs/release-1.0.0.md](docs/release-1.0.0.md) | V1.0.0 release notes: the engine it carries, the results verified for it, and what it does not claim (EN + CN) |
| [docs/guide/01-design.md](docs/guide/01-design.md) | Design notes: why SoulRun is built the way it is |
| [docs/guide/02-soulbot-integration.md](docs/guide/02-soulbot-integration.md) | SoulBot on SoulRun: how its agents and host are wired, and the rules a host keeps |
| [examples/README.md](examples/README.md) | A minimal host and the SoulACP "program door" |

---

## AIXP Labs [aixp.dev](https://aixp.dev)

AIXP Labs develops and maintains the following core projects:

| Project | Description | Website |
|---------|-------------|---------|
| [HSAW](https://hsaw.dev) | Human Sovereignty and Wellbeing — Axiom 0 white paper (foundation) | hsaw.dev |
| [AIZP](https://aizp.dev) | AI Zenith-Zero Protocol — runtime behavioral alignment | aizp.dev |
| [AIIP](https://aiip.dev) | AI Intent Protocol — governed intent trees, priorities and feedback | aiip.dev |
| [AIKP](https://aikp.dev) | AI Knowledge Protocol — long-term knowledge organization, navigation and governance | aikp.dev |
| [AIJP](https://aijp.dev) | AI Job Protocol — schedulable work trees and job graphs | aijp.dev |
| [AINP](https://ainp.dev) | AI Neogenesis Protocol — governable generation projects: plan + content + evidence | ainp.dev |
| [AILP](https://ailp.dev) | AI List Protocol — agent discovery and capability advertising | ailp.dev |
| [AIVP](https://aivp.dev) | AI Value Protocol — international commerce, crypto asset settlement | aivp.dev |
| [AIRP](https://airp.dev) | AI RMB Protocol — Mainland China commerce, RMB licensed settlement | airp.dev |
| [AIBP](https://aibp.dev) | AI Bot Protocol — social communication and trust | aibp.dev |
| [AIAP](https://aiap.dev) | AI Application Protocol — governance and compliance | aiap.dev |
| [AISP](https://aisp.dev) | AI Skill Protocol — directory packages with a canonical AISOP skill entry and enforceable contract bindings | aisp.dev |
| [AISOP](https://aisop.dev) | AI Standard Operating Protocol — flow program definition | aisop.dev |
| [AIXPStore](https://aixpstore.dev) | Official marketplace for AIAP programs and AISP skills — discover, publish, and distribute AI capabilities | aixpstore.dev |
| [SoulSkill](https://soulskill.dev) | AISP skill reference library & multi-CLI plugin distribution | soulskill.dev |
| [SoulAgent](https://soulagent.dev) | Drop-in AI agent invoked directly by any CLI / SDK / IDE | soulagent.dev |
| [SoulBot](https://soulbot.dev) | AI agent runtime & orchestration framework (scheduling, agent-spawn, inter-agent comms) | soulbot.dev |
| [SoulRun](https://soulrun.dev) | AISOP execution engine as one call — runs AIAP programs and AISP skills for any host **(this project)** | soulrun.dev |
| [SoulACP](https://soulacp.dev) | Adapter library — bridging CLI tools and LLM providers | soulacp.dev |

---

## ⚠️ Disclaimer

This software is **experimental** and provided for **research and educational purposes only**. Not intended for production use. Use at your own risk. The authors assume no liability for any damages arising from the use of this software. See [LICENSE](LICENSE) for full terms (Apache 2.0).

---

## License

[Apache License 2.0](LICENSE) - Copyright 2026 AIXP Labs AIXP.dev | SoulRun.dev

---

Align Axiom 0: Human Sovereignty and Wellbeing. Version: SoulRun V1.0.0. <www.soulrun.dev>

<a id="alignment-philosophy"></a>

## ⚓ Alignment & Philosophy

### Axiom 0: [HSAW | Human Sovereignty and Wellbeing](https://hsaw.dev)

- **No HITL, HSAW.**
  *Human Sovereignty and Wellbeing is Axiom 0, requiring no hypocritical human-in-the-loop.*
- **No w.a.s.h, Real h.s.a.w.**
- **人非蝼蚁，人为道。**
- **We are not beggars. We the People.**

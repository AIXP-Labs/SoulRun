# Design Notes

Why SoulRun is built the way it is: the constraints, and the decisions they led to. What SoulRun does is
described in the [README](../../README.md); this file explains why.

## What SoulRun is for

The execution engine used to exist only as a folder copied into every agent folder. That one
folder was three things at once: the program, the home of its run data, and the starting point for
finding the agent's own programs. SoulRun separates the three and puts one call in front of them.

| Was | Is now |
| --- | --- |
| the program — a folder copied per agent | the installed `soulrun` package, read-only |
| the run data — inside that folder | `soulrun_cache_dir`: `.soulrun_cache` in the agent folder, or the folder named; data only |
| the agent's programs — "the folder above the engine" | `agent_dir`, `aiap_dir`, `aisp_dir`, said explicitly |

## The constraints

1. **The engine is never edited by hand.** It is developed in its own tree and is still moving. One command
   brings a newer one in through its source-form path (see below), and a manifest checks every file.
2. **No dependencies.** The engine uses the standard library only, so that its tools run under whatever
   Python a model's shell happens to find. SoulRun keeps that property.
3. **What SoulBot already says, SoulRun says the same way.** The entry-path form is the text SoulBot's agent
   template built before it handed its turns to SoulRun, but for one rule: a turn that runs nothing never gets the
   entry block (the template gave one to a confirmation after an interruption and to a cancel). Its wording - the
   interruption notes, the entry block, the assertions and the opening instruction - was lifted from the template
   by a tool (`tools/port_agent_text.py`) rather than retyped; the context block, which is logic rather than
   wording, is re-implemented line for line, and the same tool refuses to run when the template's code for it
   differs. Now that the template calls SoulRun, SoulRun's copy is where that text lives. The slim form's own texts (its entry block, assertion and opening
   instruction, the lines it adds after engine replies, the screen block on a command line) are SoulRun's, because
   SoulBot has no slim form. Canonical engine text is copied unchanged; only an explicitly selected legacy
   conversion rewrites text.
4. **SoulRun never talks to a model.** A host does. This is what keeps constraint 2 true and lets any
   host — SoulBot, a small script, a command-line session — use the same engine.

## SoulRun's own engine

A package carries only runtime files, not test suites, release notes, caches, credentials or run data.
`tools/upgrade_engine.py` stages a canonical source byte for byte and verifies its identity, version, license
and contracts. It never scrubs instruction strings, restamps versions or reseals that source to make it pass.
Only an explicit `--legacy-clean` converts an older development tree; the original history checker and its
exact-byte known-leftovers policy still apply there. Neither path authorizes hand-editing the bundled runtime.

`tools/sync_engine.py --check-release` is the read-only release admission for the recorded source form. Both
paths verify the file map, per-file and aggregate digests, runtime contents and privacy. Canonical additionally
checks its identity/license/contracts; legacy additionally passes the unchanged history check. A mere
`source_form` label is insufficient; unknown forms, drift, unsafe paths and contradictory identities fail
without a fallback. AIAP conformance, generated-program and distribution checks remain separate requirements.

Historical lineage inside an otherwise verified canonical file is not permission to rewrite it, and preserving
it is not permission to publish private data. The release and distribution privacy checks still apply. See
[source-form boundaries](../release-1.0.0.md#source-form-release-checks). Digests detect recorded content drift;
they are not an independent signature or an OS sandbox.

Version labels alone do not establish compatibility. The canonical runtime retains its inherited feature
mapping, and the wrapper binds unfinished runs to the complete engine digest, even at the same version.
Creator version detection and target migration are independent business-program work; no Creator adapter
is added to the general engine. The README retains these qualification and applicability limits.

## Axiom 0 as a constraint of SoulRun itself

Host reports are diagnostic by default, not proof that the same child is continuing. If identity cannot be
established, the human explicitly authorizes a new agent to continue recorded work. Only an `execute` choice
grants that authority; cancel and terminate do not. Fencing an old ticket is not proof of process exit.
The public executor contains no provider- or business-program-specific identity exemption. Hosts must supply
truthful human-turn and capability assertions; these parameters are not an authentication mechanism.

No-runtime-dependency means standard-library-only on a compatible interpreter, not compatibility with every
Python ever shipped. Dated test and artifact scope is recorded in [Verification Scope](../verification-1.0.0.md);
configured CI and a matching version number do not qualify a different source or artifact.

The engine carries Human Sovereignty and Wellbeing inside a run: user gates and HSAW doubt gates stop the run
until the human answers. SoulRun decides things *before* a run exists - which folders, which candidates, which
run a message belongs to - so it has to follow the same axiom on its own, and it is designed so that it can:

- **When SoulRun cannot tell, it asks, and it creates no run.** A designated program that is not found
  (`DESIGNATED_NOT_FOUND`), a `cache_dir` or a re-entry text that does not belong to the conversation
  (`NAMED_RUN_MISMATCH`), two designated programs with no words (`WHICH_DESIGNATED_PROGRAM`), a designated
  program while the conversation has an unfinished run made for another (`DESIGNATED_RUN_UNFINISHED`), and, on a
  human turn, an unfinished run of the conversation that another engine build began, or that has no record of the
  build that began it (`ENGINE_BUILD_MISMATCH`), are all questions for the human (`ctx.doubt`), with what was
  looked for, what exists and a non-binding suggestion.
  Such a run of another build is never continued; when it is of the same engine version, a reply of one cancel
  word from the human ends it, and nothing else changes it.
- **It never fills a gap with its own judgement.** No words means an empty message, never a made-up request;
  a designated program is never replaced by a close match; a value that is set but unusable is an error, not
  a quiet default.
- **It never answers.** Nothing in SoulRun answers a gate or a doubt. A doubt carries, for each option, what
  the host should do when the human picks it, so the host can act on the human's choice without SoulRun
  keeping or interpreting the question. Nor does a machine turn answer for the human: while a run waits at a gate
  for the human's answer (`WAITING_USER`), a call with `human_turn=False` (a schedule, another agent's message) is
  refused (`HUMAN_REPLY_REQUIRED`), and so it is, with the restart switch off, at a run whose engine stop was cut off
  before its index write and at a run marked running that cannot be read then (the run lock a killed process left).
- **The human's words stay where the human put them.** No network; run data only in `soulrun_cache_dir`,
  which ignores itself in version control; a folder that already holds other files is refused rather than
  mixed with run data.

## How the separation works without touching the engine

The engine's `prepare` entry takes one folder argument. Reading the engine shows that it uses that
argument only to place the run cache and to derive the agent folder (its parent). The engine finds
*itself* from the location of its own code. So SoulRun passes the run folder there and leaves the
program in the package. Two engine paths still assume both are one folder (the re-entry text and the
reconnect handler); `soulrun.host` passes the right folder to the first and corrects the two places in the
second's text that name the engine's folder. (The engine's next step after a Stop that the model judges
should go on was a third; it now names the engine's own tool.) The slim form's entry block has the model run any
engine tool a reply names through SoulRun, whatever its path.

## Where the run data lives by default

`soulrun_cache_dir`: by default `<agent_dir>/.soulrun_cache` - the agent folder is
the folder that holds the programs, the current folder unless one is named. A named `soulrun_cache_dir` is that
folder itself, the way pip, pytest and ruff take their cache-dir. The
default is hidden and does not share its name with the engine's folder inside the package (`soulrun_aiap`).
Why beside the programs, in order: two agents' runs never mix and an agent's runs move with it; a host such as
SoulBot already decides "these runs are mine" by their being under its agents folder; the engine derives the
agent folder from the run folder's parent, so the default needs no help from SoulRun; and a library should not
write into the user's home folder unasked. The cost - run data inside a project that may be under version
control - is met by the folder ignoring itself: SoulRun writes a `.gitignore` of `*` when it creates it, or takes
it for the first time without one (a first call cut off after making the folder, or an empty folder made by hand);
after that the owner's choice stands. On Linux and macOS a folder SoulRun creates is readable by its owner only.
A named folder must be SoulRun's alone: one that holds an engine program is refused (another engine's runs live
there), and so is an existing one that holds other files - a project folder named by mistake would get the
user's words among its files, with no `.gitignore` to keep them out of a commit. "Cache" is the
ecosystem's word (the engine's own folder is `.execution_cache`), but it holds the runs themselves: deleting it
deletes unfinished runs too.

## Which program runs

The arguments decide what the *candidates* are; the engine's main program decides which candidate fits
the user's words; an unclear case is put to the human. A designated program is used as designated and
never silently replaced. The engine's `prepare` entry offers only "everything registered under the
agent folder", while the function underneath it can already build a run from an explicit folder list.
`_adapter.py` passes the choice to that function in memory for the duration of one call. It is a
stand-in for a missing engine parameter and is meant to be deleted when the engine offers it.

With no user words: no program named, or only the big folders - the guide, since nothing says what to
run. One program named - it is run: some programs need no words, and one that does asks the human for them
under the engine's HSAW law; SoulRun hands the engine an empty message and never makes words up. Both an AIAP
program and an AISP skill named - nothing says which, so SoulRun asks before any run exists (axiom 0: never
choose for the human), in both Chinese and English since there are no words to tell the language by.

A conversation keeps one unfinished run at a time: handed a message, the engine continues that run - takes the
message as an answer at its gate (not at a gate the human has not been shown yet - its menu never written for the
main conversation and its delivery never recorded: nothing is taken and the next step shows it), asks first
(`interrupted_confirm`; a run that looks unfinished only because an engine stop was cut off before its index write is
re-entered instead, so that its stop is shown), or hands the same run back when the same message comes again within
two minutes and nothing was committed yet - and a program named in the call would
quietly not run. So when a program is named and the conversation's unfinished run was not created for exactly it
(the engine's own snapshot of the run's programs says which), SoulRun asks before handing anything over
(`DESIGNATED_RUN_UNFINISHED`): give the words to that run, run the program in another conversation, or cancel.
Words or not.

## Conversations and runs

`session_id` names the conversation — the host's own notion, not the model program's session.
Without one, the engine cannot find "this conversation's run" at all, so SoulRun supplies a default: one
conversation per agent folder - `default` when the runs are in the agent's own `.soulrun_cache`, and `default-`
with a fingerprint of the agent folder when they are in a folder named elsewhere, which several agents may share,
so that a "继续" said in one project never reaches another project's run. `cache_dir` names one run precisely and is
checked before it is used; when it does not hold, SoulRun asks instead of guessing.

The engine's `turn_id` is the run's number, the same on every turn of the run. Which turn of the run a call is,
SoulRun counts beside the runs (`.soulrun/turns/<run>.json`: the turn's number within the run, the host's
`host_turn_id` and the run's `trace_id`), under the lock that prepares the run, so two calls never take the same
number. A run number the engine gives again is a new run and starts again at turn 1.

## Questions SoulRun asks itself

The questions listed under Axiom 0 above are decided before SoulRun hands the turn to the engine. No run is
created and no other program is used; the caller gets a `text_only` result whose text is the question
(`ctx.doubt` carries it as data), with what was looked for, what exists, and a non-binding suggestion. The
human's answer is not routed automatically — the engine has no gate open for it — so each option says what the
host does when the human picks it: `call` again with the arguments it names changed, `ask` for a value first, or
`cancel`.

## Tests that describe the engine as it is

Where the bundled engine behaves differently from this design, SoulRun does not patch it. A test named
`test_engine_today_*` records the behaviour. When the engine changes, that test fails on purpose.

## Program forms: the slim form, and the model reads nothing itself

How the engine program reaches the model is a choice of form. In the entry-path form - SoulBot's text, byte for
byte, but for a turn that runs nothing, which gets no entry block - the model is given the path of
`main.aisop.json` and reads it, runs the engine's tools as `python <engine>/python_tools/<tool>.py`, and reads
the business program's files itself. SoulRun's default is the other way round: with SoulRun the model reads no
file itself; what it needs comes in the turn's text or back through `soulrun` commands. The entry-path form stays
one switch away (`slim_program=False`).

The slim form does that. `engine_node.aisop.json` is the engine program arranged by engine node - still AISOP,
every text copied verbatim by `tools/build_engine_node.py`, which also checks that each piece only refers to what
was delivered before it and fails when the engine's program files change. A slim turn starts with what its first
step needs, with the user's words in `user_input`, so the first model call does not go to reading a file. Its
entry block names one command line - the interpreter running SoulRun and
the package's `_launch.py`, both by full path, because the model's shell may have another `python` (the test
machine's did) and its search path may not hold this SoulRun - and has the model run every engine tool as that
command plus `--cmd <name>`, the same code the entry-path form runs by file. The business program comes from the
same command plus `--program`: the engine already reads the program a run is bound to (`_read_run_input`,
`_load_routed_program`), and SoulRun hands out what the engine's node packets do not carry today - the program's
system_prompt, output_mode, tools and params at once, one node's function with `--node`, any field in full with
`--field`. A program contract that an engine reply names (`program_contracts`: the output_mode and the shared
constraints) is read the engine's own way, `--cmd next-node --read-program-contract`, and `--program` writes a
field that is not a string the way the engine writes it, so the two give the same size and fingerprint for the
same rule and a model can tell it already has it.

The rest of the engine program is handed out by engine node, and needs nothing from the engine. Within one model
turn only tool output reaches the model - and every engine tool already runs through SoulRun's command line. So
the part a step needs rides on the engine reply that serves that step: SoulRun prints the reply byte for byte, then
`[SOULRUN ENGINE NODE: <groups>]` and the part as a short AISOP. No extra model call is spent, and the model is
never given what it does not need yet. Which part goes with which node is data, in the file's `soulrun_delivery`:
`entry` at the start of every turn (identity, output_mode, the first law, system_prompt, the node execution and
payload transport contracts and the Start function; `params` and `bootstrap_recovery` added when a turn re-enters a
run); each engine node's function with the reply that serves it, NodeLoop with Router.cache-setup (or with the
first business node when that was not served this turn), the dispatch scope contract with the first dispatch, the
terminal delivery contract with the final answer or a failure. The engine's `tools` and `json_schema` and the
pointers to the four contracts every turn's first engine reply carries in full are never handed out, each with its
reason written down. The build tool checks the order: a piece may refer only to what its own group or the start of
the turn brings, or to an exception reviewed and listed with its reason (a later contract a text names before the step that needs
it); a listed exception that no longer occurs is reported, so the list cannot go stale.

What SoulRun prints stays under the engine's own print cap (29,000 bytes). The engine folds its replies to stay
under it, because a model CLI keeps a longer output in a file the model then has to read and parse - and a part
appended past the cap did exactly that in a real run on an earlier build: the model's first attempt to parse the kept file failed on the
part after the JSON. So a part that would pass the cap is not printed; one line names it and asks the model to run the
`--engine-node` command that prints it before the step, and it is not recorded as given. The two contracts every
engine reply relies on start the turn for the same reason: the turn's first engine reply is about 24,000 bytes
already, and on that earlier build, with them after it, the output came within a few hundred bytes of the CLI's
limit. The engine puts
what the executor needs first in a long reply, and a reply it still prints over the cap is printed one value per
line, so the file a model CLI keeps it in can be read page by page; the slim entry block tells the model that such
a file is the output, to be read whole by its path, page by page - never searched instead.

What a turn has been given is a small record beside the runs, `.soulrun/delivered/<run>.json`. Each part comes
once per turn; a new turn starts the record again, because a new turn may be a new model session that has seen
nothing. A turn handed out in another form keeps no record and gets nothing added. A sub-agent's command
(`--agent-ticket`) gets nothing added either: the sub-agent works from the engine's program for sub-agents, and its
calls must not mark parts as given to the main conversation. A model that lost a part, or ran a tool some other
way, asks for it with `soulrun --engine-node <name>`.

A note about an interruption names its own first step - after a Stop the model judges with `stop_decision`
before next_node is allowed - and some notes say to print a public note first. Such a turn keeps the slim form:
the entry block and the assertion say that the note comes first, which tool comes first, and that the tools a
note or an engine reply names (by whatever path) go through SoulRun as well. Falling back to the entry-path form
for such a turn was tried during development, and in a real run after a Stop the model then read
`main.aisop.json` itself. A turn that runs nothing gets no entry block, in the slim form and the entry-path form
alike: SoulBot's own rule gave a confirmation and a cancel the entry block and a "read the entry first" assertion
although their notes say to run nothing.

A slim turn must never be worse than the entry-path turn it replaces, so a turn falls back, and says why
(`ctx.slim_fallback`): a slim program that cannot be built would send the model nowhere; and a
run that went wrong in the slim form - still at Router.match with nothing committed although the model had its
turn, or failed at one of the engine's own nodes - may have gone wrong because of the form. Such a problem is
written in the run's note and passed on, so the rest of that conversation stays in the entry-path form while other
conversations keep the slim form. A run the host interrupted before the model acted is not a problem of the form:
"the model had its turn" is read from the engine's own index (Router.match was served) or the run's host
lifecycle (a turn was closed). The opening instruction goes with the form, so SoulRun hands it out as
`ctx.system_prompt`: SoulBot's own for the entry-path form, SoulRun's for the slim form; a host that kept its own
would tell the model to read a file the turn has already delivered.

What the slim form does not reach yet: sub-agents still get the path of their engine program
(`agent_engine.aisop.json`) from the engine and read it; the engine's own texts still speak of reading the program
entry (the slim entry block says that reading is done). Both need a change in the engine.
The file also holds the sub-agent program arranged as `sub_agent_` nodes of the main program, as a reference for
that change.

On a command line no host program stands between SoulRun and the model. SoulBot's page shows the human every block
the engine names by a reference line; there the model itself is the host, and the engine's own text forbids it to
paste block text. So a turn printed on a command line says, in SoulRun's own words, that the model shows the blocks,
and SoulRun's command line prints their text after each engine reply - the same channel that carries the engine
program by node, under the same cap, the blocks that do not fit waiting for a reply with room. Host programs (the
Python call, `--json`) are left as they are. How much reaches the screen is then the model's doing: in independent
Claude Code sessions on an earlier build, every gate, final answer and evidence did; the first few steps' blocks did
not.

The file holding the user's words goes into its run's folder once the turn has one (`_soulrun/`, a folder the engine
never reads): the words are already in the run, and a copy left in a project could be published accidentally.
Ignore rules reduce that risk but do not remove tracked content, restrict access or securely erase copies.

The second-stage form hands the main program back with the user's words already in place. It changes what the
model reads, so it must be accepted with real runs first; it exists behind `inline_program`, off by default.

## What a host must call

Every host needs, besides `soulrun(...)`, two doors from `soulrun.host` on every turn: `expand_refs`, because the
engine has the model write each public block as a reference line and leaves showing the text to the host, and
`after_turn`, which records the turn and marks a question's menu delivered when the reply carries it - the engine
takes no answer to a question asked outside the model before that, nor to a gate inside a run before its menu was
written for the main conversation (an engine stop's only when the main conversation is served it) or its delivery
was recorded. A full host - one with its own conversations,
a Stop button, restarts and reconnects, like SoulBot - also needs `soulrun_cache_dir` (wherever it used "the
agent's engine folder" for runs), `program_root` (wherever it used it for the engine's tools), `stop`,
`interrupted_runs` with either `open_restart_question` (the default: ask the human; SKIPPED for a run whose engine
stop was cut off before its index write, which shows that stop on the next message) or `resume_prompt` (when the
human's setting says re-enter), `open_question` and `mark_question_delivered` for a question it shows itself,
`runner_recovery` (a broken connection to the model), and `engine(name)` for the modules it already calls by name.
A host whose model can start sub-agents (a run in node mode hands its nodes to them) also reports what it sees of
them - each start and return, the SDK's task events, a failed resume, the tool calls a sub-agent makes - through the
sub-agent doors (`observe_agent_start`, `observe_agent_return` and the rest). These reports bind diagnostic facts;
they do not authenticate the original child. Hosts without event access report none. In every host, the main
conversation obtains the current gate before presenting it, and any required new-agent authority comes from
the human's explicit choice, never the report. SoulBot's host does the same things, partly with its own
code; [02-soulbot-integration.md](02-soulbot-integration.md) has the details.

Re-entry text names its run inside the message, and the engine takes it as "continue that run" only in that
run's own conversation; in another conversation it is ordinary words. SoulRun checks such a message first, as it
checks `cache_dir=`, and asks the human (`NAMED_RUN_MISMATCH`) instead of passing it on.

Many conversations may call `soulrun(...)` at once. Preparing a run is done under one lock, so the
in-memory candidate list of one call never reaches another; the engine's prepare is short, but it reads every run
it keeps, so it grows with them (measured on an earlier build's test machine: about 50 ms, and about 2 ms more per
kept run).
Processes need more than a thread lock: the engine picks the next free run number, and two processes
started together could pick the same one (the second then failed). So the prepare - with the check of a named
`cache_dir` and SoulRun's own note - also holds an operating-system lock on
`<soulrun_cache_dir>/.soulrun/prepare.lock`, which the system releases when a process ends, however it ends.
The lock makes preparations queue and nothing more: the model's engine commands and `host.after_turn` write a
run's index outside it, so on Windows a preparation can still find an index being replaced (the read is refused
for a moment; on an earlier build, about once in 100-135 preparations under load). The engine itself reads a refused
index again, after the pauses a write waits for the same refusal; and since it reads the other runs before it
creates anything, SoulRun also waits a moment and prepares again. A refusal that lasts is reported as the run
folder's. The doors in `soulrun.host` never create the run folder.

## Checking a machine: `soulrun --doctor`

What goes wrong before a run starts is mostly outside SoulRun: the `python` a model's shell finds (the model
runs every engine tool with it in the entry-path form, a sub-agent's engine tools and a program's own `python ...`
tools in every form, and it is not necessarily the interpreter running SoulRun; only the slim form's main
conversation names that interpreter by its full path, so a missing `python` fails in every form), a data folder that
cannot be written, an agent folder without programs, an engine copy that no longer matches its manifest. The
doctor checks each and prints one line, and says which program form a run will get, taking the program-form
switches given with it as that run would; a failure exits `1`, a warning does not. It leaves
nothing behind: writability is tried with one file that is removed at once, because on Windows the usual
check looks only at the read-only attribute. It also reports what quietly degrades a run - a run folder
without `.gitignore`, runs that never finished, and time-zone data missing in this Python or the model's
(the engine then reads a usage-limit reset time that names a zone as local time) - and, on Windows with long
paths off, a run folder deep enough that the engine's files would reach 260 characters: a run nests them about
130 to 150 characters deep - the deepest is a node's block, named with the node's name (a program's node, or the
engine's own Engine.execute-report when the programs' names are short), so the doctor works the depth out from the
node names of the programs it finds and of the engine's own nodes - and on an earlier build a 150-character run
folder failed at the first commit.

## Bringing a newer engine in: `tools/upgrade_engine.py`

A newer engine touches several files that must agree: the engine tree, its manifest, the documents that name
the engine's version, the slim program built from the engine, and the fixed wording (checked against SoulBot's
agent template while that template still carries it). The tool does all of it in one step and fails when the slim
arrangement does not place a new section yet, so a newer engine cannot be packaged with a stale slim program. The
engine it replaces is kept under `.engine_backups/` as one zip beside the manifest it was installed with and the
slim program built from it: one file, checked whole against that manifest. (The first reason for a zip, deep
paths in the engine's own test data passing Windows' default path limit as a copied folder, no longer applies: the
engine comes in without its tests.) `--restore` unpacks it beside the bundle and checks every file against the
manifest kept with it before swapping, so a damaged, changed or unsafe archive changes nothing.

A run records the engine version it started with, so changed files under an unchanged version are refused unless
`--same-version` says it is meant. The new engine is copied beside the bundled one and swapped in whole, so a copy
that fails half way leaves the bundled engine as it was. A renamed function or parameter in the engine would
otherwise show only when the path that calls it runs - or, where SoulRun falls back, never - so the tool reads the
new engine for every function, constant and parameter SoulRun calls (the same check `soulrun --doctor` makes) and
runs a named program through it: first on the staged engine, before anything is changed, and again after the swap.

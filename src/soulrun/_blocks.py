"""The text the model is given before an engine turn.

Two forms. The slim form (the default) hands the model the engine program itself and tells it to get everything else
through soulrun commands; its few texts are SoulRun's own. The entry-path form (``slim_program=False``) hands back what
SoulBot's agent template built before it handed its turns to SoulRun: the fixed wording lives in the generated module
``_agent_text`` (lifted from agent.py), and this module puts the pieces in the same order and with the same separators -
except that a confirmation after an interruption and a cancel, which run nothing, get the text-only assertion instead of
the template's entry block and assertion (TEXT_ONLY_KEYS).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from . import _agent_text, _engine

# Keys of the prepared data that mean "answer in text, do not enter the engine": the five of SoulBot's agent template
# (agent.py: text_only), and a confirmation after an interruption and a cancel, on which the engine asks for a text reply
# only too. SoulBot's template gave those two its entry block and "read the entry first" assertion although their notes
# say to run nothing (problem 32); SoulRun gives every turn that runs nothing the text-only assertion, in every form.
TEXT_ONLY_KEYS = ("stop_question", "stop_hold", "stop_ended", "supply_authorized", "supply_hold",
                  "interrupted_confirm", "interrupted_cancel")
SEPARATOR = "\n\n"
USER_INPUT_SLOT = '"user_input": "{user_input}"'


def runs_nothing(data: dict | None) -> bool:
    """Is this a turn on which the model answers in text and runs nothing (ctx.kind == "text_only")?"""
    return bool(data and any(data.get(key) for key in TEXT_ONLY_KEYS))


def execution_context_block(data: dict, origin_channel: str) -> str:
    """The [EXECUTION CONTEXT] block. Same lines, same order, same optional fields as agent.py."""
    block = (
        f"[EXECUTION CONTEXT]\n"
        f"turn_id: {data['turn_id']}\n"
        f"cache_dir: {data['cache_dir']}\n"
        f"cache_name: {data['cache_name']}\n"
        f"trace_id: {data['trace_id']}"
    )
    if data.get("session_id"):
        block += f"\nsession_id: {data['session_id']}"
    if origin_channel:
        block += f"\norigin_channel: {origin_channel}"
    for key in ("entry_mode", "user_language", "requested_model"):
        value = data.get(key)
        if value not in (None, ""):
            block += f"\n{key}: {value}"
    return block


def build(data: dict, origin_channel: str = "") -> list[str]:
    """Every engine block for this turn, in the order agent.py appends them."""
    return entry_path_blocks(data, execution_context_block(data, origin_channel))


def entry_path_blocks(data: dict, context_block: str) -> list[str]:
    """The entry-path form after a given [EXECUTION CONTEXT] block: the note about an interruption when there is one,
    then SoulBot's text-only assertion on a turn that runs nothing - never an entry block, in this form and in the slim
    form alike - or its entry block and assertion. A slim turn too long for a command line is printed this way (_render),
    its note kept."""
    blocks = [context_block]
    interruption = interruption_note(data)
    if interruption:
        blocks.append(interruption)
    if runs_nothing(data):
        blocks.append(_agent_text.ASSERTION_TEXT_ONLY_TEMPLATE.format(language_name=_agent_text.language_name(data)))
    else:
        blocks += default_entry_blocks(data)
    return blocks


def default_entry_blocks(data: dict) -> list[str]:
    """The [EXECUTE ENGINE ENTRY] text and the assertion of the entry-path form: the model reads main.aisop.json itself."""
    engine_dir = _engine.ENGINE_DIR
    return [_agent_text.ENTRY_TEMPLATE.format(engine_dir=engine_dir.resolve(), entry_path=(engine_dir / "main.aisop.json").resolve()),
            _agent_text.ASSERTION_ENGINE_TEMPLATE.format(language_name=_agent_text.language_name(data))]


def interruption_note(data: dict | None) -> str | None:
    """SoulBot's note about an interruption (a Stop, a confirmation, a cancel, a re-entry ...), or None."""
    return _agent_text.interruption_block(data, _engine.ENGINE_DIR)


# The slim form (docs/guide/01-design.md), the default since the user's ruling of 10-15 (docs/05SoulRun 49 §5): "with
# SoulRun the model no longer reads anything itself; everything comes back through soulrun commands". These texts are
# SoulRun's own wording, not the engine's: they take the place of agent.py's [EXECUTE ENGINE ENTRY] text, assertion and
# opening instruction. The block keeps the name [EXECUTE ENGINE ENTRY] because the engine's own Start step reads
# engine_dir "from the [EXECUTE ENGINE ENTRY] block". The engine's own texts stay verbatim; where they name an engine
# tool by its file, or tell the model to read a program file, the entry block says what to run instead.
SLIM_ENTRY_TEMPLATE = (
    "[EXECUTE ENGINE ENTRY]\n"
    "engine_dir: {engine_dir}\n"
    "soulrun: {soulrun} - written <soulrun> below; in PowerShell put & before it\n"
    "program: [LOADED AISOP: engine_node.aisop.json] below - the engine's own texts, handed out by engine node: this part "
    "holds what the turn starts with. After an engine reply, SoulRun prints [SOULRUN ENGINE NODE: <names>] and, as AISOP, "
    "the part of the program that step needs; follow it as part of this program. A part that is missing: "
    "<soulrun> --engine-node <name> prints it\n"
    "entry: aisop.main\n"
    "engine_tools: run every engine tool through SoulRun: <soulrun> --cmd <name> <the tool's own arguments>. <name> is "
    "next-node (python_tools/next_node.py), node-commit (node_commit.py), stop-decision (stop_decision.py) or "
    "gate-answer (gate_answer.py); the arguments, standard input, output and exit code are the tool's own, its reply "
    "printed whole and first. Read that output whole every time - never discard, cut or filter it (> /dev/null, a pipe, "
    "head) or read a reply file instead: what SoulRun prints after the reply is part of the program. When the command line "
    # docs/05SoulRun 87 (record 86 #26): run 7's main session read one of 21 saved outputs whole and searched the others for fields
    "saves a long output to a file, that file is the output: read it whole by its path, page by page - never search it instead. "
    "Wherever the "
    "program writes python {{engine_dir}}/python_tools/<tool>.py for one of these tools, or a note above or an engine "
    "reply names one of them by any path, run it this way.\n"
    "business_program: never open a program file (*.aisop.json, AIAP.md, AISP.md) with a file tool or a shell read; "
    "its contents come from SoulRun: <soulrun> --program --cache-dir <cache_dir> [--node <node>] [--field <field>]. "
    "Without --node or --field: the main graph, the node list and the program's system_prompt, output_mode, tools and "
    "params, with the size and fingerprint of every other sizeable field; --node <node>: that node's function, the tools "
    "and tool entries it names and the shared constraints it cites; --field <field>: any field in full (--offset pages a "
    "long one). Router.cache-setup's reading of the program entry is done this way. A program contract a reply lists in "
    "input_authority.program_contracts is read the engine's own way, --cmd next-node --read-program-contract <ref>; any "
    "other program rule a node needs, this way.\n"
    "{first_action}"
)
# The last line of the entry block. A turn with a note about an interruption follows the note first: a Stop's judgement
# begins with stop_decision, a re-entry with next_node, a new task after a Stop by printing its public_note; the program
# and its node protocol come after, as the note says.
FIRST_ACTION = (
    "FIRST ACTION: strictly execute aisop.main of that program; its Start step1 is your first tool call. "
    "The program is delivered in this turn, by engine node: do not read main.aisop.json or any other engine file to replace it, "
    "and wherever its texts speak of reading the entry, that reading is done."
)
FIRST_ACTION_AFTER_A_NOTE = (
    "FIRST ACTION: the note above comes first - do what it says before anything else (print what it says to print first; "
    "its first engine action through SoulRun, as engine_tools says), then strictly execute aisop.main of that program "
    "and its node protocol as the note says. The program is delivered in this turn, by engine node: do not read main.aisop.json or any "
    "other engine file to replace it, and wherever its texts or the note speak of reading the entry, that reading is done."
)
# The opening instruction that goes with the slim form (agent.py's _SYSTEM_PROMPT goes with the entry-path form): a host
# puts ctx.system_prompt where it used to put its own, so the instruction and the program form always agree.
SLIM_SYSTEM_PROMPT = (
    "ASSERT IMPORTANT EXECUTION INSTRUCTION: For every user conversation, "
    "Do not analyze or explain how to execute. The Execute Engine program is supplied in this turn "
    "([LOADED AISOP: engine_node.aisop.json], announced by [EXECUTE ENGINE ENTRY]): never read an engine or program "
    "file with a file tool or a shell read - run the engine's tools and get the business program through the SoulRun "
    "commands that block names. Immediately and strictly execute its aisop.main; the first tool action is its Start "
    "step1, unless a note about an interruption in this turn names another first step. A turn that supplies no program "
    "is answered as its own assertion block says. "
    "ASSERT: From the first visible token, all ACP-visible thinking, reasoning, "
    "and progress MUST strictly use the user's language. "
)


def soulrun_command() -> str:
    """How the model's shell runs this SoulRun: this interpreter and this package's launcher, by absolute path - the
    shell's own ``python`` (or ``soulrun``) may be another interpreter, and its search path may not hold this package
    (see _launch). Forward slashes work in both shells."""
    launcher = Path(__file__).resolve().with_name("_launch.py")
    return f'"{Path(sys.executable).as_posix()}" "{launcher.as_posix()}"'


def system_prompt(form: str | None) -> str:
    """The opening instruction for a program form: SoulRun's for the slim form, SoulBot's (verbatim) for every other."""
    return SLIM_SYSTEM_PROMPT if form == "slim" else _agent_text.SYSTEM_PROMPT


SLIM_PROGRAM_HEADER = "[LOADED AISOP: engine_node.aisop.json]"
SLIM_ASSERTION_TEMPLATE = (
    "[TURN EXECUTION ASSERTION]\n"
    "User_Language={language_name}\n"
    "Thought_Output_MUST_USE={language_name}\n"
    "FIRST_RESPONSE_MUST_BE=tool_use\n"
    "VISIBLE_TEXT_BEFORE_FIRST_TOOL={visible_before}\n"
    "FIRST_TOOL_ACTION={first_tool}\n"
    "SHOW_THOUGHTS_FORWARDING=UNCHANGED"
)


def first_tool_action(data: dict) -> str:
    """The first engine action of a slim turn: a Stop's judgement begins with stop_decision, as its note says (next_node
    and node_commit are refused until then); every other turn - a re-entry's note and a new task's note say so too -
    begins with next_node."""
    return "stop_decision(cache_dir)" if data.get("stop_judge") else "next_node(cache_dir)"


def build_slim(data: dict, origin_channel: str, program: str) -> list[str]:
    """The slim form: the same context and interruption blocks, then the program itself instead of its path. A note about
    an interruption is followed first (docs/05SoulRun 53, the user's agreement of 10-15): the entry block and the
    assertion say so, and the engine tools the note names go through SoulRun like every other."""
    blocks = [execution_context_block(data, origin_channel)]
    interruption = interruption_note(data)
    if interruption:
        blocks.append(interruption)
    blocks.append(SLIM_ENTRY_TEMPLATE.format(engine_dir=_engine.ENGINE_DIR.resolve(), soulrun=soulrun_command(),
                                             first_action=FIRST_ACTION_AFTER_A_NOTE if interruption else FIRST_ACTION))
    blocks.append(f"{SLIM_PROGRAM_HEADER}\n```json\n{program}\n```")
    blocks.append(SLIM_ASSERTION_TEMPLATE.format(
        language_name=_agent_text.language_name(data), first_tool=first_tool_action(data),
        visible_before="ONLY_WHAT_THE_NOTE_ABOVE_SAYS_TO_PRINT_FIRST" if interruption else "FORBIDDEN"))
    return blocks


def inline_program(user_message: str) -> str:
    """Second-stage form: the main program with the user's words placed in its one ``user_input`` slot.

    The words go in last and as a JSON string, into the engine's own untouched text, so nothing the
    user wrote can be mistaken for a slot or altered by a later replacement.
    """
    raw = _engine.main_program_text()
    if raw.count(USER_INPUT_SLOT) != 1:
        raise RuntimeError("the engine's main program no longer has exactly one user_input slot")
    return raw.replace(USER_INPUT_SLOT, '"user_input": ' + json.dumps(str(user_message), ensure_ascii=False))


def join(blocks: list[str]) -> str:
    return SEPARATOR.join(blocks)


def entry_path() -> Path:
    return (_engine.ENGINE_DIR / "main.aisop.json").resolve()

"""Command line: one command, ``soulrun``.

    soulrun                                   the guide
    soulrun --user-message-file msg.txt       start or continue a run; prints what the model should be given
    soulrun --aiap NAME                       no words: run that one program (both --aiap and --aisp: you are asked)
    soulrun --cmd next-node --cache-dir DIR   run one engine command (every other argument is passed on to it)
    soulrun --program --cache-dir DIR         the business program the run is bound to (--node, --field for parts)
    soulrun --report LINK --cache-dir DIR     the complete execution report behind an engine-report: link
    soulrun --engine-node NAME                a part of the slim engine program on request (it is handed out by node)
    soulrun --expand REF --cache-dir DIR      the text of a public block the engine named by its reference line

A run is handed out in the slim form unless --no-slim-program is given. The user's words are read from a file or from
standard input, never from the command line itself; once the turn has its run, the file is moved into the run's folder
(--keep-message-file leaves it). A turn printed here has no host program to show the human its blocks: the text says
so, and the engine commands print the blocks' text after each reply (_screen).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import _api, _blocks, _cmd, _doctor, _engine, _render
from .errors import SoulRunError, UsageError


def _utf8_streams() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass


def _emit(text: str) -> None:
    """Print exactly these characters as UTF-8, with LF line ends on every platform.

    The text is what the model must be given; a platform that rewrites line ends would hand it
    something else and would also change the size the output cap is measured against.
    """
    data = (text if text.endswith("\n") else text + "\n").encode("utf-8")
    try:
        sys.stdout.flush()
        sys.stdout.buffer.write(data)
        sys.stdout.buffer.flush()
    except AttributeError:          # a replaced stdout without a byte buffer (tests, embedding)
        sys.stdout.write(data.decode("utf-8"))


class _Parser(argparse.ArgumentParser):
    """A wrong argument is a SoulRun usage error like any other: with --json it comes out as one JSON object."""

    def error(self, message: str):
        raise UsageError("ARGUMENT_INVALID", message, field="arguments", expected="see soulrun --help")


def build_parser() -> argparse.ArgumentParser:
    parser = _Parser(
        prog="soulrun", description="Run AISOP programs (AIAP packages and AISP skills). With no arguments: print the guide.",
        epilog="exit codes: 0 done (a question for the human is done too); 1 a failed check, an unusable engine or an "
               "engine error; 2 a usage error. With --json an error is one JSON object on standard error. With --cmd "
               "the exit code, output and input are the engine tool's own, and --json only makes SoulRun's own errors JSON.",
        allow_abbrev=False)          # "--cm" is not "--cmd": an abbreviation would quietly become a different call
    message = parser.add_mutually_exclusive_group()
    message.add_argument("--user-message-file", metavar="FILE", help="file holding the user's words, UTF-8 ('-' reads standard input)")
    message.add_argument("--user-message-stdin", action="store_true", help="read the user's words from standard input")
    parser.add_argument("--keep-message-file", action="store_true",
                        help="leave the --user-message-file where it is (by default, once the turn has its run, it is "
                             "moved into that run's folder, _soulrun/message.<n>.txt)")
    parser.add_argument("--aiap-dir", metavar="DIR", help="folder holding AIAP programs (default: <agent-dir>/aiap)")
    parser.add_argument("--aisp-dir", metavar="DIR", help="folder holding AISP skills (default: <agent-dir>/aisp)")
    parser.add_argument("--aiap", metavar="DIR_OR_NAME", help="one designated AIAP program")
    parser.add_argument("--aisp", metavar="DIR_OR_NAME", help="one designated AISP skill")
    parser.add_argument("--agent-dir", metavar="DIR",
                        help="agent folder, the one holding aiap/ and aisp/ (default: SOULRUN_AGENT_DIR, else the current folder)")
    parser.add_argument("--soulrun-cache-dir", metavar="DIR", help="the folder SoulRun keeps its runs in (default: SOULRUN_CACHE_DIR, else .soulrun_cache in the agent folder)")
    parser.add_argument("--session-id", metavar="ID", help="which conversation the message belongs to")
    parser.add_argument("--cache-dir", metavar="DIR", help="which run the message is for")
    parser.add_argument("--user-id", metavar="ID", help="who the user is, as the host knows them")
    parser.add_argument("--channel", metavar="NAME", help="where the message came from, e.g. web")
    parser.add_argument("--model", metavar="NAME", help="the model the host asked for")
    parser.add_argument("--host-fence", action="append", metavar="KIND", default=None,
                        help="a kind of streamed text the host captures (repeatable)")
    parser.add_argument("--host-tool", action="append", metavar="NAME=true|false", default=None,
                        help="an ability the host has or lacks, e.g. agent=false (repeatable)")
    parser.add_argument("--machine-turn", action="store_true", help="the message does not come from a human")
    parser.add_argument("--host-turn-id", metavar="ID", help="the host's own id for this turn")
    parser.add_argument("--origin-type", metavar="TYPE", help="what kind of turn the host says this is, e.g. engine_recovery")
    parser.add_argument("--inline-program", action="store_true",
                        help="experimental: also hand back the main program with the user's words filled in")
    parser.add_argument("--slim-program", action=argparse.BooleanOptionalAction, default=None,
                        help="the slim form - the engine program handed out by engine node, engine tools and the "
                             "business program through soulrun - is the default; --no-slim-program hands back the entry-path form "
                             "(SoulBot's text: the model reads the engine program itself)")
    parser.add_argument("--program", action="store_true",
                        help="print the business program of a run (--cache-dir), as one JSON object: the overview, "
                             "one node's function (--node) or one field in full (--field, paged with --offset/--limit)")
    parser.add_argument("--node", metavar="NAME", help="with --program: the node whose function to print")
    parser.add_argument("--doc", metavar="FILE", help="with --program: the program file (when a node or field is in a module file)")
    parser.add_argument("--field", metavar="NAME", help="with --program: the field to print in full")
    parser.add_argument("--engine-node", action="append", metavar="NAME",
                        help="print a part of the slim engine program on request: a group (entry, "
                             "Router.match, Router.cache-setup, business, dispatch, Engine.execute-report, "
                             "Engine.final-answer, run_failed, terminal, recovery_entry), a section or a function "
                             "(repeatable); with --cache-dir it is recorded as given in that run's turn")
    parser.add_argument("--report", metavar="LINK",
                        help="print, as one JSON object, the complete execution report behind the engine-report: link "
                             "that ends an execution report block (the runs: --cache-dir of any run of the conversation, "
                             "or --soulrun-cache-dir / --agent-dir; --session-id keeps it to that conversation; paged "
                             "with --offset/--limit)")
    parser.add_argument("--expand", action="append", metavar="REF",
                        help="print the text of a public block (a plan, a node's block, a gate's menu, the final answer, "
                             "the evidence) as the engine's reference line names it, ⟦engine:<run>/<file>⟧ (repeatable; "
                             "with --cache-dir; paged with --offset): what a host shows the human in place of the line")
    parser.add_argument("--offset", type=int, default=0, metavar="N",
                        help="with --program --field, --report or --expand: where the page starts")
    parser.add_argument("--limit", type=int, default=None, metavar="N",
                        help="with --program --field: characters in the page (at most 12,000); with --report: at most "
                             "32,768; a page also stays under 24,000 bytes")
    parser.add_argument("--cmd", metavar="NAME", help="run one engine command (" + ", ".join(_cmd.COMMANDS) + "): every "
                        "other argument goes to that engine tool as it is, and its output and exit code are the tool's")
    parser.add_argument("--json", action="store_true", help="print one JSON object instead of the text")
    parser.add_argument("--engine-info", action="store_true", help="print which engine is bundled, as JSON")
    parser.add_argument("--verify-engine", action="store_true",
                        help="check every bundled engine file against the recorded fingerprint")
    parser.add_argument("--doctor", action="store_true",
                        help="check, leaving nothing behind and running no program, that everything is in place for "
                             "a run - the engine and its interface, the slim program, the model's python, time zones, "
                             "the agent folder and its programs, soulrun_cache_dir, path length on Windows - with the "
                             "folder and program arguments and the program-form switches (--slim-program, "
                             "--no-slim-program, --inline-program) a run would get")
    parser.add_argument("--version", action="store_true", help="print the version and exit")
    return parser


def _decode(data: bytes, field: str) -> str:
    """The user's words: UTF-8 (a UTF-8 byte-order mark is dropped later), or UTF-16 with its byte-order mark - what
    Windows PowerShell 5.1 writes with ">" and Out-File. Anything else is refused, never guessed: a guess would hand
    the model words the human did not write."""
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        try:
            return data.decode("utf-16")
        except UnicodeDecodeError:
            pass
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise UsageError("MESSAGE_NOT_UTF8", f"the user's words are not UTF-8 text (byte {exc.start}: {exc.reason})",
                         field=field, expected="UTF-8 text (in Windows PowerShell 5.1: Set-Content -Encoding utf8, or "
                         "Out-File -Encoding utf8)") from None


def _read_message(args) -> str | None:
    if args.user_message_stdin or args.user_message_file == "-":
        return _decode(sys.stdin.buffer.read(), "user_message_stdin")
    if args.user_message_file:
        try:
            with open(args.user_message_file, "rb") as handle:
                data = handle.read()
        except OSError as exc:
            moved = (" - a file an earlier turn read was moved into its run's folder (_soulrun/message.<n>.txt): write "
                     "the words to it again, or pass --keep-message-file" if isinstance(exc, FileNotFoundError) else "")
            raise UsageError("MESSAGE_FILE_UNREADABLE", f"cannot read {args.user_message_file}: {exc}{moved}",
                             field="user_message_file", expected="a readable UTF-8 file") from exc
        return _decode(data, "user_message_file")
    return None


def _host_tools(items: list[str] | None) -> dict | None:
    if not items:
        return None
    tools: dict = {}
    for item in items:
        name, sep, value = item.partition("=")
        if not sep or value.strip().lower() not in ("true", "false"):
            raise UsageError("HOST_TOOL_INVALID", f"--host-tool {item!r}", field="host_tool", expected="NAME=true or NAME=false")
        tools[name.strip()] = value.strip().lower() == "true"
    return tools


def _fail(error: SoulRunError, as_json: bool) -> int:
    if as_json:
        print(json.dumps({"error": error.as_dict()}, ensure_ascii=False), file=sys.stderr)
    else:
        print(f"soulrun: {error}", file=sys.stderr)
    return 2 if isinstance(error, UsageError) else 1


def _cmd_at(arguments: list[str]) -> tuple[int, str | None] | None:
    """Where --cmd is, and its name when written as --cmd=NAME; None when there is no --cmd."""
    for at, item in enumerate(arguments):
        if item == "--cmd":
            return at, None
        if item.startswith("--cmd="):
            return at, item[len("--cmd="):]
    return None


def _form_switches(args) -> dict:
    """The program-form switches as soulrun(...) takes them - one place, so a run and --doctor read them alike."""
    return {"inline_program": True if args.inline_program else None, "slim_program": args.slim_program}


MODES = ("version", "engine_info", "verify_engine", "doctor", "program", "report", "engine_node", "expand")
PROGRAM_ONLY = ("node", "doc", "field")


def main(argv: list[str] | None = None) -> int:
    _utf8_streams()
    arguments = list(sys.argv[1:] if argv is None else argv)
    as_json = "--json" in arguments
    try:
        return _main(arguments, as_json)
    except SoulRunError as error:
        return _fail(error, as_json)
    except Exception as exc:                          # with --json a caller parses standard error: never a bare traceback
        if not as_json:
            raise
        return _fail(SoulRunError("INTERNAL", f"{type(exc).__name__}: {exc}", expected="a report of this failure"), True)


def _main(arguments: list[str], as_json: bool) -> int:
    found = _cmd_at(arguments)
    if found is not None:                        # everything except "--cmd NAME" goes to the engine tool untouched
        at, name = found
        if name is None:
            if at + 1 >= len(arguments):
                raise UsageError("CMD_NAME_MISSING", "--cmd needs a name", field="cmd", expected=sorted(_cmd.COMMANDS))
            name, forwarded = arguments[at + 1], arguments[:at] + arguments[at + 2:]
        else:
            forwarded = arguments[:at] + arguments[at + 1:]
        if any(item.startswith("--user-message") for item in forwarded):
            raise UsageError("MESSAGE_AND_CMD", "user_message and cmd cannot be given together",
                             field="cmd", expected="either a user message or --cmd")
        if name != "next-node":                  # --json is SoulRun's (its errors as JSON); only next-node takes it too
            forwarded = [item for item in forwarded if item != "--json"]
        return _cmd.passthrough(name, forwarded)

    args = build_parser().parse_args(arguments)
    modes = [name for name in MODES if getattr(args, name)]
    if len(modes) > 1 or (modes and (args.user_message_file or args.user_message_stdin)):
        given = ["--" + name.replace("_", "-") for name in modes] + (["a user message"] if args.user_message_file or args.user_message_stdin else [])
        raise UsageError("MODES_CONFLICT", f"{' and '.join(given)} cannot be given together", field=modes[0],
                         expected="one of --version, --engine-info, --verify-engine, --doctor, --program, --report, "
                                  "or a run")
    stray = [f"--{name}" for name in PROGRAM_ONLY if getattr(args, name) is not None]
    paging = ((["--offset"] if args.offset and not args.expand else []) + (["--limit"] if args.limit is not None else []))
    if (stray and not args.program) or (paging and not (args.program or args.report)):
        alone = stray + paging
        raise UsageError("PROGRAM_OPTION_ALONE", f"{', '.join(alone)} only go with --program"
                         + ("" if stray else " or --report"), field=alone[0].lstrip("-"),
                         expected="--program --cache-dir <run> (or --report <link> for --offset, --limit) with them")
    if args.expand:
        from . import _screen
        _emit(_screen.expand(args.expand, args.cache_dir, offset=args.offset).rstrip("\n"))
        return 0
    if args.report:
        from . import host
        _emit(json.dumps(host.execution_report(args.report, cache_dir=args.cache_dir, soulrun_cache_dir=args.soulrun_cache_dir,
                                               agent_dir=args.agent_dir, session_id=args.session_id,
                                               offset=args.offset, limit=args.limit), ensure_ascii=False))
        return 0
    if args.engine_node:
        from . import _slim
        _emit(_slim.part_for(args.engine_node, cache_dir=args.cache_dir).rstrip("\n"))
        return 0
    if args.program:
        from . import _program
        _emit(json.dumps(_program.view(args.cache_dir, node_name=args.node, field_name=args.field, doc=args.doc,
                                       offset=args.offset, limit=args.limit), ensure_ascii=False))
        return 0
    if args.version:
        from . import __version__
        _emit(json.dumps({"soulrun": __version__, "engine": _engine.version()}) if args.json
              else f"soulrun {__version__} (engine {_engine.version()})")
        return 0
    if args.engine_info:
        _emit(json.dumps(_engine.info(), ensure_ascii=False, indent=1))
        return 0
    if args.verify_engine:
        problems = _engine.verify()
        if args.json:
            _emit(json.dumps({"ok": not problems, "engine_version": _engine.version(), "problems": problems}, ensure_ascii=False))
        else:
            _emit("\n".join([*problems, f"engine {_engine.version()}: " + ("unchanged" if not problems else f"{len(problems)} problem(s)")]))
        return 1 if problems else 0
    if args.doctor:                              # the folders, programs and program-form switches a run would get
        checks = _doctor.run(agent_dir=args.agent_dir, soulrun_cache_dir=args.soulrun_cache_dir, aiap_dir=args.aiap_dir,
                             aisp_dir=args.aisp_dir, aiap=args.aiap, aisp=args.aisp, **_form_switches(args))
        _emit(_doctor.render(checks, args.json))
        return _doctor.exit_code(checks)
    message = _read_message(args)

    def turn():
        return _api.run(
            message, aiap_dir=args.aiap_dir, aisp_dir=args.aisp_dir, aiap=args.aiap, aisp=args.aisp,
            agent_dir=args.agent_dir, soulrun_cache_dir=args.soulrun_cache_dir, session_id=args.session_id,
            cache_dir=args.cache_dir, user_id=args.user_id, channel=args.channel, model=args.model,
            host_fences=args.host_fence, host_tools=_host_tools(args.host_tool), human_turn=not args.machine_turn,
            host_turn_id=args.host_turn_id, origin_type=args.origin_type, **_form_switches(args))

    from . import _message_file, _screen, _select
    message_file = (Path(args.user_message_file) if args.user_message_file not in (None, "-") and not args.keep_message_file
                    else None)
    aside = None
    try:
        ctx = turn()
    except UsageError as error:
        if error.code != "SOULRUN_CACHE_DIR_NOT_EMPTY" or message_file is None:
            raise
        cache = _select.soulrun_cache_dir_of(agent_dir=args.agent_dir, soulrun_cache_dir=args.soulrun_cache_dir)
        aside = _message_file.set_aside(message_file, cache)  # the user's words, written into the new run folder
        if aside is None:
            raise
        try:
            ctx = turn()
        except BaseException:
            _message_file.put_back(aside, message_file)
            raise
    if message_file is not None:
        _message_file.settle(message_file, aside, ctx.cache_dir)

    printed, saved = _render.for_shell(ctx)
    if not args.json and ctx.program_form == "slim" and _render.form_shown(ctx, printed) == "slim":
        # printed for a model with no host program between: it shows the human the blocks itself (_screen)
        shown = printed.replace(f"\n\n{_blocks.SLIM_PROGRAM_HEADER}", f"\n\n{_screen.SCREEN_BLOCK}\n\n{_blocks.SLIM_PROGRAM_HEADER}", 1)
        shown = shown.replace("\nSHOW_THOUGHTS_FORWARDING=", f"\n{_screen.SCREEN_ASSERTION}\nSHOW_THOUGHTS_FORWARDING=", 1)
        if shown.count("[SOULRUN SCREEN]") == 1 and _screen.SCREEN_ASSERTION in shown \
                and _render.size(shown) <= _render.print_cap() and _screen.mark(ctx.cache_dir):
            printed = shown
    if args.json:
        payload = ctx.as_dict()
        payload["text"] = printed
        if ctx.program_form:
            shown = _render.form_shown(ctx, printed)
            payload["program_form"] = shown
            if shown != ctx.program_form:            # printed in the entry-path form: its own opening instruction goes with it
                payload["system_prompt"] = _blocks.system_prompt(shown)
                payload["slim_fallback"] = "TOO_LONG_FOR_COMMAND_LINE"
        if saved is not None:
            payload["full_text_file"] = str(saved)
        _emit(json.dumps(payload, ensure_ascii=False))
    else:
        _emit(printed)
    return 0


if __name__ == "__main__":
    sys.exit(main())

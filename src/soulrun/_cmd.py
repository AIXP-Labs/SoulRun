"""``cmd``: run one command of the bundled engine and hand back what it printed.

The names are the engine's own command-line tools, with dashes. The model uses the first two on every
step; ``stop-decision`` is the model's judgement after a human Stop; ``gate-answer`` is the host-side
entry for a human's answer (a human's reply normally arrives as ``user_message`` and needs no cmd).
"""
from __future__ import annotations

import contextlib
import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from typing import Any

from . import _engine
from .errors import SoulRunError, UsageError

COMMANDS = {
    "next-node": "next_node.py",
    "node-commit": "node_commit.py",
    "stop-decision": "stop_decision.py",
    "gate-answer": "gate_answer.py",
}


@dataclass(frozen=True)
class CmdResult:
    cmd: str
    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0

    def json(self) -> Any:
        """The command's printed reply as an object (the engine prints one JSON object). A reply that is not JSON - the
        tool refused its arguments, or stopped before printing - is a SoulRunError (CMD_OUTPUT_NOT_JSON) naming the exit
        code and the last line the tool wrote to standard error."""
        try:
            return json.loads(self.stdout)
        except json.JSONDecodeError:
            last = (self.stderr.strip().splitlines() or ["nothing on standard error"])[-1][:300]
            raise SoulRunError("CMD_OUTPUT_NOT_JSON", f"{self.cmd} printed no JSON (exit code {self.returncode}): {last}",
                               field="cmd", expected="one JSON object on standard output") from None

    def __str__(self) -> str:
        return self.stdout


def script(cmd: str):
    if cmd not in COMMANDS:
        raise UsageError("UNKNOWN_CMD", f"unknown cmd {cmd!r}", field="cmd", expected=sorted(COMMANDS))
    return _engine.TOOLS_DIR / COMMANDS[cmd]


def argv(cmd: str, *, cache_dir=None, args: list | None = None, **options: Any) -> list[str]:
    """The exact command line for ``cmd`` (the interpreter running SoulRun, UTF-8 mode, no bytecode files)."""
    line = [sys.executable, "-B", "-X", "utf8", str(script(cmd))]
    if cache_dir is not None:
        line += ["--cache-dir", str(cache_dir)]
    for key, value in options.items():
        flag = "--" + key.replace("_", "-")
        if value is None or value is False:
            continue
        if value is True:
            line.append(flag)
        elif isinstance(value, (list, tuple)):
            for item in value:
                line += [flag, str(item)]
        else:
            line += [flag, str(value)]
    return line + [str(a) for a in (args or [])]


def run(cmd: str, *, cache_dir=None, stdin: str | None = None, payload: Any = None, args: list | None = None,
        timeout: float | None = None, **options: Any) -> CmdResult:
    """Run the command and capture its output. ``payload`` (node-commit) is sent as JSON on standard input."""
    if payload is not None:
        if stdin is not None:
            raise UsageError("PAYLOAD_AND_STDIN", "give payload or stdin, not both", field="payload", expected="one of them")
        stdin = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
        options.setdefault("payload_stdin", True)
    answer_file = None
    if options.get("answer") is not None:
        # A human's answer never goes on a command line, where the process list and shell history show it: it is
        # handed over in a file only this user can read, removed as soon as the command is done.
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".txt", prefix="soulrun-answer-", delete=False) as handle:
            handle.write(str(options.pop("answer")))
        answer_file = options["answer_file"] = handle.name
    line = argv(cmd, cache_dir=cache_dir, args=args, **options)
    try:
        done = subprocess.run(line, input=stdin, capture_output=True, text=True, encoding="utf-8", timeout=timeout)
    except subprocess.TimeoutExpired:
        raise SoulRunError("CMD_TIMEOUT", f"{cmd} did not finish within {timeout} s and was stopped", field="timeout",
                           expected="a longer timeout, or None to wait as long as it takes") from None
    finally:
        if answer_file is not None:
            with contextlib.suppress(OSError):
                os.unlink(answer_file)
    return CmdResult(cmd=cmd, returncode=done.returncode, stdout=done.stdout, stderr=done.stderr)


def _cache_dir_in(forwarded: list[str]) -> str | None:
    """The run folder an engine command line names, written --cache-dir DIR or --cache-dir=DIR; else None."""
    for i, arg in enumerate(forwarded):
        if arg == "--cache-dir":
            return forwarded[i + 1] if i + 1 < len(forwarded) else None
        if arg.startswith("--cache-dir="):
            return arg.split("=", 1)[1] or None
    return None


def passthrough(cmd: str, forwarded: list[str]) -> int:
    """Command-line use: same standard input, output and exit code as the engine tool itself. In a turn that started
    with the slim program, the part of the engine program the reply's step needs follows the reply, once per turn
    (_slim.node_part) - or, when it would take the output past the print cap, one line naming it and the command that
    prints it; the reply itself is printed byte for byte as the tool printed it. In a turn SoulRun's command line printed
    (no host program shows the blocks), the text of the blocks the reply names for the human follows too (_screen)."""
    line = [sys.executable, "-B", "-X", "utf8", str(script(cmd)), *forwarded]
    # A sub-agent's command (--agent-ticket) gets nothing added: a sub-agent works from the engine's own program for
    # sub-agents, and what the main conversation was given must not be marked as given by a sub-agent's call.
    sub_agent = any(arg == "--agent-ticket" or arg.startswith("--agent-ticket=") for arg in forwarded)
    cache_dir = None if sub_agent else _cache_dir_in(forwarded)
    if cache_dir is None:
        return subprocess.run(line).returncode
    done = subprocess.run(line, stdout=subprocess.PIPE)
    try:
        out = sys.stdout.buffer
        out.write(done.stdout)
        out.flush()
    except (OSError, ValueError, AttributeError) as exc:
        return _not_printed(cmd, cache_dir, done, exc, printed="nothing")
    added: list[str] = []
    try:
        from . import _render, _screen, _slim
        reply = json.loads(done.stdout.decode("utf-8"))
        # the engine keeps what it prints under its cap (a model CLI keeps a longer output in a file); so does what follows
        room = _render.print_cap() - len(done.stdout)
        for make in (_slim.node_part, _screen.human_part):
            text = make(cache_dir, reply, room=room - 1)
            if text:
                added.append(text)
                room -= 1 + len(text.encode("utf-8"))
    except Exception:  # noqa: BLE001 - what is added never changes or breaks the engine's own reply and exit code
        pass
    try:
        for text in added:
            out.write(("\n" + text).encode("utf-8"))
        out.flush()
    except (OSError, ValueError) as exc:
        return _not_printed(cmd, cache_dir, done, exc, printed="the reply")
    return done.returncode


# The reader of SoulRun's standard output went away (a closed pipe; on Windows OSError 22) while SoulRun printed what the
# engine tool printed. The engine has already done its work and kept its reply (the run's _work/replies/); only this copy
# of it did not arrive. SoulRun says so on standard error, notes it in <soulrun_cache_dir>/.soulrun/undelivered/<run>.jsonl
# and ends with this exit code (sysexits EX_IOERR) - never with a traceback (docs/05SoulRun 80 B3).
REPLY_NOT_PRINTED = 74


def _not_printed(cmd: str, cache_dir: str, done: subprocess.CompletedProcess, exc: BaseException, *, printed: str) -> int:
    import hashlib
    from datetime import datetime, timezone
    try:
        status = json.loads(done.stdout.decode("utf-8")).get("status")
    except Exception:  # noqa: BLE001 - a reply that is not one JSON object has no status to note
        status = None
    note = {"at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "cmd": cmd, "exit_code": done.returncode,
            "reply_status": status, "reply_bytes": len(done.stdout), "reply_sha256": hashlib.sha256(done.stdout).hexdigest(),
            "printed": printed, "error": f"{type(exc).__name__} {getattr(exc, 'errno', None) or ''}".strip(), "delivered": False}
    where = _note_undelivered(cache_dir, note)
    with contextlib.suppress(OSError, ValueError, AttributeError):
        sys.stderr.write(f"soulrun: SOULRUN_REPLY_NOT_PRINTED - the reply of {cmd} ({len(done.stdout)} bytes, exit code "
                         f"{done.returncode}) could not be printed ({note['error']}); printed before that: {printed}. The "
                         f"engine kept its reply in the run's _work/replies/" + (f"; noted in {where}" if where else "") + "\n")
        sys.stderr.flush()
    with contextlib.suppress(OSError, ValueError, AttributeError):   # Python's own flush at exit must not fail on it again
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
    return REPLY_NOT_PRINTED


def _note_undelivered(cache_dir: str, note: dict):
    """One line in <soulrun_cache_dir>/.soulrun/undelivered/<run>.jsonl; only for a run in a folder SoulRun keeps, best effort."""
    from . import _records, _select
    run = os.path.abspath(cache_dir)
    runs, name = os.path.split(run)
    root = os.path.dirname(runs)
    notes = os.path.join(root, _select.NOTES_DIRNAME)
    if os.path.basename(runs) != _select.CACHE_DIRNAME or not name.isdigit() or not os.path.isdir(notes):
        return None
    target = os.path.join(notes, _records.UNDELIVERED, f"{name}.jsonl")
    try:
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(note, ensure_ascii=False) + "\n")
    except OSError:
        return None
    return target

"""A minimal host: the whole loop around SoulRun in one page.

A host does four things per human message:

1. ``ctx = soulrun(user_message=...)``     - the engine prepares the run, or recognises an answer to an open question;
   when ``ctx.doubt`` is set, SoulRun itself asks the human first: show ``ctx.text``, ask no model;
2. gives ``ctx.text`` and the human's words to a model - for ``program`` and ``text_only`` alike (``text_only``:
   answer in text, run no command), with ``ctx.system_prompt`` as the opening instruction; SoulRun never talks to
   a model, that is the host's part;
3. shows the reply with the engine's references expanded - ``host.expand_refs(...)``: the model writes a gate's
   menu, a block or the final answer as one ``⟦engine:…⟧`` line, never the text;
4. tells the engine what the model said     - ``host.after_turn(...)``, after every turn.

This example has no model. ``send`` is where a real host would call one (SoulBot does it through
SoulACP). Run it from a folder that has ``aiap/`` or ``aisp/`` in it, with the human's words in a file - or on
standard input - never on the command line, where the process list and the shell's history would show them:

    python minimal_host.py message.txt
    python minimal_host.py - < message.txt
"""
from __future__ import annotations

import sys
from pathlib import Path

import soulrun
from soulrun import host


def send(text: str) -> str:
    """Stand-in for the model. A real host sends ``text`` to its command-line model program and returns the reply."""
    return "(no model is connected in this example)"


def one_turn(message: str, *, session_id: str) -> soulrun.Ctx:
    ctx = soulrun(user_message=message, session_id=session_id,
                  host_fences=(), host_tools={"agent": False})       # report honestly what this host can do

    if ctx.doubt:                         # SoulRun has a question before any run exists: show it, wait for the human
        print(ctx.text)
        return ctx

    # program: the model drives the engine; text_only: it answers in text. One text channel: the opening instruction first
    reply = send(ctx.system_prompt + "\n\n" + ctx.text + "\n\n" + message)
    print(host.expand_refs(reply, cache_dir=ctx.cache_dir))          # the human reads blocks, not their references
    state = host.after_turn(ctx.cache_dir, reply)                    # every turn, a text_only one too
    if state["run_state"] == "WAITING_USER" or host.open_question(ctx.cache_dir):
        print("-- the run is waiting for the human; call one_turn(answer, session_id=...)")
    return ctx


def read_message(source: str) -> str:
    """The human's words from a file (UTF-8), or from standard input for "-"."""
    return sys.stdin.buffer.read().decode("utf-8") if source == "-" else Path(source).read_text(encoding="utf-8")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(soulrun().text)             # no message: the guide
    else:
        result = one_turn(read_message(sys.argv[1]), session_id="example")
        print(f"-- kind={result.kind} entry_mode={result.entry_mode} cache_dir={result.cache_dir}")

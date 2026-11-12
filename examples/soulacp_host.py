"""The "program door": a host that hands ``ctx.text`` to a command-line model program through SoulACP.

SoulRun never talks to a model. This example shows the smallest host that does - the loop SoulBot runs
for every message, without SoulBot's windows, schedules or several agents:

    one conversation id  ->  given to SoulRun as ``session_id`` (which conversation a message belongs to)
                         ->  given to SoulACP as ``user_id``    (which command-line session to reuse)

    python soulacp_host.py --provider claude --model claude-acp/sonnet message.txt

The human's words come from a file (or "-" for standard input), never from the command line itself, where the
process list and the shell's history would show them.

It sees none of the model's tool calls, so it reports none of the sub-agent events a host must report through the
sub-agent doors of ``soulrun.host`` (``dispatches_nodes``, ``observe_agent_start``, ``observe_agent_return``, ...):
it tells the engine its model starts no sub-agents (``host_tools={"agent": False}``), whatever the provider. The
engine then hands no node to a sub-agent: a program meant for sub-agents runs every node in the main conversation.

Running it calls a real model and uses that model's quota. Nothing in SoulRun's tests runs it; the
tests drive ``one_turn`` with a stand-in session, and ``_main`` with a stand-in for SoulACP.

SoulACP is not a dependency of SoulRun: it is imported only when this file is run as a program.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from dataclasses import dataclass
from pathlib import Path

import soulrun
from soulrun import host


@dataclass
class Turn:
    ctx: soulrun.Ctx
    reply: str | None          # what the model said; None when the model was not asked
    run_state: str | None      # RUNNING, WAITING_USER, COMPLETED ... after the turn
    needs_human: bool          # True: show ``shown`` to the human and wait for the answer
    shown: str                 # what the human should see


def prompt_for(ctx: soulrun.Ctx, message: str) -> str:
    """What is sent: the opening instruction that goes with this turn, the engine's instructions, then the human's own
    words. A SoulACP session takes no opening instruction of its own, so it goes first - as SoulBot puts its own first
    for a model that takes none."""
    return ctx.system_prompt + "\n\n" + ctx.text + "\n\n" + message


async def one_turn(session, message: str, *, conversation: str, model: str | None = None,
                   cache_dir: str | None = None, **places) -> Turn:
    """One human message, start to finish. ``session`` is anything with ``await session.query(prompt, user_id=...)``."""
    ctx = soulrun(user_message=message, session_id=conversation, cache_dir=cache_dir, model=model,
                  host_fences=(),                                  # this host captures none of the model's streamed text
                  host_tools={"agent": False},                     # and reports no sub-agent events: it starts none
                  **places)

    if ctx.doubt:                                                  # a question before any run exists: the model is not asked
        return Turn(ctx=ctx, reply=None, run_state=None, needs_human=True, shown=ctx.text)

    # program: the model drives the engine; text_only: it answers in text and runs no command. Both go to the model.
    reply = await session.query(prompt_for(ctx, message), user_id=conversation)
    shown = host.expand_refs(reply, cache_dir=ctx.cache_dir)       # a menu, a block, the final answer: as text
    state = host.after_turn(ctx.cache_dir, reply)["run_state"]    # every turn: it also marks a shown question delivered
    waiting = state == "WAITING_USER" or host.open_question(ctx.cache_dir) is not None
    return Turn(ctx=ctx, reply=reply, run_state=state, needs_human=waiting, shown=shown)


async def _main(arguments) -> int:
    from soulacp import ManagedSession                             # imported here: SoulRun itself does not need it

    source = arguments.message_file
    message = sys.stdin.buffer.read().decode("utf-8") if source == "-" else Path(source).read_text(encoding="utf-8")
    async with ManagedSession(provider=arguments.provider, model=arguments.model) as session:
        turn = await one_turn(session, message, conversation=arguments.conversation, model=arguments.model)
        print(turn.shown)
        if turn.needs_human:
            print("\n-- waiting for your answer; run again with the same --conversation and the answer in the file", file=sys.stderr)
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Send one message through SoulRun and SoulACP. Calls a real model.")
    parser.add_argument("message_file", help="file holding the human's words (UTF-8), or - for standard input")
    parser.add_argument("--provider", required=True, help="claude, codex, gemini, ...")
    parser.add_argument("--model", required=True, help="for example claude-acp/sonnet")
    parser.add_argument("--conversation", default="example")
    sys.exit(asyncio.run(_main(parser.parse_args())))

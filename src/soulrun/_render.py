"""What the command line prints for a turn.

The engine keeps every printed reply under the output cap of command-line tools, decisive fields
first, and marks whatever it had to leave out with the file to read. SoulRun follows the same rule for
its own output: the full text is always kept in a file; what is printed stays under the cap; when the
whole does not fit, the program is left out and a marker names the file.
"""
from __future__ import annotations

import json
from pathlib import Path

from . import _blocks, _engine, _records

DEFAULT_PRINT_CAP = 29_000        # UTF-8 bytes; the engine's own value (lib/reply_io.py PRINT_CAP)
ENTRIES_DIR = Path(_records.SOULRUN_DIR) / _records.ENTRIES


def print_cap() -> int:
    try:
        return int(_engine.load("lib.reply_io").PRINT_CAP)
    except Exception:
        return DEFAULT_PRINT_CAP


def size(text: str) -> int:
    return len(text.encode("utf-8"))


LONG_LINE = 2_000                 # UTF-8 bytes: a line this long is data (the human's words), not an instruction
KEEP_OF_LONG_LINE = 1_000         # characters of such a line that are still printed


def save_full(ctx) -> Path | None:
    """Keep the full text beside the run data (never inside the run's own folder, which the engine owns).

    Written to a temporary file and then put in place, so a reader never sees half of it. None when it cannot be
    written (a full disk, a file held by another program): the turn was already recorded by the engine, so the text is
    still printed - only the "read the rest in this file" pointer is missing."""
    if not ctx.cache_dir or not ctx.places:
        return None
    target = Path(ctx.places["soulrun_cache_dir"]) / ENTRIES_DIR / f"{Path(ctx.cache_dir).name}.txt"
    try:
        return _records.write_whole(target, ctx.text)
    except OSError:
        return None


def _shorten_long_lines(text: str, saved: Path | None) -> str:
    """Each line longer than LONG_LINE (the human's words inside a block: an original request, a pending message, a
    note) keeps its start and says where the rest is. The instructions around them are short lines and stay whole."""
    where = f"the full text is in {saved}" if saved is not None else "the full text could not be saved"
    lines = []
    for line in text.split("\n"):
        if size(line) > LONG_LINE:
            line = f"{line[:KEEP_OF_LONG_LINE]} … [{len(line)} characters; {where}]"
        lines.append(line)
    return "\n".join(lines)


def form_shown(ctx, printed: str) -> str | None:
    """The program form of what was printed: a slim turn too long for the command line is printed in the entry-path form."""
    return "entry_path" if ctx.program_form == "slim" and ctx.program not in printed else ctx.program_form


def for_shell(ctx) -> tuple[str, Path | None]:
    """The text to print and, for a run, the file that holds the full text. What is printed stays under the cap in every
    program form: first the program block gives way to a marker, then over-long lines are shortened."""
    if ctx.kind == "guide" or not ctx.cache_dir:
        return ctx.text, None
    saved = save_full(ctx)
    if size(ctx.text) <= print_cap():
        return ctx.text, saved
    text = ctx.text
    if ctx.program_form == "slim":
        # The slim entry says the program's first part is below: without it that would be untrue, so the turn is printed
        # in the entry-path form instead - the model reads main.aisop.json itself (see form_shown) and nothing is handed
        # out by node in this turn; a note about an interruption stays.
        from . import _records
        _records.clear_delivered(ctx.cache_dir)
        text = _blocks.join(_blocks.entry_path_blocks(ctx.data, ctx.blocks[0]))
    elif ctx.program:
        head = [block for block in ctx.blocks if ctx.program not in block]     # the program block, bare or wrapped
        marker = json.dumps({"program": {"omitted": True, "chars": len(ctx.program), "read": str(saved)}}, ensure_ascii=False)
        text = _blocks.join([*head, marker])
    if size(text) > print_cap():
        text = _shorten_long_lines(text, saved)
    return text, saved

"""What the human sees when no host program stands between SoulRun and the model (docs/05SoulRun 69, 70).

The engine has the model present each public block - a plan, a node's block with its messages, a gate, the final
answer, the evidence - as one reference line ``⟦engine:<run>/<file>⟧`` and leaves the text to the host: SoulBot's page
shows the block in its place. When SoulRun's command line prints a turn, the model itself is the host. Such a turn is
marked in the record of what it was given (mark); its text carries SCREEN_BLOCK, which tells the model to print the
blocks themselves on the screen (and SCREEN_ASSERTION joins its assertion); after each engine reply the command line
prints the text of every block that reply names for the human (human_part, called by _cmd.passthrough), once per turn.
Blocks that would take the output past the print cap wait, in order, for the next reply with room - a gate's or the
final answer's reply is short - and one line says so and names the command that prints them now (soulrun --expand). A
turn handed out by a host program (the Python call, SoulBot) is not marked: its host shows the blocks.
"""
from __future__ import annotations

import hashlib

from . import _records
from .errors import UsageError

SCREEN = "screen:on"                    # in the record of a turn: SoulRun's command line printed it, no host shows blocks
SHOWN = "shown:"                        # + a reference: that block's text was printed in this turn
WAITING = "waiting:"                    # + a number and a reference: that block waits for a reply with room
HEADER = "[SOULRUN FOR THE HUMAN]"
INTRO = ("PRINT THESE BLOCKS ON THE SCREEN NOW, before your next tool call: each in full and exactly as written, in "
         "this order, where the program says to present its reference line - the human sees only what you print")
SCREEN_BLOCK = (
    "[SOULRUN SCREEN]\n"
    "No host program shows this conversation to the human here: you do, as SoulBot's page does. Wherever the program "
    "says to present or emit a reference line ⟦engine:…⟧, print the text of that block on the screen instead - in full "
    "and exactly as written, nothing left out, shortened or retold. SoulRun prints that text after each engine reply, "
    f"under {HEADER}: print it before your next tool call, every time, from the first engine reply on - the engine's "
    "own nodes (Router.match, Router.cache-setup) included - so read each engine command's output whole. "
    "Every plan and node block with its messages, "
    "the whole of a gate (every option and every line), the final answer and the evidence go on the screen; only your "
    "own thinking does not."
)
SCREEN_ASSERTION = "SCREEN=EVERY_BLOCK_UNDER_SOULRUN_FOR_THE_HUMAN_PRINTED_IN_FULL_BEFORE_THE_NEXT_TOOL_CALL"
PAGE_BYTES = 24_000                     # one page of soulrun --expand, as soulrun --report pages


def mark(cache_dir) -> bool:
    """This turn's text was printed by SoulRun's command line: the model is the host. False when the turn has no record
    (not handed the slim program)."""
    given = _records.read_delivered(cache_dir)
    return given is not None and _records.write_delivered(cache_dir, given | {SCREEN})


def refs_in(reply) -> list[str]:
    """The blocks an engine reply names for the human, in the order the engine's program presents them: the previous
    dispatch's blocks; a served plan; the current child's ordered blocks; a node's block; a menu; terminal blocks; next plan."""
    if not isinstance(reply, dict):
        return []
    found: list[str] = []

    def add(value) -> None:
        if isinstance(value, str) and value.startswith("⟦engine:"):
            found.append(value)
        elif isinstance(value, list):
            for item in value:
                add(item)

    def sub(name: str):
        part = reply.get(name)
        return part if isinstance(part, dict) else {}

    add(sub("previous_dispatch_publication").get("public_refs"))
    add(reply.get("public_plan_ref"))
    add(sub("dispatch").get("public_refs"))
    add(reply.get("public_block_ref"))
    add(sub("gate").get("public_prompt_ref"))
    if reply.get("terminal_delivery_refs"):
        add(reply["terminal_delivery_refs"])
    else:
        for key in ("final_answer_ref", "evidence_ref", "error_report_ref"):
            add(reply.get(key))
    add(reply.get("public_plan_next_ref"))
    add(sub("next_plan").get("public_plan_ref"))
    return [ref for i, ref in enumerate(found) if ref not in found[:i]]


def block_text(ref: str, cache_dir) -> str | None:
    """The text of the public block a reference names (from the run's _public folder), or None."""
    from . import host
    text = host.expand_refs(ref, cache_dir=cache_dir)
    return None if text == ref else text.strip("\n")


def render(texts: list[tuple[str, str]], intro: str = INTRO) -> str:
    lines = [f"{HEADER} {intro}"]
    for ref, body in texts:
        lines += [f"----- {ref}", body, f"----- end of {ref}"]
    return "\n".join(lines) + "\n"


def not_printed(refs: list[str], cache_dir) -> str:
    """The line printed in place of blocks that would take the output past the print cap: they follow a later reply."""
    ask = " ".join(f'--expand "{ref}"' for ref in refs)
    return (f"{HEADER} {', '.join(refs)}: not printed here, since with it this output would pass the command line's "
            f"cap; SoulRun prints it after a later engine reply. To print it now: <soulrun> {ask} --cache-dir "
            f"\"{cache_dir}\" - then print what it prints.\n")


def human_part(cache_dir, reply, *, room: int | None = None) -> str | None:
    """The text of the blocks waiting from earlier replies and of those this reply names, in order, that this turn has
    not shown yet - or None: the turn was not printed by SoulRun's command line, or there is nothing to show. What does
    not fit in ``room`` (UTF-8 bytes) waits for a later reply, named in one line."""
    given = _records.read_delivered(cache_dir)
    if given is None or SCREEN not in given:
        return None
    waiting = _waiting(given)
    refs = refs_in(reply)
    for key in ('previous_dispatch_publication', 'dispatch'):
        dispatch = reply.get(key) if isinstance(reply, dict) else None
        returned = dispatch.get('public_refs') if isinstance(dispatch, dict) else None
        if isinstance(returned, list):
            from . import _engine
            store = _engine.load('lib.run_store').RunStore(cache_dir)
            allowed = _engine.load('lib.dispatch_publication').canonical_refs(store, returned)
            # These dispatches belong to this run; explicit historical --expand remains unchanged.
            refs = [ref for ref in refs if ref not in returned or ref in allowed]
    queue: list[tuple[str, str]] = []
    for ref in [*waiting, *refs]:
        body = block_text(ref, cache_dir) if SHOWN + ref not in given else None
        # a node served again names a new copy of the same block (the file name carries a fingerprint): shown once
        if body is not None and _seen(body) not in given and all(_seen(body) != _seen(b) for _, b in queue):
            queue.append((ref, body))
    if not queue:
        return None
    fit = len(queue)
    while fit and room is not None and len(render(queue[:fit]).encode("utf-8")) > room:
        fit -= 1
    printed, later = queue[:fit], queue[fit:]
    text = render(printed) if printed else ""
    if later:            # one short line, always: the engine's cap leaves this much under the command line's own
        text += not_printed([ref for ref, _ in later], cache_dir)
    kept = {piece for piece in given if not piece.startswith(WAITING)}
    _records.write_delivered(cache_dir, kept | _shown(printed)
                             | {f"{WAITING}{i:04d}:{ref}" for i, (ref, _) in enumerate(later)})
    return text or None


def _waiting(given: set[str]) -> list[str]:
    """The blocks waiting for a reply with room, oldest first."""
    return [piece.split(":", 2)[2] for piece in sorted(p for p in given if p.startswith(WAITING))]


def _seen(body: str) -> str:
    return SHOWN + "#" + hashlib.sha256(body.encode("utf-8")).hexdigest()[:16]


def _shown(texts: list[tuple[str, str]]) -> set[str]:
    return {SHOWN + ref for ref, _ in texts} | {_seen(body) for _, body in texts}


def expand(refs: list[str], cache_dir, *, offset: int = 0) -> str:
    """soulrun --expand: the text of these blocks, a page at a time; with the run of a printed turn, recorded as shown."""
    if cache_dir is None:
        raise UsageError("CACHE_DIR_REQUIRED", "--expand needs --cache-dir: the run the blocks belong to",
                         field="cache_dir", expected="a run folder")
    texts = []
    for ref in refs:
        body = block_text(ref, cache_dir)
        if body is None:
            raise UsageError("EXPAND_REF_UNKNOWN", f"{ref!r} names no public block of this run", field="expand",
                             expected="a reference line as the engine wrote it, ⟦engine:<run>/<file>⟧")
        texts.append((ref, body))
    text = render(texts, "the text of the blocks asked for; print each on the screen where the program says to present "
                         "its reference line, in full and exactly as written")
    if type(offset) is not int or not 0 <= offset <= len(text):
        raise UsageError("PAGE_INVALID", f"offset {offset!r}", field="offset", expected=f"0..{len(text)}")
    end = len(text)
    while end - offset > 1 and len(text[offset:end].encode("utf-8")) > PAGE_BYTES:
        end = offset + max(1, (end - offset) * PAGE_BYTES // len(text[offset:end].encode("utf-8")))
    page = text[offset:end]
    given = _records.read_delivered(cache_dir)
    if end >= len(text) and given is not None and SCREEN in given:
        _records.write_delivered(cache_dir, given | _shown(texts))
    if end < len(text):
        page += f"\n[more: run the same command with --offset {end}]\n"
    return page

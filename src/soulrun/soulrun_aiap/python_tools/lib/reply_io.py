"""alpha.48 (04 series doc 101; C2' of doc 80): every next-node / node-commit reply is echoed by the engine itself to
<cache_dir>/_work/replies/ and printed with the small, decisive fields first. The host's tool-output cap (Claude Agent SDK Bash:
30,000 characters, head kept) can then never cut the fields the model must act on - status, errors, next, the references, the
steps / skeleton / rules - and the model never needs to save a reply itself; the echoed file serves the rare read of a cut tail.
Beyond COMPACT_ABOVE printed characters the reply is printed without indentation (about a tenth smaller).
alpha.100 (doc 241 S5): the marker of newly sent contract sections comes first; node_facts and contracts precede payload_rules.
alpha.101 (doc 244): sizes are UTF-8 bytes - the CLI previews a tool output beyond about 30,000 bytes (doc 243), and a CJK character is
three bytes, so a reply under 29,000 characters could still be previewed; auxiliary fields follow the tail when that is what fits.
alpha.102 (doc 248): quality first - a fold takes only what the model already holds (marked in_your_context) or readable previews when
that brings the reply under the cap; never the program's constraints, the sub-graph's steps, the module result or input_authority itself.
docs/05SoulRun 87 (record 86 #1): what the executor needs before it acts - gate, dispatch, the program's identity, the node's constraints
(reserved), its steps and skeleton, the module result, the sub-graph (frame) - precedes the large blocks; a reply still over PRINT_CAP prints
indented, one value per line: the CLI saves it to a file, and a single line cannot be read page by page (Creator run 7: 16 cut reads)."""
from __future__ import annotations

import json
import re
import sys
from . import write_observation
from . import contracts as _contracts
from pathlib import Path

REPLIES_DIR = "_work/replies"
STDOUT_CHUNK_CHARS = 2048  # <=8192 UTF-8 bytes even for four-byte code points.
STDOUT_DELIVERY_RULE = _contracts.text('engine-faults.stdout_delivery')


class ReplyEmissionError(OSError):
    """A failed write may have reached the reader in part; never blindly resend."""
    delivery = 'UNVERIFIED'


def emit(text: str) -> None:
    """Print the exact wire + print's newline in bounded, flushed text writes."""
    stream = sys.stdout
    class Bounded:
        def write(self, value):
            for offset in range(0, len(value), STDOUT_CHUNK_CHARS):
                chunk = value[offset:offset + STDOUT_CHUNK_CHARS]
                if stream.write(chunk) != len(chunk):
                    raise OSError('Short tool-reply write; reader delivery is unverified.')
                stream.flush()
            return len(value)
        def flush(self):
            stream.flush()
    try:
        print(text, file=Bounded(), flush=True)
    except (OSError, UnicodeError) as exc:
        raise ReplyEmissionError(STDOUT_DELIVERY_RULE + ' Original emission error: ' + str(exc)) from exc
COMPACT_ABOVE = 25_000   # alpha.101 (doc 244): UTF-8 bytes
HEAD_KEYS = ("contracts_attached", "next_contracts_attached", "status", "answer_valid", "conditions_satisfied", "answer_disposition", "answer_hint", "errors", "repair_fields", "help", "contract_sections", "contract_sections_more",
             "user_message_shape", "source_input_template", "node", "user_message_hints", "next", "next_user_message", "run", "run_state", "public_block_ref", "public_plan_ref", "public_plan_next_ref",
             "final_answer_ref", "evidence_ref", "error_report_ref", "terminal_delivery_refs", "prev_public_block_ref", "gate", "dispatch", "previous_dispatch_publication", "payload_file",
             "cache_sha256", "entry_contracts", "module_execution",
             # docs/05SoulRun 87 (record 86 #1): the identity and constraints of the node before its steps, the module result and the
             # sub-graph before the rule texts; run 7 printed reserved and frame last, after payload_rules / input_authority /
             # source_support_candidates, where cut reads ended (a module result can be 49 KB: it follows the steps)
             "program_binding", "program", "reserved", "delivery_obligations", "resume", "budget", "topology",
             "steps", "payload_skeleton", "module", "frame", "node_facts", "contracts", "payload_rules", "input_authority")
TAIL_KEYS = ("next_plan",)


def order(reply):
    """The decisive fields first, the bulky ones last; a nested next_plan is ordered the same way; other keys keep their order."""
    if not isinstance(reply, dict):
        return reply
    out = {}
    for key in HEAD_KEYS:
        if key in reply:
            out[key] = reply[key]
    for key, value in reply.items():
        if key not in out and key not in TAIL_KEYS:
            out[key] = value
    for key in TAIL_KEYS:
        if key in reply:
            out[key] = order(reply[key]) if key == "next_plan" else reply[key]
    return out


def _safe(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.\-]+", "_", name or "run")[:80]


def next_numbered(cache_dir: str | Path, folder: str, stem: str, suffix: str) -> str:
    """alpha.106 (doc 265 E3): the next free `<folder>/<stem>.<n><suffix>` of the cache (n = 1 + the highest existing n, 1 when none);
    returns the cache-relative path, writes nothing."""
    root = Path(cache_dir) / folder
    pattern = re.compile(re.escape(stem) + r"\.(\d+)" + re.escape(suffix))
    taken = [int(m.group(1)) for p in (root.iterdir() if root.is_dir() else ()) if (m := pattern.fullmatch(p.name))]
    return f"{folder}/{stem}.{1 + max(taken, default=0)}{suffix}"


def next_reply_file(cache_dir: str | Path, kind: str, node: str) -> str:
    """alpha.106 (doc 265 E3): the path echo() would write now, without writing it."""
    root = Path(cache_dir) / REPLIES_DIR
    seq = (sum(1 for p in root.iterdir() if p.suffix == ".json") if root.is_dir() else 0) + 1
    return f"{REPLIES_DIR}/{seq:03d}.{kind}.{_safe(node)}.json"


def echo(reply: dict, cache_dir: str | Path, kind: str, node: str) -> str:
    """Write the full reply to <cache_dir>/_work/replies/NNN.<kind>.<node>.json; returns the cache-relative path."""
    root = Path(cache_dir) / REPLIES_DIR
    root.mkdir(parents=True, exist_ok=True)
    seq = sum(1 for p in root.iterdir() if p.suffix == ".json") + 1
    name = f"{seq:03d}.{kind}.{_safe(node)}.json"
    write_observation.writing(root / name)
    (root / name).write_text(json.dumps(reply, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_observation.writing(root / name, 'VERIFIED')
    return f"{REPLIES_DIR}/{name}"


def keep_rejected_payload(cache_dir: str | Path, rendered: str, payload_text: str) -> str | None:
    """alpha.58 (doc 123 §6 #1): a rejected payload's raw text stays beside its reply as NNN.commit.<node>.payload.txt, so a JSON or
    schema rejection can be diagnosed from the bytes the model actually sent."""
    try:
        reply_file = json.loads(rendered).get("reply_file")
    except (ValueError, AttributeError):
        return None
    if not isinstance(reply_file, str) or not reply_file.endswith(".json"):
        return None
    path = Path(cache_dir) / (reply_file[:-5] + ".payload.txt")
    write_observation.writing(path)
    path.write_text(payload_text, encoding="utf-8")
    write_observation.writing(path, 'VERIFIED')
    return path.as_posix()


PRINT_CAP = 29_000   # alpha.50 (doc 106): the printed reply stays under the host's output cap, as valid JSON; alpha.101 (doc 244): in UTF-8 bytes - the CLI previews an output beyond about 30,000 bytes (doc 243)
# alpha.102 (doc 248, quality first): a fold may only take what the model already holds or what stays readable - never what it needs to
# act and does not have. alpha.101 folded the alpha.50 tail (frame, module, program, reserved, input_authority) far more often once the
# cap counted bytes: the program's constraints of the next node (reserved) and the sub-graph's context (frame) became markers the model
# did not read (doc 247).
# 1. held: the next plan of a commit continues the model session that produced these values; they are folded first, as far as needed.
OMIT_HELD = (("next_plan", "user_message_hints"),                      # the same hints ride as next_user_message
             ("next_plan", "program"),                                 # run-constant, in this session's first reply
             ("next_plan", "input_authority", "prev_node_summary"),    # the summary the model just committed
             ("next_plan", "frame", "siblings"))                       # previews of the sub nodes this session committed
HELD_NOTE = {"next_plan.user_message_hints": "the same hints are next_user_message above",
             "next_plan.program": "unchanged since this session's first reply",
             "next_plan.input_authority.prev_node_summary": "the summary you just committed",
             "next_plan.frame.siblings": "the sub nodes you committed in this session; input_refs reads them whole"}
# 2. readable previews: complete values stay behind input_refs / --read-report-context; folded only when that brings the reply under the
# cap - otherwise the reply prints whole and the CLI's preview makes the model read it all (every previewed engine reply was read, doc 243).
OMIT_PREVIEWS = (("input_authority", "node_summaries"), ("next_plan", "input_authority", "node_summaries"),
                 ("input_authority", "final_context"), ("next_plan", "input_authority", "final_context"),
                 ("input_authority", "prev_node_summary"), ("frame", "siblings"), ("program",))
OMIT_ORDER = OMIT_HELD + OMIT_PREVIEWS
# Never folded: reserved (the program's constraints of the node), frame's steps / note / identity, module (the sub-graph's result),
# input_authority itself and its refs / catalog / assert / required_fields / gate_answer / user_message / context, steps,
# payload_skeleton / payload_schema / node_facts / contracts / payload_rules, hints / templates / examples / taxonomy / candidates /
# obligations, gate / dispatch / topology / resume / budget, status / errors / help / contract sections / references.


def size(text: str) -> int:
    """alpha.101 (doc 244): the printed size as the CLI measures it - UTF-8 bytes (a CJK character is three)"""
    return len(text.encode("utf-8"))


def _compact(reply: dict) -> str:
    return json.dumps(reply, ensure_ascii=False, separators=(",", ":"))


def _headed(out: dict, omitted: list[str]) -> dict:
    if not omitted:
        return out
    return {"reply_file": out.get("reply_file"), "omitted_fields": omitted, **{k: v for k, v in out.items() if k != "reply_file"}}


def _omit(printed: dict, path: str, order: tuple) -> tuple[dict, list[str]]:
    out = json.loads(json.dumps(printed, ensure_ascii=False))
    omitted: list[str] = []
    for keys in order:
        if size(_compact(_headed(out, omitted))) <= PRINT_CAP:
            break
        holder, original = out, printed
        for key in keys[:-1]:
            holder = holder.get(key) if isinstance(holder, dict) else None
            original = original.get(key) if isinstance(original, dict) else None
            if holder is None:
                break
        if not isinstance(holder, dict) or holder.get(keys[-1]) in (None, {}, [], ""):
            continue
        value = original[keys[-1]] if isinstance(original, dict) and keys[-1] in original else holder[keys[-1]]
        dotted = ".".join(keys)
        marker = {"omitted": True, "chars": len(json.dumps(value, ensure_ascii=False)), "read": path}
        if dotted in HELD_NOTE:
            marker["in_your_context"] = HELD_NOTE[dotted]
        holder[keys[-1]] = marker
        omitted = [o for o in omitted if not o.startswith(dotted + ".")]
        omitted.append(dotted)
    return _headed(out, omitted), omitted


def _omit_tail(printed: dict, path: str) -> tuple[dict, list[str]]:
    """alpha.50 / alpha.52 / alpha.101: above PRINT_CAP (UTF-8 bytes, the omitted_fields head counted) fields give way to
    {omitted, chars, read} markers. alpha.102 (doc 248): first what the model already holds (OMIT_HELD, marked in_your_context);
    then readable previews (OMIT_PREVIEWS) only when that brings the reply under the cap; nothing else, ever - a reply still over the
    cap prints with the held values folded and the CLI preview makes the model read it whole."""
    held, held_omitted = _omit(printed, path, OMIT_HELD)
    if size(_compact(held)) <= PRINT_CAP:
        return held, held_omitted
    more, more_omitted = _omit(printed, path, OMIT_HELD + OMIT_PREVIEWS)
    if size(_compact(more)) <= PRINT_CAP:
        return more, more_omitted
    return held, held_omitted


def _printed_text(ordered: dict, path: str) -> str:
    """The printed form of an ordered reply whose echo is `path` (alpha.106, doc 265: extracted from render unchanged, so that
    printed_size and render cannot diverge)."""
    printed = {"reply_file": path, **ordered}
    text = json.dumps(printed, ensure_ascii=False, indent=2)
    if size(text) > COMPACT_ABOVE:
        text = _compact(printed)
    if size(text) > PRINT_CAP:
        printed, omitted = _omit_tail(printed, path)
        if omitted:
            text = _compact(printed)
    if size(text) > PRINT_CAP:
        # docs/05SoulRun 87 (record 86 #1): the CLI keeps this output in a file and the model reads that file; compact text is one line
        # its reader cannot page (run 7: 16 cut reads), indented text is the echoed file's own form. Larger, so still over the cap.
        text = json.dumps(printed, ensure_ascii=False, indent=2)
    return text


def render(reply: dict, cache_dir: str | Path, kind: str, node: str) -> str:
    """The text to print: reply_file first, then the ordered reply; compact beyond COMPACT_ABOVE bytes; above PRINT_CAP bytes the
    held values (then, if that brings it under the cap, the readable previews) become markers listed in omitted_fields, so the
    printed reply is always complete JSON; a reply still over the cap prints indented (docs/05SoulRun 87)."""
    ordered = order(reply)
    path = echo(ordered, cache_dir, kind, node)
    wire = _printed_text(ordered, path)
    from . import accepted_replies
    accepted_replies.preserve(cache_dir, ordered, path, wire, kind, node)
    return wire


def printed_size(reply: dict, path: str) -> int:
    """alpha.106 (doc 265 E3): the UTF-8 size render() would print for `reply` echoed at `path` - order, the reply_file head, indent /
    compact, the folding above PRINT_CAP - without writing anything."""
    return size(_printed_text(order(reply), path))

"""``soulrun --program``: a run's business program, handed to the model by SoulRun instead of read from its files.

The user's ruling of 10-15 (docs/05SoulRun 49 §5): with SoulRun the model reads nothing itself - everything comes back
through soulrun commands. The program is the one the run is bound to: the engine's own loader loads it the way the
engine does (``engine_core._load_routed_program``, which checks the files against the run's binding), so what the
model gets is what the engine serves its nodes from. Nothing is written.

Three views, each one JSON object:
    overview  the main graph, the node list, the entry and end nodes, the files, and the entry program's
              system_prompt, output_mode, tools and params in full - with the size and fingerprint of every other
              field of LISTED_FROM characters or more (worth fetching with ``--field``) and only the names of the
              smaller ones; from AIAP.md, what the run may do (name, version, trust level, permissions, runtime) in
              full and the rest the same way (``aiap_md.<key>`` as a field);
    node      one node's function as the program writes it, the declared tools and tool entries it names, and the
              shared constraints it cites;
    field     one field of a program file in full, paged when it is long (``offset``, ``limit``): a page holds at most
              PAGE characters and PAGE_BYTES bytes as printed, so it is never cut off by a command line.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from . import _engine
from .errors import SoulRunError, UsageError

ALWAYS = ("system_prompt", "output_mode", "tools", "params")    # small, and needed on every node: given in full
PAGE = 12_000                                                   # characters of one page of a long field
PAGE_BYTES = 24_000      # and at most this many bytes of it as printed (a CJK character is three): with the rest of the
#                          answer a page stays under the engine's 29,000-byte output cap, which a model's CLI enforces
AIAP_MD_ALWAYS = ("name", "version", "trust_level", "permissions", "runtime")   # AIAP.md: what the run may do
LISTED_FROM = 200       # characters: a field this long is listed with its size and fingerprint, a smaller one by name
#                         only (docs/05SoulRun 54 S1: 31 of the 45 fields the I Ching overview listed were under it)


def _text(value) -> str:
    """A field as one text: a string as it is, anything else as JSON written the way the engine writes a program
    contract (``engine_core.read_program_contract``: compact separators), so the size and fingerprint given here are
    the ones the engine reports in ``program_contracts`` and a page holds the engine's own text
    (docs/05SoulRun 56 S5: with Python's spaced default, shared_constraints was 13,661 characters here, 13,522 there)."""
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load(cache_dir):
    """The program this run is bound to, loaded by the engine's own loader."""
    if cache_dir is None:
        raise UsageError("CACHE_DIR_REQUIRED", "--program needs the run: --cache-dir <the run's folder>", field="cache_dir",
                         expected="the cache_dir of the [EXECUTION CONTEXT] block")
    folder = Path(cache_dir)
    if not (folder / "_run_input.json").is_file():
        raise UsageError("NOT_A_RUN", f"{folder} is not a run folder", field="cache_dir",
                         expected="the cache_dir of the [EXECUTION CONTEXT] block")
    core, store = _engine.load("lib.engine_core"), _engine.load("lib.run_store")
    with _engine.translated():
        program = core._load_routed_program(core._read_run_input(store.RunStore(folder)))
    if program is None:
        raise UsageError("PROGRAM_NOT_ROUTED", "this run has no program yet: Router.match has not been committed",
                         field="cache_dir", expected="a run past Router.match")
    return program


def _listed(values: dict, listed: str, named: str) -> dict:
    """The fields worth fetching by their size and fingerprint, the small ones by name."""
    texts = {key: _text(value) for key, value in values.items()}
    return {listed: [{"field": key, "chars": len(text), "sha256": _sha(text)}
                     for key, text in texts.items() if len(text) >= LISTED_FROM],
            named: [key for key, text in texts.items() if len(text) < LISTED_FROM]}


def overview(program) -> dict:
    parse = _engine.load("lib.aisop_parse")
    entry, system = program.entry, program.entry.system
    main = entry.tasks.get("main")
    out = {
        "program": {"name": program.name, "dir": str(program.dir), "entry_file": program.entry_file,
                    "trust_level": program.trust_level, "loading_mode": program.loading_mode},
        "main_graph": (entry.user.get("aisop") or {}).get("main"),
        "main_nodes": list(main["order"]) if main else [],
        "entry_node": parse.entry_nodes(main)[0] if main and main["order"] else None,
        "end_nodes": [n for n in main["order"] if main["node_types"].get(n) == "end"] if main else [],
        "files": [{"file": name, "tasks": list(doc.tasks), "functions": list(doc.functions)} for name, doc in program.docs.items()],
        "system": {key: system[key] for key in ALWAYS if key in system},
        **_listed({key: value for key, value in system.items() if key not in ALWAYS}, "fields", "other_fields"),
    }
    front = program.frontmatter or {}
    if front:      # AIAP.md: what the run may do is given in full, its descriptive metadata by size (--field aiap_md.<key>)
        out["aiap_md"] = {key: front[key] for key in AIAP_MD_ALWAYS if key in front}
        out |= _listed({f"aiap_md.{key}": value for key, value in front.items() if key not in AIAP_MD_ALWAYS},
                       "aiap_md_fields", "aiap_md_other_fields")
    out["read"] = ("--node <node> [--doc <file>]: one node's function; --field <field> [--doc <file>] [--offset N] "
                   "[--limit N]: one field in full")
    out["rule"] = ("This is the program the run is bound to. Do not open its files with a file tool or a shell read; "
                   "ask for what you need here.")
    return out


def node(program, name: str, doc: str | None = None) -> dict:
    holders = [file for file, item in program.docs.items() if name in item.functions and (doc is None or file == doc)]
    if not holders:
        known = sorted({n for item in program.docs.values() for n in item.functions})
        raise UsageError("NODE_UNKNOWN", f"no function {name!r} in the program" + (f" file {doc}" if doc else ""),
                         field="node", expected=known)
    if len(holders) > 1:
        raise UsageError("NODE_AMBIGUOUS", f"{name!r} is defined in {', '.join(holders)}", field="doc", expected=holders)
    holder = program.docs[holders[0]]
    function = holder.functions[name]
    text = _text(function)
    system = {**program.entry.system, **holder.system} if holder is not program.entry else program.entry.system
    tools = [tool for tool in system.get("tools") or [] if isinstance(tool, dict) and tool.get("name")
             and re.search(rf"(?<![\w-]){re.escape(str(tool['name']))}(?![\w-])", text)]
    entries = [item for group in system.get("tool_dirs") or [] if isinstance(group, dict)
               for item in group.get("files") or [] if isinstance(item, dict) and item.get("file") and str(item["file"]) in text]
    shared = system.get("shared_constraints") if isinstance(system.get("shared_constraints"), dict) else {}
    cited = {key: shared[key] for key in shared if f"shared_constraints.{key}" in text}
    return {"node": name, "file": holders[0], "function": function, "chars": len(text), "sha256": _sha(text),
            "tools_named": tools, "tool_entries_named": entries, "shared_constraints_cited": cited,
            "rule": "The engine serves this node's steps in its next-node reply; this is the program's own text of it."}


def field(program, name: str, doc: str | None = None, offset: int = 0, limit: int = PAGE) -> dict:
    file = doc or program.entry_file
    if file not in program.docs:
        raise UsageError("DOC_UNKNOWN", f"no file {file!r} in the program", field="doc", expected=list(program.docs))
    item = program.docs[file]
    places = {**{f"user.{key}": value for key, value in item.user.items() if key != "functions"}, **item.system}
    if file == program.entry_file and program.frontmatter:
        places |= {"aiap_md": program.frontmatter, **{f"aiap_md.{key}": value for key, value in program.frontmatter.items()}}
    if name not in places:
        raise UsageError("FIELD_UNKNOWN", f"no field {name!r} in {file}", field="field", expected=sorted(places))
    if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= PAGE:
        raise UsageError("PAGE_INVALID", f"offset {offset!r}, limit {limit!r}", field="offset",
                         expected=f"offset >= 0 and 1 <= limit <= {PAGE}")
    text = _text(places[name])
    end = min(len(text), offset + limit)
    while end - offset > 1:
        used = len(json.dumps(text[offset:end], ensure_ascii=False).encode("utf-8"))
        if used <= PAGE_BYTES:
            break
        end = offset + max(1, (end - offset) * PAGE_BYTES // used)
    complete = offset == 0 and end >= len(text)
    return {"field": name, "file": file, "total_chars": len(text), "sha256": _sha(text), "offset": offset,
            "next_offset": end if end < len(text) else None, "complete": complete,
            **({"value": places[name]} if complete else {"text": text[offset:end]})}


def view(cache_dir, *, node_name: str | None = None, field_name: str | None = None, doc: str | None = None,
         offset: int = 0, limit: int | None = None) -> dict:
    """What ``soulrun --program`` prints (see the module's text)."""
    if node_name is not None and field_name is not None:
        raise UsageError("PROGRAM_VIEW_CONFLICT", "--node and --field cannot be given together", field="field",
                         expected="one of --node or --field, or neither for the overview")
    try:
        program = load(cache_dir)
        if node_name is not None:
            return node(program, node_name, doc)
        if field_name is not None:
            return field(program, field_name, doc, offset, PAGE if limit is None else limit)
        return overview(program)
    except SoulRunError:
        raise
    except Exception as exc:          # a program the engine itself cannot load: say so, never a bare traceback
        raise SoulRunError("PROGRAM_UNREADABLE", f"{type(exc).__name__}: {exc}", field="cache_dir",
                           expected="a run whose program the engine can load") from exc

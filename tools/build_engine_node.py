"""Build the slim, node-by-node form of the engine program: src/soulrun/engine_node.aisop.json.

    python tools/build_engine_node.py            # write it from the bundled engine's two program files
    python tools/build_engine_node.py --check    # prove the file is current and complete (exit 1 if not)

The file is still AISOP - a role "system" part and a role "user" part - and every text in it is the
engine's own text, copied verbatim from soulrun_aiap/main.aisop.json and soulrun_aiap/agent_engine.aisop.json.
What this tool adds is only the arrangement: "soulrun_delivery" says which pieces a model needs at which
engine node, so SoulRun can hand out what is needed instead of the whole program (docs/guide/01-design.md).

The sub-agent part (functions sub_agent_*, graph aisop.sub_agent, sections sub_agent_*) is a reference
for the planned engine change: the engine still starts sub-agents with agent_engine.aisop.json. Function
names inside the sub-agent texts are NOT rewritten here (only engine text is used); every place that will
need the new name is listed under soulrun_delivery.sub_agent.rename_sites instead.

--check fails when the engine's program files change, so a newer engine cannot be bundled with a stale
or incomplete slim program: run the tool again and review the arrangement below.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENGINE = ROOT / "src" / "soulrun" / "soulrun_aiap"
MAIN = ENGINE / "main.aisop.json"
AGENT = ENGINE / "agent_engine.aisop.json"
OUTPUT = ROOT / "src" / "soulrun" / "engine_node.aisop.json"

IDENTITY = ("protocol", "axiom_0", "id", "name", "version")

# ---- the main program, arranged by engine node ----------------------------------------------------------------
# A turn starts with "entry" (and "recovery_entry" when it re-enters a run). Every other group is handed out by
# SoulRun's command line after the engine reply that first needs it, once per turn (soulrun._slim.node_part): a reply
# that serves a node brings that node's group. A piece may sit in more than one group when different replies can be the
# first to need it (NodeLoop: Router.cache-setup, or the first program node of a turn that re-enters a run there;
# terminal_delivery_contract: whichever reply ends the run). The node execution and payload transport contracts are
# needed from the turn's first engine reply on; they start the turn, because that reply is long already (about 24,000
# of the 29,000 bytes the engine prints at most) and a part after it must stay under the same cap.
MAIN_DELIVERY = {
    "entry": {"when": "the start of every turn: what the first step and the first engine reply need",
              "system": ["output_mode", "hsaw_first_law", "system_prompt", "node_execution_contract",
                         "payload_transport_contract"], "functions": ["Start"]},
    "recovery_entry": {"when": "the start of a turn that re-enters a run (entry_mode other than fresh)",
                       "system": ["params", "bootstrap_recovery"], "functions": []},
    "Router.match": {"when": "a reply serves Router.match", "system": [], "functions": ["RouterMatch"]},
    "Router.cache-setup": {"when": "a reply serves Router.cache-setup", "system": [], "functions": ["CacheSetup", "NodeLoop"]},
    "business": {"when": "a reply serves a program node before NodeLoop was handed out this turn", "system": [],
                 "functions": ["NodeLoop"]},
    "dispatch": {"when": "a reply asks for a sub-agent dispatch", "system": ["dispatch_scope_contract"], "functions": []},
    "Engine.execute-report": {"when": "a reply serves Engine.execute-report", "system": [], "functions": ["Report"]},
    "Engine.final-answer": {"when": "a reply serves Engine.final-answer", "system": ["terminal_delivery_contract"],
                            "functions": ["Final"]},
    "run_failed": {"when": "a reply reports the run FAILED or ABANDONED", "system": ["terminal_delivery_contract"],
                   "functions": ["ErrorReport"]},
    "terminal": {"when": "a reply carries terminal_delivery_refs", "system": ["terminal_delivery_contract"], "functions": []},
}
# Groups every other group can count on: a turn starts with entry.
ALWAYS_BEFORE = ("entry",)
MAIN_NOT_DELIVERED = {
    "summary": "descriptive; no step refers to it",
    "description": "descriptive; no step refers to it",
    "flow_format": "format marker for loaders; the graph itself is delivered",
    "loading_mode": "the source says normal (read the whole file); this file is delivered by node",
    "trust_level": "format marker for loaders",
    "fractal_exempt": "format marker for loaders",
    "tools": "nothing for the model to do with it: the engine's tools are named in the entry block",
    "json_schema": "every engine reply names its own schema (schema_ref)",
    "source_support_contract": "a pointer only: every turn's first engine reply carries the full text (entry_contracts)",
    "report_delivery_contract": "a pointer only: every turn's first engine reply carries the full text (entry_contracts)",
    "quality_execution_contract": "a pointer only: every turn's first engine reply carries the full text (entry_contracts)",
    "loading_mode_contract": "a pointer only: every turn's first engine reply carries the full text (entry_contracts)",
}
# Sections a delivered text names whose full text the engine's own reply carries (entry_contracts of the first reply).
REPLY_CARRIES = ("source_support_contract", "report_delivery_contract", "quality_execution_contract", "loading_mode_contract")
# References from a piece to a section handed out later than the piece itself, each with why it is in time. A new
# reference of this kind fails --check until it is reviewed and listed here.
DEFERRED_REFS = {
    ("system_prompt", "terminal_delivery_contract"): "used only on a terminal reply; it comes with Engine.final-answer, "
                                                     "a failed or abandoned run, or any reply carrying terminal_delivery_refs",
    ("node_execution_contract", "terminal_delivery_contract"): "used only on a terminal reply (as above)",
    ("NodeLoop", "terminal_delivery_contract"): "used only on a terminal reply (as above)",
}
# Nothing in the slim program is replaced: params stays the engine's text (the only place the main program says what each
# entry_mode means, handed out on re-entry); its three values reach the model in the [EXECUTION CONTEXT] and
# [EXECUTE ENGINE ENTRY] blocks.
FILLED_BY_SOULRUN: dict = {}
# Not even copied into the file: descriptive fields and loader markers. The other sections that are never handed out stay
# in the file as the engine's text (the sub-agent reference shares some of them).
NOT_COPIED = ("summary", "description", "flow_format", "loading_mode", "trust_level", "fractal_exempt")

# ---- the sub-agent program, as main-program nodes - reference only --------------------------------------------
SUB_AGENT_RENAMES = {"Init": "sub_agent_init", "Execute": "sub_agent_execute", "Commit": "sub_agent_commit",
                     "ScopeNext": "sub_agent_scope_next", "Return": "sub_agent_return", "Fail": "sub_agent_fail"}
SUB_AGENT_NOT_MOVED = ("summary", "description", "flow_format", "loading_mode", "trust_level", "fractal_exempt")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load(path: Path) -> tuple[dict, dict]:
    doc = json.loads(path.read_text(encoding="utf-8"))
    roles = [part.get("role") for part in doc]
    if roles != ["system", "user"]:
        raise ValueError(f"{path.name}: expected the two parts system and user, found {roles}")
    return doc[0]["content"], doc[1]["content"]


def _refs(value, names) -> list[str]:
    """Section names a text refers to. Only identifiers with an underscore count: plain words such as
    'summary' or 'tools' also occur as ordinary English in the steps."""
    text = json.dumps(value, ensure_ascii=False)
    return sorted(n for n in names if "_" in n and re.search(r"(?<![A-Za-z0-9_])" + re.escape(n) + r"(?![A-Za-z0-9_])", text))


def build(main_path: Path = MAIN, agent_path: Path = AGENT) -> list:
    msys, musr = _load(main_path)
    asys, ausr = _load(agent_path)

    system = {key: msys[key] for key in IDENTITY}
    system["loading_mode"] = "node"
    system["soulrun_source"] = {
        "main.aisop.json": {"sha256": _sha(main_path), "engine_id": msys.get("id")},
        "agent_engine.aisop.json": {"sha256": _sha(agent_path), "engine_id": asys.get("id")},
        "engine_version": msys.get("version"),
        "generator": "tools/build_engine_node.py",
        "rule": "every text below is the engine's own text, copied verbatim; only the arrangement is SoulRun's",
    }
    for key, value in msys.items():                                    # main sections, in the engine's order
        if key not in IDENTITY and key not in NOT_COPIED:
            system[key] = value

    shared, moved = [], []
    for key, value in asys.items():                                    # sub-agent sections
        if key in IDENTITY or key in SUB_AGENT_NOT_MOVED:
            continue
        if key in msys and json.dumps(msys[key], ensure_ascii=False) == json.dumps(value, ensure_ascii=False):
            shared.append(key)                                         # byte-identical in both: one copy
        else:
            system["sub_agent_" + key] = value
            moved.append(key)

    functions = dict(musr["functions"])
    rename_sites: dict[str, dict[str, int]] = {}
    for old, new in SUB_AGENT_RENAMES.items():
        functions[new] = ausr["functions"][old]
    for old, new in SUB_AGENT_RENAMES.items():
        text = json.dumps(ausr["functions"][old], ensure_ascii=False)
        sites = {name: len(re.findall(r"(?<![A-Za-z0-9_])" + name + r"(?![A-Za-z0-9_])", text))
                 for name in SUB_AGENT_RENAMES if name != old}
        sites = {name: count for name, count in sites.items() if count}
        if sites:
            rename_sites[new] = sites
    graph_sites = {name: len(re.findall(r"(?<![A-Za-z0-9_])" + name + r"(?![A-Za-z0-9_])", ausr["aisop"]["main"]))
                   for name in SUB_AGENT_RENAMES}

    system["soulrun_delivery"] = {
        **{node: dict(piece) for node, piece in MAIN_DELIVERY.items()},
        "not_delivered": dict(MAIN_NOT_DELIVERED),
        "filled_by_soulrun": dict(FILLED_BY_SOULRUN),
        "sub_agent": {
            "status": "reference only: the engine still starts sub-agents with agent_engine.aisop.json (a planned engine change)",
            "graph": "sub_agent",
            "system": [*shared, *["sub_agent_" + key for key in moved]],
            "functions": list(SUB_AGENT_RENAMES.values()),
            "shared_with_main": shared,
            "renamed_from": {new: old for old, new in SUB_AGENT_RENAMES.items()},
            "rename_sites": rename_sites,
            "graph_rename_sites": {k: v for k, v in graph_sites.items() if v},
            "not_moved": list(SUB_AGENT_NOT_MOVED),
        },
    }
    user = {"instruction": musr["instruction"], "user_input": musr["user_input"],
            "aisop": {"main": musr["aisop"]["main"], "sub_agent": ausr["aisop"]["main"]},
            "functions": functions}
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def render(doc: list) -> str:
    return json.dumps(doc, ensure_ascii=False, indent=2) + "\n"


def check(main_path: Path = MAIN, agent_path: Path = AGENT, output: Path = OUTPUT) -> list[str]:
    """Every reason the slim program cannot be used as it is; an empty list means it is current and complete."""
    problems: list[str] = []
    msys, musr = _load(main_path)
    asys, ausr = _load(agent_path)

    # 1. every part of both engine programs has a place (nothing dropped silently, nothing new left unarranged)
    placed = set(IDENTITY) | set(MAIN_NOT_DELIVERED)
    for piece in MAIN_DELIVERY.values():
        placed |= set(piece["system"])
    for key in sorted(set(msys) - placed):
        problems.append(f"main.aisop.json section '{key}' has no place in the arrangement (new in this engine?)")
    for key in sorted(placed - set(msys)):
        problems.append(f"the arrangement names main.aisop.json section '{key}', which the engine no longer has")
    delivered_functions = [f for piece in MAIN_DELIVERY.values() for f in piece["functions"]]
    for name in sorted(set(musr["functions"]) - set(delivered_functions)):
        problems.append(f"main.aisop.json function '{name}' is not delivered at any engine node")
    for name in sorted(set(delivered_functions) - set(musr["functions"])):
        problems.append(f"the arrangement delivers function '{name}', which the engine no longer has")
    handed_sections = {k for piece in MAIN_DELIVERY.values() for k in piece["system"]}
    for key in sorted(handed_sections & set(MAIN_NOT_DELIVERED)):
        problems.append(f"section '{key}' is both handed out and listed as not delivered")
    for key in sorted(set(REPLY_CARRIES) - set(MAIN_NOT_DELIVERED)):
        problems.append(f"REPLY_CARRIES names '{key}', which is not listed as not delivered")
    for name in sorted(set(ausr["functions"]) ^ set(SUB_AGENT_RENAMES)):
        problems.append(f"agent_engine.aisop.json function '{name}' is not matched by the sub_agent arrangement")
    if musr.get("user_input") != "{user_input}":
        problems.append("main.aisop.json no longer has the user_input slot '{user_input}'")

    # 2. every handed-out text refers only to what has reached the model by then: its own group, the group every turn
    # starts with (entry), a section the engine's reply itself carries, or a reviewed deferred reference (DEFERRED_REFS)
    # to a section that a later group hands out
    names = [k for k in msys if k not in IDENTITY]
    handed_out = {k for piece in MAIN_DELIVERY.values() for k in piece["system"] + piece["functions"]}

    def available(node: str) -> set[str]:
        groups = [node] + [g for g in ALWAYS_BEFORE[:ALWAYS_BEFORE.index(node) if node in ALWAYS_BEFORE else None]]
        if node == "recovery_entry":
            groups = [node, "entry"]
        return {k for g in groups for k in MAIN_DELIVERY[g]["system"] + MAIN_DELIVERY[g]["functions"]}

    used_deferred: set[tuple[str, str]] = set()
    for node, piece in MAIN_DELIVERY.items():
        have = available(node)
        for key in piece["system"] + piece["functions"]:
            text = msys.get(key) if key in piece["system"] else musr["functions"].get(key)
            for ref in _refs(text, names):
                if ref == key or ref in have or ref in REPLY_CARRIES:
                    continue
                if (key, ref) in DEFERRED_REFS and ref in handed_out:
                    used_deferred.add((key, ref))
                    continue
                problems.append(f"{node}: '{key}' refers to '{ref}', which has not reached the model by then")
    for key, ref in sorted(set(DEFERRED_REFS) - used_deferred):
        problems.append(f"DEFERRED_REFS lists '{key}' -> '{ref}', which no handed-out text refers to any more")
    anames = [k for k in asys if k not in IDENTITY]
    for fn in ausr["functions"]:
        for ref in _refs(ausr["functions"][fn], anames):
            if ref in SUB_AGENT_NOT_MOVED:
                problems.append(f"sub-agent function '{fn}' refers to '{ref}', which is not moved")

    # 3. the file on disk is exactly what this engine produces, and its texts are the engine's texts verbatim
    expected = render(build(main_path, agent_path))
    if not output.is_file():
        problems.append(f"{output.name} does not exist: run python tools/build_engine_node.py")
    elif output.read_text(encoding="utf-8") != expected:
        problems.append(f"{output.name} is not what the bundled engine produces: run python tools/build_engine_node.py")
    else:
        doc = json.loads(expected)
        s, u = doc[0]["content"], doc[1]["content"]
        for key, value in s.items():
            if key in msys and key not in IDENTITY and key != "loading_mode" and value != msys[key]:
                problems.append(f"section '{key}' differs from main.aisop.json")
            if key.startswith("sub_agent_") and value != asys[key[len('sub_agent_'):]]:
                problems.append(f"section '{key}' differs from agent_engine.aisop.json")
        for name, value in u["functions"].items():
            source = musr["functions"].get(name) if name in musr["functions"] else \
                ausr["functions"].get(s["soulrun_delivery"]["sub_agent"]["renamed_from"].get(name, ""))
            if value != source:
                problems.append(f"function '{name}' differs from the engine's text")
    return problems


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--check", action="store_true", help="verify instead of writing")
    args = parser.parse_args(argv)
    if args.check:
        problems = check()
        for line in problems:
            print("PROBLEM:", line)
        print("engine_node.aisop.json: OK" if not problems else f"{len(problems)} problem(s)")
        return 1 if problems else 0
    text = render(build())
    OUTPUT.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {OUTPUT.relative_to(ROOT).as_posix()} ({len(text.encode('utf-8')):,} bytes)")
    problems = check()
    for line in problems:
        print("PROBLEM:", line)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

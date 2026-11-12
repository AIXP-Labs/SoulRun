"""Target program loading for the v7 engine: directory -> executable model, load checks, catalog.

Rules (04 series doc 02): R-01 structure, R-05 load checks (min_protocol_version, archived, T4
permissions, trust normalisation), R-06/I-07 skipped reference files, R-14 unsupported reserved
keys, R-16 delegate depth and cycles, I-02 candidate successors, I-03 gate sources, I-11 AISP
defaults, I-13 entry file detection, I-14 soft structure problems. The conformance tool's program
mode is a thin wrapper over analyze(). Own implementation; nothing copied from v6.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from . import aiap_md, aisop_parse, program_binding

SUPPORTED_PROTOCOL = "AIAP V1.0.0"
# AIAP §17.3: the default recursion limit of 3 applies to CROSS-PROGRAM invocations (one AIAP package running
# another, Pattern D/F, deferred to P7). Module sub-graphs inside one program are unlimited (doc 05 §0/§4.2).
MAX_RECURSION_DEPTH = 3
ENTRY_CANDIDATES = ("main.aisop.json", "aisp.aisop.json")
SOFT_STRUCTURE_PROBLEMS = {"LOADING_MODE_INVALID", "SYSTEM_MISSING_FLOW_FORMAT"}
DEFAULT_TRUST_LEVEL = 3
ENGINE_NODES = ("Router.match", "Router.cache-setup", "Engine.execute-report", "Engine.final-answer",
                "Router.report", "Router.summary", "final")   # alpha.85: the two new names; the earlier identities stay engine nodes


def execution_loading_mode(declared: str | None) -> str:
    """Lite keeps its identity; it currently borrows normal's complete executor."""
    return "node" if declared == "node" else "normal"


class ProgramError(ValueError):
    def __init__(self, code: str, detail: str):
        super().__init__(f"{code}: {detail}")
        self.code, self.detail = code, detail


@dataclass
class ProgramDoc:
    name: str
    doc: dict
    tasks: dict = field(default_factory=dict)      # task name -> parsed graph
    functions: dict = field(default_factory=dict)  # node name -> function body

    @property
    def system(self) -> dict:
        return self.doc.get("system") or {}

    @property
    def user(self) -> dict:
        return self.doc.get("user") or {}


@dataclass
class Program:
    dir: Path
    entry_file: str
    docs: dict                       # file name -> ProgramDoc
    skipped: list                    # [{file, reason}]
    frontmatter: dict                # AIAP.md frontmatter or {}
    has_aiap_md: bool
    runtime_loading_mode: str | None = None

    @property
    def entry(self) -> ProgramDoc:
        return self.docs[self.entry_file]

    @property
    def name(self) -> str:
        fm_name = self.frontmatter.get("name")
        if isinstance(fm_name, str) and fm_name:
            return fm_name
        sys_id = self.entry.system.get("id")
        if isinstance(sys_id, str) and sys_id:
            return sys_id.split(".")[0]
        return self.dir.name

    @property
    def trust_level(self):
        raw = self.frontmatter.get("trust_level", self.entry.system.get("trust_level", DEFAULT_TRUST_LEVEL))
        return aiap_md.normalize_trust_level(raw)

    @property
    def permissions(self) -> dict | None:
        p = self.frontmatter.get("permissions")
        return p if isinstance(p, dict) else None

    @property
    def runtime(self) -> dict | None:
        r = self.frontmatter.get("runtime")
        return r if isinstance(r, dict) else None

    @property
    def loading_mode(self) -> str:
        lm = self.entry.system.get("loading_mode")
        return lm if lm in aisop_parse.LOADING_MODES else "normal"

    @property
    def execution_loading_mode(self) -> str:
        return 'node' if self.loading_mode == 'node' and self.runtime_loading_mode != 'normal' else 'normal'

    def permissions_digest(self) -> str | None:
        p = self.permissions
        if not p:
            return None
        fs = p.get("file_system") if isinstance(p.get("file_system"), dict) else {}
        shell = p.get("shell")
        net = p.get("network")
        def flag(v):
            if v is False:
                return "false"
            if isinstance(v, dict):
                return "true" if v.get("allowed") else "false"
            return "unset"
        return (f"fs:{'/'.join(fs.get('operations', [])) or 'unset'} {fs.get('scope', '')} | "
                f"shell:{flag(shell)} | network:{flag(net)} | code:{flag(p.get('code_execution'))}").strip()


# ---------------------------------------------------------------------------
# loading
# ---------------------------------------------------------------------------

def _read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8-sig")), None
    except FileNotFoundError:
        return None, "missing"
    except json.JSONDecodeError as exc:
        return None, f"invalid JSON: {exc}"


def load_program(entry_path: str | Path, entry_file: str | None = None, *, binding: dict | None = None) -> Program:
    """entry_path may be the program directory or its entry .aisop.json file."""
    path = Path(entry_path)
    if path.is_file():
        entry_file = entry_file or path.name
        directory = path.parent
    else:
        directory = path
    raw_files, read_errors = program_binding.read_files(directory)
    if binding is not None:
        changes = program_binding.differences(binding, program_binding.identity(directory, entry_file, raw_files, read_errors))
        if changes:
            error = ProgramError('PROGRAM_DRIFT_DETECTED', 'program bytes differ from the run binding; no new rules may execute')
            error.changes = changes
            raise error
    if not directory.is_dir():
        raise ProgramError("PROGRAM_INVALID", f"not a directory: {directory}")
    if read_errors:
        raise ProgramError('PROGRAM_UNREADABLE', str(read_errors))
    docs, skipped = {}, []
    for name, raw in sorted(raw_files.items()):
        if not name.endswith('.aisop.json'):
            continue
        file = directory / name
        try:
            data = json.loads(raw.decode('utf-8-sig'))
        except (ValueError, UnicodeError) as exc:
            skipped.append({"file": name, "reason": f'invalid JSON: {exc}'})
            continue
        try:
            parsed = aisop_parse.parse_aisop_document(data)
        except aisop_parse.AisopFormatError as exc:
            skipped.append({"file": file.name, "reason": str(exc)})
            continue
        pd = ProgramDoc(name=file.name, doc=parsed)
        for tname, body in (parsed["user"].get("aisop") or {}).items():
            try:
                pd.tasks[tname] = aisop_parse.parse_task(body)
            except aisop_parse.AisopFormatError:
                continue
        fns = parsed["user"].get("functions")
        pd.functions = fns if isinstance(fns, dict) else {}
        docs[file.name] = pd
    if entry_file is None:
        entry_file = next((n for n in ENTRY_CANDIDATES if n in docs), None)
        if entry_file is None and len(docs) == 1:
            entry_file = next(iter(docs))
    if entry_file is None or entry_file not in docs:
        raise ProgramError("PROGRAM_INVALID",
                           f"no entry program in {directory}: tried {list(ENTRY_CANDIDATES)} / explicit / single file; parseable={sorted(docs)}")
    fm, has_md = {}, False
    if 'AIAP.md' in raw_files:
        has_md = True
        try:
            fm, _ = aiap_md.parse_frontmatter(raw_files['AIAP.md'].decode('utf-8-sig'))
        except (aiap_md.FrontmatterError, UnicodeError):
            fm = {"__unparseable__": True}
    return Program(dir=directory, entry_file=entry_file, docs=docs, skipped=skipped, frontmatter=fm, has_aiap_md=has_md)


def registry_snapshot(registry_root: str | Path) -> list[dict]:
    """Packages under a registry root: directories with an entry file (used by Router.match)."""
    root = Path(registry_root)
    out = []
    if not root.is_dir():
        return out
    for child in sorted(root.iterdir(), key=lambda p: p.name):
        if not child.is_dir():
            continue
        entry = next((n for n in ENTRY_CANDIDATES if (child / n).exists()), None)
        if entry:
            out.append({"package": child.name, "entry_file": entry, "dir": str(child)})
    return out


# ---------------------------------------------------------------------------
# analysis (load checks + doc 02 §2.2 scans)
# ---------------------------------------------------------------------------

def _protocol_version(value) -> tuple:
    m = re.search(r"V(\d+)\.(\d+)\.(\d+)", str(value or ""))
    return tuple(int(x) for x in m.groups()) if m else (0,)


def resolve_module(program: Program, doc_name: str, target: str) -> dict | None:
    """Resolve a module target (doc 05 §4.1) to a sub-graph of the same program.

    Order: a task named <target> in the same document; a document <target>.aisop.json (its main task);
    a document literally named <target> (label form X.aisop.json). None when nothing matches.
    Returns {doc, task, entry_node, ns} where ns is the cache namespace (doc stem or task name).
    """
    if not target:
        return None
    target, _, entry_override = target.partition("::")   # doc 12 §1.7: "X.aisop.json::Entry" enters the sub-document at Entry
    same = program.docs.get(doc_name)
    if same and target in same.tasks:
        parsed = same.tasks[target]
        entry = aisop_parse.entry_nodes(parsed)
        return {"doc": doc_name, "task": target, "entry_node": _entry_of(parsed, entry, entry_override), "ns": target}
    for candidate in (f"{target}.aisop.json", target):
        pd = program.docs.get(candidate)
        if pd and "main" in pd.tasks:
            if entry_override.startswith('task_') and entry_override not in pd.tasks['main']['nodes']:
                if entry_override not in pd.tasks:
                    raise ProgramError('MODULE_TASK_UNRESOLVED', f'{candidate} does not declare {entry_override}; no main-task fallback.')
                selected = pd.tasks[entry_override]
                stem = candidate[: -len('.aisop.json')] if candidate.endswith('.aisop.json') else candidate
                return {'doc': candidate, 'task': entry_override, 'entry_node': _entry_of(selected, aisop_parse.entry_nodes(selected), ''),
                        'ns': stem + '.' + entry_override}
            parsed = pd.tasks["main"]
            entry = aisop_parse.entry_nodes(parsed)
            stem = candidate[: -len(".aisop.json")] if candidate.endswith(".aisop.json") else candidate
            return {"doc": candidate, "task": "main", "entry_node": _entry_of(parsed, entry, entry_override), "ns": stem}
    return None


def _entry_of(parsed: dict, entry: list, override: str) -> str | None:
    if override and override in parsed.get("nodes", {}):
        return override
    return entry[0] if entry else None


def module_target(program: Program, doc_name: str, task: str, node: str) -> str | None:
    """The module target a node opens: its [aisop.x] / [x.aisop.json] label, else its first RUN aisop.<x> step, else
    (doc 12 §1.7) its first step whose work part starts with `Delegate to X.aisop.json` / `委托 X.aisop.json` where
    X.aisop.json is a document of this program (an optional `::Entry` names the sub-document node to enter at)."""
    pd = program.docs[doc_name]
    parsed = pd.tasks.get(task) or {}
    label_target = (parsed.get("nodes", {}).get(node) or {}).get("delegate_to")
    if label_target:
        return label_target
    fn = pd.functions.get(node)
    if isinstance(fn, dict):
        try:
            described = [aisop_parse.describe_step(step["key"], step["text"]) for step in aisop_parse.split_function(fn)["steps"]]
        except aisop_parse.AisopFormatError:
            return None  # analyze records the fatal error; invalid work is not a delegation.
        for d in described:
            if d["sub_task"]:
                return d["sub_task"]
        for d in described:
            if d.get("delegate_file") and d["delegate_file"].split("::")[0] in program.docs:
                return d["delegate_file"]
    return None


def delegate_closure(program: Program) -> dict:
    """Task-level module graph over all documents (R-16). Keys are 'doc:task'.

    Cycles are reported (a sub-graph may reference itself; termination is the graph's own decision
    nodes, doc 05 §4.2) and depth is measured, but neither is a load failure: AIAP §17.3's limit is
    for cross-program calls (P7)."""
    edges: dict[str, set[str]] = {}
    unresolved: set[str] = set()
    for dname, pd in program.docs.items():
        for tname, parsed in pd.tasks.items():
            key = f"{dname}:{tname}"
            targets: set[str] = set()
            for node in parsed["nodes"]:
                target = module_target(program, dname, tname, node)
                if not target:
                    continue
                resolved = resolve_module(program, dname, target)
                if resolved is None:
                    unresolved.add(f"{dname}:{node} -> {target}")
                else:
                    targets.add(f"{resolved['doc']}:{resolved['task']}")
            edges[key] = targets
    cycles, max_depth = [], 0

    def dfs(node, path):
        nonlocal max_depth
        if node in path:
            cycles.append(path[path.index(node):] + [node])
            return
        max_depth = max(max_depth, len(path))
        for nxt in sorted(edges.get(node, ())):
            dfs(nxt, path + [node])

    root = f"{program.entry_file}:main"
    if root in edges:
        dfs(root, [])
    return {"edges": {k: sorted(v) for k, v in edges.items()}, "max_depth": max_depth,
            "cycles": cycles, "unresolved_targets": sorted(unresolved)}


def analyze(program: Program, supported_protocol: str = SUPPORTED_PROTOCOL) -> dict:
    findings: list[dict] = []
    entry = program.entry
    declared_dispatch = entry.system.get('dispatch_requirements')
    if isinstance(declared_dispatch, dict) and 'execution_semantics' in declared_dispatch:
        findings.append(dict(code='EXECUTION_SEMANTICS_REMOVED', severity='WARN',
            detail='Obsolete execution_semantics is ignored; loading_mode and main-node execute_mode determine ownership.'))
    if program.entry_file != "main.aisop.json":
        findings.append({"code": "ENTRY_FILE", "severity": "INFO", "detail": f"entry file {program.entry_file} (not main.aisop.json)"})

    # R-01 structure
    problems = aisop_parse.validate_document(entry.doc)
    if entry.doc["shape"] == "single_object":
        findings.append({"code": "SINGLE_OBJECT_SHAPE", "severity": "WARN", "detail": "legacy single-object file (AIAP repo examples); executed with tolerance (I-15)"})
    for p in problems:
        if p in SOFT_STRUCTURE_PROBLEMS:
            findings.append({"code": p, "severity": "WARN", "detail": f"{program.entry_file}: {p} (protocol default applies, I-14)"})
    fatal = [p for p in problems if p not in SOFT_STRUCTURE_PROBLEMS]
    if fatal:
        findings.append({"code": "PROGRAM_INVALID", "severity": "FATAL", "detail": f"{program.entry_file}: {fatal}"})
    variant = aisop_parse.instruction_variant(entry.user.get("instruction"))
    if variant == "invalid":
        findings.append({"code": "PROGRAM_INVALID", "severity": "FATAL", "detail": "instruction lacks 'RUN aisop.main' (I-04)"})
    elif variant != "aiap_canonical":
        findings.append({"code": "INSTRUCTION_VARIANT", "severity": "INFO", "detail": f"instruction variant {variant} accepted (I-04)"})

    # R-05 load checks
    fm = program.frontmatter
    if not program.has_aiap_md:
        findings.append({"code": "AIAP_MD_ABSENT", "severity": "INFO", "detail": "no AIAP.md; trust defaults to T3, permissions undeclared (I-11)"})
    elif fm.get("__unparseable__"):
        findings.append({"code": "AIAP_MD_UNPARSEABLE", "severity": "WARN", "detail": "AIAP.md frontmatter could not be parsed; treated as absent"})
    mpv = fm.get("min_protocol_version")
    if mpv and _protocol_version(mpv) > _protocol_version(supported_protocol):
        findings.append({"code": "PROTOCOL_VERSION_UNSUPPORTED", "severity": "FATAL", "detail": f"min_protocol_version {mpv} > executor {supported_protocol}"})
    if fm.get("status") == "archived":
        findings.append({"code": "PROGRAM_ARCHIVED", "severity": "WARN", "detail": f"archived; successor={fm.get('successor')!r}"})
    trust = program.trust_level
    if trust is None:
        findings.append({"code": "TRUST_LEVEL_INVALID", "severity": "FATAL", "detail": f"trust_level={fm.get('trust_level', entry.system.get('trust_level'))!r}"})
    elif trust == 4 and program.permissions is None:
        findings.append({"code": "T4_WITHOUT_PERMISSIONS", "severity": "FATAL", "detail": "T4 program must declare permissions (§16.4, §17)"})
    for name, pd in program.docs.items():
        if "trust_level" in pd.system and not name.startswith(("AIAP_Standard", "AISP_Standard")):
            if aiap_md.normalize_trust_level(pd.system["trust_level"]) != trust:
                findings.append({"code": "TRUST_LEVEL_DRIFT", "severity": "WARN", "detail": f"{name} trust {pd.system['trust_level']!r} vs program {trust!r}"})

    # scans
    counts = {"files": len(program.docs), "skipped": len(program.skipped), "tasks": 0, "nodes": 0, "functional_nodes": 0,
              "functions": 0, "assert_steps": 0, "sys_calls": {}, "reserved_keys": {}, "extra_keys": {},
              "execute_mode": {}, "run_aisop_steps": 0, "mixed_steps": 0, "odd_step_keys": [],
              "gate_sources": {"sys_io_call": 0, "user_gate": 0, "advisory_text": 0},
              "instruction_variants": {}, "loading_modes": {}, "topology": {}}
    multi_candidates, gates_detail = [], []
    for fname, pd in program.docs.items():
        v = aisop_parse.instruction_variant(pd.user.get("instruction")) if "instruction" in pd.user else "absent"
        counts["instruction_variants"][v] = counts["instruction_variants"].get(v, 0) + 1
        lm = str(pd.system.get("loading_mode"))
        counts["loading_modes"][lm] = counts["loading_modes"].get(lm, 0) + 1
        counts["tasks"] += len(pd.tasks)
        for tname, parsed in pd.tasks.items():
            s = aisop_parse.graph_summary(parsed)
            for k in ("forks", "joins", "error_edges", "delegates", "decisions", "branch_edges", "loops"):
                counts["topology"][k] = counts["topology"].get(k, 0) + s[k]
            counts["nodes"] += s["nodes"]
            counts["functional_nodes"] += s["functional_nodes"]
            for name in parsed["nodes"]:
                cands = aisop_parse.next_candidates(parsed, name)
                if len(cands) > 1:
                    multi_candidates.append({"file": fname, "task": tname, "node": name, "candidates": cands})
        counts["functions"] += len(pd.functions)
        for name, fn in pd.functions.items():
            try:
                desc = aisop_parse.describe_function(name, fn)
            except aisop_parse.AisopFormatError as exc:
                findings.append({"code": "HUMAN_IO_CALL_INVALID", "severity": "FATAL", "detail": f"{fname}:{name}: {exc}"})
                continue
            for key in desc["unsupported_reserved"]:
                findings.append({"code": "UNSUPPORTED_RESERVED_KEY", "severity": "FATAL", "detail": f"{fname}:{name} uses {key} (R-14)"})
            from . import bounded_retry
            retry_error = bounded_retry.policy_error(desc['reserved'], name)
            if retry_error:
                findings.append({'code': 'BOUNDED_RETRY_POLICY_INVALID', 'severity': 'FATAL',
                                 'detail': f'{fname}:{name}: {retry_error}'})
            for key in desc["reserved"]:
                counts["reserved_keys"][key] = counts["reserved_keys"].get(key, 0) + 1
            for key in desc["extra"]:
                counts["extra_keys"][key] = counts["extra_keys"].get(key, 0) + 1
            em = desc["reserved"].get("execute_mode")
            if em is not None:
                counts["execute_mode"][str(em)] = counts["execute_mode"].get(str(em), 0) + 1
            if "EXECUTE_MODE_UNKNOWN" in desc["problems"]:
                findings.append({"code": "EXECUTE_MODE_UNKNOWN", "severity": "WARN", "detail": f"{fname}:{name} execute_mode={em!r} -> inline (AISOP §5.2.8)"})
            for step in desc["steps"]:
                if aisop_parse.STEP_KEY_RE.match(step["key"]).group(2):
                    counts["odd_step_keys"].append(step["key"])
                if step["mode"] == "assert_prefixed":
                    counts["assert_steps"] += 1
                if step["sub_task"]:
                    counts["run_aisop_steps"] += 1
                if step["mixed"]:
                    counts["mixed_steps"] += 1
                sysc = step["sys"]
                if sysc:
                    counts["sys_calls"][sysc["name"]] = counts["sys_calls"].get(sysc["name"], 0) + 1
                    if not sysc["valid"]:
                        findings.append({"code": "SYS_CALL_UNKNOWN", "severity": "WARN", "detail": f"{fname}:{name}:{step['key']} {sysc['name']}"})
            for gate in desc["gate_sources"]:
                counts["gate_sources"][gate["source"]] += 1
                gates_detail.append({"file": fname, "function": name, **gate})
    counts["odd_step_keys"] = sorted(set(counts["odd_step_keys"]))

    closure = delegate_closure(program)
    for cyc in closure["cycles"]:
        findings.append({"code": "CIRCULAR_DEPENDENCY", "severity": "WARN",
                         "detail": " -> ".join(cyc) + " (module cycle inside one program: allowed, terminates through the graph's decision nodes)"})
    if closure["unresolved_targets"]:
        findings.append({"code": "MODULE_TARGET_UNRESOLVED", "severity": "WARN",
                         "detail": f"module targets without a sub-graph in this program: {closure['unresolved_targets']} (executed as plain nodes)"})

    return {"findings": findings, "fatal_count": sum(1 for f in findings if f["severity"] == "FATAL"),
            "trust_level": trust, "counts": counts, "multi_candidates": multi_candidates,
            "gate_sources": gates_detail, "delegate_closure": closure, "skipped_files": list(program.skipped)}


# ---------------------------------------------------------------------------
# catalog (Router.cache-setup) and node views (next-node)
# ---------------------------------------------------------------------------

def compile_outer_path(program: Program, outer_nodes_in_path: list, *, report_node: str = "Engine.execute-report") -> list[dict]:
    """Ordered catalog: engine match/setup, the outer business nodes, engine summary.

    Raises ProgramError(PATH_INVALID, ...) when the path is empty, has duplicates, names unknown
    nodes, includes end nodes, or is not a walk through the entry task's main graph.
    """
    main = program.entry.tasks.get("main")
    if main is None:
        raise ProgramError("PROGRAM_INVALID", "entry document has no parseable main task")
    if not isinstance(outer_nodes_in_path, list) or not outer_nodes_in_path:
        raise ProgramError("PATH_INVALID", "outer_nodes_in_path must be a non-empty list of node names")
    if len(set(outer_nodes_in_path)) != len(outer_nodes_in_path):
        raise ProgramError("PATH_INVALID", "outer_nodes_in_path contains duplicates")
    for name in outer_nodes_in_path:
        if name not in main["nodes"]:
            raise ProgramError("PATH_INVALID", f"{name!r} is not a node of the main graph; nodes={list(main['nodes'])}")
        if main["node_types"].get(name) == "end":
            raise ProgramError("PATH_INVALID", f"{name!r} is an end node; end nodes are implicit")
    for a, b in zip(outer_nodes_in_path, outer_nodes_in_path[1:]):
        if not any(e["src"] == a and e["dst"] == b for e in main["edges"]):
            raise ProgramError("PATH_INVALID", f"no edge {a} -> {b} in the main graph; the path must follow graph edges")
    catalog = [engine_entry("Router.match", 0), engine_entry("Router.cache-setup", 1)]
    for i, name in enumerate(outer_nodes_in_path, start=2):
        catalog.append(business_entry(name, i))
    catalog.append(engine_entry(report_node, len(catalog)))
    if report_node in ("Engine.execute-report", "Router.report"):   # alpha.45: the answer node follows the report node
        catalog.append(engine_entry("final" if report_node == "Router.report" else "Engine.final-answer", len(catalog)))
    return catalog


def engine_entry(name: str, ordinal: int) -> dict:
    return {"name": name, "kind": "engine", "ordinal": ordinal, "parent": None, "depth": 0, "task": None, "doc": None, "node": None}


def business_entry(name: str, ordinal: int) -> dict:
    return {"name": name, "kind": "business", "ordinal": ordinal, "parent": None, "depth": 0, "task": "main", "doc": None, "node": name}


def sub_entry(parent_id: str, depth: int, doc: str, task: str, ns: str, node: str, ordinal: int) -> dict:
    """Catalog entry of a sub-graph node: qualified id Parent/ns.Node (doc 05 §4.3)."""
    return {"name": f"{parent_id}/{ns}.{node}", "kind": "sub", "ordinal": ordinal, "parent": parent_id, "depth": depth,
            "task": task, "doc": doc, "node": node}


def node_view(program: Program, node: str, task: str = "main", doc_name: str | None = None) -> dict:
    """Everything next-node needs about one program node: classified steps, reserved keys,
    extra keys, gate sources, topology (I-02 candidates, branches, error target, predecessors),
    and the module sub-graph the node opens (doc 05 §4.1), if any."""
    pd = program.docs[doc_name] if doc_name else program.entry
    parsed = pd.tasks.get(task)
    if parsed is None or node not in parsed["nodes"]:
        raise ProgramError("NODE_UNKNOWN", f"{node!r} not in task {task!r} of {pd.name}")
    fn = pd.functions.get(node)
    try:
        described = aisop_parse.describe_function(node, fn if isinstance(fn, dict) else {})
    except aisop_parse.AisopFormatError as exc:
        raise ProgramError("PROGRAM_INVALID", f"{pd.name}:{node}: {exc}") from exc
    nd = parsed["nodes"][node]
    preds = aisop_parse.predecessors(parsed).get(node, [])
    target = module_target(program, pd.name, task, node)
    module = resolve_module(program, pd.name, target) if target else None
    return {
        "node": node, "task": task, "file": pd.name,
        "type": parsed["node_types"].get(node), "label": parsed["node_labels"].get(node),
        "steps": described["steps"], "reserved": described["reserved"], "extra": described["extra"],
        "gate_sources": described["gate_sources"], "problems": described["problems"],
        "unsupported_reserved": described["unsupported_reserved"],
        "module": dict(module, target=target) if module else None,
        "module_unresolved": target if (target and module is None) else None,
        "topology": {
            "next_candidates": list(nd.get("next", [])),
            "branches": dict(nd.get("branches", {})),
            "error_target": nd.get("error"),
            "delegate_to": nd.get("delegate_to"),
            "is_end": parsed["node_types"].get(node) == "end",
            "predecessors": preds,
            "primary_predecessor": preds[0] if preds else None,
        },
    }

"""AISOP V1.0.0 document parsing for soulrun_aiap V1.0.0.

Own implementation written from the specifications. No code is taken from the v6 engine.

References
  AISOP V1.0.0 spec   §1 file shape, §4.2 Mermaid, §4.3 JSON flow, §5.2 reserved keys,
                      §5.3 step classification, §6 sys.*, §6.9 -> variables, §6.11 expressions
  AIAP V1.0.0 spec    Appendix F ([ASSERT] Node Gate), Appendix G.9 (one-step-one-mode)
  04 series doc 02    I-01 step keys, I-02 next candidates, I-03 gate sources, I-04 instruction
                      variants, I-05 end node by shape, I-07 skipped files
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from . import delivery_obligations

AXIOM_0 = "Human_Sovereignty_and_Wellbeing"
FLOW_FORMATS = ("mermaid", "jsonflow", "hybrid")
LOADING_MODES = ("normal", "node", "lite")
EXECUTE_MODES = ("inline", "agent")
INSTRUCTION_CANONICAL = "ASSERT RUN aisop.main"
INSTRUCTION_CORE = "RUN aisop.main"

RESERVED_KEYS = frozenset({
    "join", "map", "on_error", "retry_policy", "context_filter",
    "output_mapping", "constraints", "execute_mode",
})
# 02 号 D6 / R-14: zero hits in registered programs, rejected early at cache-setup.
UNSUPPORTED_RESERVED_KEYS = frozenset({"map", "join", "context_filter"})

VALID_SYS_CALLS = frozenset({
    "sys.io.confirm", "sys.io.input", "sys.io.select", "sys.io.notify", "sys.io.print",
    "sys.io.read", "sys.io.write",
    "sys.run", "sys.run.timeout", "sys.run.bg",
    "sys.assert",
    "sys.llm", "sys.llm.json", "sys.llm.classify",
    "sys.code.exec", "sys.code.eval",
    "sys.state.get", "sys.state.set", "sys.state.save", "sys.state.load",
    "sys.event.emit", "sys.event.wait",
    "sys.security.audit", "sys.security.redact",
})
FORCED_BLOCKING_CALLS = frozenset({"sys.io.confirm", "sys.io.input", "sys.io.select"})
NON_RETRYABLE_CALLS = frozenset({"sys.io.confirm", "sys.io.input", "sys.io.select", "sys.assert"})
SYS_ERROR_TYPES = frozenset({
    "confirm_rejected", "confirm_timeout", "assertion_error",
    "command_error", "command_timeout", "io_error",
})

STEP_KEY_RE = re.compile(r"^step(\d+)(?:_([A-Za-z0-9]+))?$")
SYS_CALL_RE = re.compile(
    r"^(sys(?:\.[a-z_]+){1,3})\((.*)\)\s*(?:->\s*([A-Za-z_][A-Za-z0-9_]*))?\s*$", re.S
)
HUMAN_IO_PREFIX_RE = re.compile(r"^sys\.io\.(confirm|input|select)(?![A-Za-z0-9_.])")
SUB_TASK_RE = re.compile(r"^RUN\s+aisop\.([A-Za-z_][A-Za-z0-9_]*)\s*$")
EMBEDDED_SYS_RE = re.compile(
    r"\bsys\.(?:io|run|assert|llm|code|state|event|security)\b(?:\.[a-z_]+)*\s*\("
)
CONFIRM_TEXT_RE = re.compile(r"sys\.io\.confirm\(\s*(['\"])(.*?)\1", re.S)
HIGH_RISK_RUN_RE = re.compile(
    r"(\brm\s+-[rf]{1,2}\b|\bdel\b|\brmdir\b|\bDROP\b|\bDELETE\b|\bTRUNCATE\b|\bshutdown\b"
    r"|\breboot\b|\bkill\b|\bchmod\b|\bchown\b|\bicacls\b|git\s+push\s+--force|git\s+reset\s+--hard)",
    re.I,
)
FIRST_STRING_ARG_RE = re.compile(r"^\s*(['\"])((?:\\.|(?!\1).)*)\1", re.S)


class AisopFormatError(ValueError):
    """The document is not an AISOP program (or is a non-executable reference file)."""


class ExpressionError(ValueError):
    """Invalid or unevaluable §6.11 expression."""


# ---------------------------------------------------------------------------
# Document shape (AISOP §1–§3)
# ---------------------------------------------------------------------------

def load_aisop(path: str | Path) -> dict:
    """Load and shape-parse an .aisop.json file. Raises AisopFormatError on non-programs."""
    data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    doc = parse_aisop_document(data)
    doc["path"] = str(path)
    return doc


def parse_aisop_document(data) -> dict:
    """Return {"shape", "system", "user", "problems"}.

    shape "array2"        AISOP §1 canonical: [ {role: system}, {role: user} ]
    shape "single_object" legacy shape used by the AIAP repository examples
                          ({role: system, content: {... instruction, aisop, functions}})
    """
    problems: list[str] = []
    if isinstance(data, list):
        if len(data) != 2:
            raise AisopFormatError("AISOP file must be a JSON array with exactly 2 elements")
        sys_e, usr_e = data
        if not isinstance(sys_e, dict) or sys_e.get("role") != "system":
            raise AisopFormatError("first element must have role='system'")
        if not isinstance(usr_e, dict) or usr_e.get("role") != "user":
            raise AisopFormatError("second element must have role='user'")
        return {
            "shape": "array2",
            "system": sys_e.get("content") if isinstance(sys_e.get("content"), dict) else {},
            "user": usr_e.get("content") if isinstance(usr_e.get("content"), dict) else {},
            "problems": problems,
        }
    if isinstance(data, dict):
        content = data.get("content") if data.get("role") == "system" else None
        if isinstance(content, dict) and "aisop" in content:
            user_keys = ("instruction", "user_input", "aisop", "functions")
            user = {k: content[k] for k in user_keys if k in content}
            system = {k: v for k, v in content.items() if k not in user_keys}
            problems.append("SINGLE_OBJECT_SHAPE")
            return {"shape": "single_object", "system": system, "user": user, "problems": problems}
    raise AisopFormatError("unrecognized AISOP document shape")


def validate_document(doc: dict) -> list[str]:
    """Required-field validation (AISOP §2, §3). Returns a list of problem codes; empty = valid."""
    problems: list[str] = []
    system, user = doc.get("system") or {}, doc.get("user") or {}
    for field in ("protocol", "axiom_0", "id", "name", "version", "flow_format"):
        if field not in system:
            problems.append(f"SYSTEM_MISSING_{field.upper()}")
    if "axiom_0" in system and system.get("axiom_0") != AXIOM_0:
        problems.append("AXIOM_0_INVALID")
    if "flow_format" in system and system.get("flow_format") not in FLOW_FORMATS:
        problems.append("FLOW_FORMAT_INVALID")
    if "loading_mode" in system and system.get("loading_mode") not in LOADING_MODES:
        problems.append("LOADING_MODE_INVALID")
    for field in ("instruction", "aisop", "functions"):
        if field not in user:
            problems.append(f"USER_MISSING_{field.upper()}")
    instruction = user.get("instruction")
    if isinstance(instruction, str):
        if INSTRUCTION_CORE not in instruction:
            problems.append("INSTRUCTION_MISSING_RUN_MAIN")
    elif "instruction" in user:
        problems.append("INSTRUCTION_NOT_STRING")
    aisop = user.get("aisop")
    if isinstance(aisop, dict):
        if "main" not in aisop:
            problems.append("AISOP_MISSING_MAIN")
        for task_name, body in aisop.items():
            if isinstance(body, str):
                if not parse_mermaid(body)["nodes"]:
                    problems.append(f"TASK_NO_NODES:{task_name}")
            elif isinstance(body, dict):
                if not body:
                    problems.append(f"TASK_EMPTY:{task_name}")
            else:
                problems.append(f"TASK_TYPE_INVALID:{task_name}")
    elif "aisop" in user:
        problems.append("AISOP_NOT_OBJECT")
    if "functions" in user and not isinstance(user.get("functions"), dict):
        problems.append("FUNCTIONS_NOT_OBJECT")
    return problems


def instruction_variant(instruction) -> str:
    """I-04: canonical AIAP constant / AISOP core / custom prefix containing the core / invalid."""
    if not isinstance(instruction, str):
        return "invalid"
    s = instruction.strip()
    if s == INSTRUCTION_CANONICAL:
        return "aiap_canonical"
    if s == INSTRUCTION_CORE:
        return "aisop_core"
    if INSTRUCTION_CORE in s:
        return "custom_prefix"
    return "invalid"


# ---------------------------------------------------------------------------
# Mermaid (AISOP §4.2)
# ---------------------------------------------------------------------------

_EDGE_SPLIT_RE = re.compile(
    r"\s*("
    r"-->\|[^|]*\|"          # -->|label|
    r"|-\.->\|[^|]*\|"       # -.->|label|
    r"|--\s+[^>]*?\s+-->"    # -- label -->
    r"|-\.\s+[^>]*?\s+\.->"  # -. label .->
    r"|-->"
    r"|-\.->"
    r")\s*"
)
_SKIP_LINE_RE = re.compile(
    r"^(graph\b|flowchart\b|%%|subgraph\b|end\s*$|classDef\b|class\b|style\b|linkStyle\b|click\b|direction\b)"
)
_NODE_PATTERNS = (
    (re.compile(r"^(\w+)\(\((.+)\)\)$", re.S), "end"),
    (re.compile(r"^(\w+)\(\[(.+)\]\)$", re.S), "process"),   # stadium
    (re.compile(r"^(\w+)\[\((.+)\)\]$", re.S), "process"),   # cylinder
    (re.compile(r"^(\w+)\{\{(.+)\}\}$", re.S), "process"),   # hexagon
    (re.compile(r"^(\w+)\{(.+)\}$", re.S), "decision"),
    (re.compile(r"^(\w+)\[(.+)\]$", re.S), "process"),
    (re.compile(r"^(\w+)\((.+)\)$", re.S), "process"),       # round edges
)
_PLAIN_NODE_RE = re.compile(r"^(\w+)$")
# Module node labels (doc 05 §4.1): [aisop.<task>] (AISOP §5.2.1) or [<name>.aisop.json] (module file of the
# same program, as used by soulbot_stock_analyzer: DelegateAnalysis[analysis.aisop.json]).
_MODULE_FILE_LABEL_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]*\.aisop\.json$")


def module_target_of_label(label: str) -> str | None:
    """Sub-graph target named by a node label, or None for an ordinary label."""
    s = (label or "").strip()
    if s.startswith("aisop.") and len(s) > len("aisop."):
        return s[len("aisop."):]
    if _MODULE_FILE_LABEL_RE.match(s):
        return s
    return None


def _edge_kind_and_label(token: str) -> tuple[str, str | None]:
    t = token.strip()
    kind = "error" if t.startswith("-.") else "next"
    label = None
    m = re.match(r"^(?:-->|-\.->)\|(.*)\|$", t, re.S)
    if m:
        label = m.group(1).strip()
    else:
        m = re.match(r"^--\s+(.*?)\s+-->$", t, re.S) or re.match(r"^-\.\s+(.*?)\s+\.->$", t, re.S)
        if m:
            label = m.group(1).strip()
    if kind == "next" and label:
        kind = "branch"
    return kind, label


def _register_node(text: str, parsed: dict) -> str | None:
    text = text.strip().rstrip(";").strip()
    if not text:
        return None
    for pattern, ntype in _NODE_PATTERNS:
        m = pattern.match(text)
        if m:
            name, label = m.group(1), m.group(2).strip()
            target = module_target_of_label(label) if ntype == "process" else None
            if target:
                ntype = "delegate"
                parsed["delegate_targets"][name] = target
            parsed["node_types"][name] = ntype
            parsed["node_labels"][name] = label
            _touch(parsed, name)
            return name
    m = _PLAIN_NODE_RE.match(text)
    if m:
        _touch(parsed, m.group(1))
        return m.group(1)
    return None


def _touch(parsed: dict, name: str) -> None:
    if name not in parsed["nodes"]:
        parsed["nodes"][name] = {}
        parsed["order"].append(name)


def parse_mermaid(mermaid: str) -> dict:
    """Parse a Mermaid flowchart into a structured graph.

    Returns {"nodes": {name: {next: [], branches: {}, error: str, delegate_to: str}},
             "node_types": {name: process|decision|end|delegate},
             "node_labels": {name: label}, "order": [first-appearance order],
             "edges": [{"src","kind","label","dst"}], "delegate_targets": {name: sub}}
    """
    parsed = {"nodes": {}, "node_types": {}, "node_labels": {}, "order": [],
              "edges": [], "delegate_targets": {}}
    for raw in mermaid.splitlines():
        line = raw.strip()
        if not line or _SKIP_LINE_RE.match(line):
            continue
        parts = _EDGE_SPLIT_RE.split(line)
        if len(parts) < 3:
            _register_node(parts[0], parsed)
            continue
        for i in range(0, len(parts) - 2, 2):
            src = _register_node(parts[i], parsed)
            dst = _register_node(parts[i + 2], parsed)
            if not src or not dst:
                continue
            kind, label = _edge_kind_and_label(parts[i + 1])
            node = parsed["nodes"][src]
            if kind == "error":
                node["error"] = dst
            elif kind == "branch":
                node.setdefault("branches", {})[label] = dst
            else:
                nxt = node.setdefault("next", [])
                if dst not in nxt:
                    nxt.append(dst)
            parsed["edges"].append({"src": src, "kind": kind, "label": label, "dst": dst})
    for name, target in parsed["delegate_targets"].items():
        parsed["nodes"][name]["delegate_to"] = target
    for name in parsed["nodes"]:
        parsed["node_types"].setdefault(name, infer_node_type(parsed["nodes"][name]))
    return parsed


def infer_node_type(node: dict) -> str:
    """AISOP §4.3.2 priority: {} end > branches decision > delegate_to > wait_for join > fork > process."""
    if not node:
        return "end"
    if "branches" in node:
        return "decision"
    if "delegate_to" in node:
        return "delegate"
    if "wait_for" in node:
        return "join"
    if "next" in node:
        return "fork" if len(node["next"]) > 1 else "process"
    return "end"


def parse_jsonflow(flow: dict) -> dict:
    """Parse an AISOP §4.3 JSON flow object into the same structure as parse_mermaid."""
    parsed = {"nodes": {}, "node_types": {}, "node_labels": {}, "order": [],
              "edges": [], "delegate_targets": {}}
    for name, node in flow.items():
        _touch(parsed, name)
        copy = {}
        for key in ("next", "branches", "error", "delegate_to", "wait_for"):
            if key in node:
                copy[key] = node[key]
        parsed["nodes"][name] = copy
        parsed["node_labels"][name] = name
        if "delegate_to" in copy:
            parsed["delegate_targets"][name] = copy["delegate_to"]
        for dst in copy.get("next", []):
            _touch(parsed, dst)
            parsed["edges"].append({"src": name, "kind": "next", "label": None, "dst": dst})
        for label, dst in copy.get("branches", {}).items():
            _touch(parsed, dst)
            parsed["edges"].append({"src": name, "kind": "branch", "label": label, "dst": dst})
        if "error" in copy:
            _touch(parsed, copy["error"])
            parsed["edges"].append({"src": name, "kind": "error", "label": None, "dst": copy["error"]})
    for name in parsed["nodes"]:
        parsed["node_types"][name] = infer_node_type(parsed["nodes"][name])
    return parsed


def parse_task(body) -> dict:
    """Dispatch on task body type: Mermaid string or JSON flow object."""
    if isinstance(body, str):
        return parse_mermaid(body)
    if isinstance(body, dict):
        return parse_jsonflow(body)
    raise AisopFormatError(f"task body must be str or dict, got {type(body).__name__}")


def predecessors(parsed: dict) -> dict[str, list[str]]:
    """Incoming sources per node over all edge kinds, in edge declaration order."""
    result: dict[str, list[str]] = {name: [] for name in parsed["nodes"]}
    for edge in parsed["edges"]:
        if edge["src"] not in result[edge["dst"]]:
            result[edge["dst"]].append(edge["src"])
    return result


def entry_nodes(parsed: dict) -> list[str]:
    """Nodes with no incoming edge; falls back to the first declared node (AISOP §4.1)."""
    preds = predecessors(parsed)
    found = [n for n in parsed["order"] if not preds[n]]
    return found or parsed["order"][:1]


def next_candidates(parsed: dict, name: str) -> list[str]:
    """I-02: unlabeled successors of a node (candidate successors, not a parallel fork)."""
    return list(parsed["nodes"].get(name, {}).get("next", []))


def loop_edges(parsed: dict) -> list[dict]:
    """Back edges of a DFS started at the entry nodes (one edge per loop-back), all edge kinds."""
    white, gray, black = 0, 1, 2
    color = {n: white for n in parsed["nodes"]}
    outgoing: dict[str, list[dict]] = {n: [] for n in parsed["nodes"]}
    for edge in parsed["edges"]:
        outgoing[edge["src"]].append(edge)
    back: list[dict] = []

    def visit(u: str) -> None:
        color[u] = gray
        for edge in outgoing[u]:
            v = edge["dst"]
            if color[v] == gray:
                back.append(edge)
            elif color[v] == white:
                visit(v)
        color[u] = black

    for start in entry_nodes(parsed) + parsed["order"]:
        if color[start] == white:
            visit(start)
    return back


def graph_summary(parsed: dict) -> dict:
    """Topology counts used by the conformance tool and doc 02 §2.2.

    loops = DFS back edges from the entry nodes (declaration order plays no role).
    """
    preds = predecessors(parsed)
    types = parsed["node_types"]
    summary = {
        "nodes": len(parsed["nodes"]),
        "functional_nodes": sum(1 for n in parsed["nodes"] if types.get(n) != "end"),
        "forks": 0, "joins": 0, "error_edges": 0, "delegates": 0,
        "decisions": 0, "branch_edges": 0, "loops": 0,
        "end_nodes": [n for n in parsed["order"] if types.get(n) == "end"],
        "entry_nodes": entry_nodes(parsed),
    }
    for name, node in parsed["nodes"].items():
        if len(node.get("next", [])) > 1:
            summary["forks"] += 1
        if "error" in node:
            summary["error_edges"] += 1
        if "delegate_to" in node:
            summary["delegates"] += 1
        if "branches" in node:
            summary["decisions"] += 1
            summary["branch_edges"] += len(node["branches"])
    summary["loops"] = len(loop_edges(parsed))
    summary["joins"] = sum(1 for n, p in preds.items() if len(p) > 1 and types.get(n) != "end")
    return summary


# ---------------------------------------------------------------------------
# Functions and steps (AISOP §5, AIAP Appendix F/G; doc 02 I-01/I-03)
# ---------------------------------------------------------------------------

def _suffix_sort_key(suffix: str | None) -> tuple:
    if suffix is None:
        return (0, 0, "")
    if suffix.isdigit():
        return (1, int(suffix), "")
    return (2, 0, suffix)


def split_function(func: dict) -> dict:
    """I-01: step keys = ^step\\d+(_suffix)?$ ordered numerically; reserved keys; extra keys passthrough."""
    steps, reserved, extra = [], {}, {}
    for key, value in func.items():
        m = STEP_KEY_RE.match(key)
        if m:
            steps.append((int(m.group(1)), _suffix_sort_key(m.group(2)), key, value))
        elif key in RESERVED_KEYS:
            reserved[key] = value
        else:
            extra[key] = value
    steps.sort(key=lambda t: (t[0], t[1]))
    return {
        "steps": [{"key": k, "text": v} for _, _, k, v in steps],
        "reserved": reserved,
        "extra": extra,
        "unsupported_reserved": sorted(set(reserved) & UNSUPPORTED_RESERVED_KEYS),
    }


def classify_step(text) -> str:
    """AISOP §5.3 three modes plus the AIAP [ASSERT] prefix (exempt from one-step-one-mode)."""
    if not isinstance(text, str):
        return "non_string"
    s = text.strip()
    if s.startswith("[ASSERT]"):
        return "assert_prefixed"
    if s.startswith("sys."):
        return "sys_call"
    if s.startswith("RUN aisop."):
        return "sub_task"
    return "natural_language"


def _human_io_parts(text: str, prefix) -> tuple[str, str | None]:
    """Find the executable call boundary without consuming trailing prose or evaluating args."""
    start = prefix.end()
    while start < len(text) and text[start].isspace():
        start += 1
    invalid = "HUMAN_IO_CALL_INVALID: expected balanced human IO call and optional -> identifier"
    if start == len(text) or text[start] != "(":
        raise AisopFormatError(invalid)
    stack, quote, escaped = [], None, False
    pairs = {')': '(', ']': '[', '}': '{'}
    for pos in range(start, len(text)):
        char = text[pos]
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
        elif char in "'\"":
            quote = char
        elif char in "([{":
            stack.append(char)
        elif char in ")]}":
            if not stack or stack.pop() != pairs[char]:
                raise AisopFormatError(invalid)
            if not stack:
                tail, store = text[pos + 1:].lstrip(), None
                if tail.startswith('->'):
                    match = re.match(r'->\s*([A-Za-z_][A-Za-z0-9_]*)(?=$|[\s.,;:!?(\uff0c。；：、！？（])', tail)
                    if not match:
                        raise AisopFormatError(invalid)
                    store, tail = match.group(1), tail[match.end():].lstrip()
                if tail.startswith((')', ']', '}')):
                    raise AisopFormatError(invalid)
                return text[start + 1:pos].strip(), store
    raise AisopFormatError(invalid)


def parse_sys_call(text) -> dict | None:
    """AISOP §6.10; leading human IO stays blocking with annotations, or fails closed."""
    if not isinstance(text, str):
        return None
    text = text.strip()
    prefix = HUMAN_IO_PREFIX_RE.match(text)
    if prefix:
        name = 'sys.io.' + prefix.group(1)
        args, store = _human_io_parts(text, prefix)
    else:
        m = SYS_CALL_RE.match(text)
        if not m:
            return None
        name, args, store = m.group(1), (m.group(2) or '').strip(), m.group(3)
    return {
        "name": name,
        "args": args,
        "store": store,
        "valid": name in VALID_SYS_CALLS,
        "forced_blocking": name in FORCED_BLOCKING_CALLS,
        "retryable": name not in NON_RETRYABLE_CALLS,
    }


def first_string_arg(args: str) -> str | None:
    """First positional string argument (single or double quoted); confirm message = MF32 key."""
    m = FIRST_STRING_ARG_RE.match(args or "")
    return m.group(2) if m else None


_ASSERT_CLAUSE_RE = re.compile(r"\[ASSERT\]\s*(?P<pred>.+?)\s+executed\b", re.S)
_REQUIRED_RE = re.compile(r"\bRequired:\s*", re.S)
_FIELD_NAME_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_BACKTRACK_RE = re.compile(r"If\s+false\s*(?:→|->|=>)\s*go\s+back\s+to\s+(\w+)", re.I)


def _required_span(text: str) -> str:
    """The `Required:` list up to its sentence end — a `.` at parenthesis depth 0 that is followed by
    whitespace, `[` or the end of text — or up to the next `[ASSERT]` / `If false`. Periods and commas
    inside parentheses (`changed_hexagram (from CastHexagram.output), …`) do not end or split the list."""
    depth = 0
    for i, ch in enumerate(text):
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth = max(0, depth - 1)
        elif depth == 0:
            if ch == "." and (i + 1 == len(text) or text[i + 1].isspace() or text[i + 1] == "["):
                return text[:i]
            if text.startswith("If false", i):
                return text[:i]
    return text


def _split_top_level(text: str, sep: str = ",") -> list[str]:
    parts, depth, cur = [], 0, []
    for ch in text:
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth = max(0, depth - 1)
        if ch == sep and depth == 0:
            parts.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    parts.append("".join(cur))
    return [p.strip() for p in parts if p.strip()]


def _required_names(span: str) -> list[str]:
    """Field names of a Required list: `changed_hexagram (from CastHexagram.output)` -> `changed_hexagram`.
    A provenance note in parentheses is not part of the name the executor looks up (F.2 names output keys)."""
    names = []
    for item in _split_top_level(span):
        m = _FIELD_NAME_RE.search(item)
        if m and m.group(0) not in names:
            names.append(m.group(0))
    return names


def parse_assert(text: str) -> dict | None:
    """AIAP Appendix F.2: [ASSERT] A∨B executed. Required: x, y. If false → go back to A. | work"""
    if not isinstance(text, str) or not text.strip().startswith("[ASSERT]"):
        return None
    head, sep, work = text.partition("|")
    clauses = []
    matches = list(_ASSERT_CLAUSE_RE.finditer(head))
    for n, m in enumerate(matches):
        preds = [p.strip() for p in re.split(r"\s*(?:∨|\bOR\b|\bor\b)\s*", m.group("pred")) if p.strip()]
        region = head[m.end(): matches[n + 1].start() if n + 1 < len(matches) else len(head)]
        rm = _REQUIRED_RE.search(region)
        required = _required_names(_required_span(region[rm.end():])) if rm else []
        clauses.append({"predecessors": preds, "required": required})
    bt = _BACKTRACK_RE.search(head)
    return {
        "clauses": clauses,
        "predecessors": [p for c in clauses for p in c["predecessors"]],
        "required": [r for c in clauses for r in c["required"]],
        "backtrack_to": bt.group(1) if bt else None,
        "work": work.strip() if sep else "",
    }


DELEGATE_STEP_RE = re.compile(
    r"(?:^|[.;|—]\s+|\bElse:\s*)(?:Delegate\s+to|委托)\s+([A-Za-z0-9_][\w.-]*\.aisop\.json)(?:\s*::\s*([A-Za-z_]\w*))?", re.I)


def module_target_of_step(text) -> str | None:
    """doc 12 §1.7 prose delegation: a sentence of the step's work part that begins `Delegate to X.aisop.json` /
    `委托 X.aisop.json` (at the start of the work part, after a sentence boundary `. ; | —`, or after `Else:`; optionally
    `X.aisop.json ::Entry`) names the sub-document it opens, exactly like a `[X.aisop.json]` label. Mentions inside a
    sentence ("wired in review.aisop.json", "if needed, delegate to …", quoted examples) are not delegations; the
    loader additionally requires the file to be a document of the program."""
    if not isinstance(text, str):
        return None
    work = text
    if text.strip().startswith("[ASSERT]"):
        parsed = parse_assert(text)
        work = parsed["work"] if parsed else ""
    m = DELEGATE_STEP_RE.search(work or "")
    if not m:
        return None
    return f"{m.group(1)}::{m.group(2)}" if m.group(2) else m.group(1)


def describe_step(key: str, text) -> dict:
    """Full classification of one step (mode, sys call, sub task, assert, mixed-mode, advisory confirm, prose delegation)."""
    mode = classify_step(text)
    info = {"key": key, "mode": mode, "text": text, "work_mode": None, "sys": None,
            "sub_task": None, "assert": None, "mixed": False, "advisory_confirm": [],
            "high_risk_run": False, "delegate_file": module_target_of_step(text)}
    if mode == "non_string":
        return info
    s = text.strip()
    if mode == "assert_prefixed":
        info["assert"] = parse_assert(s)
        work = info["assert"]["work"]
        if not work and HUMAN_IO_PREFIX_RE.match(s[len('[ASSERT]'):].lstrip()):
            raise AisopFormatError('HUMAN_IO_CALL_INVALID: ASSERT human IO needs a work separator')
        info["work_mode"] = classify_step(work) if work else "empty"
        target, target_mode = work, info["work_mode"]
    else:
        target, target_mode = s, mode
    if target_mode == "sys_call":
        info["sys"] = parse_sys_call(target)
        if info["sys"] and info["sys"]["name"].startswith("sys.run"):
            info["high_risk_run"] = bool(HIGH_RISK_RUN_RE.search(info["sys"]["args"]))
    elif target_mode == "sub_task":
        m = SUB_TASK_RE.match(target)
        info["sub_task"] = m.group(1) if m else None
        if not m:
            info["mixed"] = True
    elif target_mode == "natural_language":
        if EMBEDDED_SYS_RE.search(target):
            info["mixed"] = True
    if target_mode != "sys_call" or (info["sys"] and info["sys"]["name"] != "sys.io.confirm"):
        info["advisory_confirm"] = [m.group(2) for m in CONFIRM_TEXT_RE.finditer(s)]
    return info


def describe_function(name: str, func: dict) -> dict:
    """split_function + describe_step for every step, plus I-03 gate sources."""
    if not isinstance(func, dict):
        return {"name": name, "steps": [], "reserved": {}, "extra": {}, "unsupported_reserved": [],
                "gate_sources": [], "problems": ["FUNCTION_NOT_OBJECT"]}
    split = split_function(func)
    steps = [describe_step(s["key"], s["text"]) for s in split["steps"]]
    result = {"name": name, "steps": steps, "reserved": split["reserved"], "extra": split["extra"],
              "unsupported_reserved": split["unsupported_reserved"], "problems": []}
    em = split["reserved"].get("execute_mode")
    if em is not None and em not in EXECUTE_MODES:
        result["problems"].append("EXECUTE_MODE_UNKNOWN")
    result["gate_sources"] = scan_gate_sources(result)
    return result


def _advisory_texts(value):
    """Scan original JSON strings, not their escaped serialization."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield from _advisory_texts(key)
            yield from _advisory_texts(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _advisory_texts(item)


def scan_gate_sources(described: dict) -> list[dict]:
    """I-03 three gate sources.

    (a) sys_io_call   step-leading sys.io.confirm/input/select  -> required, prompt = first arg
    (b) user_gate     function key user_gate: true -> required; "conditional" -> advisory; false -> none
    (c) advisory_text sys.io.confirm( inside NL text / constraints / extra, or high-risk sys.run
    """
    gates: list[dict] = []
    duties = delivery_obligations.obligations(described)
    for key, required in (('reply_required_steps', True), ('reply_conditional_steps', False)):
        gates.extend(dict(source='advisory_text', kind='choice', required=required, step=step,
                          prompt_text=None, reason='explicit_human_reply') for step in duties[key])
    for step in described["steps"]:
        sysc = step.get("sys")
        if sysc and sysc["name"] in FORCED_BLOCKING_CALLS:
            gates.append({"source": "sys_io_call", "kind": sysc["name"].rsplit(".", 1)[1],
                          "required": True, "step": step["key"],
                          "prompt_text": first_string_arg(sysc["args"])})
        for msg in step.get("advisory_confirm", []):
            gates.append({"source": "advisory_text", "kind": "confirm", "required": False,
                          "step": step["key"], "prompt_text": msg})
        if step.get("high_risk_run"):
            gates.append({"source": "advisory_text", "kind": "confirm", "required": False,
                          "step": step["key"], "prompt_text": None, "reason": "high_risk_sys_run"})
    ug = described["extra"].get("user_gate")
    if ug is True:
        gates.append({"source": "user_gate", "kind": "choice", "required": True, "step": None,
                      "prompt_text": None})
    elif isinstance(ug, str) and ug.strip().lower() == "conditional":
        gates.append({"source": "user_gate", "kind": "choice", "required": False, "step": None,
                      "prompt_text": None, "reason": "conditional"})
    for holder in ("constraints",):
        value = described["reserved"].get(holder)
        for text in _advisory_texts(value):
            for msg in CONFIRM_TEXT_RE.findall(text):
                gates.append({"source": "advisory_text", "kind": "confirm", "required": False,
                              "step": holder, "prompt_text": msg[1]})
    for key, value in described["extra"].items():
        if key == "user_gate" or not isinstance(value, (str, list, dict)):
            continue
        for text in _advisory_texts(value):
            for msg in CONFIRM_TEXT_RE.findall(text):
                gates.append({"source": "advisory_text", "kind": "confirm", "required": False,
                              "step": key, "prompt_text": msg[1]})
    return gates


# ---------------------------------------------------------------------------
# Expression engine (AISOP §6.11) — deterministic, no LLM
# ---------------------------------------------------------------------------

_TOKEN_RE = re.compile(
    r"\s*(?:(\|\||&&|==|!=|>=|<=|[><!()])"
    r"|('(?:[^'\\]|\\.)*'|\"(?:[^\"\\]|\\.)*\")"
    r"|(-?\d+(?:\.\d+)?)"
    r"|([A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*))"
)


def _tokenize(expr: str) -> list[tuple[str, str]]:
    tokens, pos = [], 0
    while pos < len(expr):
        if expr[pos].isspace():
            pos += 1
            continue
        m = _TOKEN_RE.match(expr, pos)
        if not m or m.end() == pos:
            raise ExpressionError(f"unexpected character at {pos}: {expr[pos]!r}")
        op, string, number, ident = m.groups()
        if op is not None:
            tokens.append(("op", op))
        elif string is not None:
            tokens.append(("str", string[1:-1]))
        elif number is not None:
            tokens.append(("num", number))
        else:
            tokens.append(("ident", ident))
        pos = m.end()
    return tokens


class _Evaluator:
    def __init__(self, tokens, context):
        self.tokens, self.context, self.pos = tokens, context, 0

    def peek(self):
        return self.tokens[self.pos] if self.pos < len(self.tokens) else (None, None)

    def take(self):
        tok = self.peek()
        self.pos += 1
        return tok

    def expect_op(self, op):
        tok = self.take()
        if tok != ("op", op):
            raise ExpressionError(f"expected {op!r}")

    def parse_or(self):
        left = self.parse_and()
        while self.peek() == ("op", "||"):
            self.take()
            right = self.parse_and()
            left = bool(left) or bool(right)
        return left

    def parse_and(self):
        left = self.parse_not()
        while self.peek() == ("op", "&&"):
            self.take()
            right = self.parse_not()
            left = bool(left) and bool(right)
        return left

    def parse_not(self):
        if self.peek() == ("op", "!"):
            self.take()
            return not bool(self.parse_not())
        return self.parse_cmp()

    def parse_cmp(self):
        left = self.parse_primary()
        kind, op = self.peek()
        if kind == "op" and op in ("==", "!=", ">", "<", ">=", "<="):
            self.take()
            right = self.parse_primary()
            if op == "==":
                return left == right
            if op == "!=":
                return left != right
            if left is None or right is None or isinstance(left, bool) or isinstance(right, bool):
                raise ExpressionError(f"ordering comparison on null/boolean: {left!r} {op} {right!r}")
            try:
                return {">": left > right, "<": left < right,
                        ">=": left >= right, "<=": left <= right}[op]
            except TypeError as exc:
                raise ExpressionError(str(exc)) from exc
        return left

    def parse_primary(self):
        kind, value = self.take()
        if kind == "op" and value == "(":
            inner = self.parse_or()
            self.expect_op(")")
            return inner
        if kind == "str":
            return value
        if kind == "num":
            return float(value) if "." in value else int(value)
        if kind == "ident":
            if value in ("null", "None"):
                return None
            if value in ("true", "True"):
                return True
            if value in ("false", "False"):
                return False
            return self.resolve(value)
        raise ExpressionError("unexpected end of expression" if kind is None else f"unexpected token {value!r}")

    def resolve(self, dotted: str):
        obj = self.context
        for part in dotted.split("."):
            if isinstance(obj, dict) and part in obj:
                obj = obj[part]
            else:
                raise ExpressionError(f"Undefined variable: {dotted}")
        return obj


def eval_expression(expr: str, context: dict | None = None):
    """Evaluate a §6.11 expression deterministically. Raises ExpressionError on invalid input."""
    evaluator = _Evaluator(_tokenize(expr.strip()), context or {})
    if not evaluator.tokens:
        raise ExpressionError("empty expression")
    result = evaluator.parse_or()
    if evaluator.pos != len(evaluator.tokens):
        raise ExpressionError("trailing tokens in expression")
    return result

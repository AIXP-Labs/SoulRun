"""AIAP / AISOP conformance check for soulrun_aiap V1.0.0.

Read-only. Zero third-party dependencies. Two modes (04 series doc 02 §7):

  self     C-01 … C-11 governance-carrier checks for an AIAP directory (default: the engine itself)
  program  loader-side checks for a target program: R-01 structure, R-05 load checks,
           R-06 skipped files, R-14 unsupported reserved keys, R-16 delegate depth / cycles,
           plus I-01 / I-02 / I-03 scans and the doc 02 §2.2 feature counts

Usage
  python tools/aiap_conformance_check.py [DIR] [--mode self|program] [--json] [--supported-protocol "AIAP V1.0.0"]

Exit status: 1 when any FAIL (self) or any FATAL-class finding (program), else 0.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

_HERE = Path(__file__).resolve()
sys.path.insert(0, str(_HERE.parents[1] / "python_tools"))

from lib import aiap_md, aisop_parse, program_loader  # noqa: E402

ENGINE_DIR = _HERE.parents[1]
SUPPORTED_PROTOCOL = "AIAP V1.0.0"
MAX_RECURSION_DEPTH = program_loader.MAX_RECURSION_DEPTH
SEAL_TAIL = "Align Axiom 0: Human Sovereignty and Wellbeing."
MIRROR_LINE = "Mirror User's exact language and script variant."
GOVERNANCE_FILE_PATTERNS = ("*.aisop.json", "AIAP.md", "quality_baseline.json", "agent_card.json")


def _check(cid: str, status: str, detail: str, **extra) -> dict:
    row = {"id": cid, "status": status, "detail": detail}
    row.update(extra)
    return row


def _read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8-sig")), None
    except FileNotFoundError:
        return None, "missing"
    except json.JSONDecodeError as exc:
        return None, f"invalid JSON: {exc}"


def _protocol_version(value) -> tuple[int, ...] | None:
    m = re.search(r"V(\d+)\.(\d+)\.(\d+)", str(value or ""))
    return tuple(int(x) for x in m.groups()) if m else None


# ---------------------------------------------------------------------------
# self mode: C-01 … C-11
# ---------------------------------------------------------------------------

def check_self(aiap_dir: Path, supported_protocol: str = SUPPORTED_PROTOCOL) -> dict:
    checks: list[dict] = []
    main_path = aiap_dir / "main.aisop.json"

    # C-01 file shape
    doc = None
    data, err = _read_json(main_path)
    if err:
        checks.append(_check("C-01", "FAIL", f"main.aisop.json {err}"))
    else:
        try:
            doc = aisop_parse.parse_aisop_document(data)
        except aisop_parse.AisopFormatError as exc:
            checks.append(_check("C-01", "FAIL", f"main.aisop.json: {exc}"))
        else:
            if doc["shape"] == "array2":
                checks.append(_check("C-01", "PASS", "two-element [system, user] array (AISOP §1)"))
            else:
                checks.append(_check("C-01", "FAIL", "legacy single-object shape; AISOP §1 requires a two-element array"))

    system = doc["system"] if doc else {}
    user = doc["user"] if doc else {}

    # C-02 system.content fields
    missing = [f for f in ("protocol", "axiom_0", "id", "name", "version", "flow_format",
                           "loading_mode", "output_mode", "system_prompt", "trust_level", "tools") if f not in system]
    bad: list[str] = []
    if system.get("axiom_0", aisop_parse.AXIOM_0) != aisop_parse.AXIOM_0:
        bad.append("axiom_0 value")
    if "flow_format" in system and system["flow_format"] not in aisop_parse.FLOW_FORMATS:
        bad.append("flow_format enum")
    if "loading_mode" in system and system["loading_mode"] not in aisop_parse.LOADING_MODES:
        bad.append("loading_mode enum")
    if "version" in system and not aiap_md.is_semver(system["version"]):
        bad.append("version semver")
    om = system.get("output_mode")
    if "output_mode" in system:
        if not isinstance(om, dict) or not all(k in om for k in ("L0", "L1", "output")):
            bad.append("output_mode shape {L0,L1,output}")
        elif om.get("output") not in ("L1", "L0+L1"):
            bad.append("output_mode.output enum")
    if "trust_level" in system and aiap_md.normalize_trust_level(system["trust_level"]) is None:
        bad.append("trust_level form")
    if "tools" in system and not isinstance(system["tools"], (list, dict)):
        bad.append("tools type")
    advisory = [f for f in ("fractal_exempt", "json_schema") if f not in system]
    if doc is None:
        checks.append(_check("C-02", "N_A", "no document"))
    elif missing or bad:
        checks.append(_check("C-02", "FAIL", f"missing={missing} invalid={bad}"))
    elif advisory:
        checks.append(_check("C-02", "WARN", f"required fields present; Creator precheck also expects {advisory}"))
    else:
        checks.append(_check("C-02", "PASS", "system.content required fields present and valid"))
    if "version" in system and aiap_md.is_semver(system["version"]) and not aiap_md.is_plain_semver(system["version"]):
        checks.append(_check("C-02b", "WARN", f"version {system['version']!r} has a pre-release tag; Creator precheck expects plain x.y.z"))

    # C-03 user.content: instruction constant, user_input, aisop.main, functions 1:1
    tasks: dict[str, dict] = {}
    if doc is None:
        checks.append(_check("C-03", "N_A", "no document"))
    else:
        problems: list[str] = []
        warns: list[str] = []
        if user.get("instruction") != aisop_parse.INSTRUCTION_CANONICAL:
            problems.append(f"instruction={user.get('instruction')!r} (must be {aisop_parse.INSTRUCTION_CANONICAL!r})")
        if user.get("user_input") != "{user_input}":
            warns.append("user_input placeholder absent (optional for sub-modules)")
        aisop = user.get("aisop")
        functions = user.get("functions")
        if not isinstance(aisop, dict) or "main" not in aisop:
            problems.append("aisop.main missing")
        else:
            for tname, body in aisop.items():
                try:
                    tasks[tname] = aisop_parse.parse_task(body)
                except aisop_parse.AisopFormatError as exc:
                    problems.append(f"task {tname}: {exc}")
        if not isinstance(functions, dict):
            problems.append("functions missing or not an object")
        elif tasks:
            graph_nodes: set[str] = set()
            need_function: set[str] = set()
            for parsed in tasks.values():
                for name in parsed["nodes"]:
                    graph_nodes.add(name)
                    if parsed["node_types"].get(name) != "end":
                        need_function.add(name)
            missing_fn = sorted(need_function - set(functions))
            phantom = sorted(set(functions) - graph_nodes)
            if missing_fn:
                problems.append(f"nodes without function: {missing_fn}")
            if phantom:
                problems.append(f"functions without graph node: {phantom}")
        if problems:
            checks.append(_check("C-03", "FAIL", "; ".join(problems + warns)))
        elif warns:
            checks.append(_check("C-03", "WARN", "; ".join(warns)))
        else:
            checks.append(_check("C-03", "PASS", "instruction constant, aisop.main, functions 1:1 (MF31)"))

    # C-04 system_prompt seal + mirror line
    sp = system.get("system_prompt")
    if not isinstance(sp, str):
        checks.append(_check("C-04", "FAIL" if doc else "N_A", "system_prompt missing"))
    else:
        issues = []
        if not sp.rstrip().endswith(SEAL_TAIL):
            issues.append(f"must end with {SEAL_TAIL!r}")
        if MIRROR_LINE not in sp:
            issues.append(f"must contain {MIRROR_LINE!r}")
        checks.append(_check("C-04", "FAIL" if issues else "PASS", "; ".join(issues) or "seal and mirror line present"))

    # C-05 Node Gate (Appendix F) + endNode naming
    if not tasks:
        checks.append(_check("C-05", "N_A", "no parseable task graph"))
    else:
        functions = user.get("functions") if isinstance(user.get("functions"), dict) else {}
        trust = aiap_md.normalize_trust_level(system.get("trust_level"))
        total_functional = sum(aisop_parse.graph_summary(p)["functional_nodes"] for p in tasks.values())
        required = (isinstance(trust, int) and trust >= 3) or total_functional >= 6
        gate_missing, gate_wrong, end_naming = [], [], []
        for tname, parsed in tasks.items():
            preds = aisop_parse.predecessors(parsed)
            entries = set(aisop_parse.entry_nodes(parsed))
            for name in parsed["order"]:
                ntype = parsed["node_types"].get(name)
                if ntype == "end":
                    if not (name == "endNode" and parsed["node_labels"].get(name) == "End"):
                        end_naming.append(f"{tname}:{name}(({parsed['node_labels'].get(name)}))")
                    continue
                if name in entries or name not in functions or not isinstance(functions[name], dict):
                    continue
                steps = aisop_parse.split_function(functions[name])["steps"]
                first = steps[0]["text"] if steps else ""
                parsed_assert = aisop_parse.parse_assert(first) if isinstance(first, str) else None
                if not parsed_assert:
                    gate_missing.append(f"{tname}:{name}")
                    continue
                actual = set(preds.get(name, []))
                named = set(parsed_assert["predecessors"])
                unknown = {p for p in named if p not in actual and not aisop_parse.STEP_KEY_RE.match(p)}
                bt = parsed_assert["backtrack_to"]
                if unknown or (bt and bt not in actual and bt not in named):
                    gate_wrong.append(f"{tname}:{name} asserts {sorted(named)} backtrack={bt} actual={sorted(actual)}")
        details = []
        if gate_missing:
            details.append(f"missing [ASSERT] on {gate_missing}")
        if gate_wrong:
            details.append(f"predecessor mismatch: {gate_wrong}")
        if end_naming:
            details.append(f"terminal not endNode((End)): {end_naming}")
        if not details:
            checks.append(_check("C-05", "PASS", f"Node Gate complete ({'required' if required else 'optional'}); terminal endNode((End))"))
        elif required:
            checks.append(_check("C-05", "FAIL", "; ".join(details)))
        else:
            checks.append(_check("C-05", "WARN", "; ".join(details)))

    # C-06 AIAP.md
    fm, body = {}, ""
    md_path = aiap_dir / "AIAP.md"
    if not md_path.exists():
        checks.append(_check("C-06", "FAIL", "AIAP.md missing"))
    else:
        try:
            fm, body = aiap_md.load_aiap_md(md_path)
        except aiap_md.FrontmatterError as exc:
            checks.append(_check("C-06", "FAIL", f"frontmatter unparseable: {exc}"))
        else:
            problems, warns = [], []
            missing = [f for f in aiap_md.REQUIRED_FIELDS if f not in fm]
            if missing:
                problems.append(f"missing required {missing}")
            for key, fixed in aiap_md.FIXED_VALUES.items():
                if key in fm and fm[key] != fixed:
                    problems.append(f"{key}={fm[key]!r} (fixed {fixed!r})")
            if "protocol" in fm and not str(fm["protocol"]).startswith("AIAP V"):
                problems.append(f"protocol={fm['protocol']!r}")
            if "governance_mode" in fm and fm["governance_mode"] not in aiap_md.GOVERNANCE_MODES:
                problems.append(f"governance_mode={fm['governance_mode']!r}")
            if "pattern" in fm and not aiap_md.PATTERN_RE.match(str(fm["pattern"])):
                problems.append(f"pattern={fm['pattern']!r} (allowed A|B|C|D|E|F|G, combos like D+G)")
            if "flow_format" in fm and fm["flow_format"] not in aiap_md.FLOW_FORMATS:
                problems.append(f"flow_format={fm['flow_format']!r}")
            if "name" in fm and not aiap_md.SNAKE_CASE_RE.match(str(fm["name"])):
                problems.append(f"name={fm['name']!r} not snake_case")
            if "version" in fm and not aiap_md.is_semver(str(fm["version"])):
                problems.append(f"version={fm['version']!r} not semver")
            if "summary" in fm and isinstance(fm["summary"], str) and len(fm["summary"]) > 500:
                warns.append("summary > 500 chars")
            lic = fm.get("license")
            if "license" in fm:
                if not isinstance(lic, str) or not aiap_md.SPDX_RE.match(lic):
                    problems.append(f"license={lic!r}")
                elif lic == "proprietary" and not (fm.get("terms_url") or fm.get("contact")):
                    problems.append("license proprietary requires terms_url or contact")
            if "status" in fm and fm["status"] not in aiap_md.STATUSES:
                problems.append(f"status={fm['status']!r}")
            modules = fm.get("modules")
            if "modules" in fm:
                if not isinstance(modules, list):
                    problems.append("modules not a list")
                else:
                    for mod in modules:
                        if not isinstance(mod, dict):
                            problems.append(f"module entry not a mapping: {mod!r}")
                            continue
                        for f in ("id", "file", "nodes"):
                            if f not in mod:
                                problems.append(f"module {mod.get('id')!r} missing {f}")
                        if "file" in mod and not (aiap_dir / str(mod["file"])).exists():
                            problems.append(f"module file missing: {mod['file']}")
                        if mod.get("file") == "main.aisop.json" and tasks and isinstance(mod.get("nodes"), int):
                            actual = aisop_parse.graph_summary(tasks["main"])["functional_nodes"] if "main" in tasks else None
                            if actual is not None and abs(actual - mod["nodes"]) > 3:
                                problems.append(f"module nodes={mod['nodes']} vs parsed {actual} (MF6 >3)")
                            elif actual is not None and actual != mod["nodes"]:
                                warns.append(f"module nodes={mod['nodes']} vs parsed {actual} (MF6 ±3)")
            seal = aiap_md.closing_seal(body)
            expected_seal = aiap_md.SEALS.get(str(fm.get("governance_mode", "NORMAL")), aiap_md.SEALS["NORMAL"])
            if seal != expected_seal:
                problems.append(f"closing seal mismatch: {seal!r}")
            for section in ("Governance Declaration", "Feature Overview", "Usage"):
                if not re.search(rf"^#+\s*{re.escape(section)}", body, re.M):
                    warns.append(f"section missing: {section}")
            if problems:
                checks.append(_check("C-06", "FAIL", "; ".join(problems + warns)))
            elif warns:
                checks.append(_check("C-06", "WARN", "; ".join(warns)))
            else:
                checks.append(_check("C-06", "PASS", "6 governance + 8 project fields, enums, seal"))

    # C-07 four-file version / trust_level sync
    card, card_err = _read_json(aiap_dir / "agent_card.json")
    qb, qb_err = _read_json(aiap_dir / "quality_baseline.json")
    sources = {"main.aisop.json": system, "AIAP.md": fm, "agent_card.json": card, "quality_baseline.json": qb}
    absent = [k for k, v in sources.items() if not isinstance(v, dict)]
    present = {k: v for k, v in sources.items() if isinstance(v, dict)}
    versions = {k: v.get("version") for k, v in present.items()}
    trusts = {k: aiap_md.normalize_trust_level(v.get("trust_level")) for k, v in present.items() if "trust_level" in v}
    issues = []
    if absent:
        issues.append(f"missing {absent}")
    if len(set(map(str, versions.values()))) > 1:
        issues.append(f"version drift {versions}")
    if len(set(map(str, trusts.values()))) > 1:
        issues.append(f"trust_level drift {trusts}")
    checks.append(_check("C-07", "FAIL" if issues else "PASS", "; ".join(issues) or f"version {versions.get('AIAP.md')!r} / trust {trusts.get('AIAP.md')!r} consistent across 4 files"))

    # C-08 governance hash
    computed = aiap_md.governance_hash(aiap_dir)
    declared = fm.get("governance_hash") if isinstance(fm, dict) else None
    verdict = aiap_md.match_governance_hash(declared, computed)
    others = {k: aiap_md.match_governance_hash(v.get("governance_hash"), computed)
              for k, v in (("agent_card.json", card), ("quality_baseline.json", qb)) if isinstance(v, dict) and "governance_hash" in v}
    status_field = str(fm.get("status", "draft")) if isinstance(fm, dict) else "draft"
    if verdict.startswith("MATCH") and all(v.startswith("MATCH") for v in others.values()):
        st = "PASS" if verdict == "MATCH_CANONICAL" else "WARN"
        checks.append(_check("C-08", st, f"{verdict} canonical={computed['canonical']} files={computed['files']} others={others}"))
    elif verdict == "MISSING":
        checks.append(_check("C-08", "WARN", f"governance_hash not declared (recommended for T3); canonical={computed['canonical']}"))
    else:
        st = "FAIL" if status_field == "active" else "WARN"
        checks.append(_check("C-08", st, f"AIAP.md={verdict} others={others} computed canonical={computed['canonical']} hex64={computed['hex64']} (status={status_field})"))

    # C-09 NO_SELF_MODIFY (runtime-enforced; static scan of python_tools for governance-file writes)
    suspicious = []
    for py in sorted((aiap_dir / "python_tools").rglob("*.py")) if (aiap_dir / "python_tools").exists() else []:
        text = py.read_text(encoding="utf-8", errors="replace")
        for pat in ("AIAP.md", ".aisop.json", "quality_baseline.json", "agent_card.json", ".version_history"):
            if pat in text and re.search(r"open\([^)]*['\"]w|write_text\(|write_bytes\(", text):
                suspicious.append(f"{py.name}:{pat}")
    checks.append(_check("C-09", "WARN" if suspicious else "N_A",
                         f"runtime rule (node_commit SELF_MODIFY_FORBIDDEN); static scan hits {suspicious}" if suspicious
                         else "runtime rule enforced by node_commit (SELF_MODIFY_FORBIDDEN); static scan clean"))

    # C-10 permissions / runtime
    perms, rt = fm.get("permissions") if isinstance(fm, dict) else None, fm.get("runtime") if isinstance(fm, dict) else None
    trust = aiap_md.normalize_trust_level(fm.get("trust_level")) if isinstance(fm, dict) else None
    issues, warns = [], []
    if not isinstance(perms, dict):
        (issues if trust == 4 else warns).append("permissions not declared" + (" (required for T4)" if trust == 4 else ""))
    else:
        if "file_system" not in perms:
            warns.append("permissions.file_system absent")
        shell = perms.get("shell")
        net = perms.get("network")
        shell_off = shell is False or (isinstance(shell, dict) and shell.get("allowed") is False)
        net_off = net is False or (isinstance(net, dict) and net.get("allowed") is False)
        if not shell_off:
            issues.append("engine policy: shell must be disallowed")
        if not net_off:
            issues.append("engine policy: network must be disallowed")
    if not isinstance(rt, dict):
        warns.append("runtime not declared")
    checks.append(_check("C-10", "FAIL" if issues else ("WARN" if warns else "PASS"), "; ".join(issues + warns) or "permissions/runtime declared; shell and network disallowed"))

    # C-11 frontmatter key whitelist
    unknown = sorted(k for k in (fm.keys() if isinstance(fm, dict) else []) if k not in aiap_md.KNOWN_FIELDS)
    checks.append(_check("C-11", "FAIL" if unknown else "PASS", f"unknown frontmatter keys {unknown}" if unknown else "all frontmatter keys are protocol-listed"))

    fails = [c["id"] for c in checks if c["status"] == "FAIL"]
    return {"mode": "self", "target": str(aiap_dir), "checks": checks, "fail_count": len(fails),
            "governance_hash_computed": computed}


# ---------------------------------------------------------------------------
# program mode: thin wrapper over lib.program_loader (single implementation of R-01/R-05/R-06/R-14/R-16)
# ---------------------------------------------------------------------------

def check_program(aiap_dir: Path, supported_protocol: str = SUPPORTED_PROTOCOL, entry_file: str | None = None) -> dict:
    try:
        program = program_loader.load_program(aiap_dir, entry_file)
    except program_loader.ProgramError as exc:
        return {"mode": "program", "target": str(aiap_dir), "entry_file": entry_file,
                "findings": [{"code": exc.code, "severity": "FATAL", "detail": exc.detail}],
                "skipped_files": [], "fatal_count": 1}
    report = program_loader.analyze(program, supported_protocol)
    report.update({"mode": "program", "target": str(aiap_dir), "entry_file": program.entry_file})
    return report


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _render_self(report: dict) -> str:
    lines = [f"AIAP conformance (self) — {report['target']}"]
    for c in report["checks"]:
        lines.append(f"  {c['id']:<5} {c['status']:<4} {c['detail']}")
    lines.append(f"  FAIL count: {report['fail_count']}   computed governance_hash canonical={report['governance_hash_computed']['canonical']}")
    return "\n".join(lines)


def _render_program(report: dict) -> str:
    lines = [f"AIAP program load check — {report['target']}"]
    if "counts" in report:
        c = report["counts"]
        lines.append(f"  files {c['files']} skipped {c['skipped']} tasks {c['tasks']} nodes {c['nodes']} functional {c['functional_nodes']} functions {c['functions']}")
        lines.append(f"  [ASSERT] {c['assert_steps']} | RUN aisop.* {c['run_aisop_steps']} | mixed {c['mixed_steps']} | sys.* {c['sys_calls']}")
        lines.append(f"  reserved {c['reserved_keys']} | extra {c['extra_keys']} | execute_mode {c['execute_mode']}")
        lines.append(f"  topology {c['topology']} | gate sources {c['gate_sources']} | instruction {c['instruction_variants']} | loading {c['loading_modes']}")
        lines.append(f"  multi-candidate nodes {len(report['multi_candidates'])} | delegate depth {report['delegate_closure']['max_depth']}")
    for f in report["findings"]:
        lines.append(f"  {f['severity']:<5} {f['code']:<28} {f['detail']}")
    for s in report.get("skipped_files", []):
        lines.append(f"  SKIP  {s['file']}: {s['reason']}")
    lines.append(f"  FATAL count: {report.get('fatal_count', 0)}")
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dir", nargs="?", default=str(ENGINE_DIR))
    ap.add_argument("--mode", choices=("self", "program"), default="self")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--supported-protocol", default=SUPPORTED_PROTOCOL)
    ap.add_argument("--entry", default=None, help="program mode: entry file name (default main.aisop.json, aisp.aisop.json, or the single .aisop.json)")
    args = ap.parse_args(argv)
    target = Path(args.dir).resolve()
    if not target.is_dir():
        print(f"not a directory: {target}", file=sys.stderr)
        return 2
    report = check_self(target, args.supported_protocol) if args.mode == "self" else check_program(target, args.supported_protocol, args.entry)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(_render_self(report) if args.mode == "self" else _render_program(report))
    bad = report.get("fail_count", 0) if args.mode == "self" else report.get("fatal_count", 0)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())

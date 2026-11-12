"""Regenerate ``src/soulrun/_agent_text.py`` from a SoulBot ``agent.py``.

SoulBot's agent template builds the text the model reads before every engine turn. SoulRun's entry-path form (the
model reads the engine program itself, ``slim_program=False``) hands back exactly the same text, byte for byte, so the
wording is not retyped: this tool lifts it out of ``agent.py`` and writes it into a generated module - the blocks, the
interruption notes, and the opening instruction (``_SYSTEM_PROMPT``) that goes with them.

    python tools/port_agent_text.py <path to agent.py>
    python tools/port_agent_text.py <path to agent.py> --check     # fail when the generated module is stale

Nothing in ``agent.py`` is executed; only its syntax tree is read.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "src" / "soulrun" / "_agent_text.py"
sys.path.insert(0, str(Path(__file__).resolve().parent))
import clean_engine  # noqa: E402

# The code in agent.py that builds the [EXECUTION CONTEXT] block. SoulRun re-implements these lines by
# hand (they are logic, not wording); the tool refuses to run when agent.py no longer contains them.
CONTEXT_BLOCK_SOURCE = '''        ctx_block = (
            f"[EXECUTION CONTEXT]\\n"
            f"turn_id: {exec_ctx['turn_id']}\\n"
            f"cache_dir: {exec_ctx['cache_dir']}\\n"
            f"cache_name: {exec_ctx['cache_name']}\\n"
            f"trace_id: {exec_ctx['trace_id']}"
        )
        if exec_ctx.get("session_id"):
            ctx_block += f"\\nsession_id: {exec_ctx['session_id']}"
        if origin_channel:
            ctx_block += f"\\norigin_channel: {origin_channel}"
        for key in ("entry_mode", "user_language", "requested_model"):
            value = exec_ctx.get(key)
            if value not in (None, ""):
                ctx_block += f"\\n{key}: {value}"
        parts.append(ctx_block)
'''
TEXT_ONLY_SOURCE = '''    text_only = bool(exec_ctx and (exec_ctx.get("stop_question") or exec_ctx.get("stop_hold") or exec_ctx.get("stop_ended")
                                   or exec_ctx.get("supply_authorized") or exec_ctx.get("supply_hold")))
'''
PLACEHOLDERS = {"_ENGINE_AIAP_DIR.resolve()": "engine_dir", "router_entry": "entry_path", "language_name": "language_name"}


def _template(source: str, node: ast.JoinedStr) -> str:
    out = []
    for part in node.values:
        if isinstance(part, ast.Constant):
            out.append(str(part.value).replace("{", "{{").replace("}", "}}"))
        else:
            if part.conversion != -1 or part.format_spec is not None:
                # "{x!r}" or "{x:>10}": the text would no longer be the value as written - refuse, never drop it quietly
                raise SystemExit(f"agent.py formats a value ({ast.get_source_segment(source, part)!r}); this tool copies "
                                 "plain values only - extend it before porting")
            expression = ast.get_source_segment(source, part.value)
            if expression not in PLACEHOLDERS:
                raise SystemExit(f"agent.py uses a value this tool does not know: {expression!r}")
            out.append("{" + PLACEHOLDERS[expression] + "}")
    return "".join(out)


def generate(agent_py: Path) -> str:
    raw = agent_py.read_bytes()
    source = raw.decode("utf-8").replace("\r\n", "\n")
    for label, snippet in (("[EXECUTION CONTEXT] block", CONTEXT_BLOCK_SOURCE), ("text-only decision", TEXT_ONLY_SOURCE)):
        if snippet not in source:
            raise SystemExit(f"agent.py changed its {label}; update src/soulrun/_blocks.py and this tool together")
    tree = ast.parse(source)
    functions = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
    for name in ("_interruption_block", "_language_name"):
        if name not in functions:
            raise SystemExit(f"agent.py has no {name}()")

    templates: dict[str, str] = {}
    for node in ast.walk(functions["_router_instruction"]):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "append" and node.args):
            continue
        argument = node.args[0]
        if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
            argument = ast.JoinedStr(values=[argument])
        if not isinstance(argument, ast.JoinedStr):
            continue
        first = argument.values[0] if argument.values else None
        opening = str(first.value) if isinstance(first, ast.Constant) else ""
        if not opening.startswith(("[EXECUTE ENGINE ENTRY]", "[TURN EXECUTION ASSERTION]")):
            continue          # SoulBot's own blocks (time, tool guide, schedule, ...) stay in agent.py
        text = _template(source, argument)
        if text.startswith("[EXECUTE ENGINE ENTRY]"):
            templates["ENTRY_TEMPLATE"] = text
        elif text.startswith("[TURN EXECUTION ASSERTION]") and "FIRST_RESPONSE_MUST_BE=tool_use" in text:
            templates["ASSERTION_ENGINE_TEMPLATE"] = text
        elif text.startswith("[TURN EXECUTION ASSERTION]") and "FIRST_RESPONSE_MUST_BE=text" in text:
            templates["ASSERTION_TEXT_ONLY_TEMPLATE"] = text
    # The opening instruction SoulBot gives the model on every engine turn (the first part of _router_instruction): the
    # entry-path form's system prompt, handed to hosts as ctx.system_prompt so the prompt and the program form always agree.
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "_SYSTEM_PROMPT" for t in node.targets) \
                and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            templates["SYSTEM_PROMPT"] = node.value.value
    missing = {"ENTRY_TEMPLATE", "ASSERTION_ENGINE_TEMPLATE", "ASSERTION_TEXT_ONLY_TEMPLATE", "SYSTEM_PROMPT"} - set(templates)
    if missing:
        raise SystemExit(f"agent.py no longer has: {sorted(missing)}")

    def lifted(name: str, new_def: str) -> str:
        node = functions[name]
        lines = source.split("\n")[node.lineno - 1:node.end_lineno]
        header_end = next(i for i, line in enumerate(lines) if line.rstrip().endswith(":"))
        return "\n".join([new_def] + lines[header_end + 1:])

    interruption = lifted("_interruption_block", "def interruption_block(exec_ctx: dict | None, _ENGINE_AIAP_DIR) -> str | None:")
    language = lifted("_language_name", "def language_name(exec_ctx: dict | None) -> str:")
    digest = hashlib.sha256(source.encode("utf-8")).hexdigest()
    header = (
        '"""GENERATED by tools/port_agent_text.py - do not edit by hand.\n\n'
        "The wording below is lifted unchanged from SoulBot's agent template (agent.py), so that SoulRun\n"
        "hands the model exactly the text SoulBot hands it today.\n\n"
        f"Source: agent.py, sha256 (LF line endings) {digest}\n"
        '"""\n'
        "# fmt: off\n"
        "# ruff: noqa\n"
        "from __future__ import annotations\n\n"
        f'AGENT_PY_SHA256 = "{digest}"\n\n'
    )
    body = "".join(f"{name} = {templates[name]!r}\n\n"
                   for name in ("SYSTEM_PROMPT", "ENTRY_TEMPLATE", "ASSERTION_ENGINE_TEMPLATE", "ASSERTION_TEXT_ONLY_TEMPLATE"))
    # Every string stays exactly as agent.py has it; the comments beside the code lose development notes
    # (version markers, planning-document references), as the bundled engine's do (tools/clean_engine.py).
    return clean_engine.clean_comments(header + body + "\n" + language + "\n\n\n" + interruption + "\n")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("agent_py", help="SoulBot's agent.py")
    parser.add_argument("--check", action="store_true", help="only report whether the generated module is stale")
    args = parser.parse_args(argv)           # an unknown option ("--chek") is an error, never a quiet rewrite
    text = generate(Path(args.agent_py))
    if args.check:
        current = TARGET.read_text(encoding="utf-8") if TARGET.is_file() else ""
        if current != text:
            print("src/soulrun/_agent_text.py is stale; run tools/port_agent_text.py again")
            return 1
        print("src/soulrun/_agent_text.py matches agent.py")
        return 0
    TARGET.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {TARGET.relative_to(ROOT).as_posix()} ({len(text):,} chars)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

"""Record what SoulBot says and does where SoulRun must match it, so the tests compare without SoulBot too.

SoulRun hands the model SoulBot's wording word for word, SoulBot's send layer must accept SoulRun's blocks, a
SoulBot host loads engine modules by name, and the documents share SoulBot's footers, policy sections and license.
The tests read SoulBot itself when it is beside this repository; elsewhere (CI) they read
``tests/soulbot_samples.json``, recorded here from SoulBot. With SoulBot beside, a test runs ``--check`` so the
samples never fall behind it. Nothing in SoulBot is imported; only two pure functions are taken out of ``agent.py``
by their syntax tree and run, as the tests always did.

    python tools/record_soulbot_samples.py            # record from SoulBot beside this repository
    python tools/record_soulbot_samples.py --check    # fail when the samples are not SoulBot's today

The same environment variables as the tests say where SoulBot is: SOULRUN_TEST_AGENT_PY (its agent template),
SOULRUN_TEST_SOULBOT_SRC (its ``src``), SOULRUN_TEST_SOULBOT_DOCS (its repository root).

Once SoulBot's ``agent.py`` is itself a SoulRun entry (it calls soulrun and no longer carries the wording), SoulRun
is where that wording lives: the parts recorded from ``agent.py`` (AGENT_KEYS) stay as last recorded from SoulBot's
own wording, and only the host and document parts are recorded and checked against SoulBot today.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ROOT / "tests" / "soulbot_samples.json"
SOULBOT = ROOT.parent / "SoulBot"
FOOTER_HEADING = "## AIXP Labs [aixp.dev](https://aixp.dev)"
POLICY_DOCUMENTS = ("CODE_OF_CONDUCT.md", "CONTRIBUTING.md", "CONTRIBUTING_CN.md", "GOVERNANCE.md", "SECURITY.md")
ENGINE = Path("engine") / "dir"                     # any folder: SoulRun's side and SoulBot's get the same one

# Every branch of the interruption note: a run's context as the engine hands it to the host, case by case.
BASE = {"cache_dir": "runs/7", "cache_name": "7", "stop_id": "s-1", "public_note": "这一场停在第 3 步。", "question_id": "q001-abc",
        "public_block_ref": "⟦engine:7/menu.q001-abc.txt⟧", "human_note": "", "user_language": "zh"}
CASES = {
    "nothing to say": {},
    "a plain run": {},
    "the human stopped and wrote something": dict(stop_judge=True, judge_id="j-1", allowed=["continue", "stop", "ask"],
                                                  triggers=["继续", "停"], run_state_at_stop="RUNNING", stopped_node="NLU",
                                                  stopped_visit=1, human_message="先停一下", context_sha256="abc123", context="上下文"),
    "a supply question": dict(stop_question=True, question_source="supply_doubt"),
    "a restart question": dict(stop_question=True, question_source="restart_doubt"),
    "a stop question": dict(stop_question=True, question_source=None),
    "a stop question without a note": dict(stop_question=True, question_source=None, public_note=None),
    "a new task": dict(stop_new_task=True, superseded_from="6"),
    "a held machine message": dict(stop_hold=True, hold_reason="machine_message", stop_state="GATED"),
    "a held human message": dict(stop_hold=True, hold_reason="human", stop_state="GATED"),
    "an authorized supply wait": dict(supply_authorized=True, authorized_by="human"),
    "a supply hold": dict(supply_hold=True),
    "cancelled after a stop": dict(interrupted_cancel=True, stop_ended=True, ended_by="human"),
    "cancelled": dict(interrupted_cancel=True),
    "asked to confirm": dict(interrupted_confirm=True, original_request="第一行\n第二行", interrupted_node="CastHexagram"),
    "continued after a stop": dict(interrupted_reentry=True, stop_continue=True, continued_by="human",
                                   recorded_choice_label="继续这一场"),
    "resumed after a supply wait": dict(interrupted_reentry=True, supply_resume=True),
    "re-entered": dict(interrupted_reentry=True),
    "re-entered with a note from the human": dict(interrupted_reentry=True, human_note="刚才断线了"),
}
LANGUAGE_CODES = ["zh", "en", "ja", "ko", "fr", None, ""]


def agent_py() -> Path:
    return Path(os.environ.get("SOULRUN_TEST_AGENT_PY") or SOULBOT / "examples" / "simple" / "Soul_Agent" / "agent.py")


AGENT_KEYS = ("agent_py_sha256", "interruption_notes", "language_names")    # what record() takes from agent.py


def is_soulrun_entry(path: Path) -> bool:
    """True when this agent.py hands every turn to SoulRun (a SoulRun entry), so it carries none of the wording."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return False
    return bool(re.search(r"""engine_backend\s*=\s*['"]soulrun['"]""", text) or re.search(r"^\s*from soulrun import", text, re.M))


def wording_live() -> bool:
    """SoulBot's agent.py is here and still carries the wording SoulRun hands the model."""
    path = agent_py()
    return path.is_file() and not is_soulrun_entry(path)


def soulbot_package() -> Path:
    return Path(os.environ.get("SOULRUN_TEST_SOULBOT_SRC") or SOULBOT / "src") / "soulbot"


def soulbot_docs() -> Path:
    return Path(os.environ.get("SOULRUN_TEST_SOULBOT_DOCS") or SOULBOT)


def context(case: str) -> dict:
    """The context the engine would hand over in that case ({} when there is nothing to say)."""
    return {} if case == "nothing to say" else {**BASE, **CASES[case]}


def language_context(code: str | None) -> dict:
    return {"user_language": code} if code is not None else {}


def neutral(text: str | None, engine: Path = ENGINE) -> str | None:
    """A note with the engine folder written as {ENGINE} and forward slashes after it: the same on every machine."""
    if text is None:
        return None
    text = text.replace(str(engine.resolve()), "{ENGINE}")
    return re.sub(r"\{ENGINE\}\S*", lambda m: m.group(0).replace("\\", "/"), text)


def original(name: str, engine: Path = ENGINE):
    """One of agent.py's functions as SoulBot has it, taken out by its syntax tree (agent.py itself is not run)."""
    path = agent_py()
    tree = ast.parse(path.read_text(encoding="utf-8"))
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
    namespace: dict = {"_ENGINE_AIAP_DIR": engine}
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), "exec"), namespace)
    return namespace[name]


def turn_policy_source() -> str:
    """SoulBot's reader of the blocks (its send layer), as source text."""
    source = (soulbot_package() / "models" / "acp_llm.py").read_text(encoding="utf-8")
    function = next(n for n in ast.walk(ast.parse(source)) if isinstance(n, ast.FunctionDef) and n.name == "_engine_turn_policy")
    return ast.get_source_segment(source, function)


def turn_policy(source: str):
    """The reader, ready to call."""
    import datetime as _datetime
    namespace = {"re": re, "hashlib": hashlib, "datetime": _datetime.datetime}
    exec(source, namespace)
    return namespace["_engine_turn_policy"]


def host_modules() -> list[str]:
    """The engine modules SoulBot's host loads by name (its templates hold the engine itself and are not looked at)."""
    package = soulbot_package()
    loaded: set[str] = set()
    for path in package.rglob("*.py"):
        if "templates" not in path.relative_to(package).parts:
            loaded |= set(re.findall(r"""import_module\(\s*["']([A-Za-z_.]+)["']""", path.read_text(encoding="utf-8", errors="replace")))
    return sorted(loaded)


def footer(text: str) -> str:
    return text[text.rfind(FOOTER_HEADING):]


def policy(text: str) -> dict:
    return {"headings": re.findall(r"^##+ .+$", text, re.M), "last_line": text.rstrip().splitlines()[-1]}


def soulruns_license(text: str) -> str:
    return text.replace("AIXP.dev | SoulBot.dev", "AIXP.dev | SoulRun.dev")


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def record() -> dict:
    docs = soulbot_docs()
    if wording_live():
        agent_source = agent_py().read_bytes().decode("utf-8").replace("\r\n", "\n")
        interruption, language = original("_interruption_block"), original("_language_name")
        from_agent = {
            "agent_py_sha256": _sha256(agent_source),
            "interruption_notes": {case: {"context": context(case), "note": neutral(interruption(context(case)))} for case in CASES},
            "language_names": [{"context": language_context(code), "name": language(language_context(code))} for code in LANGUAGE_CODES]
            + [{"context": None, "name": language(None)}],
        }
    else:   # agent.py is a SoulRun entry: the wording lives in SoulRun, as last recorded from SoulBot's own agent.py
        current = load()
        from_agent = {key: current[key] for key in AGENT_KEYS}
    return {
        "about": "SoulBot's side of the comparisons in tests/, recorded by tools/record_soulbot_samples.py; do not edit by hand",
        **from_agent,
        "turn_policy_source": turn_policy_source(),
        "host_modules": host_modules(),
        "readme_footers": {name: footer((docs / name).read_text(encoding="utf-8")) for name in ("README.md", "README_CN.md")},
        "policy_documents": {name: policy((docs / name).read_text(encoding="utf-8")) for name in POLICY_DOCUMENTS},
        "license_as_soulruns_sha256": _sha256(soulruns_license((docs / "LICENSE").read_text(encoding="utf-8"))),
    }


def dump(samples: dict) -> str:
    return json.dumps(samples, ensure_ascii=False, indent=1) + "\n"


def load() -> dict:
    return json.loads(SAMPLES.read_text(encoding="utf-8"))


def soulbot_is_beside() -> bool:
    return agent_py().is_file() and (soulbot_package() / "models" / "acp_llm.py").is_file() and (soulbot_docs() / "README.md").is_file()


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0], allow_abbrev=False)
    parser.add_argument("--check", action="store_true", help="only report whether the samples are SoulBot's today")
    args = parser.parse_args(argv)
    if not soulbot_is_beside():
        print("SoulBot is not beside this repository (or where the SOULRUN_TEST_* variables say): nothing to record from")
        return 2
    text = dump(record())
    current = SAMPLES.read_text(encoding="utf-8") if SAMPLES.is_file() else ""
    if args.check:
        if current != text:
            print("tests/soulbot_samples.json is not SoulBot's today; run python tools/record_soulbot_samples.py")
            return 1
        print("tests/soulbot_samples.json matches SoulBot" + ("" if wording_live() else
              " (its agent.py is a SoulRun entry: the wording parts are SoulRun's own, as last recorded)"))
        return 0
    SAMPLES.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {SAMPLES.relative_to(ROOT).as_posix()} ({len(text):,} chars)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

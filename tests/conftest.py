"""Shared fixtures. Every test works in pytest's temporary folder; nothing is written into the repository."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
# By default the tests run against the source tree, without installing. Set SOULRUN_TEST_INSTALLED=1 to
# run the same tests against the copy that is installed in the interpreter (a wheel in a virtual
# environment): the source tree is then kept off the import path, and the run stops if it is used anyway.
INSTALLED = os.environ.get("SOULRUN_TEST_INSTALLED", "").strip().lower() in ("1", "true", "yes")
if not INSTALLED:
    sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))


def _package_dir() -> Path:
    try:
        import soulrun as package
    except ImportError as error:
        raise pytest.UsageError("SOULRUN_TEST_INSTALLED is set, but no soulrun is installed in this interpreter") from error
    return Path(package.__file__).resolve().parent


def pytest_report_header(config):
    where = "the installed copy" if INSTALLED else "the source tree"
    return f"soulrun under test: {where} ({_package_dir()})"


def pytest_sessionstart(session):
    inside_source = _package_dir().is_relative_to((ROOT / "src").resolve())
    if INSTALLED and inside_source:
        raise pytest.UsageError("SOULRUN_TEST_INSTALLED is set, but the soulrun that was imported is the source tree")
    if not INSTALLED and not inside_source:
        raise pytest.UsageError("the soulrun that was imported is not this source tree; set SOULRUN_TEST_INSTALLED=1 to test an installed copy")

# Two small AIAP programs and one AISP skill, in the shape the engine's own registry tests use.
AIAP_DOC = [
    {"role": "system", "content": {"protocol": "AIAP V1.0.0", "axiom_0": "Human_Sovereignty_and_Wellbeing", "id": "demo.main",
                                   "name": "Demo AIAP", "version": "1.2.3", "summary": "Demo AIAP package: says hello",
                                   "flow_format": "mermaid", "loading_mode": "normal", "trust_level": 3}},
    {"role": "user", "content": {"instruction": "ASSERT RUN aisop.main", "user_input": "{user_input}",
                                 "aisop": {"main": "graph TD\n    Start[入口] --> endNode((End))"},
                                 "functions": {"Start": {"step1": "做", "Error": "e"}}}},
]
AISP_DOC = [
    {"role": "system", "content": {"protocol": "AISP V1.0.0", "id": "demo_aisp", "name": "Demo Skill", "version": "0.1.0",
                                   "summary": "Demo AISP skill: says hello", "flow_format": "mermaid", "loading_mode": "node"}},
    {"role": "user", "content": {"instruction": "RUN aisop.main", "user_input": "{user_input}",
                                 "aisp_contract": {"profile": "aisp.skill.v1", "discovery": {"category": "demo", "tags": ["demo"]},
                                                   "invocation": {"when_to_use": ["run the demo skill"]}, "risk_level": "low"},
                                 "aisop": {"main": "graph TD\n    s[Start] --> e((End))"}, "functions": {"s": {"step1": "do"}}}},
]


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def make_agent(root: Path) -> Path:
    """<root>/aiap/{demo_aiap, other_aiap} and <root>/aisp/demo_aisp - plain folders, no registry scripts."""
    write_json(root / "aiap" / "demo_aiap" / "main.aisop.json", AIAP_DOC)
    other = json.loads(json.dumps(AIAP_DOC))
    other[0]["content"].update(id="other.main", name="Other AIAP", summary="Other AIAP package: draws a card")
    write_json(root / "aiap" / "other_aiap" / "main.aisop.json", other)
    write_json(root / "aisp" / "demo_aisp" / "aisp.aisop.json", AISP_DOC)
    return root


@pytest.fixture(autouse=True)
def _clean_environment(monkeypatch):
    for name in ("SOULRUN_CACHE_DIR", "SOULRUN_AGENT_DIR", "SOULRUN_INLINE_PROGRAM", "SOULRUN_SLIM_PROGRAM",
                 "SOULBOT_RESUME_INTERRUPTED_RUNS", "CACHE_NUM", "SOULBOT_SUPPLY_WAIT_MAX_SECONDS", "SOULBOT_HOST_REPORT_WAIT_S"):
        monkeypatch.delenv(name, raising=False)          # the engine's own settings too: no test depends on this machine's
    monkeypatch.setenv("PYTHONDONTWRITEBYTECODE", "1")
    # The `python` a model's shell would find (soulrun --doctor runs it) is the interpreter running these tests,
    # whatever python this machine's PATH happens to hold, or none: no test depends on it.
    monkeypatch.setenv("PATH", str(Path(sys.executable).parent) + os.pathsep + os.environ.get("PATH", ""))


@pytest.fixture
def agent(tmp_path, monkeypatch) -> Path:
    """A fresh agent folder; the current folder for the test, as the plan's default expects."""
    root = make_agent(tmp_path / "agent")
    monkeypatch.chdir(root)
    return root


@pytest.fixture
def soulrun():
    import soulrun as package
    return package


@pytest.fixture
def subprocess_env() -> dict:
    env = dict(os.environ)
    if not INSTALLED:
        env["PYTHONPATH"] = str(ROOT / "src") + os.pathsep + env.get("PYTHONPATH", "")
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    for name in ("SOULRUN_CACHE_DIR", "SOULRUN_AGENT_DIR", "SOULRUN_INLINE_PROGRAM", "SOULRUN_SLIM_PROGRAM"):
        env.pop(name, None)
    return env

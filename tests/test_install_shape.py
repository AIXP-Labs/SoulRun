"""What an installed SoulRun looks like: only the files the wheel carries, and they are enough to work."""
from __future__ import annotations

import fnmatch
import json
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

from conftest import ROOT, make_agent

PACKAGE = ROOT / "src" / "soulrun"
EXCLUDE = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["tool"]["hatch"]["build"]["targets"]["wheel"]["exclude"]


def _excluded(relative_to_root: str) -> bool:
    for pattern in EXCLUDE:
        plain = pattern[3:] if pattern.startswith("**/") else pattern
        parts = relative_to_root.split("/")
        if pattern.startswith("**/"):
            if plain in parts:
                return True
        elif fnmatch.fnmatch(relative_to_root, plain) or relative_to_root.startswith(plain.rstrip("*") if plain.endswith("*") else plain + "/"):
            return True
    return False


@pytest.fixture(scope="module")
def installed(tmp_path_factory) -> Path:
    """A folder holding exactly the package files the wheel would carry (the wheel's exclude list applied)."""
    site = tmp_path_factory.mktemp("site")
    for path in PACKAGE.rglob("*"):
        relative = path.relative_to(ROOT).as_posix()
        if path.is_file() and not _excluded(relative) and path.suffix != ".pyc":
            target = site / path.relative_to(ROOT / "src")
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
    return site


def test_the_installed_engine_files_are_exactly_the_manifests_installed_set(installed):
    manifest = json.loads((PACKAGE / "engine_manifest.json").read_text(encoding="utf-8"))
    engine = installed / "soulrun" / "soulrun_aiap"
    present = sorted(p.relative_to(engine).as_posix() for p in engine.rglob("*") if p.is_file())
    assert len(present) == manifest["installed_file_count"] == manifest["file_count"]
    assert not any(name.startswith(("tests/", "RELEASE")) or name == "pytest.ini" for name in present)
    assert {"main.aisop.json", "agent_engine.aisop.json", "python_tools/next_node.py", "python_tools/lib/engine_core.py"} <= set(present)


def test_an_installed_copy_runs_without_the_repository_only_files(installed, tmp_path):
    agent = make_agent(tmp_path / "agent")
    script = (
        "import json, soulrun\n"
        "assert soulrun().kind == 'guide'\n"
        "ctx = soulrun(user_message='请运行 demo：跟我打个招呼', session_id='inst', model='codex-acp/gpt-5.6', host_tools={'agent': False})\n"
        "node = soulrun(cmd='next-node', cache_dir=ctx.cache_dir).json()\n"
        "from soulrun import _engine\n"
        "print(json.dumps({'kind': ctx.kind, 'node': node['node']['name'], 'engine': soulrun.__file__, 'verify': _engine.verify()}))\n"
    )
    env = {**__import__("os").environ, "PYTHONPATH": str(installed), "PYTHONDONTWRITEBYTECODE": "1", "PYTHONIOENCODING": "utf-8"}
    done = subprocess.run([sys.executable, "-B", "-X", "utf8", "-c", script], cwd=str(agent), env=env,
                          capture_output=True, text=True, encoding="utf-8")
    assert done.returncode == 0, done.stdout + done.stderr
    result = json.loads(done.stdout.strip().splitlines()[-1])
    assert result["kind"] == "program" and result["node"] == "Router.match" and result["verify"] == []
    assert Path(result["engine"]).resolve().is_relative_to(installed.resolve())


def test_verify_engine_from_the_command_line(installed, tmp_path):
    env = {**__import__("os").environ, "PYTHONPATH": str(installed), "PYTHONDONTWRITEBYTECODE": "1", "PYTHONIOENCODING": "utf-8"}
    ok = subprocess.run([sys.executable, "-B", "-X", "utf8", "-m", "soulrun", "--verify-engine"], cwd=str(tmp_path), env=env, capture_output=True)
    assert ok.returncode == 0 and ok.stdout.decode("utf-8").strip().endswith("unchanged")
    tampered = installed / "soulrun" / "soulrun_aiap" / "AIAP.md"
    original = tampered.read_bytes()
    try:
        tampered.write_bytes(original + b"\n")
        bad = subprocess.run([sys.executable, "-B", "-X", "utf8", "-m", "soulrun", "--verify-engine"], cwd=str(tmp_path), env=env, capture_output=True)
        assert bad.returncode == 1 and "changed: AIAP.md" in bad.stdout.decode("utf-8")
    finally:
        tampered.write_bytes(original)

"""SoulRun's engine: every file as its manifest records it, no development history, loaded from the bundle only."""
from __future__ import annotations

import json
import re
import subprocess
import sys
import tomllib
from pathlib import Path

from conftest import ROOT

ENGINE = ROOT / "src" / "soulrun" / "soulrun_aiap"
MANIFEST = ROOT / "src" / "soulrun" / "engine_manifest.json"


def test_every_engine_file_matches_the_recorded_fingerprint():
    done = subprocess.run([sys.executable, "-B", "-X", "utf8", str(ROOT / "tools" / "sync_engine.py"), "--check"],
                          capture_output=True, text=True, encoding="utf-8")
    assert done.returncode == 0, done.stdout + done.stderr


def test_the_manifest_states_version_source_and_digests(soulrun):
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert manifest["engine_version"] == soulrun.ENGINE_VERSION                  # whatever engine is bundled: its version
    assert re.fullmatch(r"\d+\.\d+\.\d+(?:(?:a|b|rc)\d+)?", manifest["engine_version"]), manifest["engine_version"]
    assert manifest["source"] and len(manifest["digest"]) == 64 and len(manifest["installed_digest"]) == 64
    # Only runtime files: everything the manifest records is installed with the package.
    assert manifest["file_count"] == len(manifest["files"]) == manifest["installed_file_count"]
    assert manifest["digest"] == manifest["installed_digest"]
    from soulrun import _engine
    info = soulrun.engine_info()
    # The package under test (the source tree, or an installed copy) carries this repository's manifest
    # and points at the engine inside itself.
    assert json.loads((_engine.ENGINE_DIR.parent / "engine_manifest.json").read_text(encoding="utf-8")) == manifest
    assert info["digest"] == manifest["digest"] and Path(info["engine_dir"]).resolve() == _engine.ENGINE_DIR.resolve()
    assert _engine.ENGINE_DIR.parent.resolve() == Path(soulrun.__file__).resolve().parent


def test_the_engine_has_no_third_party_imports():
    """SoulRun promises "standard library only"; that is only true while the engine keeps it true."""
    import ast
    own = {p.stem for p in (ENGINE / "python_tools").glob("*.py")} | {"lib"}
    foreign = set()
    for path in list((ENGINE / "python_tools").rglob("*.py")) + list((ENGINE / "tools").rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ImportFrom) and node.level:
                continue
            names = [a.name for a in node.names] if isinstance(node, ast.Import) else \
                [node.module or ""] if isinstance(node, ast.ImportFrom) else []
            for name in names:
                top = name.split(".")[0]
                if top and top not in sys.stdlib_module_names and top not in own:
                    foreign.add(top)
    engine_tools = {p.stem for p in (ENGINE / "tools").glob("*.py")}
    assert foreign - engine_tools == set()


def test_engine_modules_are_loaded_from_the_bundle(soulrun):
    from soulrun import _engine, host
    for name in ("prepare_cache", "lib.engine_core", "public_delivery_observer", "checkpoint_recovery"):
        module = host.engine(name)
        assert _engine.ENGINE_DIR.resolve() in Path(module.__file__).resolve().parents
    assert _engine.load("lib.engine_core").ENGINE_VERSION == soulrun.ENGINE_VERSION


def test_what_the_wheel_leaves_out_is_what_the_sync_tool_calls_not_installed():
    """pyproject.toml and tools/sync_engine.py must agree on which engine files are repository-only."""
    sys.path.insert(0, str(ROOT / "tools"))
    import sync_engine
    excluded = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["tool"]["hatch"]["build"]["targets"]["wheel"]["exclude"]
    prefix = "src/soulrun/soulrun_aiap/"
    from_pyproject = sorted(item[len(prefix):].rstrip("*") for item in excluded if item.startswith(prefix))
    assert from_pyproject == sorted(item.rstrip("/") for item in sync_engine.NOT_INSTALLED)


def test_the_two_program_texts_are_handed_out_unchanged(soulrun):
    from soulrun import _engine
    assert _engine.main_program_text() == (ENGINE / "main.aisop.json").read_text(encoding="utf-8")
    assert _engine.agent_program_text() == (ENGINE / "agent_engine.aisop.json").read_text(encoding="utf-8")
    assert _engine.main_program_text().count('"user_input": "{user_input}"') == 1


def test_the_canonical_engine_keeps_its_identity_and_verified_runtime_sources():
    """Historical feature selectors are executable text, not material to scrub."""
    sys.path.insert(0, str(ROOT / "tools"))
    import sync_engine
    assert sync_engine.canonical_problems(ENGINE, '1.0.0') == []
    assert json.loads(MANIFEST.read_text(encoding='utf-8'))['source_form'] == 'canonical'
    card = json.loads((ENGINE / "agent_card.json").read_text(encoding="utf-8"))
    assert card["name"] == "soulrun_aiap" and card["program_id"] == "dev.soulrun.soulrun_aiap"
    assert card["version"] == json.loads(MANIFEST.read_text(encoding="utf-8"))["engine_version"]
    assert not (ENGINE / "tests").exists() and not list(ENGINE.glob("RELEASE*")) and not (ENGINE / "pytest.ini").exists()


def test_the_engine_passes_its_own_aiap_conformance_check():
    """The engine is an AIAP program; its own checker (tools/aiap_conformance_check.py) finds no FAIL - the closing
    AIAP seal of its AIAP.md, among other things, survives the cleaning."""
    done = subprocess.run([sys.executable, "-B", str(ENGINE / "tools" / "aiap_conformance_check.py"), str(ENGINE)],
                          capture_output=True, text=True, encoding="utf-8")
    assert done.returncode == 0 and "FAIL count: 0" in done.stdout, done.stdout + done.stderr


def test_the_engines_own_integrity_records_hold():
    """The engine checks contracts/manifest.json when its contracts load, and its AIAP.md, agent_card.json and
    quality_baseline.json declare the governance hash of its programs: both must match the files."""
    done = subprocess.run([sys.executable, "-B", str(ENGINE / "tools" / "refresh_governance_hash.py"), str(ENGINE), "--check"],
                          capture_output=True, text=True, encoding="utf-8")
    assert done.returncode == 0, done.stdout + done.stderr
    load = ("import sys; from pathlib import Path; sys.path.insert(0, sys.argv[1]); from lib import contracts; "
            "print(len(contracts.load_dir(Path(sys.argv[2]))))")     # its own process: the engine's "lib" stays out of ours
    done = subprocess.run([sys.executable, "-B", "-c", load, str(ENGINE / "python_tools"), str(ENGINE / "contracts")],
                          capture_output=True, text=True, encoding="utf-8")
    assert done.returncode == 0 and int(done.stdout.strip()) > 0, done.stdout + done.stderr


def test_the_governance_document_keeps_current_rules_without_version_entries():
    text = (ENGINE / "AIAP.md").read_text(encoding="utf-8")
    assert not re.search(r"^#{2,3} (?:Historical Predecessor Versions|v\d+\.)", text, re.M)
    for heading in ("Governance Declaration", "Executor Runtime Notice", "Feature Overview", "Usage",
                    "Current Recovery Policy (SoulRun V1.0.0 candidate)", "SoulRun Version Policy"):
        assert text.count("## " + heading + "\n") == 1
    assert text.rstrip().endswith(
        "Align Axiom 0: Human Sovereignty and Wellbeing. Version: AIAP V1.0.0. www.aiap.dev")


def test_a_file_changed_together_with_its_line_in_the_manifest_is_still_found(soulrun, tmp_path, subprocess_env):
    """--verify-engine compares each file with the manifest beside it; a file changed and its line rewritten passes
    that, but no longer gives the digest the manifest records. --engine-info works the digest out from the files."""
    import hashlib
    import shutil
    copy = tmp_path / "copy"
    shutil.copytree(Path(soulrun.__file__).parent, copy / "soulrun", ignore=shutil.ignore_patterns("__pycache__"))
    changed = copy / "soulrun" / "soulrun_aiap" / "python_tools" / "next_node.py"
    changed.write_bytes(changed.read_bytes() + b"\n# changed\n")
    manifest_path = copy / "soulrun" / "engine_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["files"]["python_tools/next_node.py"] = hashlib.sha256(changed.read_bytes()).hexdigest()
    manifest_path.write_text(json.dumps(manifest, indent=1) + "\n", encoding="utf-8")
    env = dict(subprocess_env, PYTHONPATH=str(copy))

    def cli(*args):
        return subprocess.run([sys.executable, "-B", "-X", "utf8", "-m", "soulrun", *args], capture_output=True,
                              text=True, encoding="utf-8", env=env, cwd=str(tmp_path), timeout=120)
    verify = cli("--verify-engine")
    assert verify.returncode == 1 and "manifest: its file list no longer gives the installed_digest" in verify.stdout
    shown = json.loads(cli("--engine-info").stdout)
    assert shown["installed_digest_now"] != shown["installed_digest"]
    assert soulrun.engine_info()["installed_digest_now"] == soulrun.engine_info()["installed_digest"]   # the real one

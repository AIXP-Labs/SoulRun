"""tools/upgrade_engine.py: a newer engine in one step - cleaned on the way in - and back again.

Every run here works on a copy of the repository's src/soulrun and tools in a temporary folder - the tool
finds its repository from its own location - so the engine bundled in this repository is never touched.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

import soulbot_side
from conftest import ROOT
from legacy_snapshot import unpack

SKIP = shutil.ignore_patterns("__pycache__", ".pytest_cache", ".execution_cache", "*.pyc")
CORE = Path("python_tools") / "lib" / "engine_core.py"
def _known_leftovers() -> dict:
    import importlib.util
    spec = importlib.util.spec_from_file_location("clean_engine_rules", ROOT / "tools" / "clean_engine.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.KNOWN_LEFTOVERS


KNOWN_LEFTOVERS = _known_leftovers()               # what the bundled engine still carries, cleaned with the next one
# The bundled engine's version, whatever it is now, a newer one to bring in and an older one: no test here names a
# version that the next engine brought in would make wrong.
CURRENT = json.loads((ROOT / "src" / "soulrun" / "engine_manifest.json").read_text(encoding="utf-8"))["engine_version"]
_MAJOR, _MINOR, _PATCH = (int(re.match(r"\d+", part).group(0)) for part in CURRENT.split(".")[:3])
NEWER, OLDER = f"{_MAJOR}.{_MINOR}.{_PATCH + 1}", "0.0.1"


def _snapshot(repo: Path) -> dict:
    package = repo / "src" / "soulrun"
    return {p.relative_to(repo).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in package.rglob("*") if p.is_file() and "__pycache__" not in p.parts}


def _engine_version(tree: Path) -> str:
    return re.search(r'ENGINE_VERSION = "([^"]+)"', (tree / CORE).read_text(encoding="utf-8")).group(1)


def _package_version(repo: Path) -> str:
    return re.search(r'^__version__ = "([^"]+)"$', (repo / "src" / "soulrun" / "__init__.py").read_text(encoding="utf-8"), re.M).group(1)


@pytest.fixture
def repo(tmp_path) -> Path:
    copy = tmp_path / "repo"
    unpack(copy / 'src/soulrun', 'src/soulrun/')
    shutil.copytree(ROOT / "tools", copy / "tools", ignore=SKIP)
    for document in ROOT.glob("*.md"):                  # where the documents name the engine's version
        shutil.copy2(document, copy / document.name)
    return copy


def _newer(repo: Path, tmp_path: Path, *, new_section: bool = False, history: str = "# alpha.200 (doc 999): a newer rule") -> Path:
    """A newer engine tree as it would come from upstream: the bundled one with a file added, a development note in
    a comment, its own tests and release notes beside it and, if asked, a new main-program section."""
    tree = tmp_path / "newer_engine"
    shutil.copytree(repo / "src" / "soulrun" / "soulrun_aiap", tree, ignore=SKIP)
    core = tree / CORE
    core.write_bytes(core.read_bytes() + f"\n{history}\nNEWER_RULE = True\n".encode("utf-8"))
    (tree / "NEW_IN_THIS_ENGINE.md").write_text("added by the newer engine\n", encoding="utf-8", newline="\n")
    (tree / "tests").mkdir()
    (tree / "tests" / "test_newer.py").write_text("def test_x():\n    pass\n", encoding="utf-8")
    (tree / "RELEASE-newer.md").write_text("internal notes\n", encoding="utf-8")
    if new_section:
        main = tree / "main.aisop.json"
        doc = json.loads(main.read_text(encoding="utf-8"))
        doc[0]["content"]["brand_new_contract"] = "a section this engine added"
        main.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    return tree


def _run(repo: Path, *args: str) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k != "SOULRUN_TEST_AGENT_PY"}   # no SoulBot beside the copy
    args = (*args, '--legacy-clean') if '--from' in args else args
    return subprocess.run([sys.executable, "-B", "-X", "utf8", str(repo / "tools" / "upgrade_engine.py"), *args],
                          capture_output=True, text=True, encoding="utf-8", env=env, cwd=repo.parent, timeout=600)


def _tool(repo: Path, name: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-B", "-X", "utf8", str(repo / "tools" / name), *args],
                          capture_output=True, text=True, encoding="utf-8", timeout=600)


def test_the_engine_version_is_required(repo, tmp_path):
    done = _run(repo, "--from", str(_newer(repo, tmp_path)))
    assert done.returncode == 2 and "--engine-version is required" in done.stderr


def test_a_dry_run_shows_the_plan_and_changes_nothing(repo, tmp_path):
    tree = _newer(repo, tmp_path)
    before = _snapshot(repo)
    done = _run(repo, "--from", str(tree), "--engine-version", NEWER, "--dry-run")
    assert done.returncode == 0, done.stdout + done.stderr
    assert f"engine   {CURRENT} -> {NEWER}" in done.stdout and "dry run: nothing was changed" in done.stdout
    assert "added: NEW_IN_THIS_ENGINE.md" in done.stdout and "changed: python_tools/lib/engine_core.py" in done.stdout
    assert "tests/" not in done.stdout.split("engine   ")[1] and "RELEASE-newer.md" not in done.stdout   # never brought in
    assert _snapshot(repo) == before and not (repo / ".engine_backups").exists()        # not even an empty folder


def _kept_dirs(repo: Path) -> list[Path]:
    return [p for p in (repo / ".engine_backups").iterdir() if p.is_dir() and not p.name.startswith(".")]


def test_the_same_engine_again_is_nothing_to_do_and_a_broken_bundle_is_not_hidden(repo, tmp_path):
    tree = _newer(repo, tmp_path)
    assert _run(repo, "--from", str(tree), "--engine-version", NEWER).returncode == 0
    before = _snapshot(repo)
    again = _run(repo, "--from", str(tree), "--engine-version", NEWER)
    assert again.returncode == 0 and "nothing to do" in again.stdout, again.stdout + again.stderr
    assert _snapshot(repo) == before
    (repo / "src" / "soulrun" / "engine_node.aisop.json").write_text("{}", encoding="utf-8")       # the slim program broken
    broken = _run(repo, "--from", str(tree), "--engine-version", NEWER)
    assert broken.returncode == 1 and "python tools/build_engine_node.py" in broken.stdout


def test_the_bundled_engine_brought_in_again(repo, tmp_path):
    """Brought in again, the bundled engine is cleaned by today's rules. While KNOWN_LEFTOVERS names files, the rules
    change them, so the version must change too (or --same-version say it is meant); once the list is empty - the
    next engine was cleaned in full - the cleaned engine is the bundled one and there is nothing to do."""
    same = tmp_path / "same_engine"
    shutil.copytree(repo / "src" / "soulrun" / "soulrun_aiap", same, ignore=SKIP)
    before = _snapshot(repo)
    done = _run(repo, "--from", str(same), "--engine-version", CURRENT)
    if KNOWN_LEFTOVERS:
        assert done.returncode == 1 and f"its version stays {CURRENT}" in done.stdout and _snapshot(repo) == before
        assert _run(repo, "--from", str(same), "--engine-version", CURRENT, "--same-version", "--dry-run").returncode == 0
    else:
        assert done.returncode == 0 and "nothing to do" in done.stdout and _snapshot(repo) == before


@pytest.mark.parametrize("version", ["../../escaped", "v1.0.1", '1.0.1"x', "not a version", "1.0"])
def test_an_engine_version_that_is_not_a_release_version_is_refused(repo, tmp_path, version):
    before = _snapshot(repo)
    done = _run(repo, "--from", str(_newer(repo, tmp_path)), "--engine-version", version)
    assert done.returncode == 1 and "is not a release version" in done.stderr and _snapshot(repo) == before
    assert not (repo / ".engine_backups").exists() or not _kept_dirs(repo)


def test_going_back_to_a_lower_version_is_noted(repo, tmp_path):
    done = _run(repo, "--from", str(_newer(repo, tmp_path)), "--engine-version", OLDER, "--dry-run")
    assert done.returncode == 0 and f"is lower than the bundled {CURRENT}" in done.stdout


def test_an_upgrade_is_cleaned_on_the_way_in_and_the_way_back_restores_every_byte(repo, tmp_path):
    tree = _newer(repo, tmp_path)
    before, old_package = _snapshot(repo), _package_version(repo)

    done = _run(repo, "--from", str(tree), "--engine-version", NEWER)
    assert done.returncode == 0, done.stdout + done.stderr
    engine = repo / "src" / "soulrun" / "soulrun_aiap"
    manifest = json.loads((repo / "src" / "soulrun" / "engine_manifest.json").read_text(encoding="utf-8"))
    assert manifest["engine_version"] == _engine_version(engine) == NEWER and manifest["source"] == f"SoulRun engine {NEWER}"
    assert _package_version(repo) == old_package                       # SoulRun's own version does not follow the engine
    assert (engine / "NEW_IN_THIS_ENGINE.md").is_file()
    assert not (engine / "tests").exists() and not (engine / "RELEASE-newer.md").exists()
    core = (engine / CORE).read_text(encoding="utf-8")
    assert "# a newer rule\nNEWER_RULE = True" in core and "alpha.200" not in core and "doc 999" not in core
    assert _tool(repo, "sync_engine.py", "--check").returncode == 0
    assert _tool(repo, "build_engine_node.py", "--check").returncode == 0
    assert _tool(repo, "clean_engine.py", "--check", str(engine)).returncode == 0
    assert subprocess.run([sys.executable, "-B", str(engine / "tools" / "refresh_governance_hash.py"), str(engine), "--check"],
                          capture_output=True).returncode == 0
    assert "SoulBot's agent.py not found" in done.stdout and "python -m pytest" in done.stdout
    assert "calls    the new engine takes every call SoulRun makes" in done.stdout
    assert f"docs     engine version {NEWER} written in DEPENDENCIES.md, DEPENDENCIES_CN.md, GUIDE.md" in done.stdout
    assert f"SoulRun engine `{NEWER}`" in (repo / "DEPENDENCIES.md").read_text(encoding="utf-8")
    kept = _kept_dirs(repo)
    assert len(kept) == 1 and kept[0].name.startswith(f"{CURRENT}-") and "-drifted-" not in kept[0].name
    texts = list((repo / ".engine_backups").glob(f"cleaned-texts-{NEWER}-*.txt"))
    assert len(texts) == 1
    if KNOWN_LEFTOVERS:                                # a known leftover of the bundled engine is cleaned on the way in
        assert any(name in texts[0].read_text(encoding="utf-8") for name in KNOWN_LEFTOVERS)
    assert sorted(p.name for p in kept[0].iterdir()) == ["engine_manifest.json", "engine_node.aisop.json", "soulrun_aiap.zip"]
    with zipfile.ZipFile(kept[0] / "soulrun_aiap.zip") as archive:
        assert f'ENGINE_VERSION = "{CURRENT}"' in archive.read("python_tools/lib/engine_core.py").decode("utf-8")

    back = _run(repo, "--restore", str(kept[0]))
    assert back.returncode == 0, back.stdout + back.stderr
    assert f"{CURRENT} restored, files match the kept manifest" in back.stdout
    assert _snapshot(repo) == before                 # byte for byte, the manifest too (the kept one is put back as it was)
    assert all((repo / d.name).read_bytes() == d.read_bytes() for d in ROOT.glob("*.md"))        # the documents too


def test_history_the_rules_do_not_know_stops_the_upgrade_before_anything_changes(repo, tmp_path):
    tree = _newer(repo, tmp_path, history="# reviewed by Codex before the release")
    before = _snapshot(repo)
    done = _run(repo, "--from", str(tree), "--engine-version", NEWER)
    assert done.returncode == 1 and "development history are left" in done.stdout and "nothing was changed" in done.stdout
    assert "Codex" in done.stdout and _snapshot(repo) == before


def test_a_section_the_arrangement_does_not_place_fails_the_upgrade(repo, tmp_path):
    tree = _newer(repo, tmp_path, new_section=True)
    before = _snapshot(repo)
    done = _run(repo, "--from", str(tree), "--engine-version", NEWER)
    assert done.returncode == 1
    assert "PROBLEM: main.aisop.json section 'brand_new_contract' has no place in the arrangement" in done.stdout
    assert 'place new sections in tools/build_engine_node.py' in done.stdout
    assert _tool(repo, "build_engine_node.py", "--check").returncode == 0 and _snapshot(repo) == before


def test_a_program_file_the_builder_cannot_read_is_reported_not_raised(repo, tmp_path):
    tree = _newer(repo, tmp_path)
    main = tree / "main.aisop.json"
    doc = json.loads(main.read_text(encoding="utf-8"))
    main.write_text(json.dumps([doc[1], doc[0]], ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    done = _run(repo, "--from", str(tree), "--engine-version", NEWER)
    assert done.returncode == 1 and "Traceback" not in done.stdout + done.stderr
    assert "PROBLEM: engine_node.aisop.json could not be rebuilt: ValueError: main.aisop.json: expected the two parts" in done.stdout
    assert "nothing was changed" in done.stdout and not _kept_dirs(repo)


def test_a_damaged_backup_is_refused_before_anything_changes(repo, tmp_path):
    tree = _newer(repo, tmp_path)
    assert _run(repo, "--from", str(tree), "--engine-version", NEWER).returncode == 0
    kept = _kept_dirs(repo)[0]
    archive = kept / "soulrun_aiap.zip"
    data = bytearray(archive.read_bytes())
    data[len(data) // 3: len(data) // 3 + 64] = b"\0" * 64                  # damage file contents inside the zip
    archive.write_bytes(bytes(data))
    before = _snapshot(repo)
    back = _run(repo, "--restore", str(kept))
    assert back.returncode == 1 and "is damaged" in back.stderr and "nothing was changed" in back.stderr
    assert _snapshot(repo) == before and [p.name for p in _kept_dirs(repo)] == [kept.name]
    archive.write_bytes(b"not a zip at all")
    assert "is damaged (BadZipFile" in _run(repo, "--restore", str(kept)).stderr and _snapshot(repo) == before


def _kept_by_hand(repo: Path, change=None, extra: dict | None = None) -> Path:
    """A kept engine made by hand: the bundled files (one changed by `change`), plus `extra` members, and a manifest
    that matches what is in the archive - so only what the test is about can be wrong."""
    kept = repo / ".engine_backups" / "old-engine"
    kept.mkdir(parents=True)
    engine = repo / "src" / "soulrun" / "soulrun_aiap"
    files = {}
    with zipfile.ZipFile(kept / "soulrun_aiap.zip", "w") as archive:
        for path in sorted(p for p in engine.rglob("*") if p.is_file() and "__pycache__" not in p.parts):
            name = path.relative_to(engine).as_posix()
            data = change(name, path.read_bytes()) if change else path.read_bytes()
            archive.writestr(name, data)
            files[name] = hashlib.sha256(data).hexdigest()
        for name, data in (extra or {}).items():
            archive.writestr(name, data)
    manifest = json.loads((repo / "src" / "soulrun" / "engine_manifest.json").read_text(encoding="utf-8"))
    (kept / "engine_manifest.json").write_text(json.dumps(dict(manifest, files=files), indent=1), encoding="utf-8")
    return kept


def test_a_kept_engine_that_was_never_cleaned_is_refused(repo, tmp_path):
    kept = _kept_by_hand(repo, lambda name, data: data + (b"\n# alpha.12: an old note\n" if name == CORE.as_posix() else b""))
    before = _snapshot(repo)
    back = _run(repo, "--restore", str(kept))
    assert back.returncode == 1 and "never cleaned" in back.stderr and _snapshot(repo) == before


def test_a_kept_engine_that_differs_from_its_kept_manifest_is_refused(repo, tmp_path):
    kept = _kept_by_hand(repo)
    with zipfile.ZipFile(kept / "soulrun_aiap.zip", "a") as archive:
        archive.writestr("slipped_in.py", "x = 1\n")                       # in the archive, not in the kept manifest
    before = _snapshot(repo)
    back = _run(repo, "--restore", str(kept))
    assert back.returncode == 1 and "does not match the manifest kept with it" in back.stderr
    assert "not in the kept manifest: slipped_in.py" in back.stderr and _snapshot(repo) == before


def test_a_kept_archive_naming_a_file_outside_the_engine_is_refused(repo, tmp_path):
    kept = _kept_by_hand(repo, extra={"../outside.txt": "x"})
    before = _snapshot(repo)
    back = _run(repo, "--restore", str(kept))
    assert back.returncode == 1 and "is unsafe" in back.stderr and "../outside.txt" in back.stderr
    assert _snapshot(repo) == before and not (repo / ".engine_backups" / "outside.txt").exists()


def test_an_engine_that_does_not_take_soulruns_calls_is_reported_with_the_way_back(repo, tmp_path):
    tree = _newer(repo, tmp_path)
    core = tree / CORE
    text = core.read_text(encoding="utf-8")
    signature = re.search(r"def init_run\([^)]*\)", text, re.S).group(0)
    core.write_text(text.replace(signature, signature.replace("registry_roots", "roots"), 1), encoding="utf-8", newline="\n")
    done = _run(repo, "--from", str(tree), "--engine-version", NEWER)
    assert done.returncode == 1 and "PROBLEM: lib.engine_core.init_run: takes no parameter registry_roots" in done.stdout
    assert 'Preflight failed; nothing was changed' in done.stdout and not _kept_dirs(repo)


def test_a_copy_that_fails_half_way_leaves_the_bundled_engine_as_it_was(repo, tmp_path, monkeypatch):
    import importlib.util
    spec = importlib.util.spec_from_file_location("sync_engine_copy", repo / "tools" / "sync_engine.py")
    sync = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sync)
    tree = _newer(repo, tmp_path)                                   # made before copytree is replaced below
    before = _snapshot(repo)

    def half_copy(source, target, **kwargs):
        Path(target).mkdir(parents=True)
        (Path(target) / "only_one_file.py").write_text("x = 1\n", encoding="utf-8")
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(sync.shutil, "copytree", half_copy)
    with pytest.raises(OSError):
        sync.replace_engine(tree)
    assert _snapshot(repo) == before
    assert not (repo / "src" / "soulrun" / "soulrun_aiap.new").exists() and not (repo / "src" / "soulrun" / "soulrun_aiap.old").exists()


def test_a_bundled_engine_that_drifted_is_kept_under_a_name_that_says_so(repo, tmp_path):
    tree = _newer(repo, tmp_path)                                   # the newer engine is not touched by the hand change
    (repo / "src" / "soulrun" / "soulrun_aiap" / "AIAP.md").write_text("changed by hand\n", encoding="utf-8")
    done = _run(repo, "--from", str(tree), "--engine-version", NEWER)
    kept = _kept_dirs(repo)
    assert done.returncode == 0, done.stdout + done.stderr
    assert len(kept) == 1 and kept[0].name.startswith(f"{CURRENT}-drifted-")
    assert "changed: AIAP.md" in (kept[0] / "DRIFTED.txt").read_text(encoding="utf-8")


def test_the_sync_tool_takes_only_a_cleaned_tree(repo, tmp_path):
    tree = _newer(repo, tmp_path)
    before = _snapshot(repo)
    done = _tool(repo, "sync_engine.py", "--from", str(tree), "--label", "raw")
    assert done.returncode == 2 and "has not been cleaned" in done.stderr and _snapshot(repo) == before


def test_an_engine_that_already_differs_from_its_manifest_is_noted(repo, tmp_path):
    tree = _newer(repo, tmp_path)
    (repo / "src" / "soulrun" / "soulrun_aiap" / "AIAP.md").write_text("changed by hand\n", encoding="utf-8")
    done = _run(repo, "--from", str(tree), "--engine-version", NEWER, "--dry-run")
    assert done.returncode == 0 and "note     the bundled engine already differs from its manifest (1 problem(s), first: changed: AIAP.md)" in done.stdout


AGENT_PY = Path(os.environ.get("SOULRUN_TEST_AGENT_PY") or ROOT.parent / "SoulBot" / "examples" / "simple" / "Soul_Agent" / "agent.py")


@pytest.mark.skipif(not AGENT_PY.is_file(), reason="SoulBot's agent.py is not available on this machine")
def test_the_fixed_wording_is_checked_when_soulbot_is_there(repo, tmp_path):
    shutil.copy2(ROOT / 'src/soulrun/_agent_text.py', repo / 'src/soulrun/_agent_text.py')
    tree = _newer(repo, tmp_path)
    done = _run(repo, "--from", str(tree), "--engine-version", NEWER, "--agent-py", str(AGENT_PY))
    assert done.returncode == 0, done.stdout + done.stderr
    if soulbot_side.TOOL.is_soulrun_entry(AGENT_PY):               # SoulBot's template now hands every turn to SoulRun
        assert "wording  SoulBot's agent.py is a SoulRun entry" in done.stdout


def test_an_agent_template_that_is_a_soulrun_entry_is_not_compared_word_for_word(repo, tmp_path):
    entry = tmp_path / "agent.py"
    entry.write_text("from soulrun import run\n\nroot_agent = LlmAgent(name='x', engine_backend='soulrun')\n", encoding="utf-8")
    tree = _newer(repo, tmp_path)
    done = _run(repo, "--from", str(tree), "--engine-version", NEWER, "--agent-py", str(entry))
    assert done.returncode == 0, done.stdout + done.stderr
    assert "wording  SoulBot's agent.py is a SoulRun entry" in done.stdout


# ---- the refusals no other test sets off (doc 35 F89) ----------------------------------------------------------
def test_a_source_that_is_not_an_engine_or_is_the_bundled_one_is_refused(repo, tmp_path):
    before = _snapshot(repo)
    (tmp_path / "notes").mkdir()
    done = _run(repo, "--from", str(tmp_path / "notes"), "--engine-version", NEWER)
    assert done.returncode == 1 and "is not an engine tree" in done.stderr
    bundled = repo / "src" / "soulrun" / "soulrun_aiap"
    for source in (bundled, bundled / "python_tools" / ".."):
        done = _run(repo, "--from", str(source.resolve()), "--engine-version", NEWER)
        assert done.returncode == 1 and "is the bundled engine itself" in done.stderr, done.stderr
    assert _snapshot(repo) == before and not (repo / ".engine_backups").exists()


def test_restore_refuses_a_folder_that_is_not_a_kept_engine(repo, tmp_path):
    before = _snapshot(repo)
    (tmp_path / "plain").mkdir()
    (tmp_path / "plain" / "readme.txt").write_text("not a backup", encoding="utf-8")
    done = _run(repo, "--restore", str(tmp_path / "plain"))
    assert done.returncode == 1 and "is not a kept engine (made by tools/upgrade_engine.py)" in done.stderr
    assert _snapshot(repo) == before


def _sync_tool(repo: Path):
    import importlib.util
    spec = importlib.util.spec_from_file_location("sync_engine_copy", repo / "tools" / "sync_engine.py")
    sync = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sync)
    return sync


def test_the_sync_tool_refuses_a_tree_without_a_version_and_reports_a_copy_it_could_not_finish(repo, tmp_path, monkeypatch, capsys):
    sync = _sync_tool(repo)
    tree = tmp_path / "no_version"
    (tree / CORE).parent.mkdir(parents=True)
    (tree / CORE).write_text("X = 1\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="no ENGINE_VERSION in"):
        sync.engine_version(tree)
    import importlib.util
    spec = importlib.util.spec_from_file_location("clean_engine_copy", repo / "tools" / "clean_engine.py")
    rules = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rules)
    cleaned = tmp_path / "cleaned"
    rules.build(_newer(repo, tmp_path), cleaned, NEWER)                 # what the sync tool takes: a cleaned tree
    before = _snapshot(repo)

    def refuse(source):
        raise OSError(13, "Permission denied")
    monkeypatch.setattr(sync, "replace_engine", refuse)
    assert sync.main(["--from", str(cleaned), "--label", "a newer engine"]) == 1
    assert "PROBLEM: the engine could not be put in place (PermissionError" in capsys.readouterr().out
    assert _snapshot(repo) == before                                   # the bundled engine and its manifest as they were

"""Project metadata and the public installation contract."""
from __future__ import annotations

import ast
import importlib.util
import re
import shutil
import socket
import sys
import tomllib

from conftest import ROOT
from helpers import HOST, QUESTION, committed_files

PYPROJECT = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
NETWORK_MODULES = {"socket", "ssl", "http", "urllib", "ftplib", "smtplib", "poplib", "imaplib", "telnetlib", "xmlrpc",
                   "asyncio", "requests", "httpx", "aiohttp"}


def test_soulrun_has_no_runtime_dependencies():
    assert PYPROJECT["project"]["dependencies"] == []


def test_release_metadata_uses_project_publisher_identity():
    assert PYPROJECT["project"]["authors"] == [
        {"name": "AIXP Labs", "email": "noreply@SoulRun.dev"},
    ]
    assert not PYPROJECT["project"].get("maintainers")
    assert PYPROJECT["project"]["license"] == "Apache-2.0"


def test_python_classifiers_and_discussion_link_match_the_supported_metadata():
    classifiers = PYPROJECT["project"]["classifiers"]
    for version in ("3.11", "3.12", "3.13", "3.14", "3.15"):
        assert f"Programming Language :: Python :: {version}" in classifiers
    urls = PYPROJECT["project"]["urls"]
    assert urls["Discussions"] == "https://github.com/AIXP-Labs/SoulRun/discussions"
    assert "Issues" not in urls


def test_readme_pair_discloses_the_unfixed_windows_permission_boundary():
    versions = ("3.11.10", "3.12.4")
    for name, heading, phrases in (
        ("README.md", "### Windows run-folder permissions",
         ("not fixed", "pre-create", "--soulrun-cache-dir", "does not prove")),
        ("README_CN.md", "### Windows运行目录权限",
         ("尚未修复", "预建", "--soulrun-cache-dir", "不证明")),
    ):
        text = (ROOT / name).read_text(encoding="utf-8")
        assert heading in text
        section = text.partition(heading)[2].split("\n### ", 1)[0].split("\n## ", 1)[0]
        assert all(value in section for value in (*versions, *phrases)), name


def test_soulrun_and_its_engine_import_no_network_library():
    """The README promises that SoulRun opens no network connection (Axiom 0 in SoulRun): none of its own modules,
    and none of the engine's - the engine's tools run in the model's shell, outside any socket a test can refuse -
    imports anything that could. A newer engine brought in is held to the same."""
    engine = ROOT / "src" / "soulrun" / "soulrun_aiap"
    paths = sorted((ROOT / "src" / "soulrun").glob("*.py")) + sorted(engine.rglob("*.py"))
    assert len(paths) > 40
    for path in paths:
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                names = [node.module or ""]
            else:
                continue
            assert not [n for n in names if n.split(".")[0] in NETWORK_MODULES], (path.relative_to(ROOT).as_posix(), names)


def test_a_call_opens_no_network_connection(soulrun, agent, monkeypatch):
    """The same promise, at run time: a run is prepared, and the guide handed back, with sockets refused."""
    def refuse(*args, **kwargs):
        raise AssertionError("a network connection was attempted")
    monkeypatch.setattr(socket, "socket", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    ctx = soulrun(user_message=QUESTION, session_id="no-network", **HOST)
    assert ctx.kind == "program" and ctx.cache_dir
    assert soulrun().kind == "guide"


def test_the_version_comes_from_the_package_and_the_engine_has_its_own(soulrun):
    """SoulRun's version changes with SoulRun's releases; the engine's changes only when the engine does (the engine
    records its version in every run)."""
    assert PYPROJECT["project"]["dynamic"] == ["version", "readme"]
    assert PYPROJECT["tool"]["hatch"]["version"]["path"] == "src/soulrun/__init__.py"
    assert re.fullmatch(r"\d+\.\d+\.\d+", soulrun.__version__), soulrun.__version__
    assert re.fullmatch(r"\d+\.\d+\.\d+", soulrun.ENGINE_VERSION), soulrun.ENGINE_VERSION


def test_a_package_index_gets_the_readme_with_every_link_absolute():
    """README.md links relatively (GitHub resolves that); a package index shows it alone, so the build hook writes
    each link against the repository. Every file a link names exists, so every address it writes is a real file."""
    spec = importlib.util.spec_from_file_location("pypi_readme", ROOT / "tools" / "pypi_readme.py")
    hook = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(hook)
    assert PYPROJECT["tool"]["hatch"]["metadata"]["hooks"]["custom"]["path"] == "tools/pypi_readme.py"
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    targets = hook.relative_targets(readme)
    assert "GUIDE.md" in targets and "#known-limits" in targets
    assert all((ROOT / target.partition("#")[0]).is_file() for target in targets if not target.startswith("#"))
    repository = PYPROJECT["project"]["urls"]["Repository"]
    shown = hook.pypi_readme(readme, repository)
    assert hook.relative_targets(shown) == []
    assert f"]({repository}/blob/main/GUIDE.md)" in shown and f"]({repository}#known-limits)" in shown
    assert f"]({repository}/blob/main/GOVERNANCE.md#versioning)" in shown        # a file's own heading keeps its anchor
    assert f"]({repository}/blob/main/.github/workflows/ci.yml)" in shown           # a leading dot is part of the name
    assert hook.pypi_readme("[a](./x.md) [b](https://x.dev/) [c](mailto:a@b.c)", "https://h/r/") == \
        "[a](https://h/r/blob/main/x.md) [b](https://x.dev/) [c](mailto:a@b.c)"


def test_one_command_and_the_same_build_backend_as_soulbot():
    assert PYPROJECT["project"]["scripts"] == {"soulrun": "soulrun.cli:main"}
    assert PYPROJECT["build-system"]["build-backend"] == "hatchling.build"
    assert PYPROJECT["tool"]["hatch"]["build"]["targets"]["wheel"]["packages"] == ["src/soulrun"]
    assert PYPROJECT["project"]["license"] == "Apache-2.0" and PYPROJECT["project"]["requires-python"] == ">=3.11"


def test_public_files_exist_and_carry_no_personal_paths():
    for name in ("README.md", "README_CN.md", "CHANGELOG.md", "LICENSE", "NOTICE", ".gitignore", ".gitattributes",
                 "GUIDE.md", "INSTALL.md", "DEPENDENCIES.md", "DEPENDENCIES_CN.md", "SECURITY.md", "GOVERNANCE.md",
                 "CODE_OF_CONDUCT.md", "CONTRIBUTING.md", "CONTRIBUTING_CN.md", ".github/dependabot.yml"):
        assert (ROOT / name).is_file(), name
    # A home folder anywhere, or any drive-letter path: SoulRun's own files name no place on one machine.
    # The paths allowed are the neutral examples D:/dir/... and /home/user/... (tools/clean_engine.py turns any other
    # example path in an engine into one of them).
    suspicious = re.compile(r"[A-Za-z]:[\\/]Users[\\/]|/home/(?!user(?:/|\b))[a-z]|/Users/[A-Za-z]|\b[A-Za-z]:[\\/](?!dir[\\/])[A-Za-z_]")
    # Only what would be committed (a .venv or a kept engine on one machine is not SoulRun's). Excluded: the bundled
    # engine, and engine_node.aisop.json - the engine's own texts copied verbatim by tools/build_engine_node.py
    # (they contain the engine's generic "dir/file" example path).
    checked = [p for p in committed_files(ROOT) if p.suffix in (".py", ".md", ".toml", ".txt", ".json")
               and "soulrun_aiap" not in p.relative_to(ROOT).parts and p.name != "engine_node.aisop.json"]
    assert checked
    for path in checked:
        assert not suspicious.search(path.read_text(encoding="utf-8", errors="replace")), path.relative_to(ROOT)


def test_soulruns_own_files_name_no_old_engine_name_or_development_version():
    """What tools/check_docs.py's STALE rule keeps out of the documents is kept out of every other file SoulRun
    owns too (NOTICE, .gitattributes, the code, the generated slim program). The engine itself is checked by
    tools/clean_engine.py --check; the two tools, and the tests that feed them old names, spell them on purpose."""
    spec = importlib.util.spec_from_file_location("check_docs", ROOT / "tools" / "check_docs.py")
    check_docs = importlib.util.module_from_spec(spec)
    sys.modules["check_docs"] = check_docs
    spec.loader.exec_module(check_docs)
    skipped = {"tools/clean_engine.py", "tools/check_docs.py", "tests/test_clean_engine.py", "tests/test_docs.py",
               "tests/test_upgrade_engine.py", "tests/test_canonical_upgrade.py", "src/soulrun/engine_node.aisop.json",
               "tests/test_engine_endings.py"}           # feeds an inherited version to runtime_identity on purpose
    checked = []
    for path in committed_files(ROOT):                   # only what would be committed: not a .venv on one machine
        rel = path.relative_to(ROOT).as_posix()
        if rel in skipped or "soulrun_aiap" in path.relative_to(ROOT).parts:
            continue
        checked.append(rel)
        found = check_docs.STALE.search(path.read_text(encoding="utf-8", errors="replace"))
        assert not found, f"{rel}: {found.group(0)}"
    assert {"NOTICE", ".gitattributes", "pyproject.toml"} <= set(checked)


def test_only_what_git_would_commit_counts_as_soulruns_own(tmp_path):
    shutil.copy2(ROOT / ".gitignore", tmp_path / ".gitignore")
    for name in ("src/a.py", ".env.example", ".venv/lib/site.py", "dist/x.whl", "agent/.soulrun_cache/r.json", ".env",
                 "tools/__pycache__/x.pyc", ".engine_backups/1.0.0-x/m.json", ".git/config", "b.pyc", "docs/build/x.md"):
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_text("x", encoding="utf-8")
    assert [p.relative_to(tmp_path).as_posix() for p in committed_files(tmp_path)] == [".env.example", ".gitignore", "src/a.py"]


def test_local_credential_directory_ignore_is_exact_and_keeps_public_examples(tmp_path):
    shutil.copy2(ROOT / '.gitignore', tmp_path / '.gitignore')
    for name in ('.ssh/session.json', '.aws/session.json', '.env.example',
                 '.ssh.example/session.json', '.aws.example/session.json',
                 'examples/ssh/session.json', 'examples/aws/session.json'):
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('{}', encoding='utf-8')
    assert [p.relative_to(tmp_path).as_posix() for p in committed_files(tmp_path)] == [
        '.aws.example/session.json', '.env.example', '.gitignore', '.ssh.example/session.json',
        'examples/aws/session.json', 'examples/ssh/session.json']


def test_generated_files_keep_lf_line_ends_on_every_checkout():
    """The generated files and the guide are written with LF line ends and checked byte for byte (a newer engine
    brought in and taken back out must leave every file as it was). A Windows checkout with core.autocrlf would
    turn them into CRLF, so .gitattributes pins each one to LF, and leaves the engine's own bytes alone."""
    rules = {}
    for line in (ROOT / ".gitattributes").read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.lstrip().startswith("#"):
            pattern, *attributes = line.split()
            rules[pattern] = attributes
    assert rules.get("/src/soulrun/soulrun_aiap/**") == ["-text"]
    for name in ("engine_manifest.json", "engine_node.aisop.json", "_agent_text.py", "guide.txt"):
        assert rules.get(f"/src/soulrun/{name}") == ["text", "eol=lf"], name
    assert rules.get("/tests/soulbot_samples.json") == ["text", "eol=lf"]                # recorded by a tool, checked too


def test_the_package_ships_its_guide_manifest_and_type_marker():
    package = ROOT / "src" / "soulrun"
    for name in ("guide.txt", "engine_manifest.json", "py.typed", "_agent_text.py"):
        assert (package / name).is_file(), name


def test_ci_and_the_documents_write_no_version_range_of_their_own():
    """Every version range lives in pyproject.toml, the one place Dependabot keeps current: CI installs the release
    tools through tools/extra_requirements.py and the test tools as the wheel's dev extra."""
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    installs = [line for line in ci.splitlines() if "pip install" in line]
    assert installs and not [line for line in installs if re.search(r"[<>=!~]=\s*\d|[<>]\s*\d", line)]
    for name in ("INSTALL.md", "CONTRIBUTING.md", "CONTRIBUTING_CN.md", "DEPENDENCIES.md", "DEPENDENCIES_CN.md"):
        lines = [line for line in (ROOT / name).read_text(encoding="utf-8").splitlines()
                 if "pip install" in line and "soulrun==" not in line]         # SoulRun's own version, e.g. a pre-release
        assert not [line for line in lines if re.search(r"[<>=!~]=\s*\d|[<>]\s*\d", line)], name
    spec = importlib.util.spec_from_file_location("extra_requirements", ROOT / "tools" / "extra_requirements.py")
    tool = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tool)
    assert tool.requirements("release") == PYPROJECT["project"]["optional-dependencies"]["release"]
    try:
        tool.requirements("no_such_extra")
    except SystemExit as error:
        assert "has no extra 'no_such_extra'" in str(error)
    else:
        raise AssertionError("an unknown extra was not refused")

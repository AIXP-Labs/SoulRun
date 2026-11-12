"""Check built packages before anyone else sees them.

    python tools/check_dist.py                 # checks every wheel and source archive in dist/
    python tools/check_dist.py <file> ...      # checks the given files

What is checked:

* the wheel carries exactly the engine files the manifest calls "installed", each with the recorded
  SHA-256, and none of the repository-only ones (the engine's tests, release notes, test configuration);
* the wheel has the guide, the manifest, the type marker, the console command, and no runtime dependencies
  (the optional "dev" and "release" extras are allowed);
* the source archive holds the sources, tests and tools, and no caches or run data;
* **privacy** (the rules in tools/privacy_rules.py): no credential, no home-folder path, no e-mail address outside
  a short allow-list, in any file; no user or group name in the archive headers. Extra words to look for (a user name, a machine name) are given at run time
  through the environment variable SOULRUN_PRIVACY_WORDS (comma separated) - they are never written
  into this repository.

Exit code 0 when everything holds, 1 otherwise.
"""
from __future__ import annotations

import hashlib
import fnmatch
import json
import os
import re
import stat
import sys
import tarfile
import tomllib
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import privacy_rules  # noqa: E402  - the rules every privacy check shares

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "src" / "soulrun" / "engine_manifest.json"
ENGINE = "soulrun/soulrun_aiap/"
NOT_INSTALLED = ("tests/", "RELEASE", "pytest.ini")
RELATIVE_LINK = re.compile(r"\]\((?!https?://|mailto:)([^)\s]+)\)")
# Folders a package must never carry: caches, run data (the users' own words), kept engines, a repository.
CACHES = ("__pycache__", ".pytest_cache", ".execution_cache", ".ruff_cache", ".mypy_cache", ".soulrun", ".soulrun_cache",
          ".engine_backups", ".git")
PRIVATE_DIRS = frozenset({".claude", ".codex", ".gemini", ".opencode", ".cursor", ".vscode", ".idea"})
LOCAL_PATTERNS = (".venv*", "venv", "venv-*", "env", ".wheel-smoke", ".tox", ".nox",
                  "dist", "build", "release-dist", "release-dist-*", "htmlcov", "*.egg-info", "*.egg")
PRIVATE_FILES = frozenset({".pypirc", ".netrc", "_netrc", "auth.json", "credentials.json",
                           "id_rsa", "id_ed25519", "id_ecdsa", ".coverage", "coverage.xml", "coverage.json",
                           ".ds_store", "thumbs.db", "desktop.ini"})


def _secret_files(names: list[str]) -> list[str]:
    """Local/private files are refused by name even when their contents look harmless."""
    result = []
    for name in names:
        for part in name.split("/"):
            base = part.casefold()
            environment = base == ".env" or (base.startswith(".env.") and base != ".env.example")
            if environment or base in PRIVATE_FILES or base.startswith(".coverage.") or \
                    base.endswith((".pem", ".key", ".p12", ".pfx", ".log")) or ".private." in base:
                result.append(name)
                break
    return result


def _private_directory(names: list[str]) -> bool:
    return any(part.casefold() in PRIVATE_DIRS or any(fnmatch.fnmatchcase(part.casefold(), pattern) for pattern in LOCAL_PATTERNS)
               for name in names for part in name.split("/"))


def _member_paths(members: list[tuple[str, bool]], label: str) -> list[str]:
    """Reject ambiguous archive names before any member can be selected by its name."""
    problems, seen = [], set()
    for number, (name, directory) in enumerate(members, 1):
        normalized = name[:-1] if directory and name.endswith("/") else name
        parts = normalized.split("/")
        if not normalized or "\\" in normalized or ":" in normalized or \
                any(part in ("", ".", "..") for part in parts) or any(ord(c) < 32 or ord(c) == 127 for c in name):
            problems.append(f"the {label} contains an unsafe member path at entry {number}")
        if normalized in seen:
            problems.append(f"the {label} contains a duplicate member path at entry {number}")
        seen.add(normalized)
    return problems


def _extra_words() -> list[bytes]:
    return [w.strip().encode("utf-8") for w in os.environ.get("SOULRUN_PRIVACY_WORDS", "").split(",") if w.strip()]


def _privacy(name: str, data: bytes, problems: list[str]) -> None:
    if name.endswith(privacy_rules.SELF):              # the rules themselves spell the patterns out
        return
    text = privacy_rules.text_of(data)                 # UTF-16 too: a path written by a Windows tool
    for label, _ in privacy_rules.credentials(text)[:1]:
        problems.append(f"credential ({label}) in {name}")
    for path, _ in privacy_rules.home_paths(text)[:1]:
        problems.append(f"home-folder path in {name}: {path}")
    for address, _ in privacy_rules.emails(text)[:1]:
        problems.append(f"e-mail address in {name}: {address}")
    lowered = data.lower()
    for word in _extra_words():
        if word.lower() in lowered:
            problems.append(f"a word from SOULRUN_PRIVACY_WORDS appears in {name}")
            break


def _own_files() -> set[str]:
    """SoulRun's own files a wheel installs: what src/soulrun holds, its engine aside (the manifest lists those)."""
    package = ROOT / "src" / "soulrun"
    return {"soulrun/" + p.relative_to(package).as_posix() for p in package.rglob("*")
            if p.is_file() and p.relative_to(package).parts[0] != "soulrun_aiap" and "__pycache__" not in p.parts
            and p.suffix != ".pyc"}


# The records a wheel carries about itself (the build backend writes them), and the license files it copies there.
DIST_INFO = {"METADATA", "WHEEL", "RECORD", "entry_points.txt", "licenses/LICENSE", "licenses/NOTICE"}


def _dist_info(name: str) -> bool:
    top, _, rest = name.partition("/")
    return top.startswith("soulrun-") and top.endswith(".dist-info") and rest in DIST_INFO


def _sdist_tops() -> set[str]:
    """What may sit at the top of a source archive: pyproject.toml's sdist include list, and the three files the
    build backend adds itself."""
    include = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["tool"]["hatch"]["build"]["targets"]["sdist"]["include"]
    return {entry.strip("/") for entry in include} | {"PKG-INFO", "pyproject.toml", ".gitignore"}


def check_wheel(path: Path) -> list[str]:
    problems: list[str] = []
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    expected = {name: sha for name, sha in manifest["files"].items() if not name.startswith(NOT_INSTALLED)}
    with zipfile.ZipFile(path) as wheel:
        members = wheel.infolist()
        problems += _member_paths([(m.orig_filename, m.is_dir()) for m in members], "wheel")
        if any(stat.S_IFMT(m.external_attr >> 16) not in (0, stat.S_IFDIR if m.is_dir() else stat.S_IFREG) for m in members):
            problems.append("the wheel contains a link or special member")
        if problems:
            return problems
        by_name = {m.filename: m for m in members}
        names = list(by_name)
        engine = {name[len(ENGINE):]: hashlib.sha256(wheel.read(info)).hexdigest()
                  for name, info in by_name.items() if name.startswith(ENGINE) and not info.is_dir()}
        for name in sorted(set(expected) - set(engine)):
            problems.append(f"engine file missing from the wheel: {name}")
        for name in sorted(set(engine) - set(expected)):
            problems.append(f"file in the wheel's engine folder that the manifest does not install: {name}")
        for name in sorted(set(engine) & set(expected)):
            if engine[name] != expected[name]:
                problems.append(f"engine file differs from the manifest: {name}")
        for required in ("soulrun/__init__.py", "soulrun/guide.txt", "soulrun/engine_manifest.json", "soulrun/py.typed",
                         "soulrun/_agent_text.py", "soulrun/cli.py", "soulrun/host.py", "soulrun/engine_node.aisop.json"):
            if required not in names:
                problems.append(f"missing from the wheel: {required}")
        if any(part in name.split("/") for name in names for part in CACHES):
            problems.append("the wheel contains a cache or run-data folder")
        problems += [f"the wheel contains a secrets file: {name}" for name in _secret_files(names)]
        if _private_directory(names):
            problems.append("the wheel contains a private or local-configuration folder")
        own = _own_files()                             # a list of what is shipped, not of what is kept out
        problems += [f"file in the wheel that SoulRun does not ship: {name}" for name in names
                     if not name.startswith(ENGINE) and name not in own and not _dist_info(name)]
        info = next((n for n in names if n.endswith(".dist-info/METADATA")), None)
        entry = next((n for n in names if n.endswith(".dist-info/entry_points.txt")), None)
        metadata = wheel.read(by_name[info]).decode("utf-8") if info else ""
        runtime = [line for line in metadata.splitlines() if line.startswith("Requires-Dist:") and "extra ==" not in line]
        if runtime:                                  # optional extras (dev, release) are not runtime dependencies
            problems.append(f"the wheel declares a runtime dependency; SoulRun must have none: {runtime[0]}")
        if not entry or "soulrun = soulrun.cli:main" not in wheel.read(by_name[entry]).decode("utf-8"):
            problems.append("the wheel does not install the soulrun command")
        description = metadata.split("\n\n", 1)[1] if "\n\n" in metadata else ""
        if not description.strip():
            problems.append("the wheel carries no long description (README.md)")
        relative = RELATIVE_LINK.findall(description)
        if relative:                                 # on a package index the README stands alone (tools/pypi_readme.py)
            problems.append(f"the long description links relatively, which leads nowhere on a package index: {relative[0]}")
        for member in members:
            if not member.is_dir():
                _privacy(f"{path.name}:{member.filename}", wheel.read(member), problems)
        print(f"{path.name}: {len(names)} files, {len(engine)} engine files (manifest installs {len(expected)})")
    return problems


def check_sdist(path: Path) -> list[str]:
    problems: list[str] = []
    with tarfile.open(path) as archive:
        members = archive.getmembers()
        problems += _member_paths([(m.name, m.isdir()) for m in members], "source archive")
        if any(not (m.isfile() or m.isdir()) for m in members):
            problems.append("the source archive contains a link or special member")
        roots = {m.name.split("/", 1)[0] for m in members}
        if len(roots) != 1 or not next(iter(roots), "").startswith("soulrun-") or \
                any("/" not in m.name.rstrip("/") for m in members if not m.isdir()):
            problems.append("the source archive must have one source root containing every file")
        if problems:
            return problems
        names = [m.name.split("/", 1)[1] if "/" in m.name else m.name for m in members if m.isfile()]
        for required in ("pyproject.toml", "README.md", "LICENSE", "NOTICE", "src/soulrun/__init__.py",
                         "src/soulrun/soulrun_aiap/main.aisop.json", "tests/conftest.py", "tools/sync_engine.py",
                         "tools/check_docs.py", "GUIDE.md", "INSTALL.md", "docs/README.md", ".github/workflows/ci.yml"):
            if required not in names:
                problems.append(f"missing from the source archive: {required}")
        all_names = [m.name.split("/", 1)[1] for m in members if "/" in m.name]
        if any(part in name.split("/") for name in all_names for part in CACHES):
            problems.append("the source archive contains a cache or run-data folder")
        problems += [f"the source archive contains a secrets file: {name}" for name in _secret_files(all_names)]
        if _private_directory([m.name for m in members]):
            problems.append("the source archive contains a private or local-configuration folder")
        tops, allowed = sorted({name.split("/", 1)[0] for name in names}), _sdist_tops()
        problems += [f"in the source archive but not in pyproject.toml's sdist include list: {top}" for top in tops if top not in allowed]
        owners = sorted({(m.uname, m.gname) for m in members if m.uname or m.gname})
        if owners:
            problems.append(f"the source archive records {len(owners)} user/group name(s) in its headers")
        for member in members:
            if member.isfile():
                _privacy(f"{path.name}:{member.name}", archive.extractfile(member).read(), problems)
        print(f"{path.name}: {len(names)} files")
    return problems


def main(argv: list[str]) -> int:
    targets = [Path(a) for a in argv] or sorted((ROOT / "dist").glob("soulrun-*"))
    if not targets:
        print("nothing to check: build first (python -m build)")
        return 1
    problems: list[str] = []
    checked = 0
    for target in targets:
        if not target.is_file():
            problems.append(f"no such file: {target}")
        elif target.suffix == ".whl":
            problems += check_wheel(target)
            checked += 1
        elif target.name.endswith(".tar.gz"):
            problems += check_sdist(target)
            checked += 1
        else:
            problems.append(f"not a package (a .whl or a .tar.gz): {target}")
    if not checked:
        problems.append("no package was checked")
    for line in problems:
        print("PROBLEM:", line)
    print("OK" if not problems else f"{len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

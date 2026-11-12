"""Keep the bundled engine identical to its manifest.

SoulRun's engine lives under ``src/soulrun/soulrun_aiap``; ``src/soulrun/engine_manifest.json`` records its
version and the SHA-256 of every file. This tool proves the bundled tree has not drifted. Release admission
separates lossless canonical sources from explicitly cleaned legacy sources. tools/upgrade_engine.py brings
one in using its appropriate source path and keeps the engine it replaces.

    python tools/sync_engine.py --check
        Verify every bundled engine file against src/soulrun/engine_manifest.json.

    python tools/sync_engine.py --check-release
        Read-only release admission: verify the record, exact payload and privacy, then the declared source form.
        Canonical sources keep their text and must pass identity/license/contract checks; legacy-clean sources
        must still pass the original history checker. Unknown forms and failed canonical checks never fall back.

    python tools/sync_engine.py --from <cleaned engine tree> --label "<what it is>"
        Replace the bundled tree with a copy of a cleaned engine tree and rewrite the manifest.

    python tools/sync_engine.py --write-manifest --label "<what it is>"
        Record the manifest of the tree that is already bundled.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
ENGINE = ROOT / "src" / "soulrun" / "soulrun_aiap"
MANIFEST = ROOT / "src" / "soulrun" / "engine_manifest.json"
NEVER_COPIED = ("__pycache__", ".pytest_cache", ".execution_cache")
# Files an engine tree may carry that are never part of the installed package. tools/clean_engine.py leaves them
# out, so a bundled engine has none; the list stays as a guard (pyproject.toml excludes the same).
NOT_INSTALLED = ("tests/", "RELEASE", "pytest.ini")


def canonical_problems(tree: Path, version: str | None = None) -> list[str]:
    """Validate a public SoulRun tree without changing its executable strings."""
    problems = []
    try:
        actual = engine_version(tree)
        if version is not None and version != actual:
            problems.append(f"source version {actual} differs from requested {version}; never restamp a canonical tree")
        for name, identity in (("main.aisop.json", "soulrun_aiap.main"),
                               ("agent_engine.aisop.json", "soulrun_aiap.agent")):
            doc = json.loads((tree / name).read_text(encoding="utf-8"))
            if [p.get("role") for p in doc] != ["system", "user"]:
                problems.append(f"{name}: expected the two parts system and user")
            else:
                system = doc[0]["content"]
                if system.get("id") != identity or system.get("version") != actual:
                    problems.append(f"{name}: canonical identity/version differs")
        card = json.loads((tree / "agent_card.json").read_text(encoding="utf-8"))
        if card.get("name") != "soulrun_aiap" or card.get("program_id") != "dev.soulrun.soulrun_aiap" or card.get("version") != actual:
            problems.append("agent_card.json: canonical identity/version differs")
        identity = ast.parse((tree / "python_tools/lib/runtime_identity.py").read_text(encoding="utf-8"))
        constants = {n.targets[0].id: n.value.value for n in identity.body
                     if isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name)
                     and isinstance(n.value, ast.Constant)}
        if constants.get("NAME") != "soulrun_aiap" or constants.get("VERSION") != actual:
            problems.append("runtime_identity.py: canonical identity/version differs")
        for name in ("LICENSE", "NOTICE"):
            if not (tree/name).is_file() or not (tree/name).read_bytes().strip():
                problems.append(f"missing legal file: {name}")
        if (tree/'LICENSE').is_file() and 'Apache License' not in (tree/'LICENSE').read_text(encoding='utf-8'):
            problems.append('LICENSE: expected Apache License text')
        if (tree/'NOTICE').is_file() and 'AIXP Labs AIXP.dev | SoulRun.dev' not in (tree/'NOTICE').read_text(encoding='utf-8'):
            problems.append('NOTICE: expected SoulRun copyright attribution')
        manifest = json.loads((tree / "contracts/manifest.json").read_text(encoding="utf-8"))
        for name, digest in manifest["files"].items():
            p = tree / "contracts" / name
            if not p.resolve().is_relative_to((tree/"contracts").resolve()) or _sha256(p) != digest:
                problems.append(f"contract digest differs: {name}")
    except (OSError, ValueError, KeyError, TypeError, IndexError, SyntaxError, SystemExit) as exc:
        problems.append(f"canonical source cannot be verified: {exc}")
    return problems


def stage_canonical(source: Path, target: Path, version: str) -> dict:
    problems = canonical_problems(source, version)
    if problems:
        raise ValueError("; ".join(problems))
    if target.exists():
        raise ValueError(f"staging target already exists: {target}")
    kept = 0
    for p in _files(source):
        relative = p.relative_to(source)
        name = relative.as_posix()
        if not _installed(name) or name == "tools/replay_v6_cache.py" or any(x.startswith('.') for x in relative.parts):
            continue
        if p.is_symlink() or not p.resolve().is_relative_to(source.resolve()):
            raise ValueError(f"source link escapes the frozen tree: {name}")
        out = target / relative
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, out)
        if _sha256(out) != _sha256(p):
            raise OSError(f"source copy changed: {name}")
        kept += 1
    return dict(kept=kept, dropped=len(_files(source))-kept, texts=[], resealed=[])


def _files(tree: Path) -> list[Path]:
    return sorted(
        p for p in tree.rglob("*")
        if p.is_file() and not (set(p.relative_to(tree).parts) & set(NEVER_COPIED)) and p.suffix != ".pyc"
        and not p.name.startswith(".env")
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _installed(relative: str) -> bool:
    return not any(relative.startswith(prefix) for prefix in NOT_INSTALLED)


def engine_version(tree: Path) -> str:
    core = (tree / "python_tools" / "lib" / "engine_core.py").read_text(encoding="utf-8")
    match = re.search(r'ENGINE_VERSION = "([^"]+)"', core)
    if not match:
        raise SystemExit(f"no ENGINE_VERSION in {tree}")
    return match.group(1)


def build_manifest(tree: Path, label: str) -> dict:
    files = {p.relative_to(tree).as_posix(): _sha256(p) for p in _files(tree)}
    digest = hashlib.sha256("".join(f"{name}\0{sha}\n" for name, sha in sorted(files.items())).encode("utf-8")).hexdigest()
    installed = {name: sha for name, sha in files.items() if _installed(name)}
    installed_digest = hashlib.sha256(
        "".join(f"{name}\0{sha}\n" for name, sha in sorted(installed.items())).encode("utf-8")
    ).hexdigest()
    return {
        "engine_version": engine_version(tree),
        "source_form": "canonical" if not canonical_problems(tree) else "legacy-clean",
        "source": label,
        "recorded_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "file_count": len(files),
        "digest": digest,
        "installed_file_count": len(installed),
        "installed_digest": installed_digest,
        "files": files,
    }


def replace_engine(source: Path) -> None:
    """Copy the new engine beside the bundled one first, then swap the two folders: a copy that fails half way (a file
    held by another program, a full disk, a path too long) never leaves half an engine behind."""
    new, old = ENGINE.with_name(ENGINE.name + ".new"), ENGINE.with_name(ENGINE.name + ".old")
    for leftover in (new, old):
        if leftover.exists():
            shutil.rmtree(leftover)
    try:
        shutil.copytree(source, new, ignore=shutil.ignore_patterns(*NEVER_COPIED, "*.pyc", ".env*"))
    except OSError:
        shutil.rmtree(new, ignore_errors=True)
        raise
    try:
        if ENGINE.exists():
            ENGINE.rename(old)
        new.rename(ENGINE)
    except OSError:
        if not ENGINE.exists() and old.exists():
            old.rename(ENGINE)                            # put the bundled engine back as it was
        shutil.rmtree(new, ignore_errors=True)
        raise
    shutil.rmtree(old, ignore_errors=True)


def check() -> list[str]:
    if not MANIFEST.is_file():
        return [f"missing manifest: {MANIFEST.relative_to(ROOT).as_posix()}"]
    recorded = json.loads(MANIFEST.read_text(encoding="utf-8"))["files"]
    actual = {p.relative_to(ENGINE).as_posix(): _sha256(p) for p in _files(ENGINE)}
    problems = [f"missing: {name}" for name in sorted(set(recorded) - set(actual))]
    problems += [f"not in manifest: {name}" for name in sorted(set(actual) - set(recorded))]
    problems += [f"changed: {name}" for name in sorted(set(recorded) & set(actual)) if recorded[name] != actual[name]]
    return problems


def _unique_object(pairs: list[tuple]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate record key: {key}")
        result[key] = value
    return result


def _release_name(name: str) -> bool:
    return (isinstance(name, str) and bool(name) and not any(c in name for c in "\\:\0")
            and not PurePosixPath(name).is_absolute() and name == PurePosixPath(name).as_posix()
            and all(p not in {".", ".."} and p == p.rstrip(" .") for p in name.split("/")))


def _release_link(path: Path) -> bool:
    return path.is_symlink() or bool(getattr(path.lstat(), "st_file_attributes", 0) & 0x400)


def check_release() -> list[str]:
    """Verify release inputs without editing/resealing them or treating source_form as authorization."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import check_dist
    import clean_engine

    problems = []
    try:
        if any(_release_link(path) for path in (ENGINE, MANIFEST)):
            return ["release root/manifest link or reparse point refused"]
        record = json.loads(MANIFEST.read_text(encoding="utf-8"), object_pairs_hook=_unique_object)
        if not isinstance(record, dict) or record.get("source_form") not in ("canonical", "legacy-clean"):
            return ["missing or unknown source_form; no legacy fallback"]
        files = record.get("files")
        if not isinstance(files, dict) or not files or any(
                not _release_name(n) or not isinstance(d, str) or not re.fullmatch(r"[0-9a-f]{64}", d)
                for n, d in files.items()):
            return ["invalid or empty release file map"]
        if not isinstance(record.get("source"), str) or not record["source"].strip():
            problems.append("release record has no source description")
        actual = {}
        for path in [ENGINE, MANIFEST, *sorted(ENGINE.rglob("*"))]:
            if _release_link(path):
                problems.append(f"release source link/reparse point refused: {path.name}")
                continue
            if path == ENGINE or path == MANIFEST or not path.is_file():
                continue
            relative = path.relative_to(ENGINE).as_posix()
            if "__pycache__" in path.relative_to(ENGINE).parts or path.suffix in {".pyc", ".pyo"}:
                continue
            runtime_kind = clean_engine.kept(relative) or relative in {"LICENSE", "NOTICE"}
            if not path.resolve().is_relative_to(ENGINE.resolve()) or not runtime_kind:
                problems.append(f"not a release runtime file: {relative}")
                continue
            actual[relative] = _sha256(path)
            check_dist._privacy(relative, path.read_bytes(), problems)
        problems += [f"missing: {n}" for n in sorted(files.keys() - actual.keys())]
        problems += [f"not in manifest: {n}" for n in sorted(actual.keys() - files.keys())]
        problems += [f"changed: {n}" for n in sorted(files.keys() & actual.keys()) if files[n] != actual[n]]
        installed = {n: d for n, d in files.items() if _installed(n)}
        for prefix, entries in (("", files), ("installed_", installed)):
            count = record.get(prefix + "file_count")
            digest = hashlib.sha256("".join(f"{n}\0{d}\n" for n, d in sorted(entries.items())).encode()).hexdigest()
            if type(count) is not int or count != len(entries) or record.get(prefix + "digest") != digest:
                problems.append(f"release {prefix}count/digest does not match the file map")
        if record.get("engine_version") != engine_version(ENGINE):
            problems.append("recorded engine version differs from source")
        if problems:
            return problems
        if record["source_form"] == "canonical":
            contracts = ENGINE / "contracts"
            contract_record = json.loads((contracts / "manifest.json").read_text(encoding="utf-8"),
                                         object_pairs_hook=_unique_object)
            contract_files = contract_record.get("files") if isinstance(contract_record, dict) else None
            expected = {p.name for p in contracts.glob("*.contract.json")}
            if (not expected or not isinstance(contract_files, dict) or set(contract_files) != expected
                    or any(not _release_name(n) or not isinstance(d, str) or not re.fullmatch(r"[0-9a-f]{64}", d)
                           for n, d in contract_files.items())):
                return ["canonical contract file map is empty, incomplete or unsafe"]
            return canonical_problems(ENGINE, record["engine_version"])
        # A canonical identity cannot select the legacy cleaner to bypass its own failed checks.
        card = json.loads((ENGINE / "agent_card.json").read_text(encoding="utf-8"), object_pairs_hook=_unique_object)
        if card.get("program_id") == "dev.soulrun.soulrun_aiap":
            return ["canonical source identity cannot be declared legacy-clean"]
        return clean_engine.check(ENGINE)
    except (OSError, ValueError, TypeError, KeyError, AttributeError, IndexError, SyntaxError, SystemExit) as exc:
        return [f"release source cannot be verified: {exc}"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="verify the bundled engine against the manifest")
    mode.add_argument("--check-release", action="store_true", help="read-only verification of the recorded source form and release payload")
    mode.add_argument("--from", dest="source", help="replace the bundled engine with a copy of this tree")
    mode.add_argument("--write-manifest", action="store_true", help="record the manifest of the bundled tree")
    parser.add_argument("--label", help="where the engine tree came from (required when writing a manifest)")
    parser.add_argument("--canonical", action="store_true", help="accept a verified canonical tree without text cleaning")
    args = parser.parse_args(argv)

    if args.check_release:
        problems = check_release()
        for line in problems:
            print(f"PROBLEM: {line}")
        if not problems:
            recorded = json.loads(MANIFEST.read_text(encoding="utf-8"))
            print(f"release {recorded['source_form']} | {recorded['file_count']} files | OK (read-only)")
        return 1 if problems else 0

    if args.check:
        problems = check()
        for line in problems:
            print(line)
        recorded = json.loads(MANIFEST.read_text(encoding="utf-8")) if MANIFEST.is_file() else {}
        print(f"engine {recorded.get('engine_version')} | {recorded.get('file_count')} files | "
              f"{'OK' if not problems else str(len(problems)) + ' problem(s)'}")
        return 1 if problems else 0

    if not args.label:
        parser.error("--label is required when writing a manifest")
    if args.source:
        source = Path(args.source).resolve()
        if not (source / "python_tools" / "lib" / "engine_core.py").is_file():
            parser.error(f"{source} is not an engine tree")
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import clean_engine
        leftovers = canonical_problems(source) if args.canonical else clean_engine.check(source)
        if leftovers:
            parser.error(f"{source} has not been cleaned ({len(leftovers)} problem(s), first: {leftovers[0]}); "
                         "bring an engine in with tools/upgrade_engine.py, which cleans it first")
        try:
            replace_engine(source)
        except OSError as exc:
            print(f"PROBLEM: the engine could not be put in place ({type(exc).__name__}: {exc}); the bundled engine was "
                  "left as it was")
            return 1
    manifest = build_manifest(ENGINE, args.label)
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(f"engine {manifest['engine_version']} | {manifest['file_count']} files "
          f"({manifest['installed_file_count']} installed) | digest {manifest['digest'][:16]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

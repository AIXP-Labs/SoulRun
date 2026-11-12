"""Bring a newer engine into SoulRun in one step, keeping the old one; or go back to a kept one.

    python tools/upgrade_engine.py --from <engine tree> --engine-version 1.0.1 --dry-run   # the plan only
    python tools/upgrade_engine.py --from <engine tree> --engine-version 1.0.1             # do it
    python tools/upgrade_engine.py --restore .engine_backups/<kept>                         # go back

Steps of an upgrade, in order:
  1. canonical runtime files are staged byte for byte, with identity, version, license and contracts checked.
     --legacy-clean explicitly selects the old development-tree cleaner; never use it on a canonical source;
  2. the plan: old and new engine version, files added / removed / changed. The version must be a release version
     (1.0.1, 1.1.0rc1); new contents under the version already bundled are refused (--same-version allows it);
  3. a backup of what is replaced - the bundled engine (as soulrun_aiap.zip), its manifest and engine_node.aisop.json
     - under .engine_backups/<old version>-<UTC time>/ (never published: not in the packages, ignored by git);
  4. the staged engine copied in beside the old one and swapped in, and its manifest written (tools/sync_engine.py);
  5. what SoulRun calls in the engine is checked, and one run with a named program is made without a model;
  6. engine_node.aisop.json rebuilt from the new engine (tools/build_engine_node.py) - a section the new engine added
     and the arrangement does not place yet is reported, and the step fails until it is placed;
  7. the fixed wording checked against SoulBot's agent.py (tools/port_agent_text.py), when one is found;
  8. the engine version where the documents name it (tools/check_docs.py: DEPENDENCIES, GUIDE).
Then it prints what is left to run by hand. SoulRun's own version (src/soulrun/__init__.py) is not touched: it
changes with SoulRun's releases (python tools/check_docs.py --set-version X.Y.Z), not with the engine.

The wrapper binds unfinished runs to the exact installed engine digest, including same-version changes.
Restore an older complete SoulRun combination when its engine does not satisfy the current wrapper's interface.

--restore puts a kept engine back the same way (the engine being replaced is kept first, too) - only when every file
in the kept archive matches the kept manifest - and checks it.
"""
from __future__ import annotations

import argparse
import contextlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
import zlib
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parent
sys.path.insert(0, str(TOOLS))
import build_engine_node  # noqa: E402
import check_docs  # noqa: E402
import clean_engine  # noqa: E402
import record_soulbot_samples  # noqa: E402
import sync_engine  # noqa: E402

PACKAGE = ROOT / "src" / "soulrun"
BACKUPS = ROOT / ".engine_backups"
STAGING = BACKUPS / ".staging"
ENGINE_ZIP = "soulrun_aiap.zip"
KEPT_FILES = ("engine_manifest.json", "engine_node.aisop.json")
VERSION = check_docs.RELEASE_VERSION             # the same rule as a SoulRun release version
LEFT_TO_RUN = ("left to run by hand:\n"
               "  python -m pytest\n"
               "  python -m build && python tools/check_dist.py\n"
               "  python tools/check_docs.py\n"
               "  note the engine change in CHANGELOG.md, and date the README's Verified Test Baseline anew")

# One run made without a model through the installed SoulRun and the new engine: a named program must be the only
# candidate, and the re-entry text must name a tool that exists. Run in a fresh process so the new engine is loaded.
SMOKE = r'''
import json, shutil, sys, tempfile
from pathlib import Path
import soulrun
from soulrun import _engine, host
problems = list(_engine.interface_problems())
program = [{"role": "system", "content": {"protocol": "AIAP V1.0.0", "axiom_0": "Human_Sovereignty_and_Wellbeing",
            "id": "smoke.main", "name": "Smoke", "version": "1.0.0", "summary": "Smoke test package",
            "flow_format": "mermaid", "loading_mode": "normal", "trust_level": 3}},
           {"role": "user", "content": {"instruction": "ASSERT RUN aisop.main", "user_input": "{user_input}",
            "aisop": {"main": "graph TD\n    Start[Start] --> endNode((End))"}, "functions": {"Start": {"step1": "do", "Error": "e"}}}}]
agent = Path(tempfile.mkdtemp(prefix="soulrun-smoke-"))
try:
    for name in ("smoke_aiap", "other_aiap"):
        (agent / "aiap" / name).mkdir(parents=True)
        (agent / "aiap" / name / "main.aisop.json").write_text(json.dumps(program), encoding="utf-8")
    ctx = soulrun.run(aiap="smoke_aiap", agent_dir=str(agent), session_id="smoke", host_fences=[], host_tools={"agent": False})
    snapshot = json.loads((Path(ctx.cache_dir) / "_run_input.json").read_text(encoding="utf-8"))["snapshot"]
    names = [Path(item["dir"]).name for item in snapshot]
    if names != ["smoke_aiap"]:
        problems.append(f"a run with a named program has the candidates {names}")
    prompt = host.resume_prompt(ctx.cache_dir) or ""
    tools = [word for word in prompt.split() if word.endswith("next_node.py")]
    if not tools or not all(Path(tool).is_file() for tool in tools):
        problems.append(f"the re-entry text names no next_node.py that exists: {tools}")
except Exception as exc:
    problems.append(f"a run with a named program failed: {type(exc).__name__}: {exc}")
finally:
    shutil.rmtree(agent, ignore_errors=True)
print(json.dumps(problems))
'''


def _engine_tree(source: Path) -> Path:
    if not (source / "python_tools" / "lib" / "engine_core.py").is_file():
        raise SystemExit(f"{source} is not an engine tree")
    bundled = sync_engine.ENGINE.resolve()
    if source == bundled or bundled in source.parents:
        raise SystemExit(f"{source} is the bundled engine itself: give the folder of the newer engine")
    return source


def _fresh_staging() -> Path:
    if STAGING.exists():
        shutil.rmtree(STAGING)
    STAGING.parent.mkdir(parents=True, exist_ok=True)
    return STAGING


def _drop_staging(staging: Path) -> None:
    """The staging folder goes, and .engine_backups with it when nothing else is kept there: a dry run, or a run
    refused before a backup was made, leaves nothing behind."""
    shutil.rmtree(staging, ignore_errors=True)
    with contextlib.suppress(OSError):
        BACKUPS.rmdir()                          # only when empty


def _release(version: str) -> tuple:
    return tuple(int(n) for n in re.findall(r"\d+", version)[:3])


def plan(staging: Path) -> dict:
    recorded = json.loads(sync_engine.MANIFEST.read_text(encoding="utf-8"))
    new = {p.relative_to(staging).as_posix(): sync_engine._sha256(p) for p in sync_engine._files(staging)}
    old = recorded["files"]
    added, removed = sorted(set(new) - set(old)), sorted(set(old) - set(new))
    changed = sorted(n for n in set(new) & set(old) if new[n] != old[n])
    return {"old_engine": recorded["engine_version"], "new_engine": sync_engine.engine_version(staging),
            "added": added, "removed": removed, "changed": changed, "same_contents": not (added or removed or changed)}


def backup() -> Path:
    """Keep the bundled engine, its manifest and the slim program under .engine_backups/.

    The engine goes into one zip file: nothing inside a zip is picked up by lint or test runs, and deep paths do not
    meet the 260-character limit Windows applies by default. A bundled engine that no longer matches its manifest is
    kept too, under a name that says so, with the differences written beside it."""
    old_engine = json.loads(sync_engine.MANIFEST.read_text(encoding="utf-8"))["engine_version"]
    if not re.fullmatch(r"[\w.+-]{1,40}", str(old_engine)) or ".." in str(old_engine):
        old_engine = "unknown-version"                    # never part of a path as it is
    drift = sync_engine.check()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    base = f"{old_engine}-drifted" if drift else old_engine
    target, n = BACKUPS / f"{base}-{stamp}", 1
    while target.exists():
        n += 1
        target = BACKUPS / f"{base}-{stamp}-{n}"
    target.mkdir(parents=True)
    with zipfile.ZipFile(target / ENGINE_ZIP, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sync_engine._files(sync_engine.ENGINE):
            archive.write(path, path.relative_to(sync_engine.ENGINE).as_posix())
    for name in KEPT_FILES:
        if (PACKAGE / name).is_file():
            shutil.copy2(PACKAGE / name, target / name)
    if drift:
        (target / "DRIFTED.txt").write_text("The bundled engine differed from its manifest when it was kept:\n"
                                            + "\n".join(drift) + "\n", encoding="utf-8")
    return target


def _texts_file(report: dict, version: str) -> Path:
    """Every text a model or a human may read that the cleaning changed, for review (beside the backups, never published)."""
    BACKUPS.mkdir(parents=True, exist_ok=True)
    target = BACKUPS / f"cleaned-texts-{version}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.txt"
    target.write_text("".join(f"--- {relative}\n  - {before!r}\n  + {after!r}\n" for relative, before, after in report["texts"]),
                      encoding="utf-8")
    return target


def _fits_soulrun(source: Path | None = None) -> list[str]:
    """The installed engine against SoulRun's calls, in a new process (the engine is loaded fresh there)."""
    env = dict(os.environ, PYTHONPATH=str(PACKAGE.parent) + os.pathsep + os.environ.get("PYTHONPATH", ""))
    setup = ""
    if source is not None:
        setup = ("from pathlib import Path\nfrom soulrun import _engine\n"
                 f"_engine.ENGINE_DIR=Path({str(source)!r})\n"
                 "_engine.TOOLS_DIR=_engine.ENGINE_DIR/'python_tools'\n"
                 "_engine.MAIN_PROGRAM=_engine.ENGINE_DIR/'main.aisop.json'\n"
                 "_engine.AGENT_PROGRAM=_engine.ENGINE_DIR/'agent_engine.aisop.json'\n")
    done = subprocess.run([sys.executable, "-B", "-X", "utf8", "-c", setup + SMOKE], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", env=env, timeout=300)
    try:
        return json.loads(done.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return [f"the check could not run: {(done.stderr or done.stdout).strip()[-300:]}"]


def _rebuild_and_check(agent_py: str | None) -> bool:
    """Rebuild the slim program and check the fixed wording; True when both are fine."""
    try:
        ok = build_engine_node.main([]) == 0
    except Exception as exc:  # noqa: BLE001 - a program file the builder cannot read is reported, not a traceback
        print(f"PROBLEM: engine_node.aisop.json could not be rebuilt: {type(exc).__name__}: {exc}")
        ok = False
    if not ok:
        print("engine_node.aisop.json: the new engine has parts the arrangement does not place yet - see the PROBLEM "
              "lines above; place them in tools/build_engine_node.py, then run python tools/build_engine_node.py")
    return _check_wording(agent_py) and ok


def _check_wording(agent_py: str | None) -> bool:
    found = Path(agent_py) if agent_py else Path(os.environ.get("SOULRUN_TEST_AGENT_PY")
                                                  or ROOT.parent / "SoulBot" / "examples" / "simple" / "Soul_Agent" / "agent.py")
    if not found.is_file():
        print("wording  SoulBot's agent.py not found: run python tools/port_agent_text.py <agent.py> --check by hand")
        return True
    if record_soulbot_samples.is_soulrun_entry(found):
        print("wording  SoulBot's agent.py is a SoulRun entry: the fixed wording is SoulRun's own (src/soulrun/_agent_text.py)")
        return True
    done = subprocess.run([sys.executable, "-B", "-X", "utf8", str(TOOLS / "port_agent_text.py"), str(found), "--check"],
                          capture_output=True, text=True, encoding="utf-8")
    print("wording  " + ((done.stdout.strip() or done.stderr.strip() or "(no output)").splitlines()[-1]))
    return done.returncode == 0


def _already_bundled() -> int:
    """The cleaned engine is the one bundled: nothing to copy, but the same checks still decide the exit code."""
    problems = [f"engine: {line}" for line in sync_engine.check()]
    problems += [f"engine_node.aisop.json: {line}" for line in build_engine_node.check()]
    if not problems:
        print("the cleaned engine is the one already bundled, and it matches its manifest: nothing to do")
        return 0
    for line in problems:
        print(f"PROBLEM: {line}")
    print("the cleaned engine is the one already bundled, but the checks above fail: the bundled files were changed "
          "by hand (bring the engine in again from a kept backup with --restore), or engine_node.aisop.json needs "
          "python tools/build_engine_node.py")
    return 1


def upgrade(source: Path, version: str, label: str | None, dry_run: bool, agent_py: str | None,
            same_version: bool, legacy_clean: bool = False) -> int:
    if not VERSION.fullmatch(version):
        raise SystemExit(f"--engine-version {version!r} is not a release version such as 1.0.1 (or 1.1.0rc1)")
    source = _engine_tree(source)                 # refused before anything is made
    staging = _fresh_staging()
    try:
        if legacy_clean:
            report = clean_engine.build(source, staging, version)
            problems = clean_engine.check(staging)
        else:
            try:
                report = sync_engine.stage_canonical(source, staging, version)
            except (OSError, ValueError) as exc:
                print(f"PROBLEM: {exc}; nothing was changed (legacy sources require --legacy-clean)")
                return 1
            problems = sync_engine.canonical_problems(staging, version)
        if legacy_clean:
            where = "listed at the end" if dry_run else f"listed in {_texts_file(report, version).relative_to(ROOT).as_posix()}"
            print(f"clean    kept {report['kept']} file(s), dropped {report['dropped']}, {len(report['texts'])} text(s) "
                  f"a model or a human may read changed ({where}); resealed: {', '.join(report['resealed']) or 'nothing'}")
        else:
            print(f"canonical kept {report['kept']} file(s), dropped {report['dropped']}; no texts changed, no resealing")
        if problems:
            for line in problems[:20]:
                print(f"  left: {line}")
            print(f"PROBLEM: {len(problems)} piece(s) of development history are left - add a rule to tools/clean_engine.py "
                  "and run again; nothing was changed")
            return 1
        p = plan(staging)
        print(f"engine   {p['old_engine']} -> {p['new_engine']}")
        print(f"files    {len(p['added'])} added, {len(p['removed'])} removed, {len(p['changed'])} changed")
        for kind, names in (("added", p["added"]), ("removed", p["removed"]), ("changed", p["changed"])):
            for name in names[:20]:
                print(f"  {kind}: {name}")
            if len(names) > 20:
                print(f"  ... {len(names) - 20} more {kind}")
        if p["same_contents"]:
            return _already_bundled()
        if p["new_engine"] == p["old_engine"] and not same_version:
            print(f"PROBLEM: the engine's files changed but its version stays {version}: a run records the version it "
                  "started with, so a changed engine needs a new one. Give a new --engine-version (or --same-version "
                  "to keep it on purpose); nothing was changed")
            return 1
        if _release(p["new_engine"]) < _release(p["old_engine"]):
            print(f"note     {p['new_engine']} is lower than the bundled {p['old_engine']}: going back to an older engine")
        drift = sync_engine.check()
        if drift:
            print(f"note     the bundled engine already differs from its manifest ({len(drift)} problem(s), "
                  f"first: {drift[0]}); the backup keeps it as it is, named as drifted")
        if dry_run:
            for relative, before, after in report["texts"]:
                print(f"--- {relative}\n  - {before!r}\n  + {after!r}")
            print("dry run: nothing was changed")
            return 0
        with tempfile.TemporaryDirectory(prefix="soulrun-preflight-") as temporary:
            output = Path(temporary) / "engine_node.aisop.json"
            try:
                output.write_text(build_engine_node.render(build_engine_node.build(
                    staging / "main.aisop.json", staging / "agent_engine.aisop.json")), encoding="utf-8")
                gaps = build_engine_node.check(staging / "main.aisop.json", staging / "agent_engine.aisop.json", output)
            except Exception as exc:
                print(f"PROBLEM: engine_node.aisop.json could not be rebuilt: {type(exc).__name__}: {exc}; nothing was changed")
                return 1
            gaps += _fits_soulrun(staging)
            if not _check_wording(agent_py):
                gaps.append('fixed host wording is stale; regenerate it before upgrading')
            if gaps:
                for line in gaps:
                    print(f"PROBLEM: {line}")
                print("Preflight failed; nothing was changed. Fix the source or place new sections in tools/build_engine_node.py.")
                return 1
        kept = backup()
        print(f"backup   {kept.relative_to(ROOT).as_posix()}/ (to go back: python tools/upgrade_engine.py --restore "
              f"{kept.relative_to(ROOT).as_posix()})")
        flags = [] if legacy_clean else ["--canonical"]
        if sync_engine.main(["--from", str(staging), "--label", label or f"SoulRun engine {version}", *flags]) != 0:
            return 1
    finally:
        _drop_staging(staging)
    gaps = _fits_soulrun()
    for line in gaps:
        print(f"PROBLEM: {line}")
    if gaps:
        print(f"the new engine does not take SoulRun's calls as they are made: change SoulRun, or go back with "
              f"python tools/upgrade_engine.py --restore {kept.relative_to(ROOT).as_posix()}")
    else:
        print("calls    the new engine takes every call SoulRun makes, and a run with a named program was made")
    ok = _rebuild_and_check(agent_py) and not gaps
    changed = check_docs.set_engine_version(ROOT, version)
    if changed:
        print(f"docs     engine version {version} written in {', '.join(changed)}")
    print(LEFT_TO_RUN)
    return 0 if ok else 1


def _unpack(kept: Path, staging: Path) -> str | None:
    """Unpack the kept archive; the reason it is unusable, or None. A name that would land outside the folder
    (../ or an absolute path) makes it unusable before anything is written."""
    try:
        with zipfile.ZipFile(kept / ENGINE_ZIP) as archive:
            for name in archive.namelist():
                path = PurePosixPath(name)
                if path.is_absolute() or ".." in path.parts or ":" in name or name.startswith(("/", "\\")):
                    return f"it names a file outside the engine: {name!r}"
            damaged = archive.testzip()
            if damaged is not None:
                return f"damaged member {damaged}"
            archive.extractall(staging)
    except (zipfile.BadZipFile, zlib.error, EOFError, OSError) as exc:      # every way a damaged archive shows
        return f"{type(exc).__name__}: {exc}"
    if not (staging / "python_tools" / "lib" / "engine_core.py").is_file():
        return "no engine inside"
    return None


def _against_kept_manifest(kept: Path, staging: Path) -> list[str]:
    """Every unpacked file against the manifest kept with it: nothing missing, nothing more, nothing changed."""
    recorded = json.loads((kept / "engine_manifest.json").read_text(encoding="utf-8"))
    files = recorded.get("files") or {}
    actual = {p.relative_to(staging).as_posix(): sync_engine._sha256(p) for p in sync_engine._files(staging)}
    problems = [f"missing: {name}" for name in sorted(set(files) - set(actual))]
    problems += [f"not in the kept manifest: {name}" for name in sorted(set(actual) - set(files))]
    problems += [f"changed: {name}" for name in sorted(set(files) & set(actual)) if files[name] != actual[name]]
    if recorded.get("engine_version") != sync_engine.engine_version(staging):
        problems.append(f"the kept manifest says {recorded.get('engine_version')}, the engine says {sync_engine.engine_version(staging)}")
    return problems


def restore(kept: Path, agent_py: str | None) -> int:
    if not all((kept / name).is_file() for name in (ENGINE_ZIP, "engine_manifest.json")):
        raise SystemExit(f"{kept} is not a kept engine (made by tools/upgrade_engine.py)")
    label = json.loads((kept / "engine_manifest.json").read_text(encoding="utf-8")).get("source") or "restored engine"
    # Unpack beside the bundled engine first: a damaged archive must not cost the engine that is there now.
    staging = _fresh_staging()
    unusable = _unpack(kept, staging)
    if unusable is not None:
        _drop_staging(staging)
        state = "is unsafe" if unusable.startswith("it names a file outside") else "is damaged"
        raise SystemExit(f"{kept / ENGINE_ZIP} {state} ({unusable}): nothing was changed")
    differs = _against_kept_manifest(kept, staging)
    if differs:
        _drop_staging(staging)
        raise SystemExit(f"{kept}: the archive does not match the manifest kept with it ({len(differs)} difference(s), "
                         f"first: {differs[0]}): nothing was changed")
    recorded = json.loads((kept / "engine_manifest.json").read_text(encoding="utf-8"))
    canonical = recorded.get("source_form") == "canonical"
    leftovers = sync_engine.canonical_problems(staging) if canonical else clean_engine.check(staging)
    if leftovers:
        _drop_staging(staging)
        raise SystemExit(f"{kept} holds an engine that was never cleaned ({leftovers[0]}): bring it in with --from "
                         "instead; nothing was changed")
    gaps = _fits_soulrun(staging)
    if not _check_wording(agent_py):
        gaps.append('fixed host wording is stale')
    if gaps:
        _drop_staging(staging)
        print('PROBLEM: backup is incompatible with this wrapper: ' + '; '.join(gaps))
        print('Restore the complete older SoulRun combination; nothing was changed.')
        return 1
    replaced = backup()
    print(f"backup   {replaced.relative_to(ROOT).as_posix()}/ (the engine being replaced)")
    try:
        if sync_engine.main(["--from", str(staging), "--label", label, *(["--canonical"] if canonical else [])]) != 0:
            return 1
    finally:
        _drop_staging(staging)
    shutil.copy2(kept / "engine_manifest.json", PACKAGE / "engine_manifest.json")     # the kept record, as it was
    if (kept / "engine_node.aisop.json").is_file():
        shutil.copy2(kept / "engine_node.aisop.json", PACKAGE / "engine_node.aisop.json")
    problems = sync_engine.check()
    for line in problems:
        print(line)
    restored = sync_engine.engine_version(sync_engine.ENGINE)
    print(f"engine   {restored} restored, {'files match the kept manifest' if not problems else str(len(problems)) + ' problem(s)'}")
    ok = _rebuild_and_check(agent_py) and not problems
    check_docs.set_engine_version(ROOT, restored)
    print(LEFT_TO_RUN)
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--from", dest="source", help="the newer engine tree")
    mode.add_argument("--restore", metavar="KEPT", help="a folder under .engine_backups/ to put back")
    parser.add_argument("--engine-version", help="the version the new engine carries (required with --from)")
    parser.add_argument("--same-version", action="store_true",
                        help="allow new engine contents under the version already bundled (normally refused)")
    parser.add_argument("--legacy-clean", action="store_true", help="explicitly clean a legacy development tree; not for canonical inputs")
    parser.add_argument("--label", help="what the engine is, as the manifest records it (default: SoulRun engine <version>)")
    parser.add_argument("--dry-run", action="store_true", help="print the plan and change nothing")
    parser.add_argument("--agent-py", help="SoulBot's agent.py to check the fixed wording against (default: beside this repository)")
    args = parser.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="backslashreplace")
    if args.source:
        if not args.engine_version:
            parser.error("--engine-version is required with --from")
        return upgrade(Path(args.source).resolve(), args.engine_version, args.label, args.dry_run, args.agent_py,
                       args.same_version, args.legacy_clean)
    if args.dry_run or args.same_version or args.legacy_clean:
        parser.error("--dry-run and --same-version go with --from")
    return restore(Path(args.restore).resolve(), args.agent_py)


if __name__ == "__main__":
    sys.exit(main())

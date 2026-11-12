"""``soulrun --doctor``: is everything in place for a run? Nothing is left behind and no program's own script runs.

Each check is one line - OK, WARN or FAIL - with what was found. The checks cover what has gone wrong, or could:
the bundled engine and its fingerprint, the slim program against that engine, the agent folder and its programs,
the run folder (soulrun_cache_dir), and the ``python`` a model's shell will find: the model runs every engine tool with
that one in the entry-path form, a sub-agent's engine tools in every form, and a program's own ``python ...`` tools in
every form, and it is not necessarily the interpreter running SoulRun (only the slim form's main conversation names that
interpreter by its full path). The program form follows the switches a run would get (inline_program, slim_program),
resolved as soulrun(...) resolves them. The engine's own environment settings are reported too, read
the way the engine reads them: SoulRun reads none of them, and CACHE_NUM decides how many runs the engine keeps.

Whether an existing soulrun_cache_dir can be written is tried, not guessed: one file with an unused name is created
and removed at once. For a missing folder, only its nearest existing parent is probed; this does not verify access
after private creation or prove privacy. ``os.access`` cannot tell: on Windows it looks only at the read-only
attribute, so a folder its permissions keep closed passes it.

Time zones: when the model's provider says when its usage limit resets and names a zone ("resets 2pm
(America/New_York)"), the engine reads that zone with ``zoneinfo``; when it cannot read that zone (no time-zone data,
or a zone name it does not know) it uses local time instead and records that in the run
(SUPPLY_RESET_ZONE_UNREADABLE). Windows has no time-zone data of its own: Pythons from python.org, and virtual
environments made from them, need the ``tzdata`` package. Both this process and the model's python run that code.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import uuid
import zoneinfo
from dataclasses import asdict, dataclass
from pathlib import Path

from . import _engine, _select
from .errors import SoulRunError

OK, WARN, FAIL = "OK", "WARN", "FAIL"
PROBE = ("import sys; sys.path.insert(0, sys.argv[1]); import next_node, node_commit; "
         "print('.'.join(map(str, sys.version_info[:3])))")
ZONE = "America/New_York"                      # any named zone: either the data is there or none is
ZONE_PROBE = f"import zoneinfo; zoneinfo.ZoneInfo({ZONE!r})"
WINDOWS_PATH_LIMIT = 260
# Windows' MAX_PATH counts the null that ends a path: with long paths off the longest path that fits is one shorter.
WINDOWS_LONGEST_PATH = WINDOWS_PATH_LIMIT - 1
# docs/05SoulRun 87 (#24): how deep a run's files go inside soulrun_cache_dir, by the engine's own naming. The deepest is a
# node's public block written again with other content - 146 characters in the Creator's run 7:
#   .execution_cache/<run>/_public/plan.<n>.<node>.v<visit>.<sha256>.txt   (<node>: lib.engine_core._safe_name of its id)
# so it follows the longest node name among the programs and the engine's own nodes, which write a block in every run
# (lib.program_loader.ENGINE_NODES but the answer nodes, lib.engine_core.ANSWER_NODES): with short program names the
# engine's Engine.execute-report block goes deepest, 130 characters at a three-digit run number - deeper than an
# accepted reply's receipt, 123:
#   .execution_cache/<run>/_work/_receipts/<sha256>.<operation id, 16 hex>.json   (moved out of _work/replies/ in 87, #19)
# Run numbers are counted with at least three digits. With no program's node name to go by: DEEPEST_IN_CACHE, or the
# engine's own files when they go deeper.
DEEPEST_IN_CACHE = 150
_RUN_FOLDER = len(_select.CACHE_DIRNAME) + 2                       # ".execution_cache/" and the "/" after the run number
_BLOCK = len("_public/plan.") + 2 + len(".") + len(".v") + 1 + len(".") + 64 + len(".txt")   # ordinal 2 digits, visit 1
_RECEIPT = len("_work/_receipts/") + 64 + len(".") + 16 + len(".json")


@dataclass(frozen=True)
class Check:
    status: str
    name: str
    detail: str


def _engine_checks() -> list[Check]:
    from . import __version__
    out = [Check(OK, "versions", f"soulrun {__version__}, engine {_engine.version()}")]
    try:                                          # each item on its own: one broken file never hides the others
        problems = _engine.verify()
        out.append(Check(OK, "engine files", f"{_engine.manifest().get('installed_file_count', '?')} files match the manifest")
                   if not problems else Check(FAIL, "engine files", "; ".join(problems[:5]) + (" ..." if len(problems) > 5 else "")))
    except (SoulRunError, OSError, ValueError) as error:
        out.append(Check(FAIL, "engine files", getattr(error, "message", None) or f"{type(error).__name__}: {error}"))
    try:
        from . import _slim
        _slim.document()
        out.append(Check(OK, "slim program", "engine_node.aisop.json was built from this engine"))
    except (SoulRunError, OSError, ValueError) as error:
        out.append(Check(FAIL, "slim program", getattr(error, "message", None) or f"{type(error).__name__}: {error}"))
    # What SoulRun calls in the engine: a renamed function or parameter would otherwise show only when that path runs
    # (or, where SoulRun falls back - the language, the print cap - not at all).
    gaps = _engine.interface_problems()
    out.append(Check(OK, "engine interface", f"{sum(len(v) for v in _engine.INTERFACE.values())} functions and constants "
                     "as SoulRun calls them") if not gaps else Check(FAIL, "engine interface", "; ".join(gaps[:5])))
    return out


def _model_python(python: str | None) -> str | None:
    """What a model's shell runs as `python` - only that name: the engine and SoulRun give the model `python ...`
    commands, so a `python3` alone does not help it."""
    return python or shutil.which("python")


def _in_current_folder(found: str) -> bool:
    """Windows looks in the current folder before PATH: a `python.bat` dropped in a folder someone else made would be
    run by a check meant to run nothing of the folder's own."""
    try:
        return Path(found).resolve().parent == Path.cwd().resolve()
    except OSError:
        return False


# What runs with the `python` a model's shell finds, in every program form: none on PATH is a FAIL whatever the form.
# The slim form names the interpreter running SoulRun by its full path, but only in the main conversation's text: a
# sub-agent reads the engine's own agent_engine.aisop.json, whose steps run `python {engine_dir}/python_tools/...`, and
# a program's own tools run as the program writes them.
NO_PYTHON = ("no `python` on PATH, which these need: every engine tool in the entry-path form (slim_program off, the full "
             "form, or a turn that falls back to it), so such a run stops at its first step; a sub-agent's engine tools, "
             "in every form (`python <engine>/python_tools/...`); a program's own tools written as `python ...`, in every "
             "form. Only the slim form's main conversation runs the engine's tools without it (the interpreter running "
             "SoulRun, by its full path)")


def _python_check(python: str | None) -> Check:
    """The interpreter a model's shell finds as `python` must be able to load the engine's tools. With none, every
    program form fails (NO_PYTHON says which runs need one)."""
    found = _model_python(python)
    if not found:
        other = shutil.which("python3")
        return Check(FAIL, "python for the model", NO_PYTHON
                     + (f"; only `python3` was found ({other}) - install python-is-python3 or make `python` a link to it"
                        if other else ""))
    if python is None and _windows() and _in_current_folder(found):
        return Check(WARN, "python for the model", f"the `python` found first is in the current folder ({found}); it was "
                     "not run. A model's shell started here would run it too: check it, or start from another folder")
    try:
        done = subprocess.run([found, "-B", "-c", PROBE, str(_engine.TOOLS_DIR)], capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=60)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return Check(FAIL, "python for the model", f"{found} could not be started: {exc}")
    if done.returncode != 0:
        last = ((done.stderr or "").strip().splitlines() or ["(no error text)"])[-1]
        return Check(FAIL, "python for the model", f"{found} cannot load the engine's tools: {last}")
    note = "" if python else " (the model's shell may see a different PATH than this one)"
    return Check(OK, "python for the model", f"{found}, Python {(done.stdout or '').strip()}, loads the engine's tools{note}")


def _form_check(inline_program: bool | None = None, slim_program: bool | None = None) -> Check:
    """Which program form a run with these switches gets, resolved as soulrun(...) resolves them - each switch as
    given, else its environment variable; a value that is not a switch, or both forms asked for, stops every such run -
    the slim form unless a switch says otherwise, and only when the slim program can be built, since a run falls back to
    the entry-path form when not. The detail names the switch that decided the form and where it came from - the
    argument, or the variable (the slim form asked for by neither switch names the full form's switch when that is
    off) - and says "the default" only when no switch was given."""
    from . import _api, _blocks, _slim
    try:
        inline_given = _api.switch_given(inline_program, _api.ENV_INLINE_PROGRAM, "inline_program")
        slim_asked = _api.switch_given(slim_program, _api.ENV_SLIM_PROGRAM, "slim_program")
    except SoulRunError as error:
        return Check(FAIL, "program form", error.message)
    inline = bool(inline_given)                          # _api.read_switch: not given is off
    inline_by = "inline_program" if inline_program is not None else _api.ENV_INLINE_PROGRAM
    slim_by = "slim_program" if slim_program is not None else _api.ENV_SLIM_PROGRAM
    if inline and slim_asked:
        return Check(FAIL, "program form", f"both {inline_by} and {slim_by} are on: every run would stop with "
                     "PROGRAM_FORMS_CONFLICT")
    if inline:
        return Check(OK, "program form", f"full (the whole main program in the text; {inline_by})")
    if slim_asked is False:
        return Check(OK, "program form", f"entry_path ({slim_by} is off: the model reads the engine program itself, "
                     "SoulBot's text)")
    # The slim form: asked for by the slim switch, or the default - with the full form's switch off, or not given at all.
    why = (f"{slim_by} is on" if slim_asked else
           f"{inline_by} is off and no slim switch is given" if inline_given is False else "the default")
    try:
        _slim.entry_program("x", cache_dir="x", entry_mode="fresh")
    except (SoulRunError, OSError, ValueError) as error:
        return Check(WARN, "program form", f"slim ({why}), but the slim program cannot be built "
                     f"({getattr(error, 'message', error)}): every run falls back to entry_path")
    return Check(OK, "program form", f"slim ({why}: the engine program handed out by engine node; the model runs "
                 f"engine tools and reads the business program through {_blocks.soulrun_command()})")


def _settings_check() -> Check:
    """The engine's own environment settings. SoulRun reads none of them; the engine does, in every run, and falls
    back without a word when one is not what it expects - so each is read here the way the engine reads it."""
    prepare, supply = _engine.load("prepare_cache"), _engine.load("lib.supply_flow")
    said, status = [], OK
    raw = os.environ.get("CACHE_NUM")
    if raw is not None:
        kept = prepare._cache_num()
        try:
            int(raw)
            said.append(f"CACHE_NUM={raw}: keeps the newest {kept} runs; a new run deletes the oldest finished ones beyond that")
        except ValueError:
            status = WARN
            said.append(f"CACHE_NUM={raw!r} is not a number: the engine keeps {kept} runs")
    policy = prepare.resume_interrupted_policy()
    if policy.get("source") == "invalid_env":
        status = WARN
        said.append(f"{prepare.RESUME_INTERRUPTED_ENV}={os.environ.get(prepare.RESUME_INTERRUPTED_ENV)!r} is not a switch value: "
                    "the engine treats it as off (after a restart the human is asked)")
    elif policy.get("source") == "explicit_env":
        said.append(f"{prepare.RESUME_INTERRUPTED_ENV} is " + ("on: after a restart an unfinished run re-enters by itself"
                                                              if policy.get("enabled") else "off: after a restart the human is asked"))
    raw = os.environ.get(supply.SUPPLY_WAIT_MAX_ENV)
    if raw is not None:
        seconds = supply.max_wait_seconds()
        try:
            given = int(raw)
        except ValueError:
            given = None
        if given is None or given != seconds:
            status = WARN
            said.append(f"{supply.SUPPLY_WAIT_MAX_ENV}={raw!r} is not a number of seconds from 60 up: the engine waits up to "
                        f"{seconds} s for a usage limit")
        else:
            said.append(f"{supply.SUPPLY_WAIT_MAX_ENV}={raw}: the engine waits up to {seconds} s for a usage limit")
    raw = os.environ.get("SOULBOT_HOST_REPORT_WAIT_S")
    if raw is not None:
        try:
            said.append(f"SOULBOT_HOST_REPORT_WAIT_S={float(raw):g}: seconds the engine waits for the host's report of streamed text")
        except ValueError:
            return Check(FAIL, "engine settings", f"SOULBOT_HOST_REPORT_WAIT_S={raw!r} is not a number: the engine cannot be "
                         "loaded with it, so no run starts")
    if not said:
        return Check(OK, "engine settings", f"none set: the engine keeps {prepare.DEFAULT_CACHE_NUM} runs, asks the human after "
                     f"a restart, and waits up to {supply.SUPPLY_WAIT_MAX_DEFAULT // 3600} h for a usage limit")
    return Check(status, "engine settings", "; ".join(said))


def _zone_data(python: str | None) -> bool:
    """Can this interpreter (None: the one running SoulRun) read a named time zone?"""
    if python is None:
        try:
            zoneinfo.ZoneInfo(ZONE)
            return True
        except (zoneinfo.ZoneInfoNotFoundError, ValueError, OSError):
            return False
    try:
        return subprocess.run([python, "-B", "-c", ZONE_PROBE], capture_output=True, timeout=60).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def _zone_check(model_python: str | None) -> Check:
    pythons = [("this Python", sys.executable, None)]
    if model_python and os.path.normcase(os.path.abspath(model_python)) != os.path.normcase(os.path.abspath(sys.executable)):
        pythons.append(("the model's python", model_python, model_python))
    missing = [f"{who} ({path})" for who, path, probe in pythons if not _zone_data(probe)]
    if not missing:
        return Check(OK, "time zones", "named time zones can be read" + (" by both Pythons" if len(pythons) > 1 else ""))
    return Check(WARN, "time zones", f"no time-zone data in {' and '.join(missing)}: a usage-limit reset time that names "
                 "a zone is read as local time; `python -m pip install tzdata` in that Python fixes it")


def _writable(folder: Path) -> bool:
    """One attempt at creating a file here, removed at once (on Windows the system removes it when it is closed).

    Not ``tempfile``: on Windows, a refusal in a folder that ``os.access`` calls writable makes it try another
    name, up to ``os.TMP_MAX`` times (2,147,483,647 there) - in practice it never gives up.
    """
    probe = folder / f".soulrun-doctor-{uuid.uuid4().hex}"
    try:
        handle = os.open(probe, os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_TEMPORARY", 0))
    except OSError:
        return False
    os.close(handle)
    try:
        probe.unlink()
    except OSError:                                            # already removed when it was closed
        pass
    return True


def _windows() -> bool:
    return os.name == "nt"


def _long_paths_enabled() -> bool:
    """Windows' own switch for paths of 260 characters and more (read only; Python itself is ready for them)."""
    try:
        import winreg  # noqa: PLC0415 - Windows only
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\FileSystem") as key:
            return winreg.QueryValueEx(key, "LongPathsEnabled")[0] == 1
    except (ImportError, OSError):
        return False


def _node_names(program: Path) -> list[str]:
    """Every node id of one program as the engine gives them (a node of the entry graph by its name, a node of a module
    as <parent>/<module>.<node>), worked out by the engine's own loader; nothing of the program is run."""
    loader = _engine.load("lib.program_loader")
    loaded = loader.load_program(program)
    names = set(loaded.entry.tasks.get("main", {}).get("nodes", {}))
    for doc_name, doc in loaded.docs.items():
        for task, parsed in doc.tasks.items():
            for node in parsed.get("nodes", {}):
                try:
                    target = loader.module_target(loaded, doc_name, task, node)
                    module = loader.resolve_module(loaded, doc_name, target) if target else None
                except loader.ProgramError:
                    continue
                if module:
                    inner = loaded.docs[module["doc"]].tasks.get(module["task"], {}).get("nodes", {})
                    names |= {f"{node}/{module['ns']}.{name}" for name in inner}
    return sorted(names)


def _engine_block_stems() -> list[tuple[int, str]]:
    """The engine's own nodes that write a public block in every run - its node list but the answer nodes, which write
    none - with the length of their file-name stem; [] when the engine cannot say."""
    try:
        core = _engine.load("lib.engine_core")
        return [(len(core._safe_name(name)), name) for name in _engine.load("lib.program_loader").ENGINE_NODES
                if name not in core.ANSWER_NODES]
    except Exception:  # noqa: BLE001 - the engine checks report a broken engine; this one goes on without its nodes
        return []


def _deepest(programs: list[Path], cache: Path) -> tuple[int, str | None]:
    """How deep, about, the deepest file a run of these programs goes inside ``cache`` (soulrun_cache_dir), and which
    file that is: a block of a program's node or of one of the engine's own nodes. ``(DEEPEST_IN_CACHE, None)`` when no
    program's node names can be read (see DEEPEST_IN_CACHE; more, when the engine's own files go deeper)."""
    runs = [int(p.name) for p in (cache / _select.CACHE_DIRNAME).glob("*") if p.name.isdigit()] \
        if (cache / _select.CACHE_DIRNAME).is_dir() else []
    run = _RUN_FOLDER + max(3, len(str(max(runs, default=0) + 1)))
    longest = None
    for program in programs:
        try:
            stems = [(len(_engine.load("lib.engine_core")._safe_name(name)), name) for name in _node_names(program)]
        except Exception:  # noqa: BLE001 - a program the engine cannot load names no node; the check goes on
            continue
        for size, name in stems:
            if longest is None or size > longest[0]:
                longest = (size, name.rsplit("/", 1)[-1], program.name)
    floor = (run + _RECEIPT, "the receipt of an accepted reply")    # the deepest of what every run writes, whatever the program
    for size, name in _engine_block_stems():
        if run + _BLOCK + size > floor[0]:
            floor = (run + _BLOCK + size, f"a block of engine node {name}")
    if longest is None:
        return max(DEEPEST_IN_CACHE, floor[0]), None
    block = run + _BLOCK + longest[0]
    if block >= floor[0]:
        return block, f"a block of node {longest[1]} ({longest[2]})"
    return floor


def _path_check(cache: Path, programs: list[Path] | None = None) -> Check | None:
    """On Windows, would the deepest file a run writes be too long for the 260-character limit, which counts the null
    that ends a path (WINDOWS_LONGEST_PATH)? How deep a run's files go follows the engine's naming and the node names
    of the programs (_deepest)."""
    if not _windows():
        return None
    depth, deepest = _deepest(programs or [], cache)
    longest = len(str(cache).encode("utf-16-le")) // 2 + 1 + depth   # Windows counts UTF-16 units (docs/05SoulRun 88, problem 84)
    which = f" ({deepest})" if deepest else f" (no node name to go by: {depth} assumed inside the folder)"
    if longest <= WINDOWS_LONGEST_PATH:
        return Check(OK, "path length", f"the deepest file a run writes would be about {longest} characters long{which}, "
                     f"within Windows' {WINDOWS_PATH_LIMIT}")
    if _long_paths_enabled():
        return Check(OK, "path length", f"the deepest file a run writes would be about {longest} characters long{which}; "
                     "Windows long paths are enabled")
    return Check(WARN, "path length", f"the deepest file a run writes would be about {longest} characters long{which}, "
                 f"past the {WINDOWS_LONGEST_PATH} characters Windows allows (its {WINDOWS_PATH_LIMIT} counts the null that "
                 "ends a path; long paths are not enabled): the engine could fail to write it. Name a shorter "
                 f"soulrun_cache_dir (at most {WINDOWS_LONGEST_PATH - 1 - depth} characters), or enable long paths "
                 "in Windows")


def _programs(places: _select.Places) -> tuple[dict, list[str]]:
    """The programs a run can choose from, folder by folder (a registry may list them deeper than one level), and the
    ones in the wrong folder: an AISP skill under aiap/ or an AIAP program under aisp/ is not a candidate there."""
    found, misplaced = {}, []
    for protocol, folder in (("aiap", places.aiap_dir), ("aisp", places.aisp_dir)):
        other = "aisp" if protocol == "aiap" else "aiap"
        own = sorted({p.parent.name for p in folder.rglob(_select.ENTRY_FILES[protocol])}) if folder.is_dir() else []
        found[protocol] = own
        if folder.is_dir():
            misplaced += [f"{p.parent.name} ({_select.ENTRY_FILES[other]} under {protocol}/)" for p in folder.rglob(_select.ENTRY_FILES[other])
                          if not (p.parent / _select.ENTRY_FILES[protocol]).is_file()]
    return found, sorted(misplaced)


def _place_checks(agent_dir, soulrun_cache_dir, aiap_dir=None, aisp_dir=None, aiap=None, aisp=None) -> list[Check]:
    # The program side first, on its own: a wrong run folder must not hide that the agent folder has no programs.
    try:
        agent, aiap_folder, aisp_folder, sources = _select.program_places(agent_dir=agent_dir, aiap_dir=aiap_dir, aisp_dir=aisp_dir)
    except SoulRunError as error:                              # name the check after the folder that is wrong
        name = {"agent_dir": "agent folder", "aiap_dir": "programs", "aisp_dir": "programs"}
        return [Check(FAIL, name.get(error.field or "", "folders"), error.message)]
    places = _select.Places(agent_dir=agent, aiap_dir=aiap_folder, aisp_dir=aisp_folder,
                            soulrun_cache_dir=agent / _select.SOULRUN_CACHE, sources=sources)
    out = _program_checks(places, aiap, aisp)
    programs = _program_dirs(places, aiap, aisp)
    try:
        places = _select.resolve_places(agent_dir=agent_dir, aiap_dir=aiap_dir, aisp_dir=aisp_dir,
                                        soulrun_cache_dir=soulrun_cache_dir, create=False)
    except SoulRunError as error:
        return out + [Check(FAIL, "soulrun_cache_dir" if error.field == "soulrun_cache_dir" else "folders", error.message)]
    return out + _cache_checks(places, programs)


def _program_dirs(places, aiap, aisp) -> list[Path]:
    """The programs a run with these arguments can run: the ones named, else every one in the program folders."""
    named = [_select.resolve_designated(protocol, value, places) for protocol, value in (("aiap", aiap), ("aisp", aisp))
             if value is not None]
    if named:
        return [item.directory for item in named if item.found]
    return sorted({entry.parent for protocol, folder in (("aiap", places.aiap_dir), ("aisp", places.aisp_dir))
                   if folder.is_dir() for entry in folder.rglob(_select.ENTRY_FILES[protocol])})


def _program_checks(places, aiap, aisp) -> list[Check]:
    out = [Check(OK, "agent folder", f"{places.agent_dir} (given by {places.sources['agent_dir']})")]
    designated = [_select.resolve_designated(protocol, value, places) for protocol, value in (("aiap", aiap), ("aisp", aisp))
                  if value is not None]
    if designated:
        missing = [f"{item.protocol}={item.given} (looked in {item.directory})" for item in designated if not item.found]
        out.append(Check(FAIL, "programs", "named but not found: " + "; ".join(missing)) if missing else
                   Check(OK, "programs", "named: " + ", ".join(item.directory.name for item in designated)))
    else:
        programs, misplaced = _programs(places)
        total = sum(len(v) for v in programs.values())
        listing = "; ".join(f"{kind}: {', '.join(names) if names else 'none'}" for kind, names in programs.items())
        out.append(Check(OK if total else FAIL, "programs", f"{total} program(s) - {listing}" if total else
                         f"no program with an entry file under {places.aiap_dir} or {places.aisp_dir}"))
        if misplaced:
            out.append(Check(WARN, "misplaced programs", "not candidates where they are: " + "; ".join(misplaced)))
        out += _registry_checks(places)
    return out


def _registry_checks(places) -> list[Check]:
    """Registry scripts: the engine runs them - with the interpreter running SoulRun, at every run - when it is given
    the agent folder, and they decide which programs are candidates. Not run here: only named."""
    from . import _api
    try:
        _api._registry_folders_need_their_agent(places)
    except SoulRunError as error:                       # a call with these folders would be refused the same way
        return [Check(FAIL, "registry scripts", error.message)]
    scripts = [places.agent_dir / protocol / name for protocol, name in _select.REGISTRY_SCRIPTS.items()
               if places.aiap_dir == places.agent_dir / "aiap" and places.aisp_dir == places.agent_dir / "aisp"
               and (places.agent_dir / protocol / name).is_file()]
    if not scripts:
        return []
    return [Check(WARN, "registry scripts", f"{', '.join(str(s) for s in scripts)}: run by the engine at every run, with "
                  f"the Python running SoulRun ({sys.executable}), to decide which programs are candidates - keep only "
                  "scripts you trust here")]


def _cache_checks(places, programs: list[Path] | None = None) -> list[Check]:
    out: list[Check] = []
    data = places.soulrun_cache_dir  # a file, another engine's folder or one with other files was refused above
    target = data if data.is_dir() else next((p for p in data.parents if p.exists()), None)
    if target is None or not _writable(target):
        out.append(Check(FAIL, "soulrun_cache_dir", f"{data} cannot be written"))
        return out
    length = _path_check(data, programs)
    if length is not None:
        out.append(length)
    if not data.is_dir():
        out.append(Check(OK, "soulrun_cache_dir", f"{data} (given by {places.sources['soulrun_cache_dir']}): "
                         f"write probe passed for {target}; creation will be attempted at the first run; "
                         "access to the new folder and its privacy are not verified"))
        return out
    root = data / _select.CACHE_DIRNAME
    runs = [p for p in root.iterdir() if p.is_dir() and p.name.isdigit()] if root.is_dir() else []
    out.append(Check(OK, "soulrun_cache_dir", f"{data} (given by {places.sources['soulrun_cache_dir']}), {len(runs)} run(s) kept"))
    if not (data / _select.IGNORE_FILE).is_file():
        out.append(Check(WARN, "version control", f"{data} has no .gitignore: if it sits in a repository, run data could be committed"))
    mode = data.stat().st_mode & 0o777
    if os.name != "nt" and mode & 0o077:                 # POSIX: run data holds the users' own words
        out.append(Check(WARN, "permissions", f"{data} can be opened by other users of this machine (mode {mode:o}); "
                         f"run data holds the users' words: chmod 700 {data}"))
    unfinished = []
    try:
        unfinished = _engine.load("prepare_cache").interrupted_runs(data)
    except Exception:  # noqa: BLE001 - a check never fails on a report
        pass
    if unfinished:
        out.append(Check(WARN, "unfinished runs", f"{len(unfinished)} run(s) not finished: still running, or cut off by a "
                         "restart (host.interrupted_runs lists them)"))
    return out


def _safely(name: str, check) -> list[Check]:
    """One check group; whatever goes wrong inside it becomes its FAIL line - the doctor never breaks on the broken
    setup it is there to describe (a damaged manifest, a missing slim program, a folder it may not read)."""
    try:
        result = check()
    except SoulRunError as error:
        return [Check(FAIL, name, error.message)]
    except Exception as exc:  # noqa: BLE001 - reported as the check's result
        return [Check(FAIL, name, f"{type(exc).__name__}: {exc}")]
    return result if isinstance(result, list) else [result]


def run(*, agent_dir=None, soulrun_cache_dir=None, aiap_dir=None, aisp_dir=None, aiap=None, aisp=None,
        inline_program: bool | None = None, slim_program: bool | None = None, python: str | None = None) -> list[Check]:
    """Every check, with the same folders, named programs and program-form switches a run with these arguments would
    use."""
    engine = _safely("engine", _engine_checks)
    if engine[0].name == "engine":             # the engine itself cannot be read: every other check would only repeat it
        return engine
    return (engine + _safely("python for the model", lambda: _python_check(python))
            + _safely("time zones", lambda: _zone_check(_model_python(python)))
            + _safely("program form", lambda: _form_check(inline_program, slim_program))
            + _safely("engine settings", _settings_check)
            + _safely("folders", lambda: _place_checks(agent_dir, soulrun_cache_dir, aiap_dir, aisp_dir, aiap, aisp)))


def render(checks: list[Check], as_json: bool) -> str:
    if as_json:
        return json.dumps({"ok": not any(c.status == FAIL for c in checks), "checks": [asdict(c) for c in checks]},
                          ensure_ascii=False, indent=1)
    lines = [f"{c.status:<4} {c.name}: {c.detail}" for c in checks]
    fails = sum(c.status == FAIL for c in checks)
    lines.append("all checks passed" if not fails else f"{fails} check(s) failed")
    return "\n".join(lines)


def exit_code(checks: list[Check]) -> int:
    return 1 if any(c.status == FAIL for c in checks) else 0


__all__ = ["Check", "run", "render", "exit_code", "OK", "WARN", "FAIL", "PROBE", "ZONE"]

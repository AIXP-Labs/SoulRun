"""Where SoulRun's engine lives, and the one place that loads its modules.

The engine ships with a manifest of its files (see tools/sync_engine.py). Its Python tools are plain top-level
modules (``prepare_cache``, ``lib.engine_core`` ...) that expect their own folder on ``sys.path`` -
the way SoulBot loads them. SoulRun does the same, but in one place and with a check that the names
really come from the bundled engine.
"""
from __future__ import annotations

import contextlib
import importlib
import inspect
import json
import re
import sys
import threading
from functools import lru_cache
from pathlib import Path
from types import ModuleType

from .errors import EngineUnavailable, SoulRunError

ENGINE_DIRNAME = "soulrun_aiap"
ENGINE_DIR: Path = (Path(__file__).resolve().parent / ENGINE_DIRNAME)
TOOLS_DIR: Path = ENGINE_DIR / "python_tools"
MAIN_PROGRAM: Path = ENGINE_DIR / "main.aisop.json"
AGENT_PROGRAM: Path = ENGINE_DIR / "agent_engine.aisop.json"
MANIFEST: Path = Path(__file__).resolve().parent / "engine_manifest.json"

_LOCK = threading.RLock()


def _require_engine() -> None:
    if not (TOOLS_DIR / "lib" / "engine_core.py").is_file():
        raise EngineUnavailable("ENGINE_MISSING", f"the bundled engine is not at {ENGINE_DIR}",
                                field="engine", expected="soulrun installed with its engine files")


@lru_cache(maxsize=1)
def engine_names() -> frozenset:
    """The top-level module names the engine's tools use (``lib``, ``prepare_cache`` ...). Once SoulRun has loaded the
    engine, these names belong to it in this process: the tools import each other by them."""
    return frozenset({p.stem for p in TOOLS_DIR.glob("*.py")} | {p.name for p in TOOLS_DIR.iterdir() if (p / "__init__.py").is_file()})


_CHECKED: set = set()                                 # (name, id(module)) already found to be the engine's own


def _check_names() -> None:
    """Every module in this process under one of the engine's names must be the engine's own - also the ones the
    engine only imports indirectly: another copy (a host's own ``lib`` package, a second engine) would be used by it."""
    tools = TOOLS_DIR.resolve()
    for key, module in list(sys.modules.items()):
        if key.split(".", 1)[0] not in engine_names() or (key, id(module)) in _CHECKED:
            continue
        origin = getattr(module, "__file__", None)
        where = Path(origin).resolve() if origin else None
        if where is None or tools not in where.parents:
            raise EngineUnavailable(
                "ENGINE_NAME_CLASH", f"the name {key!r} is already taken in this process by {where or 'a module without a file'}; "
                "the engine's tools use it too, so the engine cannot be loaded beside it", field=key,
                expected=f"no module of that name other than the engine's (under {TOOLS_DIR})")
        _CHECKED.add((key, id(module)))


def load(name: str) -> ModuleType:
    """Import one engine module (``"prepare_cache"``, ``"lib.engine_core"`` ...) from the bundled engine. A name that is
    not one of the engine's modules is refused before anything is imported."""
    _require_engine()
    base = TOOLS_DIR.joinpath(*name.split("."))
    if not re.fullmatch(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*", name) or not (base.with_suffix(".py").is_file() or (base / "__init__.py").is_file()):
        raise EngineUnavailable("ENGINE_MODULE_UNKNOWN", f"{name!r} is not a module of the bundled engine", field=name,
                                expected=f"a module under {TOOLS_DIR}, such as prepare_cache or lib.engine_core")
    with _LOCK:
        _check_names()
        tools = str(TOOLS_DIR)
        if tools not in sys.path:
            sys.path.insert(0, tools)
        try:
            module = importlib.import_module(name)
        except ImportError as exc:
            raise EngineUnavailable("ENGINE_IMPORT_FAILED", f"{name} could not be imported from the bundled engine: {exc}",
                                    field=name, expected="the engine files as installed (soulrun --verify-engine)") from exc
        _check_names()                                # what the import brought in, too
    origin = Path(getattr(module, "__file__", "") or "").resolve()
    if TOOLS_DIR.resolve() not in origin.parents:
        raise EngineUnavailable(
            "ENGINE_NAME_CLASH",
            f"the name {name!r} is already taken by {origin} in this process; the engine's own module was not loaded",
            field=name, expected=f"a module under {TOOLS_DIR}")
    return module


@lru_cache(maxsize=1)
def version() -> str:
    """The engine's own version string, read from its source (nothing is imported)."""
    _require_engine()
    text = (TOOLS_DIR / "lib" / "engine_core.py").read_text(encoding="utf-8")
    match = re.search(r'ENGINE_VERSION = "([^"]+)"', text)
    if not match:
        raise EngineUnavailable("ENGINE_VERSION_UNKNOWN", "the bundled engine does not state its version", field="engine")
    return match.group(1)


@lru_cache(maxsize=1)
def manifest() -> dict:
    """The recorded fingerprint of the bundled engine (empty when the manifest is absent)."""
    if not MANIFEST.is_file():
        return {}
    try:
        data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise EngineUnavailable("ENGINE_MANIFEST_INVALID", f"{MANIFEST.name} cannot be read: {exc}", field="engine",
                                expected="the manifest installed with SoulRun (reinstall the package)") from exc
    if not isinstance(data, dict):
        raise EngineUnavailable("ENGINE_MANIFEST_INVALID", f"{MANIFEST.name} is not a JSON object", field="engine",
                                expected="the manifest installed with SoulRun (reinstall the package)")
    return data


# What SoulRun calls in the engine, and the parameters it passes by name (None: a constant). A newer engine that renames
# one fails only when that path runs; tools/upgrade_engine.py and soulrun --doctor check the list instead.
INTERFACE = {
    "prepare_cache": {
        "prepare_execution_context": ("engine_aiap_dir", "session_id", "origin_channel", "requested_model", "host_fences",
                                      "user_id", "host_tools", "human_turn", "host_turn_id", "origin_type"),
        "latest_cache_for_session": (), "_read_index": (), "_read_lifecycle": (), "recovery_reentry_dir": (),
        "interrupted_runs": ("created_before",),
        "mark_interrupted": (), "resume_prompt_for": (), "open_restart_question": ("instance_started_at", "resume_mode"),
        "finalize_execution_context": ("response_persisted",), "resume_interrupted_enabled": (), "PROTECTED_STATES": None,
        "resume_interrupted_policy": (), "_cache_num": (), "DEFAULT_CACHE_NUM": None, "RESUME_INTERRUPTED_ENV": None,
        "is_cancel_message": (),
        "_cut_off_stop_id": ("undecided",),       # docs/05SoulRun 90 rounds 6-7: _api's machine-turn and named-program checks
    },
    "lib.supply_flow": {"max_wait_seconds": (), "SUPPLY_WAIT_MAX_ENV": None, "SUPPLY_WAIT_MAX_DEFAULT": None},
    "lib.engine_core": {"init_run": ("agent_dir", "registry_roots"), "ENGINE_VERSION": None,
                        "terminate_run": ("kind", "by", "reason"),                   # a run of another build (_api._other_build_turn)
                        "_read_run_input": (), "_load_routed_program": (),           # soulrun --program (_program)
                        "_node_key": (),                                              # soulrun --report (_report)
                        "_safe_name": (), "ANSWER_NODES": None,                       # soulrun --doctor, path length
                        # docs/05SoulRun 87 (#12): the sub-agent doors of soulrun.host
                        "observe_dispatch_start": ("session_id", "tool_call_id", "event_id", "at", "resume_agent_id", "policy_ref"),
                        "record_dispatch_return": ("session_id", "tool_call_id", "event_id", "at", "status", "agent_id",
                                                   "completion_tool_call_id", "observation"),
                        "record_dispatch_task_event": ("session_id", "agent_id", "tool_call_id", "event_id", "at", "event_type",
                                                       "status"),
                        "record_dispatch_resume_failure": ("session_id", "agent_id", "tool_call_id", "event_id", "at"),
                        "native_resume_start": ("session_id", "agent_id", "bootstrap_sha"), "native_parent_policy": ()},
    "lib.dispatch_scope": {"enabled": ()},
    "lib.dispatch_resource_context": {
        "record_request": ("parent_session_id", "parent_tool_call_id", "tool_call_id", "tool_name", "raw_input", "event_id", "at",
                           "native_parent_tool_call_id"),
        "record_result": ("parent_session_id", "parent_tool_call_id", "tool_call_id", "tool_name", "status", "event_id", "at",
                          "native_parent_tool_call_id"),
        "resolve_parent": ("parent_session_id", "parent_tool_call_id", "native_parent_tool_call_id")},
    "lib.run_store": {"RunStore": ()},
    "lib.aisop_parse": {"entry_nodes": ()},
    "lib.program_loader": {"registry_snapshot": (), "load_program": (), "module_target": (), "resolve_module": (),
                           "ProgramError": None, "ENGINE_NODES": None},              # soulrun --doctor, path length
    "checkpoint_recovery": {"handle_runner_recovery": ("resume_mode",)},
    "public_delivery_observer": {"observe_persisted_response": (), "_norm": ()},
    "lib.stop_flow": {"mark_stop": ("session_id",), "mark_stop_menu_delivered": ("question_id",)},
    "lib.stop_state": {"stop_status": ()},
    "lib.render": {"detect_language": ()},
    "lib.reply_io": {"PRINT_CAP": None},
    "lib.menu_history": {"ref": (), "current_refs": ()},
}


def interface_problems() -> list[str]:
    """Each function or constant of INTERFACE the bundled engine lacks, or a parameter SoulRun passes that it does not
    take ([] = the engine takes every call as SoulRun makes it)."""
    problems = []
    for module_name, names in INTERFACE.items():
        try:
            module = load(module_name)
        except Exception as exc:  # noqa: BLE001 - reported, whatever it is
            problems.append(f"{module_name}: cannot be loaded ({type(exc).__name__}: {exc})")
            continue
        for name, parameters in names.items():
            if not hasattr(module, name):
                problems.append(f"{module_name}.{name}: missing")
                continue
            if not parameters:
                continue
            try:
                accepted = inspect.signature(getattr(module, name)).parameters
            except (TypeError, ValueError):
                continue
            if any(p.kind is p.VAR_KEYWORD for p in accepted.values()):
                continue
            missing = [p for p in parameters if p not in accepted]
            if missing:
                problems.append(f"{module_name}.{name}: takes no parameter {', '.join(missing)}")
    return problems


def _from_engine(exc: BaseException) -> bool:
    """Was this exception's class defined by the bundled engine (its modules have plain names such as lib.engine_core)?"""
    for cls in type(exc).__mro__:
        source = getattr(sys.modules.get(cls.__module__), "__file__", None)
        if source and Path(source).resolve().is_relative_to(ENGINE_DIR.resolve()):
            return True
    return False


@contextlib.contextmanager
def translated(*, interface: bool = False):
    """Errors the engine raises come out as SoulRun's own (``SoulRunError``): the engine's code, field and expected
    kept, the original attached as the cause. ``interface``: a TypeError or AttributeError here means the engine
    no longer takes SoulRun's call as it is made (ENGINE_INTERFACE_CHANGED) - used only where SoulRun has checked
    its own arguments first."""
    try:
        yield
    except SoulRunError:
        raise
    except Exception as exc:
        if _from_engine(exc):
            raise SoulRunError(str(getattr(exc, "code", None) or type(exc).__name__),
                               str(getattr(exc, "message", None) or getattr(exc, "detail", None) or exc),
                               field=getattr(exc, "field", None), expected=getattr(exc, "expected", None)) from exc
        if interface and isinstance(exc, (TypeError, AttributeError)):
            raise SoulRunError("ENGINE_INTERFACE_CHANGED", f"the engine refused SoulRun's call: {type(exc).__name__}: {exc}",
                               field="engine", expected="the engine this SoulRun was built with (soulrun --verify-engine)") from exc
        raise


def main_program_text() -> str:
    """The engine's main program, exactly as shipped."""
    _require_engine()
    return MAIN_PROGRAM.read_text(encoding="utf-8")


def agent_program_text() -> str:
    """The engine's sub-agent program, exactly as shipped."""
    _require_engine()
    return AGENT_PROGRAM.read_text(encoding="utf-8")


NOT_INSTALLED = ("tests/", "RELEASE", "pytest.ini")       # repository-only engine files (same list as tools/sync_engine.py)


def verify() -> list[str]:
    """Compare the engine files that are present with the recorded manifest. An empty list means "unchanged".

    Repository-only files (the engine's tests, release notes) may be absent - an installed package does
    not carry them - but when present they are checked like the rest.
    """
    import hashlib

    _require_engine()
    recorded = manifest().get("files")
    if not recorded:
        return ["no manifest: the bundled engine cannot be verified"]
    problems = []
    for name, digest in sorted(recorded.items()):
        path = ENGINE_DIR / name
        if not path.is_file():
            if not name.startswith(NOT_INSTALLED):
                problems.append(f"missing: {name}")
            continue
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            problems.append(f"changed: {name}")
    skip = {"__pycache__", ".pytest_cache", ".execution_cache"}
    for path in ENGINE_DIR.rglob("*"):
        relative = path.relative_to(ENGINE_DIR)
        if path.is_file() and not (set(relative.parts) & skip) and path.suffix != ".pyc" and relative.as_posix() not in recorded:
            problems.append(f"not in manifest: {relative.as_posix()}")
    # The manifest itself: its file list must still give the digest it records. A file changed together with its line
    # in the manifest passes the checks above but not this one (unless the digest was rewritten too: against that,
    # compare `soulrun --engine-info`'s installed_digest_now with the digest published with the release).
    listed = {name: sha for name, sha in recorded.items() if not name.startswith(NOT_INSTALLED)}
    if manifest().get("installed_digest") != _list_digest(listed):
        problems.append("manifest: its file list no longer gives the installed_digest it records (the manifest was edited)")
    return problems


def _list_digest(files: dict) -> str:
    """A manifest's digest of a file list, as tools/sync_engine.py writes it: one "name NUL sha256" line per file, sorted."""
    import hashlib
    return hashlib.sha256("".join(f"{name}\0{sha}\n" for name, sha in sorted(files.items())).encode("utf-8")).hexdigest()


def installed_digest_now() -> str:
    """The digest of the engine files present now (installed ones, caches left out), worked out from the files
    themselves - comparable with a digest published with a release, which the manifest beside them cannot vouch for."""
    import hashlib
    skip = {"__pycache__", ".pytest_cache", ".execution_cache"}
    files = {}
    for path in ENGINE_DIR.rglob("*"):
        relative = path.relative_to(ENGINE_DIR)
        name = relative.as_posix()
        if path.is_file() and not (set(relative.parts) & skip) and path.suffix != ".pyc" and not name.startswith(NOT_INSTALLED):
            files[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    return _list_digest(files)


def info() -> dict:
    recorded = manifest()
    return {
        "engine_version": version(),
        "engine_dir": str(ENGINE_DIR),
        "source": recorded.get("source"),
        "digest": recorded.get("digest"),
        "installed_digest": recorded.get("installed_digest"),
        "installed_digest_now": installed_digest_now() if ENGINE_DIR.is_dir() else None,   # from the files themselves
        "recorded_at": recorded.get("recorded_at"),
    }

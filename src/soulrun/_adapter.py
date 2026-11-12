"""Telling the engine which programs are candidates.

The engine's ``prepare`` entry creates a run from "everything registered under the agent folder" and
takes no other choice. The engine itself can already build a run from an explicit folder list
(``registry_roots``); that path is simply not offered by ``prepare`` yet. Until it is, this module
passes the choice through *in memory, for the duration of one prepare call*: the engine's files are
never modified, and the moment the engine offers these parameters this file can be deleted.

Everything here is a workaround for a missing engine parameter and is recorded as such in the
project's issue log.
"""
from __future__ import annotations

import contextlib
import threading
from pathlib import Path

from . import _engine

_LOCK = threading.RLock()


@contextlib.contextmanager
def candidates(*, agent_dir: Path | None = None, registry_roots: list[Path] | None = None, only: list[Path] | None = None):
    """While active, every run the engine creates uses these candidates.

    ``agent_dir``       - use the engine's normal discovery, but for this agent folder.
    ``registry_roots``  - scan these folders instead (no registry scripts needed).
    ``only``            - of what the scan finds, keep just these program folders (designated programs).

    With no argument the engine is left completely alone.
    """
    if agent_dir is None and not registry_roots:
        yield
        return
    core = _engine.load("lib.engine_core")
    loader = _engine.load("lib.program_loader")
    with _LOCK:
        original_init, original_scan = core.init_run, loader.registry_snapshot
        keep = {Path(p).resolve() for p in only} if only else None

        def init_run(cache_dir, **kwargs):
            kwargs.pop("entry_path", None)
            if registry_roots:
                kwargs["agent_dir"] = None
                kwargs["registry_roots"] = [str(root) for root in registry_roots]
            else:
                kwargs["agent_dir"] = str(agent_dir)
                kwargs["registry_roots"] = None
            return original_init(cache_dir, **kwargs)

        def registry_snapshot(root):
            found = original_scan(root)
            if keep is None:
                return found
            return [item for item in found if Path(item["dir"]).resolve() in keep]

        core.init_run, loader.registry_snapshot = init_run, registry_snapshot
        try:
            yield
        finally:
            core.init_run, loader.registry_snapshot = original_init, original_scan

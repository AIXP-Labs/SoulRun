"""The file holding the user's words (soulrun --user-message-file), once its run is ready (docs/05SoulRun 69, 70).

An agent writes the human's words into a file for SoulRun; left where it was written, the words would sit in the
project, outside the run data and its .gitignore. Once a turn has its run, the file is moved into that run's folder -
``<run>/_soulrun/message.<n>.txt`` - and goes when the engine removes the run. A turn without a run (the guide, a
question asked before any run exists) leaves the file where it is: such a question's options call again with the same
file. ``--keep-message-file`` leaves it in every case.

A file written into a new run folder before its first run - the only thing in it - would have that folder refused as
already holding other files (SOULRUN_CACHE_DIR_NOT_EMPTY): it is set aside while the folder is checked, then moved the
same way, or put back when the turn fails or has no run.
"""
from __future__ import annotations

import contextlib
import shutil
import tempfile
from pathlib import Path

from . import _select

FOLDER = "_soulrun"          # SoulRun's own folder in a run: the engine reads only its own names in a run's folder


def into_run(path: Path, cache_dir) -> Path | None:
    """Move the message file into the run's folder: its new place, or None when it could not be moved (it stays)."""
    folder = Path(cache_dir) / FOLDER
    try:
        folder.mkdir(exist_ok=True)
        number = 1 + sum(1 for _ in folder.glob("message.*.txt"))
        while (folder / f"message.{number}.txt").exists():
            number += 1
        dest = folder / f"message.{number}.txt"
        shutil.move(str(path), str(dest))
    except OSError:
        return None
    return dest


def set_aside(path: Path, cache: Path) -> Path | None:
    """When ``path`` alone keeps ``cache`` from becoming the run folder, move it to a temporary folder (a folder of its
    own in ``cache``, left empty, goes too) and return where it is now; otherwise None."""
    if not _select.blocked_only_by(cache, path):
        return None
    rel = Path(path).resolve().relative_to(Path(cache).resolve())
    aside = Path(tempfile.mkdtemp(prefix="soulrun-message-")) / Path(path).name
    shutil.move(str(path), str(aside))
    if len(rel.parts) > 1:
        top = Path(cache) / rel.parts[0]
        for folder in sorted((p for p in top.rglob("*") if p.is_dir()), key=lambda p: len(p.parts), reverse=True):
            folder.rmdir()
        top.rmdir()
    return aside


def put_back(aside: Path, path: Path) -> None:
    """Undo set_aside."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(aside), str(path))
    with contextlib.suppress(OSError):
        aside.parent.rmdir()


def settle(path: Path, aside: Path | None, cache_dir) -> Path | None:
    """After the turn: into the run's folder when there is a run; otherwise (or when that fails) back where the agent
    wrote it. The file's place now, or None when it was left untouched."""
    current = aside or Path(path)
    moved = into_run(current, cache_dir) if cache_dir else None
    if moved is not None:
        if aside is not None:
            with contextlib.suppress(OSError):
                aside.parent.rmdir()
        # the folder the agent wrote it in stays, even empty: the agent writes the next turn's words there again
        return moved
    if aside is not None:
        put_back(aside, Path(path))
        return Path(path)
    return None

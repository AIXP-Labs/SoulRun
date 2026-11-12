"""One run prepared at a time per soulrun_cache_dir - across processes, not only threads.

The engine's prepare picks the next free run number and reads every kept run; two processes doing that at
the same moment can pick the same number (the second one then fails). In one process the threads already queue
on a lock; this lock makes separate processes - each ``soulrun`` on a command line is one - queue the same way.
It makes preparations queue, nothing more: the engine's own commands (the model's next-node, node-commit) and
``host.after_turn`` write a run's index outside it, so on Windows a preparation can still find an index being
replaced; SoulRun then waits and tries again (see _api).

The lock is the operating system's own lock on ``<soulrun_cache_dir>/.soulrun/prepare.lock``: it is released when the
process ends, however it ends, so a crash never leaves a stale lock behind. The file itself stays, empty.
"""
from __future__ import annotations

import contextlib
import errno
import os
import time
from pathlib import Path

from .errors import SoulRunError

LOCK_NAME = "prepare.lock"
WAIT_SECONDS = 120.0          # a prepare takes well under a second; this only stops a wait from never ending
POLL_SECONDS = 0.02
# What "another process holds the lock" looks like: flock with LOCK_NB (EAGAIN / EWOULDBLOCK, EACCES on some systems),
# msvcrt.locking with LK_NBLCK (EACCES, EDEADLOCK). Any other error means the lock cannot be taken at all.
BUSY = {errno.EAGAIN, errno.EWOULDBLOCK, errno.EACCES, getattr(errno, "EDEADLOCK", errno.EDEADLK)}

if os.name == "nt":
    import msvcrt

    def _try_lock(handle) -> None:
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)       # raises OSError while another process holds it

    def _unlock(handle) -> None:
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
else:
    import fcntl

    def _try_lock(handle) -> None:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

    def _unlock(handle) -> None:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


@contextlib.contextmanager
def held(folder: Path, *, wait: float = WAIT_SECONDS):
    """Hold the prepare lock of ``folder`` (SoulRun's own notes folder inside soulrun_cache_dir)."""
    folder.mkdir(parents=True, exist_ok=True)
    with open(folder / LOCK_NAME, "a+b") as handle:
        deadline = time.monotonic() + wait
        while True:
            try:
                _try_lock(handle)
                break
            except OSError as error:
                if error.errno not in BUSY:          # a file system without locks: waiting would never help
                    raise SoulRunError(
                        "PREPARE_LOCK_UNSUPPORTED", f"the lock file in {folder} cannot be locked "
                        f"({type(error).__name__}: {error}); SoulRun needs a folder whose file system supports locks",
                        field="soulrun_cache_dir", expected="a soulrun_cache_dir on a local disk") from error
                if time.monotonic() >= deadline:
                    raise SoulRunError(
                        "PREPARE_BUSY", f"another process has been preparing a run in {folder.parent} for over {wait:.0f} s",
                        field="soulrun_cache_dir", expected="the other process to finish, or a different soulrun_cache_dir") from None
                time.sleep(POLL_SECONDS)
        try:
            yield
        finally:
            _unlock(handle)


__all__ = ["held", "LOCK_NAME", "WAIT_SECONDS"]

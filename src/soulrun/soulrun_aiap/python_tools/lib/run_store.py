"""Run store: _index.json, node caches, gate records and the final answer under one file lock.

Rules (04 series doc 01 v0.2 §5.1 layout, §5.3 write rules; doc 02 R-20, R-35, R-37):
  * every write goes through the lock; index and caches are written atomically (tmp + replace)
    and read back; a read-back sha mismatch is an error, never silently accepted
  * node caches are write-once; a same-occurrence continuation (after WAITING_USER) is appended
    to continuations[] of the same file, the first commit is never overwritten
  * _gate.<question_id>.json is write-once (audit, R-20); _final_user_answer.txt is write-once
  * strict JSON on read and on payload parsing: duplicate keys and NaN/Infinity are rejected
  * the index is validated against schemas/index.v1.json on every write
  * every read re-reads and re-parses the index bytes; the full validation runs once per exact bytes in a process
    (docs/05SoulRun 87)
Own implementation; nothing copied from v6.
"""
from __future__ import annotations

import errno
import hashlib
import json
import os
import time
import secrets
from collections import OrderedDict
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path

from . import schema_lite
from . import write_observation

SCHEMA_DIR = Path(__file__).resolve().parents[2] / "schemas"
MODULE_DIR_PREFIX = "_"          # doc 05 §4.3: sub-node caches live in _<Parent>/ (nested per ancestor)
MANIFEST = "_manifest.json"
_HELD_LOCKS = ContextVar('engine_held_file_locks', default=())
_REPLACE_DELAYS = (0.05, 0.2, 0.5, 1.0, 1.0)
_DENIED_WHILE_DELETED = os.name == "nt"   # docs/05SoulRun 90 round 4 (problem 93): see FileLock.acquire
# docs/05SoulRun 90 round 5 (problem 93, ledger decision 185): how long FileLock.acquire waits out an uninterrupted run of access
# denied - as long as problem 23's read retry (the sum of _REPLACE_DELAYS, 2.75 s)
_DENIED_FOR = sum(_REPLACE_DELAYS)
_LONG_PATH_THRESHOLD = 240       # Windows MAX_PATH is 260; the \\?\ prefix lifts it to 32,767 (doc 05 §4.6)
# docs/05SoulRun 87: index bytes that already passed the full schema validation in this process, keyed by the sha256 of
# the exact bytes and of the shipped schema. A command read the same index 5-9 times and validated it each time (75-80%
# of its time on a large run). The bytes are still read and parsed on every read, so a change from outside is new bytes
# and gets the full validation again; only hashes are kept, never an index. Oldest first out; a forgotten key only means
# one more full validation.
_VALIDATED_INDEX = OrderedDict()
_VALIDATED_INDEX_MAX = 64


def os_path(path) -> str:
    """Absolute OS path string; on Windows, long paths get the extended-length prefix so an unlimited
    sub-node tree never hits MAX_PATH regardless of the LongPathsEnabled system setting."""
    s = os.path.abspath(str(path))
    if os.name == "nt" and len(s) >= _LONG_PATH_THRESHOLD and not s.startswith("\\\\?\\"):
        return "\\\\?\\" + s
    return s


def path_exists(path) -> bool:
    return os.path.exists(os_path(path))


def _refused_while_replaced(exc, path) -> bool:
    """docs/05SoulRun 90 (problem 23): the refusal Windows gives a read of a file another process is replacing - access denied,
    a sharing or lock violation (winerror 5 / 32 / 33). Round 5 (ledger decision 185): builtin open() reports it as a
    PermissionError with errno EACCES and no winerror at all, so on Windows that counts too - except for a folder, which open()
    always refuses with EACCES there (a lasting refusal, raised at once as before)."""
    if getattr(exc, "winerror", None) in (5, 32, 33):
        return True
    return (_DENIED_WHILE_DELETED and isinstance(exc, PermissionError) and exc.errno == errno.EACCES
            and not os.path.isdir(os_path(path)))


def read_bytes(path) -> bytes:
    # docs/05SoulRun 90 (problem 23): on Windows a file another process is replacing (atomic_write_bytes' os.replace) is
    # refused for a moment (_refused_while_replaced). The read is tried again after the pauses a write waits for the same
    # refusal; a refusal that lasts, and every other error, is raised as before.
    for pause in (*_REPLACE_DELAYS, None):
        try:
            with open(os_path(path), "rb") as fh:
                return fh.read()
        except OSError as exc:
            if pause is None or not _refused_while_replaced(exc, path):
                raise
            time.sleep(pause)


def read_text(path) -> str:
    return read_bytes(path).decode("utf-8")


class RunStoreError(RuntimeError):
    def __init__(self, code: str, detail: str):
        super().__init__(f"{code}: {detail}")
        self.code, self.detail = code, detail


class LockTimeout(RunStoreError):
    pass


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _reject_duplicates(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError(f"duplicate key {key!r}")
        obj[key] = value
    return obj


def _reject_constant(name):
    raise ValueError(f"non-finite number {name}")


def strict_loads(text: str):
    """json.loads that rejects duplicate keys and NaN/Infinity (doc 01 §4.3 step 3)."""
    return json.loads(text, object_pairs_hook=_reject_duplicates, parse_constant=_reject_constant)


def dumps(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False) + "\n"


class FileLock:
    """Exclusive lock via O_EXCL lock file; stale locks (older than stale_after seconds) are reclaimed."""

    def __init__(self, path: Path, timeout: float = 30.0, stale_after: float = 120.0, poll: float = 0.05):
        self.path, self.timeout, self.stale_after, self.poll = Path(path), timeout, stale_after, poll
        self._fd = None

    def acquire(self) -> "FileLock":
        deadline = time.monotonic() + self.timeout
        denied_since = None     # docs/05SoulRun 90 round 5: when the current uninterrupted run of access denied began
        while True:
            try:
                try:
                    self._fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                except PermissionError as exc:
                    # docs/05SoulRun 90 round 4 (problem 93, ledger decision 184; as problem 23 for read_bytes): on Windows,
                    # creating the lock file while its holder is deleting it (release) is refused for a moment - access denied,
                    # EACCES (winerror 5, 32 or none at all, as os.open reports it) - where a held lock gives FileExistsError:
                    # wait and try again. Round 5 (ledger decision 185): an uninterrupted run of refusals is waited out only
                    # _DENIED_FOR (problem 23's read retry, 2.75 s) - any FileExistsError or a taken lock starts it again - and
                    # never past the timeout; then the same PermissionError is raised, as for every other error (any on
                    # POSIX, where no such moment exists): a refusal that lasts is a real permission problem.
                    now = time.monotonic()
                    denied_since = now if denied_since is None else denied_since
                    if not _DENIED_WHILE_DELETED or exc.errno != errno.EACCES or now >= deadline \
                            or now - denied_since >= _DENIED_FOR:
                        raise
                    time.sleep(self.poll)
                    continue
                os.write(self._fd, f"{os.getpid()} {now_iso()}\n".encode("utf-8"))
                os.close(self._fd)
                self._fd = None
                self._identity = self.path.stat()
                _HELD_LOCKS.set(_HELD_LOCKS.get() + (self,))
                return self
            except FileExistsError:
                denied_since = None
                try:
                    age = time.time() - self.path.stat().st_mtime
                except FileNotFoundError:
                    continue
                if age > self.stale_after:
                    try:
                        self.path.unlink()
                    except FileNotFoundError:
                        pass
                    continue
                if time.monotonic() >= deadline:
                    raise LockTimeout("LOCK_TIMEOUT", f"could not acquire {self.path} within {self.timeout}s")
                time.sleep(self.poll)

    def release(self) -> None:
        _HELD_LOCKS.set(tuple(lock for lock in _HELD_LOCKS.get() if lock is not self))
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass

    def __enter__(self):
        return self.acquire()

    def __exit__(self, *exc):
        self.release()
        return False


def lock_holder_alive(path) -> bool:
    """docs/05SoulRun 90 round 7 (line C, C2): does the lock file `path` prove its holder alive? FileLock.acquire writes
    '<process id> <now_iso() when it took the lock>' into it; True only when that process is running now and was already
    running at that time (so the id is not one a later process took over). Anything else proves nothing (False): a file
    that cannot be read or parsed, an ended process - a killed holder's lock file stays until FileLock reclaims it, after
    stale_after - an id now held by a process started after that time, a platform this cannot ask (only Windows and
    Linux are asked), any error asking it. Reads only."""
    try:
        pid_text, taken = Path(path).read_text(encoding="utf-8").split()
        pid = int(pid_text)
        taken_at = datetime.strptime(taken, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc).timestamp()
    except (OSError, ValueError):
        return False
    try:
        started = _process_started_at(pid) if pid > 0 else None
    except Exception:  # noqa: BLE001 - whatever the system answers here, it proves nothing
        return False
    return started is not None and started < taken_at


def _process_started_at(pid: int) -> float | None:
    """When the running process `pid` started (seconds since the epoch), or None: not running, or not to be asked here.
    Windows: OpenProcess, still running (WaitForSingleObject times out at once), its creation time (GetProcessTimes).
    Linux: /proc/<pid>/stat (not a zombie) and its start, placed one second late - the boot time /proc/stat gives is whole
    seconds - so a start is never put before the time it really was."""
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        kernel32.WaitForSingleObject.restype = wintypes.DWORD
        kernel32.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
        kernel32.GetProcessTimes.restype = wintypes.BOOL
        kernel32.GetProcessTimes.argtypes = (wintypes.HANDLE,) + (ctypes.POINTER(wintypes.FILETIME),) * 4
        kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
        handle = kernel32.OpenProcess(0x1000 | 0x00100000, False, pid)   # PROCESS_QUERY_LIMITED_INFORMATION | SYNCHRONIZE
        if not handle:
            return None
        try:
            if kernel32.WaitForSingleObject(handle, 0) != 0x102:          # WAIT_TIMEOUT: the process is still running
                return None
            times = [wintypes.FILETIME() for _ in range(4)]
            if not kernel32.GetProcessTimes(handle, *(ctypes.byref(t) for t in times)):
                return None
            ticks = (times[0].dwHighDateTime << 32) | times[0].dwLowDateTime   # 100 ns since 1601-01-01 UTC
            return ticks / 1e7 - 11644473600
        finally:
            kernel32.CloseHandle(handle)
    if Path("/proc/stat").is_file():
        stat_text = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
        fields = stat_text[stat_text.rindex(")") + 2:].split()
        if fields[0] in ("Z", "X"):
            return None
        boot = next(int(line.split()[1]) for line in Path("/proc/stat").read_text(encoding="utf-8").splitlines()
                    if line.startswith("btime "))
        return boot + int(fields[19]) / os.sysconf("SC_CLK_TCK") + 1.0
    return None


def _regular_path(path):
    import stat
    for part in (path, *path.parents):
        try:
            # Review round 2 of docs/05SoulRun 88 (L3): through the long-path helper - a plain lstat of a path beyond
            # Windows' 260 characters raises FileNotFoundError and would skip the file itself.
            info = os.lstat(os_path(part))
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
            return False
    return True


def _write_guard(path):
    for lock in reversed(_HELD_LOCKS.get()):
        try:
            Path(os.path.abspath(path)).relative_to(Path(os.path.abspath(lock.path.parent)))
            info = lock.path.stat()
            if (info.st_ino, info.st_mtime_ns) != (lock._identity.st_ino, lock._identity.st_mtime_ns):
                continue
            if _regular_path(path):
                return lock
        except (OSError, ValueError):
            continue
    return None


def _preimage(path):
    try:
        return sha256_bytes(read_bytes(path))
    except FileNotFoundError:
        return 'ABSENT'


@contextmanager
def lifecycle_lock(cache_dir):
    store=RunStore(cache_dir)
    if store.index_path.exists():
        from . import program_guard
        # Control-plane metadata also serves legacy host records, not business commits.
        program_guard.assert_run_version(strict_loads(read_text(store.index_path)))
    if _write_guard(store.cache_dir/'_host_lifecycle.json') is not None:
        yield
    else:
        store.cache_dir.mkdir(parents=True,exist_ok=True)
        with FileLock(store.cache_dir/store.LOCK):yield


def _replacement_receipt(lock, path, errors, attempts, actual):
    record = dict(owner='execute_engine_atomic_write', at=now_iso(), path=str(path),
                  attempts=attempts, errors=errors, sha256=actual)
    record['receipt_sha256'] = sha256_bytes(dumps(record).encode('utf-8'))
    receipt = lock.path.parent / '_atomic_replace_recoveries.jsonl'
    if not _regular_path(receipt):
        raise RunStoreError('RECOVERY_RECEIPT_INVALID', 'replacement diagnostic path is not regular')
    if receipt.exists():
        from . import recovery_diagnostics
        raw=read_bytes(receipt)
        _,tail=recovery_diagnostics.rows(raw)
        if tail:
            directory=lock.path.parent/'_atomic_replace_recoveries'
            if directory.is_symlink():raise RunStoreError('RECOVERY_RECEIPT_INVALID','diagnostic directory is not regular')
            directory.mkdir(exist_ok=True)
            target=directory/(record['receipt_sha256']+'.json')
            data=(json.dumps(record,ensure_ascii=False)+'\n').encode('utf-8')
            if target.exists():
                if not _regular_path(target) or read_bytes(target)!=data:
                    raise RunStoreError('RECOVERY_RECEIPT_INVALID','diagnostic record changed')
            else:
                with open(os_path(target),'xb') as stream:
                    stream.write(data);stream.flush();os.fsync(stream.fileno())
            return
        if raw and not raw.endswith(b'\n'):
            with open(os_path(receipt),'ab') as stream:
                stream.write(b'\n');stream.flush();os.fsync(stream.fileno())
    with open(os_path(receipt), 'ab') as stream:
        stream.write((json.dumps(record, ensure_ascii=False) + '\n').encode('utf-8'))
        stream.flush()
        os.fsync(stream.fileno())


def atomic_write_bytes(path: Path, data: bytes) -> str:
    """tmp + os.replace, then read back; returns sha256 of the bytes on disk."""
    path = Path(path)
    write_observation.writing(path, expected=sha256_bytes(data))
    os.makedirs(os_path(path.parent), exist_ok=True)
    tmp = path.with_name(path.name + f".tmp.{os.getpid()}.{secrets.token_hex(6)}")
    with open(os_path(tmp), "xb") as fh:
        fh.write(data)
        fh.flush()
        os.fsync(fh.fileno())
    guard = _write_guard(path)
    try:
        before = _preimage(path) if guard else None
    except OSError:
        before = None
    errors = []
    for attempt in range(len(_REPLACE_DELAYS) + 1):
        try:
            os.replace(os_path(tmp), os_path(path))
            break
        except OSError as exc:
            errors.append(dict(type=type(exc).__name__, errno=exc.errno, winerror=getattr(exc, 'winerror', None)))
            if attempt == len(_REPLACE_DELAYS) or getattr(exc, 'winerror', None) not in (5, 32, 33) or before is None:
                raise
            try:
                safe = guard is _write_guard(path) and _regular_path(tmp) and read_bytes(tmp) == data and _preimage(path) == before
            except OSError:
                safe = False
            if not safe:
                raise
            time.sleep(_REPLACE_DELAYS[attempt])
            try:
                safe = guard is _write_guard(path) and _regular_path(tmp) and read_bytes(tmp) == data and _preimage(path) == before
            except OSError:
                safe = False
            if not safe:
                raise
    write_observation.writing(path, 'PERSISTED_UNCONFIRMED')
    expected = sha256_bytes(data)
    actual = sha256_bytes(read_bytes(path))
    if actual != expected:
        raise RunStoreError("READ_BACK_MISMATCH", f"{path}: wrote {expected[:16]} read {actual[:16]}")
    write_observation.writing(path, 'VERIFIED', receipt=actual)
    if errors:
        _replacement_receipt(guard, path, errors, attempt + 1, actual)
    return actual


def seal_process_output(cache_dir: Path, data: bytes) -> str:
    """Content-addressed, exclusive creation; never repair a damaged historical receipt."""
    relative = f'_proc/sha256-{sha256_bytes(data)}.out'
    path = cache_dir / relative
    if path.parent.resolve() != cache_dir.resolve() / '_proc' or path.is_symlink():
        raise RunStoreError('EVIDENCE_SNAPSHOT_INVALID', 'snapshot must be a regular file inside this cache')
    try:
        write_observation.writing(path)
        with open(os_path(path), 'xb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError:
        pass
    if read_bytes(path) != data:
        raise RunStoreError('EVIDENCE_SNAPSHOT_INVALID', f'{relative}: existing snapshot differs; never overwrite it')
    write_observation.writing(path, 'VERIFIED', receipt=sha256_bytes(data))
    return relative


class RunStore:
    INDEX = "_index.json"
    LOCK = "_index.lock"
    FINAL = "_final_user_answer.txt"
    PUBLIC = "_public"
    PROC = "_proc"               # alpha.22: process stdout files the model redirects into; the engine hashes them
    EVIDENCE = "_evidence.json"  # alpha.22: hash-chained evidence ledger

    def __init__(self, cache_dir: str | Path, index_schema: dict | None = None):
        self.cache_dir = Path(cache_dir).resolve()
        self._index_schema = index_schema
        self._index_schema_sha256 = None   # docs/05SoulRun 87: set only for the shipped schema file

    # -- paths ---------------------------------------------------------------
    @property
    def index_path(self) -> Path:
        return self.cache_dir / self.INDEX

    def node_cache_path(self, program: str, node: str, visit: int = 1) -> Path:
        suffix = "" if visit <= 1 else f".visit{visit}"
        return self.cache_dir / f"{program}.{node}{suffix}.json"

    # Sub-node tree (doc 05 §4.3). A qualified node id is "Parent/ns.Node" (any depth, "/"-separated);
    # the frame directory of a module node is one "_<segment>" directory per ancestor segment:
    #   DelegateAnalysis            -> _DelegateAnalysis/
    #   DelegateAnalysis/analysis.X -> _DelegateAnalysis/_analysis.X/
    @staticmethod
    def frame_dir_rel(parent_id: str) -> str:
        return "/".join(MODULE_DIR_PREFIX + seg for seg in parent_id.split("/"))

    def frame_dir(self, parent_id: str) -> Path:
        return self.cache_dir.joinpath(*(MODULE_DIR_PREFIX + seg for seg in parent_id.split("/")))

    def sub_cache_path(self, parent_id: str, local: str, visit: int = 1) -> Path:
        """local = 'ns.Node' (the last segment of the qualified id)."""
        suffix = "" if visit <= 1 else f".visit{visit}"
        return self.frame_dir(parent_id) / f"{local}{suffix}.json"

    def manifest_path(self, parent_id: str) -> Path:
        return self.frame_dir(parent_id) / MANIFEST

    def gate_path(self, question_id: str) -> Path:
        return self.cache_dir / f"_gate.{question_id}.json"

    def dispatch_path(self, ticket: str) -> Path:
        """doc 10 §3.1: one record per sub-agent dispatch ticket (bootstrap text, sha, claim / commit times)."""
        return self.cache_dir / f"_dispatch.{ticket}.json"

    @property
    def final_answer_path(self) -> Path:
        return self.cache_dir / self.FINAL

    @property
    def public_dir(self) -> Path:
        return self.cache_dir / self.PUBLIC

    @property
    def proc_dir(self) -> Path:
        return self.cache_dir / self.PROC

    @property
    def evidence_path(self) -> Path:
        return self.cache_dir / self.EVIDENCE

    # -- lock / schema -------------------------------------------------------
    def lock(self, timeout: float = 30.0) -> FileLock:
        if self.exists():
            from . import program_guard
            program_guard.assert_run_version(self.read_index())
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        return FileLock(self.cache_dir / self.LOCK, timeout=timeout)

    @property
    def index_schema(self) -> dict:
        if self._index_schema is None:
            raw = (SCHEMA_DIR / "index.v1.json").read_bytes()
            self._index_schema = strict_loads(raw.decode("utf-8"))
            self._index_schema_sha256 = sha256_bytes(raw)
        return self._index_schema

    def validate_index(self, index: dict) -> list[dict]:
        return schema_lite.validate(index, self.index_schema)

    def _validation_key(self, raw: bytes):
        """docs/05SoulRun 87: the _VALIDATED_INDEX key of these exact index bytes under the shipped schema; None for a
        schema the caller handed in, which is validated on every read."""
        if self.index_schema is not None and self._index_schema_sha256:
            return sha256_bytes(raw), self._index_schema_sha256
        return None

    # -- index ---------------------------------------------------------------
    def exists(self) -> bool:
        return self.index_path.exists()

    def read_index(self) -> dict:
        try:
            raw = read_bytes(self.index_path)
        except FileNotFoundError as exc:
            raise RunStoreError("INDEX_MISSING", str(self.index_path)) from exc
        text = raw.decode("utf-8")
        try:
            index = strict_loads(text)
        except ValueError as exc:
            raise RunStoreError("INDEX_CORRUPT", f"{self.index_path}: {exc}") from exc
        key = self._validation_key(raw)
        if key is not None and key in _VALIDATED_INDEX:
            return index
        errors = self.validate_index(index)
        if errors:
            raise RunStoreError("INDEX_CORRUPT", f"{self.index_path}: {errors[0]['field']} {errors[0]['message']}")
        if key is not None:
            _VALIDATED_INDEX[key] = None
            while len(_VALIDATED_INDEX) > _VALIDATED_INDEX_MAX:
                _VALIDATED_INDEX.popitem(last=False)
        return index

    def write_index(self, index: dict) -> str:
        errors = self.validate_index(index)
        if errors:
            raise RunStoreError("INDEX_SCHEMA_INVALID", f"{errors[0]['field']}: {errors[0]['message']}")
        return atomic_write_bytes(self.index_path, dumps(index).encode("utf-8"))

    # -- caches --------------------------------------------------------------
    @staticmethod
    def exists_path(path: Path) -> bool:
        return path_exists(path)

    @staticmethod
    def read_bytes(path: Path) -> bytes:
        return read_bytes(path)

    def read_json(self, path: Path):
        try:
            return strict_loads(read_text(path))
        except FileNotFoundError as exc:
            raise RunStoreError("CACHE_MISSING", str(path)) from exc
        except ValueError as exc:
            raise RunStoreError("CACHE_CORRUPT", f"{path}: {exc}") from exc

    def write_json(self, path: Path, obj) -> str:
        """Engine-owned mutable files (manifests): atomic rewrite, no write-once guard."""
        return atomic_write_bytes(path, dumps(obj).encode("utf-8"))

    def write_json_once(self, path: Path, obj) -> str:
        path = Path(path)
        if path_exists(path):
            raise RunStoreError("WRITE_ONCE_VIOLATION", f"{path} already exists")
        return atomic_write_bytes(path, dumps(obj).encode("utf-8"))

    def append_continuation(self, path: Path, continuation: dict) -> str:
        """Same-occurrence continuation after WAITING_USER: first commit stays, continuations[] grows."""
        current = self.read_json(path)
        if not isinstance(current, dict):
            raise RunStoreError("CACHE_CORRUPT", f"{path}: not an object")
        current.setdefault("continuations", []).append(continuation)
        return atomic_write_bytes(path, dumps(current).encode("utf-8"))

    def write_text_once(self, path: Path, text: str) -> str:
        path = Path(path)
        if path_exists(path):
            raise RunStoreError("WRITE_ONCE_VIOLATION", f"{path} already exists")
        return atomic_write_bytes(path, text.encode("utf-8"))

    def write_final_answer_once(self, text: str) -> str:
        return self.write_text_once(self.final_answer_path, text)

    def ensure_final_answer(self, text: str) -> str:
        """Called under the run lock: recover an identical final file, never replace it."""
        data = text.encode("utf-8")
        if self.exists_path(self.final_answer_path):
            if self.read_bytes(self.final_answer_path) != data:
                raise RunStoreError("FINAL_ANSWER_CONFLICT", "existing final answer differs from the authoritative commit")
            return sha256_bytes(data)
        return self.write_final_answer_once(text)

    def write_public(self, name: str, text: str) -> Path:
        path = self.public_dir / name
        if name.startswith('menu.'):
            from . import menu_history
            menu_history.preserve(self, name, text)
        atomic_write_bytes(path, text.encode("utf-8"))
        return path

    def ensure_final_artifact(self, value: dict) -> str:
        """Same write-once recovery rule as the final text, under the existing run lock."""
        path = self.cache_dir / 'final_answer.json'
        data = dumps(value).encode('utf-8')
        if self.exists_path(path):
            if self.read_bytes(path) != data:
                raise RunStoreError('FINAL_ARTIFACT_CONFLICT', 'existing final artifact differs from the authoritative commit')
            return sha256_bytes(data)
        return atomic_write_bytes(path, data)

    def write_public_snapshot(self, name: str, text: str) -> Path:
        """Under the run lock: keep published references immutable, including legacy paths."""
        path = self.public_dir / name
        data = text.encode("utf-8")
        if self.exists_path(path):
            if self.read_bytes(path) == data:
                return path
            path = path.with_name(f"{path.stem}.{sha256_bytes(data)}{path.suffix}")
            if self.exists_path(path):
                if self.read_bytes(path) != data:
                    raise RunStoreError("PUBLIC_SNAPSHOT_CONFLICT", f"{path}: existing snapshot differs")
                return path
        self.write_text_once(path, text)
        return path

    # -- constructors --------------------------------------------------------
    @staticmethod
    def new_index(engine_version: str, trace_id: str, session_id: str | None, program: dict,
                  budget: dict, user_language: str | None, started_at: str | None = None) -> dict:
        """A fresh, schema-valid index (identity group filled, everything else at its initial value)."""
        return {
            "schema_version": 1,
            "engine_version": engine_version,
            "trace_id": trace_id,
            "session_id": session_id,
            "program": {
                "name": program.get("name"), "entry_path": program.get("entry_path"),
                "entry_file": program.get("entry_file"), "trust_level": program.get("trust_level"),
                "loading_mode": program.get("loading_mode"), "permissions_digest": program.get("permissions_digest"),
                "checks": list(program.get("checks", [])), "skipped_files": list(program.get("skipped_files", [])),
            },
            "started_at": started_at or now_iso(),
            "user_language": user_language,
            "catalog": [], "current": {"name": None, "visit": 0}, "completed": [],
            "route": {"package": None, "decided_at": None, "snapshot": []},
            "call_stack": [], "context": {},
            "gate": {"state": "CLEAR", "question_id": None, "node": None, "source": None, "kind": None,
                     "presented_at": None, "delivered_at": None, "answered_at": None, "history": []},
            "tickets": [],
            "dispatch": RunStore.new_dispatch_group(),
            "run_termination": {"kind": None, "by": None, "at": None, "reason": None,
                                "rejection_report": None, "resume_prohibited": False},
            "nodes": {},
            "semantics": None, "accounting": None, "final_answer_sha256": None,
            "run_state": "RUNNING", "anomalies_summary": [],
            "budget": {"source": budget.get("source", "engine_default"), "active_ms": int(budget.get("active_ms", 1200000))},   # alpha.115: the authorized business default
        }

    @staticmethod
    def new_dispatch_group() -> dict:
        """doc 10 §3.1: run-level sub-agent dispatch accounting (policy is decided at Router.cache-setup)."""
        return {"policy": None, "tickets_issued": 0, "spawns_claimed": 0, "fallbacks": 0, "spawn_hard_limit": 48,
                "independent_claimed": 0, "independent_hard_limit": 16}

    @staticmethod
    def new_node_entry(visit: int, planned_at: str | None = None, *, parent: str | None = None, parent_visit: int | None = None,
                       depth: int = 0, order: int | None = None) -> dict:
        entry = {"status": "PLANNED", "visit": visit, "planned_at": planned_at or now_iso(), "ready_at": None,
                 "committed_at": None, "elapsed_ms": None, "human_wait_ms": None, "active_elapsed_ms": None,
                 "cache_sha256": None, "artifacts": [], "sources_count": 0, "logical_tool_calls": 0, "serves": 0}
        if parent is not None:  # sub node (doc 05 §4.3): tree coordinates are machine-owned
            entry.update({"parent": parent, "parent_visit": parent_visit, "depth": depth, "order": order})
        return entry

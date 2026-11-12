"""``host.execution_report`` / ``soulrun --report``: the complete execution report behind an ``engine-report:`` link.

The engine shows a run's execution report as a summary followed by a link,
``[…](engine-report:<run>/<node>@<visit>/<sha256>)``, and keeps the complete text in the run's
``_reports/sha256-<sha256>.txt``. SoulBot's web page opens such a link (server/routes/engine_view.py); this is the
same reading for every other host. The report must be bound to the run - an Engine.execute-report record whose bytes
match the run's index and whose execution_report names this digest - and the file must hash to it; anything else is
answered with a status, never a guess. Reads only.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from . import _engine
from .errors import SoulRunError, UsageError

LINK = re.compile(r"engine-report:(?P<cache>\d{1,9})/(?P<node>[^/@()\s]+)@(?P<visit>\d{1,6})/(?P<digest>[a-f0-9]{64})")
PAGE, MAX_PAGE = 16_384, 32_768             # characters, as SoulBot's page
PAGE_BYTES = 24_000                          # and at most this many bytes as printed (see _program.PAGE_BYTES)
REPORT_NODE = "Engine.execute-report"


def parse(link: str) -> dict:
    """The parts of an ``engine-report:`` link; the link may be given bare or inside its Markdown."""
    found = LINK.search(str(link or ""))
    if not found:
        raise UsageError("REPORT_LINK_INVALID", f"not an engine-report link: {str(link)[:120]!r}", field="link",
                         expected="engine-report:<run>/<node>@<visit>/<sha256>, as the execution report block shows it")
    return {"cache": found.group("cache"), "node": found.group("node"), "visit": int(found.group("visit")),
            "digest": found.group("digest")}


def _bound(cache_dir: Path, index: dict, digest: str) -> bool:
    """Is there an Engine.execute-report record of this run, unchanged since the index recorded it, whose execution
    report is this digest?"""
    node_key = _engine.load("lib.engine_core")._node_key
    for path in cache_dir.glob(f"*.{REPORT_NODE}*.json"):
        if path.is_symlink():
            continue
        try:
            raw = path.read_bytes()
            record = json.loads(raw)
            node, visit = record.get("node"), record.get("visit")
            if node != REPORT_NODE or not isinstance(visit, int):
                continue
            if hashlib.sha256(raw).hexdigest() != ((index.get("nodes") or {}).get(node_key(node, visit)) or {}).get("cache_sha256"):
                continue
            last = (record.get("continuations") or [record])[-1]
            if ((last.get("machine") or {}).get("execution_report") or {}).get("full_sha256") == digest:
                return True
        except (OSError, ValueError, TypeError, AttributeError):
            continue
    return False


def read(link: str, runs_root: Path, *, session_id: str | None = None, offset: int = 0, limit: int = PAGE) -> dict:
    """The report behind ``link``, one page of it: status OK with the text, or a status saying why there is none
    (CACHE_EXPIRED, NOT_IN_SESSION, REPORT_UNBOUND, REPORT_FILE_MISSING, REPORT_DIGEST_MISMATCH, REPORT_UNREADABLE)."""
    parts = parse(link)
    if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= MAX_PAGE:
        raise UsageError("PAGE_INVALID", f"offset {offset!r}, limit {limit!r}", field="offset",
                         expected=f"offset >= 0 and 1 <= limit <= {MAX_PAGE}")
    digest, root = parts["digest"], Path(runs_root)
    answer = {"link": f"engine-report:{parts['cache']}/{parts['node']}@{parts['visit']}/{digest}", "sha256": digest,
              "text": None, "complete": False}
    cache_dir = root / parts["cache"]
    if not cache_dir.is_dir():
        return {"status": "CACHE_EXPIRED", **answer}
    if cache_dir.is_symlink() or not cache_dir.resolve().is_relative_to(root.resolve()):
        raise SoulRunError("REPORT_PATH_UNSAFE", f"{cache_dir} is not a run folder under {root}", field="link")
    index = _engine.load("prepare_cache")._read_index(cache_dir) or {}
    if session_id is not None and index.get("session_id") != session_id:
        return {"status": "NOT_IN_SESSION", **answer}
    if not _bound(cache_dir, index, digest):
        return {"status": "REPORT_UNBOUND", **answer}
    path = cache_dir / "_reports" / f"sha256-{digest}.txt"
    if path.is_symlink() or path.parent.is_symlink() or path.resolve().parent != cache_dir.resolve() / "_reports":
        raise SoulRunError("REPORT_PATH_UNSAFE", f"{path} is not the run's own report file", field="link")
    if not path.is_file():
        return {"status": "REPORT_FILE_MISSING", **answer}
    try:
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != digest:
            return {"status": "REPORT_DIGEST_MISMATCH", **answer}
        text = raw.decode("utf-8")
    except (OSError, UnicodeError):
        return {"status": "REPORT_UNREADABLE", **answer}
    if offset > len(text):
        raise UsageError("PAGE_INVALID", f"offset {offset} is past the report's {len(text)} characters", field="offset",
                         expected=f"0..{len(text)}")
    end = min(len(text), offset + limit)
    while end - offset > 1:                  # a page stays under the command line's output cap, CJK text included
        used = len(json.dumps(text[offset:end], ensure_ascii=False).encode("utf-8"))
        if used <= PAGE_BYTES:
            break
        end = offset + max(1, (end - offset) * PAGE_BYTES // used)
    return {"status": "OK", **answer, "text": text[offset:end], "offset": offset,
            "next_offset": end if end < len(text) else None, "total_chars": len(text),
            "complete": offset == 0 and end >= len(text)}      # the whole report in this answer (as soulrun --program)

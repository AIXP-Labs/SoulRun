"""Strict, read-only equality projection for generated runtime program data.

This is not resume authorization: the host still needs the Engine's verified native return receipt.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from . import _blocks, _engine, _slim
from .errors import SoulRunError

HEADER = r'\[LOADED AISOP: engine_node\.aisop\.json\]'
FRAGMENT = re.compile(r'(?m)^'+HEADER+r'\n```json\n(.*?)\n```', re.S)


def project(text: str, *, cache_dir: Any, entry_mode: str | None) -> dict[str, str] | None:
    """Replace only an exact current-package fragment; retain all other instruction bytes.

    `runtime_fragment` must accompany the current turn unchanged. Never send `policy_text` as a replacement prompt.
    """
    if not isinstance(text, str) or len(re.findall(r'(?m)^'+HEADER+r'$', text)) != 1:
        return None
    match = FRAGMENT.search(text)
    if match is None:
        return None
    try:
        doc = json.loads(match.group(1))
        message = doc[1]['content']['user_input']
        if not isinstance(message, str):
            return None
        expected = _slim.entry_program(message, cache_dir=cache_dir, entry_mode=entry_mode)
        if match.group(1) != expected or _engine.verify():
            return None
        # The full generated document binds every re-entry group, not just the fresh fragment.
        source = hashlib.sha256()
        for path in (_slim.FILE, Path(_slim.__file__), Path(_blocks.__file__), Path(__file__)):
            source.update(path.name.encode()+b'\0'+hashlib.sha256(path.read_bytes()).digest())
        source.update(str(_engine.manifest()['digest']).encode())
        digest = source.hexdigest()
        marker = '[VALIDATED SOULRUN RUNTIME PROGRAM source-sha256='+digest+']'
        return {'policy_text': text[:match.start()]+marker+text[match.end():],
                'runtime_fragment': match.group(0), 'source_digest': digest}
    except (OSError, ValueError, KeyError, TypeError, IndexError, SoulRunError):
        return None

"""Frozen pre-canonical combination, for explicit legacy tooling tests only.

Never use this archive as an installed runtime. Canonical tests use the current package.
"""
import hashlib
import base64
import io
import json
import zipfile
from pathlib import Path, PurePosixPath

from conftest import ROOT

ARCHIVE = ROOT / 'tests/data/precanonical.json'
EXPECTED = '8df01feae1aa031dc5dae8e60f735ff5639e65563eb3f5d2c4b2ee0ae65fcf24'


def unpack(target: Path, prefix: str) -> None:
    raw = base64.b64decode(json.loads(ARCHIVE.read_text('utf-8'))['data'], validate=True)
    assert hashlib.sha256(raw).hexdigest() == EXPECTED
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        for info in archive.infolist():
            if info.is_dir() or not info.filename.startswith(prefix):
                continue
            relative = PurePosixPath(info.filename[len(prefix):])
            assert not relative.is_absolute() and '..' not in relative.parts and ':' not in str(relative)
            path = target.joinpath(*relative.parts)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(archive.read(info))

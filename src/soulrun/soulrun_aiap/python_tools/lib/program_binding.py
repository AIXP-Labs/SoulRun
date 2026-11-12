"""Raw program identity. No business/history scan, semantic inference or writes."""
from __future__ import annotations

import hashlib
from pathlib import Path


def read_files(directory):
    root = Path(directory)
    names = sorted(p.name for p in root.glob('*.aisop.json')) if root.is_dir() else []
    raw, errors = {}, {}
    for name in names + ['AIAP.md']:
        try:
            raw[name] = (root / name).read_bytes()
        except FileNotFoundError:
            if name != 'AIAP.md':
                errors[name] = 'MISSING_DURING_READ'
        except OSError as exc:
            errors[name] = type(exc).__name__
    if not root.is_dir():
        errors['.'] = 'DIRECTORY_UNAVAILABLE'
    return raw, errors


def identity(directory, entry_file, raw, errors):
    return dict(directory=str(Path(directory).resolve()), entry_file=entry_file,
                files={name: dict(bytes=len(value), sha256=hashlib.sha256(value).hexdigest())
                       for name, value in raw.items()}, errors=errors)


def capture(directory, entry_file):
    return identity(directory, entry_file, *read_files(directory))


def differences(expected, actual):
    if not isinstance(expected, dict) or not isinstance(expected.get('files'), dict) \
            or not isinstance(expected.get('errors'), dict) or not expected.get('directory') or not expected.get('entry_file'):
        return [dict(kind='BASELINE_INVALID')]
    rows = []
    for key in ('directory', 'entry_file'):
        if expected.get(key) != actual.get(key):
            rows.append(dict(kind='IDENTITY_CHANGED', file=key, expected=expected.get(key), actual=actual.get(key)))
    for name in sorted(set(expected['files']) | set(actual['files'])):
        before, after = expected['files'].get(name), actual['files'].get(name)
        if before != after:
            rows.append(dict(kind='ADDED' if before is None else 'REMOVED' if after is None else 'CHANGED',
                             file=name, expected=before, actual=after))
    for name, reason in actual['errors'].items():
        rows.append(dict(kind='UNREADABLE', file=name, reason=reason))
    if expected['errors']:
        rows.append(dict(kind='BASELINE_UNREADABLE', files=expected['errors']))
    return rows

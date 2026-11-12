"""Bound capture diagnostics; never repair history or infer semantic correctness."""
from __future__ import annotations

import hashlib
from pathlib import Path


def _probe(root, name, expected=None):
    try:
        text = str(name or '').replace('\\','/')
        path = root/(text[6:] if text.startswith('_proc/') else text)
        if not name or path.parent.resolve() != root.resolve() or any(
                p.is_symlink() or (hasattr(p, 'is_junction') and p.is_junction()) for p in (path, *path.parents)):
            return dict(status='INVALID_PATH')
        if not path.is_file():
            return dict(status='MISSING')
        if path.stat().st_size > 8*1024*1024:
            return dict(status='UNREADABLE', reason='bounded_diagnostic_size')
        data = path.read_bytes()
        sha = hashlib.sha256(data).hexdigest()
        return dict(status='MATCH' if expected and sha == expected else 'MISMATCH' if expected else 'UNVERIFIED',
                    path=str(path), sha256=sha, bytes=len(data))
    except (OSError, ValueError):
        return dict(status='UNREADABLE')


def records(store, caches):
    results = []
    for cache in caches:
        for revision, row in enumerate([cache, *(cache.get('continuations') or [])]):
            for call in row.get('payload', {}).get('evidence', {}).get('tool_calls', []):
                if len(results) >= 12:
                    return results
                work = call.get('stdout_path')
                sealed, sha = call.get('stdout_snapshot'), call.get('stdout_sha256')
                if not work:
                    continue
                original = _probe(store.proc_dir, work, sha)
                snapshot = _probe(store.proc_dir, sealed, sha) if sealed and sha else dict(status='LEGACY_UNBOUND')
                status = ('SEALED_COPY_VERIFIED' if snapshot['status'] == 'MATCH' else
                          'SEALED_COPY_MISSING' if snapshot['status'] == 'MISSING' else
                          'SEALED_COPY_CHANGED' if snapshot['status'] == 'MISMATCH' else 'SEALED_COPY_UNVERIFIED')
                results.append(dict(node=cache.get('node'), visit=cache.get('visit'), revision=revision,
                    status=status, work=original, sealed=snapshot,
                    rule='Verified sealed bytes remain available; do not rerun side effects or rewrite prior defects/status.'
                         if snapshot['status'] == 'MATCH' else 'No verified recovery claim; preserve history and investigate.'))
    return results


def summary(store, caches):
    rows = records(store, caches)
    if not rows:
        return None
    unhealthy = [r for r in rows if r['status'] != 'SEALED_COPY_VERIFIED' or r['work']['status'] != 'MATCH']
    return dict(verified=len(rows)-len(unhealthy), **(dict(records=unhealthy) if unhealthy else {}))

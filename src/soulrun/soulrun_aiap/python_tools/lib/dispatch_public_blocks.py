"""Read-only public blocks sealed by a bound host Agent return, not new authority."""
from __future__ import annotations

import hashlib
import re

from . import dispatch_lifecycle, dispatch_publication, program_guard
from .run_store import RunStore, RunStoreError, _regular_path

SCHEMA = 'dispatch_public_blocks.v1'


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _sources(store, index, dispatch):
    from . import engine_core as ec
    root = dispatch['scope_root']
    entries = {entry['name']: entry for entry in [*index.get('catalog_history', {}).values(), *index['catalog']]}
    for entry in entries.values():
        name = entry['name']
        if name != root['node'] and not name.startswith(root['node'] + '/'):
            continue
        for key, state in index['nodes'].items():
            visit = state.get('visit', 1)
            if key != ec._node_key(name, visit) or not state.get('cache_sha256'):
                continue
            path = ec._cache_path_for(store, index, entry, visit)
            if not _regular_path(path) or not path.resolve().is_relative_to(store.cache_dir.resolve()):
                raise ValueError('PUBLICATION_SOURCE_PATH_UNSAFE')
            cached = store.read_json(path)
            latest = (cached.get('continuations') or [cached])[-1]
            machine = latest.get('machine') or {}
            owner = machine.get('dispatch') or {}
            if (cached.get('node') != name or cached.get('visit') != visit
                    or machine.get('trace_id') != index['trace_id']
                    or owner.get('actor') != 'sub_agent' or owner.get('ticket') != dispatch['ticket']
                    or owner.get('scope_root') != root):
                continue
            raw = store.read_bytes(path)
            if _sha(raw) != state['cache_sha256']:
                raise ValueError('PUBLICATION_SOURCE_CHANGED')
            # Backedges may rebase catalog positions after this cache was accepted.
            ordinal = cached.get('ordinal')
            if type(ordinal) is not int or ordinal < 0:
                raise ValueError('PUBLICATION_SOURCE_POSITION_INVALID')
            stem = f"{ordinal + 1:02d}.{ec._safe_name(name)}"
            pattern = re.compile(r'(?:plan|node)\.' + re.escape(stem) + r'\.v' + str(visit)
                + r'(?:\.[a-f0-9]{64})?\.txt|pause\.' + re.escape(stem)
                + r'\.[A-Za-z0-9_-]+\.v' + str(visit) + r'\.txt')
            source = dict(node=name, visit=visit, source_cache=path.relative_to(store.cache_dir).as_posix(),
                          source_sha256=state['cache_sha256'])
            yield pattern, source
            revisit = machine.get('revisit') or {}
            if (revisit.get('reason') == 'graph_backedge' and revisit.get('source') == name
                    and revisit.get('source_visit') == visit and entry['ordinal'] != ordinal):
                # The closing receipt is emitted after that same commit rebases the catalog.
                current_stem = f"{entry['ordinal'] + 1:02d}.{ec._safe_name(name)}"
                yield re.compile(r'node\.' + re.escape(current_stem) + r'\.v' + str(visit) + r'\.txt'), source


def _uncommitted_plan(index, dispatch, name):
    """Exclude only the current reached plan, never authorize an unaccepted result."""
    from . import engine_core as ec
    current = index.get('current') or {}
    entry = ec._catalog_entry(index, current.get('name'))
    root = dispatch['scope_root']
    if not entry or (entry['name'] != root['node'] and not entry['name'].startswith(root['node'] + '/')):
        return False
    visit = current.get('visit')
    state = index['nodes'].get(ec._node_key(entry['name'], visit)) or {}
    _, owner = ec._self_dispatch(index, entry, visit)
    if not state.get('ready_at') or not owner or owner.get('ticket') != dispatch['ticket'] \
            or owner.get('scope_root') != root:
        return False
    stem = f"{entry['ordinal'] + 1:02d}.{ec._safe_name(entry['name'])}"
    return bool(re.fullmatch(r'plan\.' + re.escape(stem) + r'\.v' + str(visit)
                            + r'(?:\.[a-f0-9]{64})?\.txt', name))


def seal_return(store, index, dispatch):
    """Added only at the first verified return; never backfill an old receipt."""
    from .engine_core import EngineError, _unshown_dispatch_gate_ref
    try:
        sources = list(_sources(store, index, dispatch))
        rows, excluded = [], []
        refs = dispatch.get('public_refs') or []
        canonical = dispatch_publication.canonical_refs(store, refs)
        if refs != canonical:
            held_menu = _unshown_dispatch_gate_ref(store, index, dispatch)
            if not held_menu or refs.count(held_menu) != 1 or canonical != [ref for ref in refs if ref != held_menu]:
                raise ValueError('PUBLICATION_REFERENCE_INVALID')
        # Menus retain their original gate/delivery path, never this supplement.
        for ref in canonical:
            name = dispatch_publication._REF.fullmatch(ref)[2]
            if not name.startswith(('plan.', 'node.', 'pause.')):
                continue
            path = store.public_dir / name
            if not _regular_path(path):
                raise ValueError('PUBLICATION_PATH_UNSAFE')
            raw = store.read_bytes(path)
            raw.decode('utf-8')
            digest_name = re.fullmatch(r'plan\..*\.([a-f0-9]{64})\.txt', name)
            if digest_name and digest_name[1] != _sha(raw):
                raise ValueError('PUBLICATION_BLOCK_CHANGED')
            matches = [source for pattern, source in sources if pattern.fullmatch(name)]
            if not matches and _uncommitted_plan(index, dispatch, name):
                excluded.append(dict(ref=ref, reason='UNCOMMITTED_PLAN', node=index['current']['name'], visit=index['current']['visit']))
                continue
            if len(matches) != 1:
                raise ValueError('PUBLICATION_SOURCE_UNBOUND')
            rows.append(dict(ref=ref, bytes=len(raw), sha256=_sha(raw), **matches[0]))
        return dict(schema=SCHEMA, status='SEALED', artifacts=rows, excluded_refs=excluded)
    except (OSError, ValueError, KeyError, EngineError, RunStoreError) as exc:
        # Losing presentation proof must not erase an actual Agent return fact.
        return dict(schema=SCHEMA, status='UNAVAILABLE', reason=str(exc)[:160], artifacts=[])


def project(cache_dir, ticket, *, run_session_id, provider_session_id, trace_id, seen_refs=()):
    """No lock, writes, claims, menu acknowledgement, ticket issue or business replay."""
    store = RunStore(cache_dir)
    from .engine_core import EngineError
    try:
        before = store.read_bytes(store.index_path)
        index = store.read_index()
        program_guard.assert_run_version(index)
        if index.get('session_id') != run_session_id or index.get('trace_id') != trace_id:
            raise ValueError('PUBLICATION_RUN_MISMATCH')
        segments = [segment for node in index['nodes'].values()
                    for segment in [node.get('dispatch') or {}, *((node.get('dispatch') or {}).get('history') or [])]
                    if segment.get('ticket') == ticket]
        if len(segments) != 1:
            raise ValueError('PUBLICATION_TICKET_UNBOUND')
        dispatch = segments[0]
        if dispatch.get('mode') != 'agent' or dispatch.get('actor') != 'sub_agent':
            raise ValueError('PUBLICATION_EXECUTOR_UNBOUND')
        proof = dispatch_lifecycle.verify(store, dispatch)
        call, result = proof.get('call') or {}, proof.get('result') or {}
        # Failed returns may contain accepted blocks, not permission to resume the child.
        terminal_return = (result.get('status') == 'completed' and not proof.get('tool_is_error')
                           or result.get('status') == 'failed' and proof.get('tool_is_error') is True)
        if (proof.get('source') != 'host_agent_tool_return'
                or proof.get('trace_id') != trace_id or call.get('trace_id') != trace_id
                or proof.get('bootstrap_sha256') != dispatch.get('bootstrap_sha256')
                or call.get('bootstrap_sha256') != dispatch.get('bootstrap_sha256')
                or result.get('session_id') != provider_session_id or call.get('session_id') != provider_session_id
                or not result.get('event_id') or not result.get('tool_call_id')
                or result.get('tool_call_id') != call.get('tool_call_id') or not terminal_return):
            raise ValueError('PUBLICATION_RETURN_UNBOUND')
        sealed = proof.get('public_artifacts') or {}
        if sealed.get('schema') != SCHEMA or sealed.get('status') != 'SEALED':
            raise ValueError('PUBLICATION_RETURN_NOT_SEALED')
        blocks = []
        for row in sealed['artifacts']:
            if row['ref'] in seen_refs:
                continue
            if dispatch_publication.canonical_refs(store, [row['ref']]) != [row['ref']]:
                raise ValueError('PUBLICATION_PATH_UNSAFE')
            name = dispatch_publication._REF.fullmatch(row['ref'])[2]
            path = store.public_dir / name
            if not _regular_path(path):
                raise ValueError('PUBLICATION_PATH_UNSAFE')
            raw = store.read_bytes(path)
            source = store.cache_dir / row['source_cache']
            if (not source.resolve().is_relative_to(store.cache_dir.resolve()) or not _regular_path(source)
                    or _sha(store.read_bytes(source)) != row['source_sha256']):
                raise ValueError('PUBLICATION_SOURCE_CHANGED')
            if len(raw) != row['bytes'] or _sha(raw) != row['sha256']:
                raise ValueError('PUBLICATION_BLOCK_CHANGED')
            blocks.append(dict(row, text=raw.decode('utf-8')))
        if before != store.read_bytes(store.index_path):
            raise ValueError('PUBLICATION_INDEX_CHANGED')
        return dict(status='READY', ticket=ticket, trace_id=trace_id,
                    returned_at=result['at'],
                    return_evidence=dict(dispatch['exit_evidence']), blocks=blocks,
                    excluded_refs=sealed.get('excluded_refs', []),
                    authority='presentation_only', dom_verified=False)
    except (OSError, ValueError, KeyError, EngineError, RunStoreError) as exc:
        return dict(status='UNAVAILABLE', ticket=ticket, reason=str(exc)[:160], blocks=[])

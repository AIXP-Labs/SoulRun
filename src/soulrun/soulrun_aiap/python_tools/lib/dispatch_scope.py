"""Entry-file nodes own execution; external modules inherit the nearest owner."""
from __future__ import annotations


def enabled(index):
    return index.get('program', {}).get('execution_loading_mode',
            index.get('program', {}).get('loading_mode')) == 'node'


def is_main(index, entry):
    entry_file = index.get('program', {}).get('entry_file')
    return bool(entry and entry.get('kind') in ('business', 'sub')
                and ((entry.get('doc') or entry_file) == entry_file if entry_file else entry.get('kind') == 'business'))


def root_entry(index, entry):
    from . import engine_core as ec
    seen = set()
    while entry and entry.get('parent') and not is_main(index, entry):
        if entry['name'] in seen:
            raise ec.EngineError('DISPATCH_SCOPE_INVALID', 'Cyclic node ancestry.')
        seen.add(entry['name'])
        entry = ec._catalog_entry(index, entry['parent'])
    return entry


def owner(index, entry, visit):
    from . import engine_core as ec
    key = ec._node_key(entry['name'], visit)
    if not enabled(index):
        return key, (index['nodes'].get(key) or {}).get('dispatch')
    seen = set()
    while entry and key not in seen:
        seen.add(key)
        ne = index['nodes'].get(key) or {}
        record = ne.get('dispatch')
        if record and record.get('scope_root'):
            return key, record
        if is_main(index, entry):
            break
        parent = entry.get('parent')
        if not parent:
            break
        frame = ec._frame_of(index, entry)
        parent_visit = ne.get('parent_visit') or (frame or {}).get('parent_visit')
        if not parent_visit:
            break
        entry = ec._catalog_entry(index, parent)
        key = ec._node_key(parent, parent_visit)
    return '', None


def assert_ticket(index, entry, visit, ticket):
    from . import engine_core as ec
    if not enabled(index) or not ticket:
        return
    key, record = owner(index, entry, visit) if entry else ('', None)
    # docs/05SoulRun 87: once the human chose to replace this ticket, its holder works no further
    replaced = bool(record and (record.get('human_replacement') or {}).get('previous_ticket') == ticket)
    if (not record or record.get('ticket') != ticket or record.get('state') not in ('ISSUED', 'CLAIMED')
            or record.get('paused_at') or index['run_state'] != 'RUNNING' or replaced):
        raise ec._ticket_error(index, key, ticket, None if replaced else record)


def view(record, *, include_refs=True):
    result = dict(scope='reachable subtree of this root occurrence', scope_root=dict(record['scope_root']),
                  execution_policy='inline')
    if include_refs:
        result['public_refs'] = list(record.get('public_refs') or [])
    return result


def append_ref(record, ref):
    if record and record.get('scope_root') and ref and ref not in record['public_refs']:
        record['public_refs'].append(ref)


def pending_root(index, entry, visit):
    _, record = owner(index, entry, visit)
    return record if record and record.get('state') in ('ISSUED', 'CLAIMED', 'ABANDONED', 'EXHAUSTED', 'FALLBACK') else None

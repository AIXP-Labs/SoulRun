"""Recognize only the sealed original segment's verified host-return delta."""
import copy
import json
from . import write_observation as wo
from .run_store import dumps, sha256_bytes, _regular_path
from . import contracts as _contracts

RETURN_REPLY_RULE = _contracts.text('engine-faults.return_reply')

INDEX_FIELDS = ('state', 'lifecycle', 'exit_evidence', 'context_resume')
FORMAL_FIELDS = ('state', 'lifecycle', 'exit_evidence')


def fields(value, names):
    return {k:value[k] for k in names if k in value}


def restore(value, names, saved, order):
    for key in names:
        value.pop(key, None)
    value.update(copy.deepcopy(saved))
    rebuilt = {k:value[k] for k in order if k in value}
    rebuilt.update({k:v for k,v in value.items() if k not in rebuilt})
    value.clear()
    value.update(rebuilt)


def capture(store, index, request):
    ticket = request.get('agent_ticket')
    if not ticket:
        return None
    matches = [(k,n['dispatch']) for k,n in index['nodes'].items()
               if (n.get('dispatch') or {}).get('ticket') == ticket and ticket]
    if len(matches) != 1:
        return None
    key, dispatch = matches[0]
    if dispatch.get('exit_evidence') or not dispatch.get('scope_root'):
        return None
    formal = store.read_json(store.dispatch_path(ticket))
    start_path = store.cache_dir/f'_dispatch_start.{ticket}.json'
    if not _regular_path(start_path) or not start_path.exists():
        return None
    return dict(schema_version=1, owner_key=key, ticket=ticket,
        index_fields=fields(dispatch, INDEX_FIELDS), formal_fields=fields(formal, FORMAL_FIELDS),
        index_field_order=list(dispatch), formal_field_order=list(formal),
        formal_sha256=sha256_bytes(dumps(formal).encode()),
        start_sha256=sha256_bytes(store.read_bytes(start_path)))


def matches(store, index, receipt):
    from . import dispatch_lifecycle, engine_core as ec
    from .run_store import RunStoreError
    try:
        proof = receipt.get('return_transition') or {}
        if proof.get('schema_version') != 1 or index['run_state'] != 'RUNNING' \
                or index['gate']['state'] != 'CLEAR':
            return False
        dispatch = index['nodes'][proof['owner_key']]['dispatch']
        if dispatch.get('ticket') != proof['ticket'] or not dispatch_lifecycle.returned(dispatch):
            return False
        event = dispatch_lifecycle.verify(store, dispatch)
        start_path = store.cache_dir/f'_dispatch_start.{proof["ticket"]}.json'
        if not _regular_path(start_path) or sha256_bytes(store.read_bytes(start_path)) != proof['start_sha256']:
            return False
        start = store.read_json(start_path)
        if start.get('source') != 'host_synchronous_agent_event' or any(start.get(k) != v for k,v in
                dict(ticket=dispatch['ticket'],trace_id=index['trace_id'],bootstrap_sha256=dispatch['bootstrap_sha256']).items()):
            return False
        if event.get('source') != 'host_agent_tool_return' or event.get('call') != start \
                or event.get('trace_id') != index['trace_id'] or event.get('scope_root') != dispatch['scope_root'] \
                or event.get('bootstrap_sha256') != dispatch['bootstrap_sha256']:
            return False
        result = event.get('result') or {}
        if result.get('status') not in ('completed', 'failed') or not result.get('event_id') or not result.get('at') \
                or any(result.get(k) != start.get(k) for k in ('session_id','tool_call_id')):
            return False
        before = proof['index_fields']
        expected_state = before['state'] if dispatch.get('paused_at') or before['state'] == 'COMMITTED' else 'ABANDONED'
        if dispatch['state'] != expected_state:
            return False
        context = 'ORIGINAL_SESSION_RESUME_OBSERVED' if dispatch.get('resume_executor') else before.get('context_resume')
        if dispatch.get('context_resume') != context:
            return False
        projected = copy.deepcopy(index)
        restore(projected['nodes'][proof['owner_key']]['dispatch'], INDEX_FIELDS, before, proof['index_field_order'])
        if not wo.state_matches(projected, receipt):
            return False
        formal = store.read_json(store.dispatch_path(proof['ticket']))
        if any(formal.get(k) != dispatch.get(k) for k in FORMAL_FIELDS):
            return False
        restore(formal, FORMAL_FIELDS, proof['formal_fields'], proof['formal_field_order'])
        return sha256_bytes(dumps(formal).encode()) == proof['formal_sha256']
    except (OSError, ValueError, KeyError, TypeError, AttributeError, RunStoreError, ec.EngineError):
        return False

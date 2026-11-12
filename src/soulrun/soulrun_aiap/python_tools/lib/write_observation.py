"""CLI write facts; original commit intent is persisted before its writes."""
from contextvars import ContextVar
import copy
import secrets
from contextlib import contextmanager

_current = ContextVar('engine_cli_write_observation', default=None)

def core_hash(index):
    from .run_store import dumps, sha256_bytes
    return sha256_bytes(dumps({k:v for k,v in index.items() if k not in ('host','updated_at')}).encode())

def recovery_hash(index):
    """Exclude only host diagnostic projections, never execution or ticket authority."""
    from .run_store import dumps, sha256_bytes
    protected = copy.deepcopy(index)
    for key in ('host', 'updated_at', 'anomalies_summary'):
        protected.pop(key, None)
    for node in protected.get('nodes', {}).values():
        for key in ('transport_wait_ms', 'transport_wait_legacy_ms', 'transport_wait_intervals'):
            node.pop(key, None)
        if isinstance(node.get('dispatch'), dict):
            node['dispatch'].pop('interruption_observation', None)
    return sha256_bytes(dumps(protected).encode())

def state_matches(index, proof, *, accepted=False):
    prefix = 'accepted_' if accepted else ''
    if proof.get(prefix + 'recovery_projection_version') == 1:
        return recovery_hash(index) == proof.get(prefix + 'recovery_state_sha256')
    return core_hash(index) == proof.get(prefix + 'index_core_sha256')

def _baseline(cache_dir):
    from .run_store import RunStore, sha256_bytes
    try:
        store=RunStore(cache_dir)
        index=store.read_index()
        return dict(index_core_sha256=core_hash(index),
                    recovery_projection_version=1, recovery_state_sha256=recovery_hash(index),
                    input_sha256=sha256_bytes((store.cache_dir/'_run_input.json').read_bytes()),
                    ticket_files=sorted(p.name for p in store.cache_dir.glob('_dispatch.d*.json')))
    except Exception:return None

def begin(tool, cache_dir):
    from .run_store import RunStore
    index = {}
    try:
        index = RunStore(cache_dir).read_index()
    except Exception:
        pass
    return _current.set(dict(operation_id=secrets.token_hex(8), tool=tool,
        trace_id=index.get('trace_id'), original_current=copy.deepcopy(index.get('current')),
        cache_dir=str(cache_dir), writes=[], accepted=False, baseline=_baseline(cache_dir)))

@contextmanager
def suboperation(tool, cache_dir):
    token=begin(tool,cache_dir)
    try:yield
    finally:end(token)

def end(token):
    _current.reset(token)

def bind_request(**request):
    state = _current.get()
    if state is not None:
        state['request'] = copy.deepcopy(request)


def bind_forward_commit(proof):
    state = _current.get()
    if state is not None:
        state['forward_commit'] = copy.deepcopy(proof)

def request():
    return copy.deepcopy((_current.get() or {}).get('request'))

@contextmanager
def maintenance():
    token=_current.set(None)
    try:yield
    finally:_current.reset(token)

def writing(path, phase='STARTED_UNCONFIRMED', *, receipt=None, expected=None):
    state = _current.get()
    if state is None:return
    name = str(path)
    row = next((r for r in state['writes'] if r['path'] == name), None)
    if row is None:
        row = dict(path=name)
        try:
            from .run_store import sha256_bytes
            from pathlib import Path
            row['before_sha256']=sha256_bytes(Path(path).read_bytes()) if Path(path).exists() else 'ABSENT'
        except OSError:row['before_sha256']=None
        state['writes'].append(row)
    row['phase'] = phase
    if expected is not None:row['expected_sha256'] = expected
    if receipt is not None:row['sha256'] = receipt
    if phase == 'VERIFIED' and state.get('forward_commit'):
        from pathlib import Path
        if Path(path).name == '_index.json' and Path(path).parent.resolve() == Path(state['cache_dir']).resolve():
            state['forward_index_verified'] = True
    if expected is not None and state.get('forward_commit') and state['tool'] == 'node_commit' \
            and not state.get('intent_persistence_failed') and not state.get('accepted') \
            and not state.get('forward_index_verified'):
        from . import partial_commit
        observed = facts()
        if state.get('preserved_request') is not None:
            observed['request'] = copy.deepcopy(state['preserved_request'])
        try:
            state['intent_raw'] = partial_commit.persist_intent(state['cache_dir'], observed, state.get('intent_raw'))
        except Exception as exc:
            state['intent_persistence_failed'] = type(exc).__name__
            from .engine_core import EngineError
            raise EngineError('ENGINE_FAULT_RECORD_INVALID',
                'Original commit intent could not be persisted; preserve the payload and stop.',
                example=dict(original_error_type=type(exc).__name__)) from exc
        state['preserved_request'] = copy.deepcopy(observed['request'])

def accepted(reply=None, *, kind=None, node=None):
    state = _current.get()
    if state is not None:
        state['accepted'] = True
        if reply is not None:
            from .run_store import RunStore, sha256_bytes
            store = RunStore(state['cache_dir'])
            index_raw=store.index_path.read_bytes()
            import json
            state['trace_id']=json.loads(index_raw)['trace_id']
            state['reply'] = dict(result=copy.deepcopy(reply), kind=kind, node=node,
                index_core_sha256=core_hash(json.loads(index_raw)),
                index_sha256=sha256_bytes(index_raw),
                input_sha256=sha256_bytes((store.cache_dir / '_run_input.json').read_bytes()))


def reply_candidate():
    state = _current.get()
    return copy.deepcopy((state or {}).get('reply'))


def bind_accepted_reply(reference):
    state = _current.get()
    if state is not None:
        state['accepted_reply'] = copy.deepcopy(reference)

def facts():
    state = _current.get()
    if state is None:return dict(write_started=None, effect_phase='UNKNOWN')
    rows = state['writes']
    phases = {r['phase'] for r in rows}
    phase = ('NOT_STARTED' if not rows else 'STARTED_UNCONFIRMED' if 'STARTED_UNCONFIRMED' in phases
             else 'PERSISTED_UNCONFIRMED' if 'PERSISTED_UNCONFIRMED' in phases else 'WRITES_VERIFIED')
    if state['accepted']:phase = 'ACCEPTED'
    return dict(operation_id=state['operation_id'], tool=state['tool'], trace_id=state['trace_id'],
        original_current=state['original_current'], write_started=bool(rows), effect_phase=phase,
        baseline=copy.deepcopy(state.get('baseline')),
        request=request(),
        **({'forward_commit':copy.deepcopy(state['forward_commit'])} if state.get('forward_commit') else {}),
        acceptance={k:v for k,v in (state.get('reply') or {}).items() if k in ('index_core_sha256','input_sha256')},
        **({'accepted_reply':copy.deepcopy(state['accepted_reply'])} if state.get('accepted_reply') else {}),
        writes=copy.deepcopy(rows), scope='this_cli_call_only_not_prior_agent_business_effects')

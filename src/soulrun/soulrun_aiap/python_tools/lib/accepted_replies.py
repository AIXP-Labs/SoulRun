"""Small acceptance receipts bind existing full echoes; never replay a commit."""

from . import runtime_identity
import json
import re
from pathlib import Path
from . import write_observation as wo
from .run_store import RunStore, RunStoreError, _regular_path, dumps, os_path, sha256_bytes


# docs/05SoulRun 87: receipts live beside the replies, not among them - a script that takes "the newest file" of
# _work/replies/ met this directory. A run written before keeps its receipts in the old place; both places are read,
# only the new one is written.
RECEIPTS = '_work/_receipts'
RECEIPT_DIRS = (RECEIPTS, '_work/replies/_receipts')
# docs/05SoulRun 88 (S2): a receipt's name carries a 64-character request key and its operation id, so its path passes
# Windows' 260 characters about 103 characters sooner than the run directory; every receipt and echo read, write and listing
# goes through the store (run_store.os_path), which adds the extended-length prefix to a long path.


def _receipt_names(store, folder, pattern):
    """The receipt files of `folder` matching `pattern` (a glob), listed through the long-path helper."""
    import fnmatch
    import os
    directory = store.cache_dir/folder
    if not store.exists_path(directory):
        return []
    return [directory/name for name in sorted(os.listdir(os_path(directory))) if fnmatch.fnmatchcase(name, pattern)]


def enabled(index):
    match = runtime_identity.revision_match(index.get('engine_version', ''))
    return bool(match and int(match[1]) >= 155)


def _path(store, relative, folder):
    path = store.cache_dir/relative
    folders = (folder,) if isinstance(folder, str) else folder
    if path.parent not in [store.cache_dir/f for f in folders] or not _regular_path(path) or path.suffix != '.json':
        raise ValueError('reply evidence path is not regular or bound to this cache')
    return path


def _request(request):
    from .fault_reentry import content_hash
    value = {k:request.get(k) for k in ('node','agent_ticket','interpretation')}
    value['payload_content_sha256'] = content_hash(request['payload_text']) if 'payload_text' in request else request.get('payload_content_sha256')
    return value


def _key(index, request, origin):
    return sha256_bytes(dumps(dict(request=_request(request), origin=origin,
        **{k:index[k] for k in ('engine_version','trace_id','session_id')})).encode())


def _payload_bound(store, request):
    from . import fault_reentry
    if not any(k in request for k in ('payload_ref', 'payload_sha256')):
        return True  # Existing immutable receipts predate raw request references.
    observed = dict(tool='node_commit', write_observation=dict(request=request))
    return fault_reentry.original_request(store, observed) is not None


def _commit_proof(store, index, origin):
    from . import engine_core as ec
    entry = ec._catalog_entry(index, origin['name'])
    key = ec._node_key(origin['name'], origin['visit'])
    path = ec._cache_path_for(store, index, entry, origin['visit'])
    ledger = ec._read_ledger(store)
    return dict(origin=origin, cache_ref=path.relative_to(store.cache_dir).as_posix(),
        cache_sha256=index['nodes'][key].get('cache_sha256'), ledger_count=len(ledger),
        ledger_sha256=sha256_bytes(dumps(ledger).encode()))


def _commit_chain_matches(store, index, receipt):
    from . import engine_core as ec
    proof = receipt.get('commit_proof')
    if not proof:
        return False
    current = _commit_proof(store, index, proof['origin'])
    ledger = ec._read_ledger(store)
    return all(current[k] == proof[k] for k in ('origin','cache_ref','cache_sha256')) \
        and bool(proof['cache_sha256']) and len(ledger) >= proof['ledger_count'] \
        and sha256_bytes(dumps(ledger[:proof['ledger_count']]).encode()) == proof['ledger_sha256']


def _history_matches(store, index, receipt):
    proof = receipt.get('commit_proof')
    return bool(proof) and (index.get('gate') or {}).get('state') != 'WAITING_USER' \
        and (index.get('current') or {}).get('name') != proof['origin']['name'] \
        and _commit_chain_matches(store, index, receipt)


def preserve(cache_dir, reply, relative, wire, kind, node):
    candidate, facts = wo.reply_candidate(), wo.facts()
    if not candidate or facts.get('effect_phase') != 'ACCEPTED':
        return
    store = RunStore(cache_dir)
    with wo.maintenance(), store.lock():
        index = store.read_index()
        if not enabled(index):
            return
        if wo.core_hash(index) != candidate['index_core_sha256']:
            raise ValueError('accepted state changed before reply sealing')
        path = _path(store, relative, '_work/replies')
        from . import fault_reentry
        observed = dict(request=dict(facts.get('request') or {}))
        fault_reentry.preserve_request(store, observed)
        request = observed['request'] or {}
        origin = facts.get('original_current')
        identity = _key(index, request, origin) if facts['tool'] == 'node_commit' and origin \
            and origin.get('name') == request.get('node') and not request.get('interpretation') else None
        receipt_path = f'{RECEIPTS}/{identity+"." if identity else ""}{facts["operation_id"]}.json'
        target = _path(store, receipt_path, RECEIPTS)
        if not store.exists_path(target):
            raw = store.read_bytes(path)
            if json.loads(raw) != reply:
                raise ValueError('reply echo changed before sealing')
            record = dict(schema_version=1, operation_id=facts['operation_id'], tool=facts['tool'],
                engine_version=index['engine_version'], trace_id=index['trace_id'], session_id=index['session_id'],
                request=request, kind=kind, node=node, reply_ref=relative, reply_sha256=sha256_bytes(raw),
                wire_sha256=sha256_bytes(wire.encode('utf-8')), input_sha256=candidate['input_sha256'],
                recovery_projection_version=1, recovery_state_sha256=wo.recovery_hash(index))
            if identity:
                record['request_key'] = identity
                record['commit_proof'] = _commit_proof(store, index, origin)
                from . import reply_state
                transition = reply_state.capture(store, index, request)
                if transition:
                    record['return_transition'] = transition
            record['sha256'] = sha256_bytes(dumps(record).encode())
            store.write_json_once(target, record)
        reference = dict(path=receipt_path, sha256=sha256_bytes(store.read_bytes(target)), operation_id=facts['operation_id'])
    wo.bind_accepted_reply(reference)


def read(cache_dir, index, observed, *, allow_history=False):
    from . import reply_io, engine_core as ec, tool_faults
    ref = observed.get('accepted_reply') or {}
    try:
        if not enabled(index) or not ref:
            return None
        store = RunStore(cache_dir)
        path = _path(store, ref['path'], RECEIPT_DIRS)
        raw = store.read_bytes(path)
        receipt = json.loads(raw)
        if not isinstance(receipt, dict):
            return None
        body = {k:v for k,v in receipt.items() if k != 'sha256'}
        if sha256_bytes(raw) != ref['sha256'] or sha256_bytes(dumps(body).encode()) != receipt['sha256'] \
                or receipt['operation_id'] != ref['operation_id'] or receipt['tool'] != observed['tool'] \
                or any(receipt[k] != index[k] for k in ('engine_version','trace_id','session_id')) \
                or not (wo.state_matches(index, receipt) or allow_history and _history_matches(store, index, receipt)) \
                or receipt.get('commit_proof') and not _commit_chain_matches(store, index, receipt) \
                or sha256_bytes(store.read_bytes(store.cache_dir/'_run_input.json')) != receipt['input_sha256']:
            return None
        request = observed.get('request') or {}
        if any(receipt['request'].get(k) != request.get(k) for k in
               ('node','agent_ticket','interpretation','payload_content_sha256','abandon','reason')):
            return None
        if not _payload_bound(store, receipt['request']):
            return None
        ec.program_guard.assert_run_version(index)
        if not tool_faults.accepted_state_proof(cache_dir, index):
            return None
        raw = store.read_bytes(_path(store, receipt['reply_ref'], '_work/replies'))
        if sha256_bytes(raw) != receipt['reply_sha256']:
            return None
        result = json.loads(raw)
        wire = reply_io._printed_text(reply_io.order(result), receipt['reply_ref'])
        if sha256_bytes(wire.encode('utf-8')) != receipt['wire_sha256']:
            return None
        return dict(result=result, wire=wire, receipt=receipt, reference=ref)
    except (OSError, ValueError, KeyError, TypeError, AttributeError, RunStoreError, ec.EngineError):
        return None


def inspect(cache_dir, index, observed):
    """Explain evidence rejection; a historical reply never grants execution rights."""
    from . import reply_io, engine_core as ec, tool_faults
    checks = dict(available=False, integrity=None, identity=None, request=None,
                  input=None, commit_chain=None, accepted_state=None, current_state=None)
    result = dict(status='UNVERIFIED', checks=checks, old_plan_and_ticket_executable=False)
    ref = observed.get('accepted_reply') or {}
    if not enabled(index) or not ref:
        result['status'] = 'MISSING_RECEIPT'
        return result
    try:
        store = RunStore(cache_dir)
        path = _path(store, ref['path'], RECEIPT_DIRS)
        if not store.exists_path(path):
            result['status'] = 'MISSING_RECEIPT'
            return result
        raw = store.read_bytes(path)
        receipt = json.loads(raw)
        body = {k:v for k,v in receipt.items() if k != 'sha256'}
        echo = _path(store, receipt['reply_ref'], '_work/replies')
        checks['available'] = store.exists_path(echo)
        checks['integrity'] = sha256_bytes(raw) == ref['sha256'] \
            and sha256_bytes(dumps(body).encode()) == receipt['sha256']
        checks['identity'] = receipt['operation_id'] == ref['operation_id'] \
            and receipt['tool'] == observed['tool'] \
            and all(receipt[k] == index[k] for k in ('engine_version','trace_id','session_id'))
        request = observed.get('request') or {}
        checks['request'] = _payload_bound(store, receipt['request']) and all(receipt['request'].get(k) == request.get(k) for k in
            ('node','agent_ticket','interpretation','payload_content_sha256','abandon','reason'))
        checks['input'] = sha256_bytes(store.read_bytes(store.cache_dir/'_run_input.json')) == receipt['input_sha256']
        checks['commit_chain'] = not receipt.get('commit_proof') or _commit_chain_matches(store, index, receipt)
        ec.program_guard.assert_run_version(index)
        checks['accepted_state'] = tool_faults.accepted_state_proof(cache_dir, index)
        checks['current_state'] = wo.state_matches(index, receipt)
        if checks['available']:
            raw_echo = store.read_bytes(echo)
            wire = reply_io._printed_text(reply_io.order(json.loads(raw_echo)), receipt['reply_ref'])
            checks['integrity'] = checks['integrity'] and sha256_bytes(raw_echo) == receipt['reply_sha256'] \
                and sha256_bytes(wire.encode('utf-8')) == receipt['wire_sha256']
        if not checks['available']:
            result['status'] = 'MISSING_ECHO'
        elif not all(checks[k] for k in checks if k != 'current_state'):
            result['status'] = 'INVALID_EVIDENCE'
        elif read(cache_dir, index, observed, allow_history=True):
            result.update(status='VERIFIED_CURRENT' if checks['current_state'] else 'VERIFIED_HISTORICAL_READ_ONLY',
                reply_ref=receipt['reply_ref'], wire_sha256=receipt['wire_sha256'])
        else:
            result['status'] = 'STATE_OR_HISTORY_NOT_VERIFIED'
    except (OSError, ValueError, KeyError, TypeError, AttributeError, RunStoreError, ec.EngineError) as exc:
        result.update(status='UNVERIFIABLE_EVIDENCE', error_type=type(exc).__name__)
    return result


def recoverable(cache_dir, index, observed):
    """Historical evidence permits only a current-state-bound read-only notice."""
    strict = read(cache_dir, index, observed)
    if strict:
        return dict(strict, reply_mode='ORIGINAL_WIRE')
    history = read(cache_dir, index, observed, allow_history=True)
    if history:
        from . import reply_state
        if reply_state.matches(RunStore(cache_dir), index, history['receipt']):
            return dict(history, reply_mode='HISTORICAL_PROJECTION', recovery_rule=reply_state.RETURN_REPLY_RULE)
    return None


def identical(cache_dir, index, request):
    """Retrieve an exact accepted operation, never grant authority to its old next plan."""
    from . import engine_core as ec
    try:
        if not enabled(index) or not request or request.get('interpretation'):
            return None
        node = request['node']
        if (index.get('current') or {}).get('name') == node:
            origin = index['current']
        else:
            visits = [int((key.partition('@')[2] or '1').removeprefix('v')) for key in index['nodes'] if key.partition('@')[0] == node]
            if not visits:
                return None
            origin = dict(name=node, visit=max(visits))
        key = _key(index, request, origin)
        store = RunStore(cache_dir)
        matches = []
        for path in (p for folder in RECEIPT_DIRS for p in _receipt_names(store, folder, key+'.*.json')):
            receipt = store.read_json(_path(store, path.relative_to(store.cache_dir).as_posix(), RECEIPT_DIRS))
            if not isinstance(receipt, dict):
                return None
            observed = dict(tool='node_commit', request=_request(request), accepted_reply=dict(
                path=path.relative_to(store.cache_dir).as_posix(), sha256=sha256_bytes(store.read_bytes(path)), operation_id=receipt['operation_id']))
            if receipt.get('request_key') != key:
                continue
            saved = read(cache_dir, index, observed, allow_history=True)
            if saved:
                matches.append(saved)
        if len(matches) != 1:
            return None
        saved = matches[0]
        return dict(status='ACCEPTED_REPLY_READ_ONLY', node=node, visit=origin['visit'],
            reply_file=saved['receipt']['reply_ref'], wire_sha256=saved['receipt']['wire_sha256'],
            historical=not wo.state_matches(index, saved['receipt']), old_plan_and_ticket_executable=False,
            rule='Only read this accepted reply. No commit or serve was repeated; use next_node for current authority.')
    except (OSError, ValueError, KeyError, TypeError, AttributeError, RunStoreError, ec.EngineError):
        return None
